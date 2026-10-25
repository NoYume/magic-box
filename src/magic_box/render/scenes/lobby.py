"""Lobby scene placeholder: title, both players' tracking status (spec section 12).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.
"""

from magic_box.core.contracts import GameView
from magic_box.render.scenes import SceneStyle, lobby_lines

TOP_FRAC = 0.2
GAP = 12


def draw(surface, view: GameView, style: SceneStyle) -> None:
    title, *rest = lobby_lines(view)
    w, h = surface.get_size()
    img = style.title_font.render(title, True, style.text_rgb)
    surface.blit(img, img.get_rect(midtop=(w // 2, int(h * TOP_FRAC))))
    y = int(h * TOP_FRAC) + img.get_height() + 3 * GAP
    for line in rest:
        img = style.text_font.render(line, True, style.text_rgb)
        surface.blit(img, img.get_rect(midtop=(w // 2, y)))
        y += img.get_height() + GAP
