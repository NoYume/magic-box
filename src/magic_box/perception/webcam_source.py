"""Monocular laptop webcam pose adapter using Apache-2.0 OpenCV Zoo models.

Owner: Adetola

This is a development fallback, not a replacement for ZED depth. It estimates absolute
range from apparent shoulder width and uses MediaPipe's relative landmark Z for thrusts.
Detector and landmark preprocessing follows OpenCV Zoo's Apache-2.0 MediaPipe examples:
https://github.com/opencv/opencv_zoo/tree/main/models/pose_estimation_mediapipe
"""

import hashlib
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np

from magic_box.core.config import Config
from magic_box.perception.raw import RawBody

_MODEL_BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
_MODELS = {
    "person_detection_mediapipe_2023mar.onnx": (
        f"{_MODEL_BASE}/person_detection_mediapipe/person_detection_mediapipe_2023mar.onnx",
        "47fd5599d6fa17608f03e0eb0ae230baa6e597d7e8a2c8199fe00abea55a701f",
    ),
    "pose_estimation_mediapipe_2023mar.onnx": (
        f"{_MODEL_BASE}/pose_estimation_mediapipe/pose_estimation_mediapipe_2023mar.onnx",
        "9d89c599319a18fb7d2e28451a883476164543182bafca5f09eb2cf767ed2f3f",
    ),
}
_INPUT_DET = 224
_INPUT_POSE = 256
# MediaPipe landmark indices.
_DIRECT = {
    "head": 0,
    "l_shoulder": 11,
    "r_shoulder": 12,
    "l_wrist": 15,
    "r_wrist": 16,
    "l_ankle": 27,
    "r_ankle": 28,
}


def _cache_dir() -> Path:
    root = os.environ.get("XDG_CACHE_HOME")
    return Path(root) / "magic-box" if root else Path.home() / ".cache" / "magic-box"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_models(cache: Path | None = None) -> dict[str, Path]:
    """Download and verify OpenCV Zoo's pose models once into the user cache."""
    cache = cache or _cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    for name, (url, expected) in _MODELS.items():
        path = cache / name
        if not path.exists() or _sha256(path) != expected:
            print(f"webcam: downloading pose model {name}...", file=sys.stderr, flush=True)
            temp = path.with_suffix(".download")
            try:
                urllib.request.urlretrieve(url, temp)
                actual = _sha256(temp)
                if actual != expected:
                    raise RuntimeError(
                        f"model checksum mismatch: expected {expected}, got {actual}"
                    )
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
        result[name] = path
    return result


def _anchors() -> np.ndarray:
    """MediaPipe BlazePose SSD anchors: 28²×2, 14²×2 and 7²×6."""
    values = []
    for size, repeats in ((28, 2), (14, 2), (7, 6)):
        for y in range(size):
            for x in range(size):
                values.extend(((x + 0.5) / size, (y + 0.5) / size) for _ in range(repeats))
    return np.asarray(values, dtype=np.float32)


