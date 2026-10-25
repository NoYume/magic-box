"""Loading scene: generated or fallback incantation cards.

Owner: Adetola
"""

import pygame

from magic_box.core.config import Config
from magic_box.core.contracts import GameView


def draw(surface, view: GameView, cfg: Config) -> None:
    color = tuple(cfg["render"]["text_rgb"])
    title = pygame.font.Font(None, 72)
    body = pygame.font.Font(None, 32)
    heading = title.render("LEARN YOUR INCANTATIONS", True, color)
    surface.blit(heading, heading.get_rect(center=(surface.get_width() // 2, 100)))
    half = surface.get_width() // 2
    for player in view.players:
        x = player.slot * half + 48
        surface.blit(body.render(player.name, True, color), (x, 190))
        for index, spell in enumerate(player.spells):
            y = 270 + index * 150
            surface.blit(body.render(spell.name.upper(), True, color), (x, y))
            surface.blit(body.render(f'"{spell.incantation}"', True, color), (x, y + 42))
