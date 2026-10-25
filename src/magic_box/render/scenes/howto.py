"""How to play: four steps, as a strip under the lobby cards and full screen at loading's start.

Owner: Adetola

The lobby strip gives one line per step so people walking past learn the game. The loading
screen (`GameView.howto_s` set, the first `game.howto_s` seconds of loading) shows the same steps
bigger, with the win condition and a countdown to the spell cards.
"""

import math

import pygame

from magic_box.core.contracts import GameView
from magic_box.render.scenes import SceneStyle, card

# (title, one line for the lobby strip, lines for the full-screen loading version)
STEPS = (
    (
        "SPEAK",
        "SAY YOUR SPELL INTO YOUR MIC",
        ("Say a spell's words into", "your own mic to charge it.", "Your spells are on your side."),
    ),
    (
        "PUSH",
        "PUSH TOWARD THE SCREEN TO CAST",
        (
            "Push toward the screen to cast",
            "(or do the move your spell shows).",
            "Nothing charged: basic attack.",
        ),
    ),
    (
        "DODGE",
        "STEP ASIDE OR DUCK WHEN IT'S RED",
        ("When an attack turns RED,", "step aside or duck.", "Holy Knight: arm forward to parry."),
    ),
    (
        "DISTANCE",
        "CLOSER HITS HARDER, BACK IS SAFER",
        (
            "RED zone, close: you hit harder,",
            "and get hit harder too.",
            "BLUE zone, a step back: safer.",
        ),
    ),
)
WIN_LINE = "WIN: KNOCK THEM OUT, OR HAVE MORE HP WHEN TIME RUNS OUT"


def draw_strip(surface, style: SceneStyle, rect: pygame.Rect) -> None:
    """The lobby version: a row of four numbered tiles, one line each."""
    th = style.theme
    assert th is not None
    c = th.c
    gap = 16
    tile_w = (rect.w - gap * (len(STEPS) - 1)) // len(STEPS)
    th.blit_text(surface, "HOW TO PLAY", "small", c["dim"], "bottomleft", (rect.x, rect.y - 6))
    for i, (title, line, _) in enumerate(STEPS):
        tile = pygame.Rect(rect.x + i * (tile_w + gap), rect.y, tile_w, rect.h)
        card(surface, style, tile, edge=c["gold"])
        num = th.blit_text(
            surface, str(i + 1), "huge", c["gold"], "midleft", (tile.x + 20, tile.centery)
        )
        tx = num.right + 18
        th.blit_text(surface, title, "big", c["text"], "bottomleft", (tx, tile.centery + 4))
        th.blit_text(
            surface,
            th.fit_text(line, "tiny", tile.right - tx - 12),
            "tiny",
            c["dim"],
            "topleft",
            (tx, tile.centery + 8),
        )


def draw(surface, view: GameView, style: SceneStyle, t: float = 0.0) -> None:
    """The loading version: a 2x2 grid of big steps, the win line and the countdown."""
    th = style.theme
    assert th is not None
    c = th.c
    w, h = surface.get_size()
    th.blit_text(
        surface,
        "HOW TO PLAY",
        th.font_px(th.title_px.get("loading", 96), display=True),
        c["gold"],
        "midtop",
        (w // 2, 20),
    )
    margin, gap, top = 60, 28, 170
    tile_w = (w - 2 * margin - gap) // 2
    tile_h = 320
    for i, (title, _, lines) in enumerate(STEPS):
        col, row = i % 2, i // 2
        tile = pygame.Rect(
            margin + col * (tile_w + gap), top + row * (tile_h + gap), tile_w, tile_h
        )
        card(surface, style, tile, edge=c["gold"])
        num = th.blit_text(
            surface, str(i + 1), "giant", c["gold"], "midleft", (tile.x + 30, tile.centery)
        )
        tx = num.right + 30
        y = tile.y + 30
        r = th.blit_text(surface, title, "huge", c["text"], "topleft", (tx, y))
        y = r.bottom + 8
        for line in lines:
            r = th.blit_text(
                surface,
                th.fit_text(line, "big", tile.right - tx - 24),
                "big",
                c["text"] if line is lines[0] else c["dim"],
                "topleft",
                (tx, y),
            )
            y = r.bottom + 6
    y = top + 2 * (tile_h + gap) + 10
    win = th.fit_text(WIN_LINE, "big", w - 2 * margin)
    th.blit_text(surface, win, "big", c["gold"], "midtop", (w // 2, y))
    if view.howto_s is not None:
        secs = max(1, math.ceil(view.howto_s))
        th.blit_text(
            surface, f"YOUR SPELLS IN {secs}", "text", c["dim"], "midtop", (w // 2, y + 70)
        )
