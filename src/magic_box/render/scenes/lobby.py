"""Lobby scene: player presence and the raise-hands start cue.

Owner: Adetola
"""

import pygame

from magic_box.core.config import Config
from magic_box.core.contracts import GameView


def draw(surface, view: GameView, cfg: Config) -> None:
    color = tuple(cfg["render"]["text_rgb"])
    title = pygame.font.Font(None, 96)
    body = pygame.font.Font(None, 42)
    heading = title.render("MAGIC BOX", True, color)
    surface.blit(heading, heading.get_rect(center=(surface.get_width() // 2, 150)))
    half = surface.get_width() // 2
    class_names = "  ·  ".join(row["name"].upper() for row in cfg["game"]["classes"].values())
    for player in view.players:
        center_x = half * player.slot + half // 2
        tracking = "IN POSITION" if player.tracking_ok else "STEP INTO VIEW"
        mic = "MIC CHECKED" if player.mic_ok else 'SAY "MY NAME IS ..."'
        lines = [player.name, player.class_id.replace("_", " ").upper(), mic, tracking]
        for index, line in enumerate(lines):
            image = body.render(line, True, color)
            surface.blit(image, image.get_rect(center=(center_x, 330 + index * 58)))
    choices = body.render(f"SAY A CLASS:  {class_names}", True, color)
    surface.blit(choices, choices.get_rect(center=(surface.get_width() // 2, 650)))
    cue = body.render("BOTH PLAYERS: RAISE YOUR HANDS TO BEGIN", True, color)
    surface.blit(cue, cue.get_rect(center=(surface.get_width() // 2, surface.get_height() - 140)))
