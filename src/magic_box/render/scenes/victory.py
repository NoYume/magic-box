"""Victory scene placeholder: the chronicle under the center banner (spec section 12).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.
"""

from magic_box.core.contracts import GameView
from magic_box.render.scenes import SceneStyle, victory_lines, wrap_text

MARGIN = 80
BELOW_CENTER = 100  # clears the window's center banner
GAP = 6


def draw(surface, view: GameView, style: SceneStyle) -> None:
    w, h = surface.get_size()
    y = h // 2 + BELOW_CENTER
    for text in victory_lines(view):
        for line in wrap_text(text, style.text_font, w - 2 * MARGIN):
            img = style.text_font.render(line, True, style.text_rgb)
            surface.blit(img, img.get_rect(midtop=(w // 2, y)))
            y += img.get_height() + GAP
