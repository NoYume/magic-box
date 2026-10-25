"""Pose flags from one body's keypoints (spec 7.6).

Owner: Enoch
"""

import math
from collections.abc import Mapping
from typing import Any

from magic_box.core.contracts import Vec3


def detect_poses(
    kp3d: Mapping[str, Vec3], head: Vec3, perception: Mapping[str, Any]
) -> frozenset[str]:
    """Return "hands_up" and/or "hands_together". Image coordinates: +y is down."""
    flags: set[str] = set()
    left, right = kp3d.get("l_wrist"), kp3d.get("r_wrist")
    wrists = [w for w in (left, right) if w is not None]

    if any(w[1] < head[1] - perception["hands_up_margin_m"] for w in wrists):
        flags.add("hands_up")

    if left is not None and right is not None:
        pelvis = kp3d.get("pelvis")
        if (
            math.dist(left, right) < perception["hands_together_max_m"]
            and all(w[1] > head[1] for w in wrists)
            and (pelvis is None or all(w[1] < pelvis[1] for w in wrists))
        ):
            flags.add("hands_together")
    return frozenset(flags)
