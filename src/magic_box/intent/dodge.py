"""Windowed step and duck dodge detection (spec section 8, intent/).

Owner: Nikhil
"""

from magic_box.core.config import Config
from magic_box.core.contracts import PlayerState


class DodgeDetector:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def update(self, state: PlayerState) -> str | None:
        """Returns "step", "duck" or None."""
        raise NotImplementedError("TODO(Nikhil): windowed step/duck detection")
