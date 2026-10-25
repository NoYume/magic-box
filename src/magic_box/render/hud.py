"""Placeholder HUD: viewer's own panel and the enemy HP bar (nikhil-pipeline spec section 12).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.
"""

import pygame

from magic_box.core.contracts import PlayerView, SpellView
from magic_box.render.layout import Rect

# TODO(Adetola): replace this placeholder with the real HUD; colors move to config then.
TEXT_RGB = (240, 240, 240)
BAR_BACK_RGB = (40, 36, 52)
HP_RGB = (200, 50, 60)
MANA_RGB = (60, 110, 220)
PAD = 8
RELEASE_CUES = {
    "push": "PUSH!",
    "two_hand_push": "TWO-HAND PUSH!",
    "arm_overhead": "RAISE ARM!",
    "hands_together": "HANDS TOGETHER!",
}
BAR_H = 22


def release_cue(release: str) -> str:
    return RELEASE_CUES.get(release, release.upper() + "!")


def spell_line(spell: SpellView) -> str:
    if spell.charged:
        return f"{spell.name}  CHARGED: {release_cue(spell.release)}"
    return f'{spell.name}: "{spell.incantation}"'


def name_line(me: PlayerView) -> str:
    return f"{me.name} · {me.class_id} · {'MIC OK' if me.mic_ok else 'MIC OFF'}"


def _bar(surface, rect: Rect, frac: float, rgb) -> None:
    pygame.draw.rect(surface, BAR_BACK_RGB, rect.as_tuple())
    fill = max(0.0, min(1.0, frac))
    pygame.draw.rect(surface, rgb, (rect.x, rect.y, round(rect.w * fill), rect.h))


def draw_hud(surface, rect: Rect, me: PlayerView, font) -> None:
    pygame.draw.rect(surface, (0, 0, 0), rect.as_tuple(), width=1)
    lines = [name_line(me), f"{me.dist:.1f} m · {me.zone.upper()}"]
    y = rect.y + PAD
    for text in lines:
        surface.blit(font.render(text, True, TEXT_RGB), (rect.x + PAD, y))
        y += font.get_linesize()
    bar_w = rect.w - 2 * PAD
    _bar(surface, Rect(rect.x + PAD, y, bar_w, BAR_H), me.hp / me.hp_max, HP_RGB)
    y += BAR_H + 4
    _bar(surface, Rect(rect.x + PAD, y, bar_w, BAR_H), me.mana / me.mana_max, MANA_RGB)
    y += BAR_H + 8
    for spell in me.spells:
        surface.blit(
            font.render(spell_line(spell), True, TEXT_RGB),
            (rect.x + PAD, y),
        )
        y += font.get_linesize()


def draw_enemy_bar(surface, rect: Rect, enemy: PlayerView, font) -> None:
    _bar(surface, rect, enemy.hp / enemy.hp_max, HP_RGB)
    label = font.render(enemy.name, True, TEXT_RGB)
    surface.blit(label, label.get_rect(center=(rect.x + rect.w // 2, rect.y + rect.h // 2)))
