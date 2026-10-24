"""Body-to-slot assignment (spec section 8, perception/).

Owner: Enoch
"""

from typing import Any

from magic_box.core.config import Config


class SlotAssigner:
    """Binds tracked bodies to player slots.

    Slot 0 = the body with the larger image x (P1 stands on the left of the
    players' view, so appears on the image's right). Re-binds by side after loss.
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def assign(self, bodies: list[Any], now: float) -> dict[int, Any]:
        raise NotImplementedError("TODO(Enoch): assign bodies to slots by x position")
