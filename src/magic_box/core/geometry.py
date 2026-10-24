"""Pure geometry helpers: depth zones and pinhole projection.

Owner: Nikhil
"""

from collections.abc import Mapping

from magic_box.core.contracts import Px, Vec3


def zone_for_distance(z: float, zones: Mapping[str, float]) -> str:
    """Classify a root depth (meters) as "danger", "neutral" or "far"."""
    if z < zones["danger_max_m"]:
        return "danger"
    if z >= zones["far_min_m"]:
        return "far"
    return "neutral"


def project_point(p: Vec3, fx: float, fy: float, cx: float, cy: float) -> Px:
    """Project a camera-frame point (meters) to image pixels with a pinhole model."""
    x, y, z = p
    return (fx * x / z + cx, fy * y / z + cy)
