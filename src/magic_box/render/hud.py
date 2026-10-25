"""Layout C player HUD and enemy health bar (spec section 9).

Owner: Adetola
"""

from collections.abc import Mapping

import pygame

from magic_box.core.contracts import PlayerView
from magic_box.render.layout import Rect

PAD = 8
BAR_H = 22


def _bar(surface, rect: Rect, frac: float, rgb, background) -> None:
    pygame.draw.rect(surface, background, rect.as_tuple())
    fill = max(0.0, min(1.0, frac))
    pygame.draw.rect(surface, rgb, (rect.x, rect.y, round(rect.w * fill), rect.h))


def draw_hud(surface, rect: Rect, me: PlayerView, font, render_cfg: Mapping) -> None:
    text_rgb = tuple(render_cfg["text_rgb"])
    background = tuple(render_cfg["bar_back_rgb"])
    pygame.draw.rect(surface, background, rect.as_tuple(), width=1)
    lines = [f"{me.name} · {me.class_id}", f"{me.dist:.1f} m · {me.zone.upper()}"]
    y = rect.y + PAD
    for text in lines:
        surface.blit(font.render(text, True, text_rgb), (rect.x + PAD, y))
        y += font.get_linesize()
    bar_w = rect.w - 2 * PAD
    _bar(
        surface,
        Rect(rect.x + PAD, y, bar_w, BAR_H),
        me.hp / me.hp_max,
        tuple(render_cfg["hp_rgb"]),
        background,
    )
    y += BAR_H + 4
    _bar(
        surface,
        Rect(rect.x + PAD, y, bar_w, BAR_H),
        me.mana / me.mana_max,
        tuple(render_cfg["mana_rgb"]),
        background,
    )
    y += BAR_H + 8
    if me.can_parry:
        surface.blit(
            font.render(_parry_status(me), True, tuple(render_cfg["guard_rgb"])), (rect.x + PAD, y)
        )
        y += font.get_linesize()
    for spell in me.spells:
        cue = "  CHARGED, PUSH!" if spell.charged else ""
        surface.blit(
            font.render(f'{spell.name}: "{spell.incantation}"{cue}', True, text_rgb),
            (rect.x + PAD, y),
        )
        y += font.get_linesize()


def _parry_status(me: PlayerView) -> str:
    if me.riposte_s > 0:
        return f"RIPOSTE! PUSH NOW {me.riposte_s:.1f}s"
    if me.guard_s > 0:
        return "GUARD UP"
    if me.guard_cooldown_s > 0:
        return f"Guard {me.guard_cooldown_s:.1f}s"
    return "Guard ready: arm forward to parry"


def draw_parry_flash(
    surface, half: Rect, me: PlayerView, font, render_cfg: Mapping, flash_s: float
) -> None:
    """First-person shield flash over the viewer's half when a parry lands."""
    if me.parry_flash_s <= 0:
        return
    fade = min(1.0, me.parry_flash_s / flash_s)
    r, g, b, a = render_cfg["parry_flash_rgba"]
    overlay = pygame.Surface((half.w, half.h), pygame.SRCALPHA)
    cx, w, top = half.w // 2, half.w // 3, half.h // 3
    shield = [
        (cx - w // 2, top),
        (cx + w // 2, top),
        (cx + w // 2, top + w // 2),
        (cx, top + w),
        (cx - w // 2, top + w // 2),
    ]
    pygame.draw.polygon(overlay, (r, g, b, round(a * fade)), shield)
    pygame.draw.polygon(overlay, (r, g, b, round(255 * fade)), shield, width=6)
    surface.blit(overlay, (half.x, half.y))
    label = font.render("PARRIED!", True, (r, g, b))
    label.set_alpha(round(255 * fade))
    surface.blit(label, label.get_rect(center=(half.x + cx, half.y + top - font.get_linesize())))


def draw_enemy_bar(surface, rect: Rect, enemy: PlayerView, font, render_cfg: Mapping) -> None:
    _bar(
        surface,
        rect,
        enemy.hp / enemy.hp_max,
        tuple(render_cfg["hp_rgb"]),
        tuple(render_cfg["bar_back_rgb"]),
    )
    label = font.render(f"{enemy.name} · {enemy.class_id}", True, tuple(render_cfg["text_rgb"]))
    surface.blit(label, label.get_rect(center=(rect.x + rect.w // 2, rect.y + rect.h // 2)))
