"""ZED X camera source, live or SVO playback (perception spec §8).

Owner: Enoch

The only module that talks to the ZED SDK. `pyzed` is imported inside methods, never at the
module top, so laptops and CI import this file without the SDK.
"""

from typing import Any

import numpy as np

from magic_box.core.config import Config
from magic_box.core.contracts import Frame
from magic_box.perception.keypoints import PART_NAMES, map_keypoints
from magic_box.perception.raw import CameraInfo, Capture, RawBody

OPEN_HINT = (
    "ZED X not detected? Run `sudo systemctl restart zed_x_daemon`, "
    "or reboot with the camera plugged in."
)


class CameraError(Exception):
    """Opening the camera failed in a way worth retrying."""


def grab_succeeded(status: Any, success: Any) -> bool:
    """True for SUCCESS and for warnings ordered below it (SDK 5); equality for unordered enums."""
    try:
        return bool(status <= success)
    except TypeError:
        return bool(status == success)


def bbox_from_corners(corners: Any) -> tuple[int, int, int, int]:
    """(x, y, w, h) pixel box from the SDK's 4x2 corner array."""
    pts = np.asarray(corners, dtype=float)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0)


def check_part_indices(body_format: str, parts_enum: Any) -> None:
    """Fail loudly if the SDK's part order differs from `keypoints.PART_NAMES`."""
    for ours, name in enumerate(PART_NAMES[body_format]):
        sdk = int(getattr(parts_enum, name).value)
        if sdk != ours:
            raise RuntimeError(
                f"{body_format}: SDK part {name} is index {sdk}, keypoints.py says {ours}"
            )


