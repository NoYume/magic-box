"""Motion features: root_vx and head tracking (spec section 8, perception/).

Owner: Enoch
"""

from magic_box.core.config import Config
from magic_box.core.contracts import Vec3


class MotionTracker:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def update(self, slot: int, root: Vec3, head: Vec3, cam_t: float) -> float:
        """Returns root_vx in m/s."""
        raise NotImplementedError("TODO(Enoch): compute root_vx")
