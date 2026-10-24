"""Debug overlay: top-down view, wrist_vz graph, fps (spec section 8, render/).

Owner: Enoch
"""

from collections.abc import Mapping

import pygame

from magic_box.core.contracts import PlayerState


def draw_debug_overlay(
    surface, states: Mapping[int, PlayerState], fps: float, dropped: int
) -> None:
    # TODO(Enoch): top-down meters view and wrist_vz graph. Placeholder draws fps only.
    font = pygame.font.Font(None, 24)
    text = font.render(f"fps {fps:.0f}  dropped {dropped}", True, (255, 255, 255))
    surface.blit(text, (8, 8))
