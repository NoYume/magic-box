"""Spell projectiles flying from the attacker's wrist toward the viewer.

Spec: 2026-10-24 nikhil-pipeline spec section 12.

Owner: Nikhil (procedural sprites: Adetola)

Each projectile is drawn per spell family (`render.projectiles.family`): fire (flickering
flame tongues), lightning (jagged arcs), holy (rotating rays) or basic, with an additive glow
and a stateless trail (ghost copies at earlier progress values). In the dodge window a red ring
pulses around it with "DODGE!" above the impact point.
"""

import math
import random
from collections.abc import Mapping, Sequence

import pygame

from magic_box.core.contracts import ProjectileView
from magic_box.render.layout import Rect
from magic_box.render.style import Theme, blit_glow, lerp_rgb, rgb


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _screen_at(
    p: ProjectileView, progress: float, half: Rect, crop: Rect, cfg_proj: Mapping
) -> tuple[tuple[float, float], float]:
    sx = half.x + (p.origin_px[0] - crop.x) * half.w / crop.w
    sy = half.y + (p.origin_px[1] - crop.y) * half.h / crop.h
    sx = min(max(sx, half.x), half.x + half.w)
    sy = min(max(sy, half.y), half.y + half.h)
    tx = half.x + half.w / 2
    ty = half.y + cfg_proj["end_y_frac"] * half.h
    center = (_lerp(sx, tx, progress), _lerp(sy, ty, progress))
    radius = _lerp(cfg_proj["start_radius_px"], cfg_proj["end_radius_px"], progress)
    return center, radius


def projectile_screen(
    p: ProjectileView, half: Rect, crop: Rect, cfg_proj: Mapping
) -> tuple[tuple[float, float], float, tuple[int, int, int]]:
    """Return (center, radius, rgb) in screen pixels for one projectile."""
    center, radius = _screen_at(p, p.progress, half, crop, cfg_proj)
    if p.in_dodge_window:
        color = cfg_proj["dodge_rgb"]
    else:
        color = cfg_proj["rgb"].get(p.spell_id, cfg_proj["default_rgb"])
    return center, radius, rgb(color)


def spell_family(spell_id: str, cfg_proj: Mapping) -> str:
    return cfg_proj.get("family", {}).get(spell_id, "basic")


def _spell_rgb(p: ProjectileView, cfg_proj: Mapping) -> tuple[int, int, int]:
    return rgb(cfg_proj["rgb"].get(p.spell_id, cfg_proj["default_rgb"]))


def _draw_fire(surface, center, radius: float, color, rng: random.Random, th: Theme) -> None:
    cx, cy = center
    hot = lerp_rgb(color, th.c["fire_hot"], 0.6)
    for _ in range(7):
        a = rng.uniform(0, 2 * math.pi)
        d = radius * rng.uniform(0.4, 1.05)
        r = radius * rng.uniform(0.25, 0.5)
        pygame.draw.circle(
            surface,
            hot if rng.random() < 0.5 else color,
            (cx + d * math.cos(a), cy + d * math.sin(a)),
            r,
        )
    pygame.draw.circle(surface, color, center, radius * 0.85)
    pygame.draw.circle(surface, th.c["fire_core"], center, radius * 0.45)


def _zigzag(start, end, rng: random.Random, jitter: float, segments: int = 6) -> list:
    (x0, y0), (x1, y1) = start, end
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    pts = [start]
    for i in range(1, segments):
        f = i / segments
        off = rng.uniform(-jitter, jitter)
        pts.append((x0 + dx * f + nx * off, y0 + dy * f + ny * off))
    pts.append(end)
    return pts


def _draw_lightning(surface, center, radius: float, color, rng: random.Random, tail, white) -> None:
    pygame.draw.circle(surface, color, center, radius * 0.8)
    pygame.draw.circle(surface, white, center, radius * 0.45)
    width = max(2, round(radius / 14))
    for _ in range(4):
        a = rng.uniform(0, 2 * math.pi)
        end = (center[0] + radius * 1.9 * math.cos(a), center[1] + radius * 1.9 * math.sin(a))
        pygame.draw.lines(surface, white, False, _zigzag(center, end, rng, radius * 0.35, 4), width)
    if tail is not None:
        pts = _zigzag(tail, center, rng, radius * 0.6, 7)
        pygame.draw.lines(surface, color, False, pts, width + 3)
        pygame.draw.lines(surface, white, False, pts, width)


