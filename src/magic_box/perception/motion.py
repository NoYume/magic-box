"""Sideways speed (root_vx) from the root's X over a short window (spec 7.4).

Owner: Enoch
"""

from magic_box.core.config import Config
from magic_box.core.contracts import Vec3
from magic_box.perception.kinematics import WindowedVelocity


class MotionTracker:
    """One instance per player slot."""

    def __init__(self, cfg: Config) -> None:
        self._window_s = cfg["perception"]["motion_window_s"]
        self._root_x = WindowedVelocity(self._window_s)

    def update(self, root: Vec3, cam_t: float) -> float:
        """Returns root_vx in m/s."""
        self._root_x.add(cam_t, root[0])
        return self._root_x.velocity()

    def reset(self) -> None:
        self._root_x.clear()