class WebcamPoseEstimator:
    """Turn one BGR webcam image into up to two approximate metric RawBodies."""

    def __init__(self, cfg: Config, cv2_module: Any, cache: Path | None = None) -> None:
        self._cfg = cfg
        self._cv = cv2_module
        wc = cfg["fake"]["webcam"]
        self._det_threshold = float(wc["detection_confidence"])
        self._pose_threshold = float(wc["pose_confidence"])
        self._landmark_threshold = float(wc["landmark_confidence"])
        self._shoulder_m = float(wc["shoulder_width_m"])
        self._focal = float(cfg["fake"]["focal_px"])
        self._min_z = float(cfg["fake"]["min_z_m"])
        self._max_z = float(cfg["fake"]["max_z_m"])
        models = ensure_models(cache)
        self._det = cv2_module.dnn.readNet(str(models["person_detection_mediapipe_2023mar.onnx"]))
        self._pose = cv2_module.dnn.readNet(str(models["pose_estimation_mediapipe_2023mar.onnx"]))
        self._anchors = _anchors()

    def estimate(self, image: np.ndarray) -> list[RawBody]:
        people = self._detect(image)
        bodies = []
        for person in sorted(people, key=lambda row: row[12], reverse=True)[:2]:
            pose = self._infer_pose(image, person)
            if pose is not None:
                body = self._raw_body(pose, image.shape[1], image.shape[0])
                if body is not None:
                    bodies.append(body)
        # Stable IDs by side are sufficient for the intended side-by-side laptop setup.
        bodies.sort(key=lambda body: body.position[0])
        return [
            RawBody(
                id=100 if body.position[0] < 0 else 101,
                tracking_ok=body.tracking_ok,
                confidence=body.confidence,
                position=body.position,
                kp3d=body.kp3d,
                kp2d=body.kp2d,
                bbox_px=body.bbox_px,
            )
            for body in bodies
        ]

    def _detect(self, image: np.ndarray) -> np.ndarray:
        cv = self._cv
        h, w = image.shape[:2]
        ratio = min(_INPUT_DET / h, _INPUT_DET / w)
        resized = cv.resize(image, (round(w * ratio), round(h * ratio)))
        top = (_INPUT_DET - resized.shape[0]) // 2
        left = (_INPUT_DET - resized.shape[1]) // 2
        padded = cv.copyMakeBorder(
            resized,
            top,
            _INPUT_DET - resized.shape[0] - top,
            left,
            _INPUT_DET - resized.shape[1] - left,
            cv.BORDER_CONSTANT,
            None,
            (0, 0, 0),
        )
        blob = cv.cvtColor(padded, cv.COLOR_BGR2RGB).astype(np.float32) / 127.5 - 1.0
        self._det.setInput(np.transpose(blob, (2, 0, 1))[None])
        boxes_out, scores_out = self._det.forward(self._det.getUnconnectedOutLayersNames())
        scores = np.clip(scores_out[0, :, 0].astype(np.float64), -100, 100)
        scores = 1.0 / (1.0 + np.exp(-scores))
        raw = boxes_out[0]
        scale = max(w, h)
        xy1 = (raw[:, :2] / _INPUT_DET - raw[:, 2:4] / (_INPUT_DET * 2) + self._anchors) * scale
        xy2 = (raw[:, :2] / _INPUT_DET + raw[:, 2:4] / (_INPUT_DET * 2) + self._anchors) * scale
        boxes = np.concatenate((xy1, xy2), axis=1) - (left / ratio, top / ratio) * 2
        keep = cv.dnn.NMSBoxes(boxes, scores, self._det_threshold, 0.3, top_k=10)
        if len(keep) == 0:
            return np.empty((0, 13), dtype=np.float32)
        keep = np.asarray(keep).reshape(-1)
        landmarks = raw[keep, 4:].reshape(-1, 4, 2) / _INPUT_DET
        landmarks += self._anchors[keep, None, :]
        landmarks = landmarks * scale - np.array((left / ratio, top / ratio))
        return np.c_[boxes[keep], landmarks.reshape(-1, 8), scores[keep]]

    def _infer_pose(self, image: np.ndarray, person: np.ndarray):
        cv = self._cv
        hip, full = person[4:6].copy(), person[6:8].copy()
        radius = float(np.linalg.norm(hip - full))
        if radius < 2:
            return None
        full_box = np.asarray((hip - radius, hip + radius), dtype=np.int32)
        clipped = full_box.copy()
        clipped[:, 0] = np.clip(clipped[:, 0], 0, image.shape[1])
        clipped[:, 1] = np.clip(clipped[:, 1], 0, image.shape[0])
        crop = image[clipped[0, 1] : clipped[1, 1], clipped[0, 0] : clipped[1, 0]]
        if crop.size == 0:
            return None
        left, top = clipped[0] - full_box[0]
        right, bottom = full_box[1] - clipped[1]
        crop = cv.copyMakeBorder(
            crop, top, bottom, left, right, cv.BORDER_CONSTANT, None, (0, 0, 0)
        )
        bias = clipped[0] - (left, top)
        hip_local, full_local = hip - bias, full - bias
        angle = np.rad2deg(
            np.pi / 2 - np.arctan2(-(full_local[1] - hip_local[1]), full_local[0] - hip_local[0])
        )
        angle -= 360 * np.floor((angle + 180) / 360)
        rotation = cv.getRotationMatrix2D(tuple(hip_local), angle, 1.0)
        rotated = cv.warpAffine(crop, rotation, (crop.shape[1], crop.shape[0]))
        blob = cv.resize(rotated, (_INPUT_POSE, _INPUT_POSE), interpolation=cv.INTER_AREA)
        blob = cv.cvtColor(blob, cv.COLOR_BGR2RGB).astype(np.float32) / 255.0
        self._pose.setInput(blob[None])
        outputs = self._pose.forward(self._pose.getUnconnectedOutLayersNames())
        landmarks, confidence, _mask, _heatmap, world = outputs
        confidence = float(confidence[0, 0])
        if confidence < self._pose_threshold:
            return None
        landmarks = landmarks[0].reshape(-1, 5)
        landmarks[:, 3:] = 1.0 / (1.0 + np.exp(-landmarks[:, 3:]))
        world = world[0].reshape(-1, 3)
        scale = np.asarray((crop.shape[1], crop.shape[0])) / _INPUT_POSE
        landmarks[:, :2] = (landmarks[:, :2] - _INPUT_POSE / 2) * scale
        landmarks[:, 2] *= max(scale)
        point_rotation = cv.getRotationMatrix2D((0, 0), angle, 1.0)[:, :2]
        landmarks[:, :2] = landmarks[:, :2] @ point_rotation
        world[:, :2] = world[:, :2] @ point_rotation
        component = np.asarray(((rotation[0, 0], rotation[1, 0]), (rotation[0, 1], rotation[1, 1])))
        translation = rotation[:, 2]
        inverse = np.c_[component, -component @ translation]
        center = np.asarray((crop.shape[1] / 2, crop.shape[0] / 2, 1))
        original_center = inverse @ center
        landmarks[:, :2] += original_center + bias
        return landmarks, world, confidence

    def _raw_body(self, pose, width: int, height: int) -> RawBody | None:
        landmarks, world, confidence = pose

        def valid(index: int) -> bool:
            return bool(
                landmarks[index, 3] >= self._landmark_threshold
                and landmarks[index, 4] >= self._landmark_threshold
            )

        if not all(valid(i) for i in (11, 12, 23, 24)):
            return None
        shoulder_px = float(np.linalg.norm(landmarks[11, :2] - landmarks[12, :2]))
        if shoulder_px < 2:
            return None
        root_z = float(
            np.clip(self._focal * self._shoulder_m / shoulder_px, self._min_z, self._max_z)
        )
        hip_world_z = float((world[23, 2] + world[24, 2]) / 2)

        indices = dict(_DIRECT)
        points_px: dict[str, tuple[float, float]] = {}
        points_world: dict[str, tuple[float, float, float]] = {}

        def add(name: str, px: np.ndarray, relative_z: float) -> None:
            x, y = float(px[0]), float(px[1])
            z = root_z + float(relative_z - hip_world_z)
            points_px[name] = (x, y)
            points_world[name] = (
                (x - width / 2) * root_z / self._focal,
                (y - height / 2) * root_z / self._focal,
                z,
            )

        for name, index in indices.items():
            if valid(index):
                add(name, landmarks[index, :2], world[index, 2])
        add("neck", (landmarks[11, :2] + landmarks[12, :2]) / 2, (world[11, 2] + world[12, 2]) / 2)
        add("pelvis", (landmarks[23, :2] + landmarks[24, :2]) / 2, hip_world_z)
        visible = landmarks[:33][
            (landmarks[:33, 3] >= self._landmark_threshold)
            & (landmarks[:33, 4] >= self._landmark_threshold)
        ]
        if len(visible) == 0:
            return None
        x0, y0 = np.maximum(np.min(visible[:, :2], axis=0), (0, 0))
        x1, y1 = np.minimum(np.max(visible[:, :2], axis=0), (width - 1, height - 1))
        bbox = (int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0)))
        return RawBody(
            id=0,
            tracking_ok=True,
            confidence=confidence * 100,
            position=points_world["pelvis"],
            kp3d=points_world,
            kp2d=points_px,
            bbox_px=bbox,
        )
