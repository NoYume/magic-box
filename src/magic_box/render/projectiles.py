"""Spell projectiles flying from the attacker's wrist toward the viewer (spec section 9).

Owner: Nikhil
"""

from collections.abc import Sequence

from magic_box.core.contracts import ProjectileView
from magic_box.render.layout import Rect


def draw_projectiles(
    surface,
    half: Rect,
    crop: Rect,
    projectiles: Sequence[ProjectileView],
    target_slot: int,
) -> None:
    if not any(p.target_slot == target_slot for p in projectiles):
        return
    raise NotImplementedError("TODO(Nikhil): draw projectiles, scaled by progress")