def _draw_holy(surface, center, radius: float, color, t: float, white) -> None:
    cx, cy = center
    width = max(2, round(radius / 10))
    for k in range(8):
        a = t * 2.5 + k * math.pi / 4
        r0, r1 = radius * 0.9, radius * (2.0 if k % 2 == 0 else 1.5)
        pygame.draw.line(
            surface,
            color,
            (cx + r0 * math.cos(a), cy + r0 * math.sin(a)),
            (cx + r1 * math.cos(a), cy + r1 * math.sin(a)),
            width,
        )
    pygame.draw.circle(surface, color, center, radius * 1.15, width)
    pygame.draw.circle(surface, color, center, radius * 0.8)
    pygame.draw.circle(surface, white, center, radius * 0.5)


def _draw_basic(surface, center, radius: float, color, white) -> None:
    pygame.draw.circle(surface, color, center, radius * 0.75)
    pygame.draw.circle(surface, white, center, radius * 0.4)


def _draw_styled(
    surface, p: ProjectileView, half: Rect, crop: Rect, cfg_proj: Mapping, theme: Theme, t: float
) -> tuple[tuple[float, float], float]:
    family = spell_family(p.spell_id, cfg_proj)
    color = _spell_rgb(p, cfg_proj)
    glow_scale = float(cfg_proj["glow_scale"])
    glow_max = float(cfg_proj["glow_max_px"])
    steps, spacing = int(cfg_proj["trail_steps"]), float(cfg_proj["trail_spacing"])
    center, radius = _screen_at(p, p.progress, half, crop, cfg_proj)
    tail = None
    for k in range(steps, 0, -1):
        prog = p.progress - k * spacing
        if prog < 0:
            continue
        c_k, r_k = _screen_at(p, prog, half, crop, cfg_proj)
        fade = 1.0 - k / (steps + 1)
        blit_glow(surface, theme, c_k, min(glow_max, r_k * glow_scale * 0.6 * fade), color)
        if tail is None:
            tail = c_k
    blit_glow(surface, theme, center, min(glow_max, radius * glow_scale), color)
    rng = random.Random(int(t * 30) * 7919 + sum(map(ord, p.spell_id)) + round(p.origin_px[0]))
    if family == "fire":
        _draw_fire(surface, center, radius, color, rng, theme)
    elif family == "lightning":
        _draw_lightning(surface, center, radius, color, rng, tail, theme.c["white"])
    elif family == "holy":
        _draw_holy(surface, center, radius, color, t, theme.c["white"])
    else:
        _draw_basic(surface, center, radius, color, theme.c["white"])
    return center, radius


def draw_projectiles(
    surface,
    half: Rect,
    crop: Rect,
    projectiles: Sequence[ProjectileView],
    target_slot: int,
    cfg_proj: Mapping,
    font,
    theme: Theme | None = None,
    t: float = 0.0,
) -> None:
    """Draw the projectiles aimed at `target_slot` on its half (plain circles without a theme)."""
    for p in projectiles:
        if p.target_slot != target_slot:
            continue
        if theme is None:
            center, radius, color = projectile_screen(p, half, crop, cfg_proj)
            pygame.draw.circle(surface, color, (round(center[0]), round(center[1])), round(radius))
        else:
            center, radius = _draw_styled(surface, p, half, crop, cfg_proj, theme, t)
        if p.in_dodge_window:
            dodge = rgb(cfg_proj["dodge_rgb"])
            if theme is not None:
                ring = radius + cfg_proj["dodge_ring_px"] * (1.0 + 0.5 * math.sin(t * 20.0))
                pygame.draw.circle(
                    surface, dodge, (round(center[0]), round(center[1])), round(ring), 6
                )
            tx = half.x + half.w / 2
            ty = half.y + cfg_proj["end_y_frac"] * half.h
            img = (
                theme.text("DODGE!", font, dodge)
                if theme is not None
                else font.render("DODGE!", True, dodge)
            )
            surface.blit(
                img, img.get_rect(center=(round(tx), round(ty - radius - img.get_height())))
            )
