"""Map ZED SDK body-format keypoints to our named keypoints.

Owner: Enoch
"""

import numpy as np

from magic_box.core.contracts import Px, Vec3

PART_NAMES = {
    "BODY_18": (
        "NOSE", "NECK", "RIGHT_SHOULDER", "RIGHT_ELBOW", "RIGHT_WRIST", "LEFT_SHOULDER",
        "LEFT_ELBOW", "LEFT_WRIST", "RIGHT_HIP", "RIGHT_KNEE", "RIGHT_ANKLE", "LEFT_HIP",
        "LEFT_KNEE", "LEFT_ANKLE", "RIGHT_EYE", "LEFT_EYE", "RIGHT_EAR", "LEFT_EAR",
    ),
    "BODY_34": (
        "PELVIS", "NAVAL_SPINE", "CHEST_SPINE", "NECK", "LEFT_CLAVICLE", "LEFT_SHOULDER",
        "LEFT_ELBOW", "LEFT_WRIST", "LEFT_HAND", "LEFT_HANDTIP", "LEFT_THUMB", "RIGHT_CLAVICLE",
        "RIGHT_SHOULDER", "RIGHT_ELBOW", "RIGHT_WRIST", "RIGHT_HAND", "RIGHT_HANDTIP",
        "RIGHT_THUMB", "LEFT_HIP", "LEFT_KNEE", "LEFT_ANKLE", "LEFT_FOOT", "RIGHT_HIP",
        "RIGHT_KNEE", "RIGHT_ANKLE", "RIGHT_FOOT", "HEAD", "NOSE", "LEFT_EYE", "LEFT_EAR",
        "RIGHT_EYE", "RIGHT_EAR", "LEFT_HEEL", "RIGHT_HEEL",
    ),
    "BODY_38": (
        "PELVIS", "SPINE_1", "SPINE_2", "SPINE_3", "NECK", "NOSE", "LEFT_EYE", "RIGHT_EYE",
        "LEFT_EAR", "RIGHT_EAR", "LEFT_CLAVICLE", "RIGHT_CLAVICLE", "LEFT_SHOULDER",
        "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP",
        "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_BIG_TOE",
        "RIGHT_BIG_TOE", "LEFT_SMALL_TOE", "RIGHT_SMALL_TOE", "LEFT_HEEL", "RIGHT_HEEL",
        "LEFT_HAND_THUMB_4", "RIGHT_HAND_THUMB_4", "LEFT_HAND_INDEX_1", "RIGHT_HAND_INDEX_1",
        "LEFT_HAND_MIDDLE_4", "RIGHT_HAND_MIDDLE_4", "LEFT_HAND_PINKY_1", "RIGHT_HAND_PINKY_1",
    ),
}  # fmt: skip


def _sources(head: str, pelvis: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    out = {"head": (head,), "neck": ("NECK",), "pelvis": pelvis}
    for ours, sdk in (("shoulder", "SHOULDER"), ("wrist", "WRIST"), ("ankle", "ANKLE")):
        out[f"l_{ours}"] = (f"LEFT_{sdk}",)
        out[f"r_{ours}"] = (f"RIGHT_{sdk}",)
    return out


SOURCES = {
    "BODY_18": _sources("NOSE", ("LEFT_HIP", "RIGHT_HIP")),
    "BODY_34": _sources("HEAD", ("PELVIS",)),
    "BODY_38": _sources("NOSE", ("PELVIS",)),
}


def part_indices(body_format: str) -> dict[str, tuple[int, ...]]:
    """Our keypoint name -> SDK part indices (several indices = take the mean)."""
    order = PART_NAMES[body_format]
    return {
        name: tuple(order.index(part) for part in parts)
        for name, parts in SOURCES[body_format].items()
    }


def map_keypoints(
    body_format: str, kp3d: np.ndarray, kp2d: np.ndarray
) -> tuple[dict[str, Vec3], dict[str, Px]]:
    """Named float tuples from SDK arrays; points with any invalid part are dropped."""
    valid = np.isfinite(kp3d).all(axis=1) & np.isfinite(kp2d).all(axis=1) & (kp2d >= 0).all(axis=1)
    pts3: dict[str, Vec3] = {}
    pts2: dict[str, Px] = {}
    for name, idx in part_indices(body_format).items():
        if not all(valid[i] for i in idx):
            continue
        m3 = np.mean(kp3d[list(idx)], axis=0)
        m2 = np.mean(kp2d[list(idx)], axis=0)
        pts3[name] = (float(m3[0]), float(m3[1]), float(m3[2]))
        pts2[name] = (float(m2[0]), float(m2[1]))
    return pts3, pts2
