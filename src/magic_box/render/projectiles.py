"""Spell projectiles flying from the attacker's wrist toward the viewer (spec section 9).

Owner: Nikhil
"""

from collections.abc import Mapping, Sequence

import pygame

from magic_box.core.contracts import ProjectileView
from magic_box.render.camera_view import map_point_to_dest
from magic_box.render.layout import Rect


def draw_projectiles(
    surface,
    half: Rect,
    crop: Rect,
    projectiles: Sequence[ProjectileView],
    target_slot: int,
    render_cfg: Mapping,
    can_parry: bool = False,
) -> None:
    """Draw incoming projectiles moving from the attacker's wrist toward the viewer."""
    font = pygame.font.Font(None, 42)
    for projectile in projectiles:
        if projectile.target_slot != target_slot:
            continue
        start = map_point_to_dest(projectile.origin_px, crop, half, mirror=False)
        end = (half.x + half.w // 2, half.y + half.h)
        progress = max(0.0, min(1.0, projectile.progress))
        x = round(start[0] + (end[0] - start[0]) * progress)
        y = round(start[1] + (end[1] - start[1]) * progress)
        minimum = int(render_cfg["projectile_min_px"])
        maximum = int(render_cfg["projectile_max_px"])
        radius = round(minimum + (maximum - minimum) * progress * progress)
        if projectile.spell_id == "riposte":
            _draw_blade_wave(surface, (x, y), radius, projectile.in_dodge_window, render_cfg)
        else:
            color = tuple(
                render_cfg["dodge_rgb"]
                if projectile.in_dodge_window
                else render_cfg["projectile_rgb"]
            )
            pygame.draw.circle(surface, color, (x, y), radius)
            pygame.draw.circle(
                surface, tuple(render_cfg["projectile_core_rgb"]), (x, y), max(2, radius // 3)
            )
        if projectile.in_dodge_window:
            text = "PARRY / DODGE!" if can_parry else "DODGE!"
            label = font.render(text, True, tuple(render_cfg["dodge_rgb"]))
            surface.blit(label, label.get_rect(center=(half.x + half.w // 2, half.y + half.h // 2)))


def _draw_blade_wave(surface, center, radius: int, in_dodge_window: bool, render_cfg) -> None:
    """A horizontal crescent: the knight's riposte slash flying toward the viewer."""
    x, y = center
    w, h = radius * 3, max(4, radius)
    outer = pygame.Rect(x - w // 2, y - h, w, 2 * h)
    color = tuple(render_cfg["dodge_rgb"] if in_dodge_window else render_cfg["riposte_rgb"])
    pygame.draw.arc(surface, color, outer, 0.15, 2.99, max(3, radius // 2))
    inner = outer.inflate(-w // 6, -h // 2)
    pygame.draw.arc(
        surface, tuple(render_cfg["riposte_core_rgb"]), inner, 0.3, 2.84, max(2, radius // 6)
    )
