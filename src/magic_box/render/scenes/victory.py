"""victory scene placeholder (spec section 10).

Owner: Adetola
"""

import pygame

from magic_box.core.contracts import GameView


def draw(surface, view: GameView) -> None:
    # TODO(Adetola): real victory scene. Placeholder draws the scene name centered.
    font = pygame.font.Font(None, 96)
    text = font.render(view.scene.upper(), True, (255, 255, 255))
    surface.blit(text, text.get_rect(center=surface.get_rect().center))
