"""Push detection from smoothed wrist Z velocity (spec section 8, perception/).

Owner: Enoch
"""

from magic_box.core.config import Config
from magic_box.core.contracts import Push, Px, Vec3


class PushDetector:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def update(self, slot: int, hand: str, wrist: Vec3, cam_t: float, wrist_px: Px) -> Push | None:
        raise NotImplementedError("TODO(Enoch): detect a push with cooldown")
