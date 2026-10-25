"""Spell projectiles flying from the attacker's wrist toward the viewer.

Spec: 2026-10-24 nikhil-pipeline spec section 12.

Owner: Nikhil
"""

from collections.abc import Mapping, Sequence

import pygame

from magic_box.core.contracts import ProjectileView
from magic_box.render.layout import Rect


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def projectile_screen(
    p: ProjectileView, half: Rect, crop: Rect, cfg_proj: Mapping
) -> tuple[tuple[float, float], float, tuple[int, int, int]]:
    """Return (center, radius, rgb) in screen pixels for one projectile."""
    sx = half.x + (p.origin_px[0] - crop.x) * half.w / crop.w
    sy = half.y + (p.origin_px[1] - crop.y) * half.h / crop.h
    sx = min(max(sx, half.x), half.x + half.w)
    sy = min(max(sy, half.y), half.y + half.h)
    tx = half.x + half.w / 2
    ty = half.y + cfg_proj["end_y_frac"] * half.h
    t = p.progress
    center = (_lerp(sx, tx, t), _lerp(sy, ty, t))
    radius = _lerp(cfg_proj["start_radius_px"], cfg_proj["end_radius_px"], t)
    if p.in_dodge_window:
        rgb = cfg_proj["dodge_rgb"]
    else:
        rgb = cfg_proj["rgb"].get(p.spell_id, cfg_proj["default_rgb"])
    return center, radius, (int(rgb[0]), int(rgb[1]), int(rgb[2]))


def draw_projectiles(
    surface,
    half: Rect,
    crop: Rect,
    projectiles: Sequence[ProjectileView],
    target_slot: int,
    cfg_proj: Mapping,
    font,
) -> None:
    for p in projectiles:
        if p.target_slot != target_slot:
            continue
        center, radius, rgb = projectile_screen(p, half, crop, cfg_proj)
        pygame.draw.circle(surface, rgb, (round(center[0]), round(center[1])), round(radius))
        if p.in_dodge_window:
            tx = half.x + half.w / 2
            ty = half.y + cfg_proj["end_y_frac"] * half.h
            img = font.render("DODGE!", True, tuple(cfg_proj["dodge_rgb"]))
            surface.blit(
                img, img.get_rect(center=(round(tx), round(ty - radius - img.get_height())))
            )
