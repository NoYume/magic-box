"""Pose flag detection (spec section 8, perception/).

Owner: Enoch
"""

from collections.abc import Mapping

from magic_box.core.contracts import Vec3


def detect_poses(keypoints: Mapping[str, Vec3]) -> frozenset[str]:
    raise NotImplementedError("TODO(Enoch): detect pose flags from keypoints")
