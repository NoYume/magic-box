"""Screen layout geometry (spec section 9). Task 9 extends this module.

Owner: Adetola + Nikhil
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    """Integer pixel rectangle."""

    x: int
    y: int
    w: int
    h: int

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    def contains(self, other: "Rect") -> bool:
        """True when `other` lies fully inside this rectangle."""
        return (
            other.x >= self.x
            and other.y >= self.y
            and other.x + other.w <= self.x + self.w
            and other.y + other.h <= self.y + self.h
        )


@dataclass(frozen=True)
class HalfLayout:
    """One half of the monitor. The viewer watches `shows_slot` (their opponent)."""

    viewer_slot: int
    shows_slot: int
    half: Rect
    enemy_bar: Rect
    selfview: Rect
    hud: Rect


ENEMY_BAR_H = 28
SELFVIEW_TOP_OFFSET = 44  # selfview sits below the enemy bar


def compute_layout(width: int, height: int, render_cfg: Mapping) -> tuple[HalfLayout, HalfLayout]:
    """Return (left half for P1, right half for P2) for a width x height screen."""
    m = int(render_cfg["margin_px"])
    hw = width // 2
    sv_w = int(hw * render_cfg["selfview_width_frac"])
    sv_h = sv_w * 3 // 4
    hud_h = int(height * render_cfg["hud_height_frac"])
    halves = []
    for viewer in (0, 1):
        x0 = viewer * hw
        halves.append(
            HalfLayout(
                viewer_slot=viewer,
                shows_slot=1 - viewer,
                half=Rect(x0, 0, hw, height),
                enemy_bar=Rect(x0 + int(hw * 0.24), m, int(hw * 0.52), ENEMY_BAR_H),
                selfview=Rect(x0 + hw - m - sv_w, m + SELFVIEW_TOP_OFFSET, sv_w, sv_h),
                hud=Rect(x0 + m, height - m - hud_h, hw - 2 * m, hud_h),
            )
        )
    return halves[0], halves[1]