class ZedSource:
    """Opens the camera (live or SVO), grabs frames and returns plain `Capture` data."""

    def __init__(self, cfg: Config) -> None:
        self._cam = cfg["camera"]
        self._sl: Any = None
        self._zed: Any = None
        self._recording = False
        self._frame_idx = 0
        self._info: CameraInfo | None = None
        self._runtime: Any = None
        self._mat: Any = None
        self._body_runtime: Any = None

    @property
    def is_open(self) -> bool:
        return self._zed is not None

    @property
    def info(self) -> CameraInfo | None:
        return self._info

    def open(self) -> None:
        try:
            import pyzed.sl as sl
        except ImportError as exc:
            raise RuntimeError(
                f"pyzed is not installed or failed to import ({exc}): "
                "live mode needs the ZED SDK (use --fake on a laptop)"
            ) from exc
        self._sl = sl
        cam = self._cam
        fmt = cam["body_format"]

        init = sl.InitParameters()
        init.camera_resolution = getattr(sl.RESOLUTION, cam["resolution"])
        init.camera_fps = cam["fps"]
        init.depth_mode = getattr(sl.DEPTH_MODE, cam["depth_mode"])
        init.coordinate_units = sl.UNIT.METER
        init.coordinate_system = sl.COORDINATE_SYSTEM.IMAGE
        init.depth_maximum_distance = cam["max_range_m"]
        svo = cam.get("svo_path")
        if svo:
            init.set_from_svo_file(svo)
            init.svo_real_time_mode = True

        zed = sl.Camera()
        status = zed.open(init)
        if not grab_succeeded(status, sl.ERROR_CODE.SUCCESS):
            zed.close()
            raise CameraError(f"ZED open failed: {status}. {OPEN_HINT}")
        self._zed = zed
        try:
            self._configure(sl, zed, fmt, svo)
        except BaseException:
            self.close()
            raise

    def _configure(self, sl: Any, zed: Any, fmt: str, svo: str | None) -> None:
        cam = self._cam
        raw = zed.get_camera_information()
        res = raw.camera_configuration.resolution
        model = raw.camera_model
        self._info = CameraInfo(
            model=model.name if hasattr(model, "name") else str(model),
            serial=int(raw.serial_number),
            width=int(res.width),
            height=int(res.height),
            fps=float(raw.camera_configuration.fps),
            sdk_version=str(sl.Camera.get_sdk_version()),
            source=svo or "live",
        )
        cw, ch = cam["image_width"], cam["image_height"]
        if (self._info.width, self._info.height) != (cw, ch):
            raise RuntimeError(
                f"camera opened at {self._info.width}x{self._info.height} but config expects "
                f"{cw}x{ch} (camera.resolution {cam['resolution']})"
            )

        check_part_indices(fmt, getattr(sl, f"{fmt}_PARTS"))

        record = cam.get("record_svo")
        if record:
            params = sl.RecordingParameters(record, sl.SVO_COMPRESSION_MODE.H264)
            if not grab_succeeded(zed.enable_recording(params), sl.ERROR_CODE.SUCCESS):
                raise RuntimeError(f"could not start SVO recording to {record}")
            self._recording = True

        pos = sl.PositionalTrackingParameters()
        pos.set_as_static = True
        status = zed.enable_positional_tracking(pos)
        if not grab_succeeded(status, sl.ERROR_CODE.SUCCESS):
            raise CameraError(f"ZED positional tracking failed: {status}")

        bp = sl.BodyTrackingParameters()
        bp.enable_tracking = True
        bp.enable_body_fitting = cam["body_fitting"]
        bp.detection_model = getattr(sl.BODY_TRACKING_MODEL, cam["body_model"])
        bp.body_format = getattr(sl.BODY_FORMAT, fmt)
        bp.max_range = cam["max_range_m"]
        status = zed.enable_body_tracking(bp)
        if not grab_succeeded(status, sl.ERROR_CODE.SUCCESS):
            raise CameraError(f"ZED body tracking failed: {status}")

        self._body_runtime = sl.BodyTrackingRuntimeParameters()
        self._body_runtime.detection_confidence_threshold = cam["detection_confidence"]
        self._mat = sl.Mat()  # reused: get_data() is a view that needs the Mat alive
        self._runtime = sl.RuntimeParameters()
        self._runtime.measure3D_reference_frame = sl.REFERENCE_FRAME.CAMERA

    def grab(self) -> Capture | None:
        """Next frame with its bodies, or None (failed grab, or the SVO just rewound)."""
        sl, zed = self._sl, self._zed
        status = zed.grab(self._runtime)
        if status == sl.ERROR_CODE.END_OF_SVOFILE_REACHED:
            zed.set_svo_position(0)
            return None
        if not grab_succeeded(status, sl.ERROR_CODE.SUCCESS):
            return None

        bodies = sl.Bodies()
        zed.retrieve_bodies(bodies, self._body_runtime)
        mat = self._mat
        zed.retrieve_image(mat, sl.VIEW.LEFT)
        cam_t = zed.get_timestamp(sl.TIME_REFERENCE.IMAGE).get_nanoseconds() / 1e9
        fmt = self._cam["body_format"]

        raw_bodies = []
        n_parts = len(PART_NAMES[fmt])
        for b in bodies.body_list:
            if b.tracking_state != sl.OBJECT_TRACKING_STATE.OK:
                continue  # filtered out downstream anyway; its arrays may be empty
            # pyzed vectors can come back empty: treat a wrong-sized array as "no keypoints"
            k3, k2 = np.asarray(b.keypoint), np.asarray(b.keypoint_2d)
            if len(k3) == n_parts and len(k2) == n_parts:
                kp3d, kp2d = map_keypoints(fmt, k3, k2)
            else:
                kp3d, kp2d = {}, {}
            corners = np.asarray(b.bounding_box_2d)
            bbox = bbox_from_corners(corners) if len(corners) >= 4 else (0, 0, 0, 0)
            x, y, z = (float(v) for v in b.position)
            raw_bodies.append(
                RawBody(
                    id=int(b.id),
                    tracking_ok=True,
                    confidence=float(b.confidence),
                    position=(x, y, z),
                    kp3d=kp3d,
                    kp2d=kp2d,
                    bbox_px=bbox,
                )
            )
        frame = Frame(frame_idx=self._frame_idx, cam_t=cam_t, image=mat.get_data())
        self._frame_idx += 1
        return Capture(frame=frame, bodies=raw_bodies)

    def close(self) -> None:
        zed, self._zed = self._zed, None
        self._mat = None
        if zed is None:
            return
        if self._recording:
            zed.disable_recording()
            self._recording = False
        zed.close()
