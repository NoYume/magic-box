"""Victory scene with the Duel Chronicle.

Owner: Adetola
"""

import textwrap

import pygame

from magic_box.core.config import Config
from magic_box.core.contracts import GameView


def draw(surface, view: GameView, cfg: Config) -> None:
    color = tuple(cfg["render"]["text_rgb"])
    title = pygame.font.Font(None, 96)
    body = pygame.font.Font(None, 38)
    heading = title.render(view.banner or "DUEL COMPLETE", True, color)
    surface.blit(heading, heading.get_rect(center=(surface.get_width() // 2, 180)))
    chronicle = view.chronicle or "The Duel Chronicle is being written…"
    for index, line in enumerate(textwrap.wrap(chronicle, width=75)):
        image = body.render(line, True, color)
        surface.blit(
            image,
            image.get_rect(center=(surface.get_width() // 2, 390 + index * body.get_linesize())),
        )
