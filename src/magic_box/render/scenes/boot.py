"""Boot scene: the self-check list (camera, mics, network, api key) with OK and missing marks.

Owner: Adetola
"""

import math

import pygame

from magic_box.core.contracts import GameView
from magic_box.render.scenes import SceneStyle, card
from magic_box.render.style import draw_mark, draw_ring

ROW_H = 92
CARD_W = 1100


def draw(surface, view: GameView, style: SceneStyle, t: float = 0.0) -> None:
    th = style.theme
    assert th is not None
    c = th.c
    w = surface.get_width()
    th.blit_text(surface, "MAGIC BOX", "giant", c["gold"], "midtop", (w // 2, 50))
    th.blit_text(surface, "SYSTEM CHECK", "big", c["dim"], "midtop", (w // 2, 225))
    rows = max(1, len(view.checks))
    rect = pygame.Rect((w - CARD_W) // 2, 300, CARD_W, rows * ROW_H + 40)
    card(surface, style, rect, edge=c["panel_edge"])
    y = rect.y + 20
    if not view.checks:
        cy = y + ROW_H // 2
        draw_ring(surface, (rect.x + 70, cy), 26, 7, 0.3, c["gold"], c["faint"])
        spin = (t * 4.0) % (2 * math.pi)
        dot = (rect.x + 70 + 22 * math.cos(spin), cy + 22 * math.sin(spin))
        pygame.draw.circle(surface, c["text"], dot, 6)
        th.blit_text(surface, "STARTING…", "big", c["text"], "midleft", (rect.x + 130, cy))
        return
    for check in view.checks:
        cy = y + ROW_H // 2
        col = c["ok"] if check.ok else c["bad"]
        pygame.draw.circle(surface, col, (rect.x + 70, cy), 32)
        draw_mark(surface, (rect.x + 70, cy), 40, check.ok, c["ink"], 7)
        name = th.blit_text(
            surface, check.name.upper(), "big", c["text"], "midleft", (rect.x + 130, cy)
        )
        status = "OK" if check.ok else "MISSING"
        th.blit_text(surface, status, "big", col, "midright", (rect.right - 40, cy))
        if check.detail:
            max_w = rect.right - 240 - name.right
            th.blit_text(
                surface,
                th.fit_text(check.detail, "small", max_w),
                "small",
                c["dim"],
                "midleft",
                (name.right + 24, cy + 2),
            )
        y += ROW_H
    missing = sum(1 for ch in view.checks if not ch.ok)
    if missing:
        note = f"{missing} MISSING: keyboard spell keys still work"
        th.blit_text(surface, note, "text", c["warn"], "midtop", (w // 2, rect.bottom + 24))
    else:
        th.blit_text(
            surface, "ALL SYSTEMS GO", "big", c["ok"], "midtop", (w // 2, rect.bottom + 24)
        )
