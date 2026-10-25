"""Loading scene: a tutorial card per half (each spell's incantation and release) and a countdown.

Owner: Adetola

P1's card is on the left half. Each spell row shows the name and cost, what to say, and how to
release it. Basic attack and dodge tips sit under the spells; the countdown ring is bottom center.
"""

import math

import pygame

from magic_box.core.contracts import GameView, PlayerView
from magic_box.render.hud import class_label, release_cue
from magic_box.render.scenes import SceneStyle, card, family_rgb, wrap_text
from magic_box.render.style import draw_chip, draw_ring

CARD_TOP = 150
SPELL_ROW_H = 178
TIPS = (
    "BASIC ATTACK: PUSH WITH NO SPELL CHARGED",
    "DODGE: STEP ASIDE OR DUCK WHEN IT TURNS RED",
)


def draw(surface, view: GameView, style: SceneStyle, t: float = 0.0) -> None:
    th = style.theme
    assert th is not None
    w, _ = surface.get_size()
    half = w // 2
    for p in view.players:
        _draw_card(surface, style, p, view, p.slot * half, half)
    _countdown(surface, style, view.timer_s, (w // 2, surface.get_height() - 150))


def _draw_card(
    surface, style: SceneStyle, me: PlayerView, view: GameView, x0: int, hw: int
) -> None:
    th = style.theme
    assert th is not None
    c = th.c
    scfg = style.scene_cfg or {}
    cw = int(hw * float(scfg.get("card_w_frac", 0.86)))
    rx = x0 + (hw - cw) // 2
    slot_rgb = th.slot_rgb(me.slot)
    title = th.fit_text(f"GET READY, {me.name.upper()}", "big", cw)
    th.blit_text(surface, title, "big", slot_rgb, "topleft", (rx, 40))
    th.blit_text(
        surface, class_label(me, view.classes).upper(), "text", c["dim"], "topleft", (rx, 94)
    )
    y = CARD_TOP
    for spell in me.spells[:3]:
        rect = pygame.Rect(rx, y, cw, SPELL_ROW_H - 12)
        fam = family_rgb(style, spell.id)
        card(surface, style, rect, edge=fam)
        name = th.blit_text(
            surface, spell.name.upper(), "big", fam, "topleft", (rect.x + 22, rect.y + 14)
        )
        draw_chip(
            surface,
            th,
            f"{spell.cost:.0f} MANA",
            "tiny",
            (name.right + 16, name.centery),
            c["mana"],
            "midleft",
        )
        cue = th.blit_text(
            surface,
            release_cue(spell.release),
            "text",
            c["gold"],
            "midright",
            (rect.right - 22, name.centery),
        )
        th.blit_text(surface, "THEN", "small", c["dim"], "midright", (cue.x - 12, name.centery))
        say = th.blit_text(
            surface, "SAY", "small", c["dim"], "topleft", (rect.x + 22, name.bottom + 18)
        )
        inc = spell.incantation or "…"
        lines = wrap_text(f"“{inc}”", th.font("big"), rect.right - say.right - 40)[:2]
        ly = name.bottom + 8
        for line in lines:
            r = th.blit_text(surface, line, "big", c["text"], "topleft", (say.right + 14, ly))
            ly = r.bottom - 4
        y += SPELL_ROW_H
    y += 4
    for tip in TIPS:
        r = th.blit_text(
            surface, th.fit_text(tip, "small", cw), "small", c["dim"], "topleft", (rx, y)
        )
        y = r.bottom + 8


def _countdown(surface, style: SceneStyle, timer_s: float | None, center) -> None:
    if timer_s is None:
        return
    th = style.theme
    assert th is not None
    c = th.c
    secs = max(0, math.ceil(timer_s))
    part = timer_s - math.floor(timer_s) if timer_s > 0 else 0.0
    pygame.draw.circle(surface, c["panel"], center, 112)
    draw_ring(surface, center, 112, 12, part if secs > 0 else 1.0, c["gold"], c["faint"])
    text = str(secs) if secs > 0 else "GO!"
    font = th.font_px(
        int((style.scene_cfg or {}).get("countdown_px", 260) * (1.0 if secs > 0 else 0.6))
    )
    th.blit_text(surface, text, font, c["text"], "center", (center[0], center[1] + 8))
