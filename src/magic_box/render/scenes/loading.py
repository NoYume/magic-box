"""Loading scene placeholder: one card per player and a countdown (spec section 12).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.
"""

import math

from magic_box.core.contracts import GameView
from magic_box.render.scenes import SceneStyle, loading_lines

TOP_FRAC = 0.15
MARGIN = 40
GAP = 10


def draw(surface, view: GameView, style: SceneStyle) -> None:
    w, h = surface.get_size()
    half = w // 2
    for slot in range(len(view.players)):
        x = slot * half + MARGIN
        y = int(h * TOP_FRAC)
        for i, line in enumerate(loading_lines(view, slot)):
            font = style.title_font if i == 0 else style.text_font
            img = font.render(line, True, style.text_rgb if i else style.dim_rgb)
            surface.blit(img, (x, y))
            y += img.get_height() + GAP
    if view.timer_s is not None:
        img = style.title_font.render(f"{math.ceil(view.timer_s)}", True, style.text_rgb)
        surface.blit(img, img.get_rect(midbottom=(w // 2, h - MARGIN)))
