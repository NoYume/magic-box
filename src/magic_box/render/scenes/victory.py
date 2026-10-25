"""Victory scene: winner headline, a stats card per player and the Duel Chronicle.

Owner: Adetola

The headline is the engine's banner when present (it names the winner), else built from
`winner_slot` ("DRAW" when None). Stats show only the keys present in `PlayerView.stats`.
"""

import pygame

from magic_box.core.contracts import GameView, PlayerView
from magic_box.render.scenes import SceneStyle, card, headline, stat_lines, wrap_text
from magic_box.render.style import Theme, blit_glow, draw_chip, headline_glow_rgb, lerp_rgb, pulse

CARD_TOP = 230
CARD_H = 420
STAT_ROW_H = 38
CHRONICLE_TOP = 676


def glow_tints(theme: Theme) -> list:
    """The headline glow tints (P1, P2, draw), for `Theme.prewarm`."""
    top = float(theme.glow_steps[-1])
    return [(headline_glow_rgb(theme, theme.slot_rgb(s)), False, top) for s in (0, 1, None)]


def draw(surface, view: GameView, style: SceneStyle, t: float = 0.0) -> None:
    th = style.theme
    assert th is not None
    c = th.c
    w, h = surface.get_size()
    win = view.winner_slot
    col = th.slot_rgb(win) if win is not None else c["gold"]
    blit_glow(surface, th, (w // 2, 120), th.glow_steps[-1], headline_glow_rgb(th, col), core=False)
    text = headline(view)
    px = th.title_px["headline"]
    font = th.font_px(px, display=True)
    if font.size(text)[0] > w - 120:
        font = th.font_px(max(40, int(px * (w - 120) / font.size(text)[0])), display=True)
    th.blit_text(surface, text, font, col, "center", (w // 2, 120))
    half = w // 2
    for p in view.players:
        _stats_card(surface, style, p, win, p.slot * half, half, t)
    _chronicle(surface, style, view, pygame.Rect(0, CHRONICLE_TOP, w, h - CHRONICLE_TOP - 20), t)


def _stats_card(surface, style: SceneStyle, p: PlayerView, win, x0: int, hw: int, t: float) -> None:
    th = style.theme
    assert th is not None
    c = th.c
    scfg = style.scene_cfg or {}
    cw = int(hw * float(scfg.get("card_w_frac", 0.86)))
    rect = pygame.Rect(x0 + (hw - cw) // 2, CARD_TOP, cw, CARD_H)
    is_winner = win is not None and win == p.slot
    slot_rgb = th.slot_rgb(p.slot)
    card(surface, style, rect, edge=c["gold"] if is_winner else slot_rgb, hi=is_winner)
    x, y = rect.x + 24, rect.y + 16
    name = th.blit_text(
        surface, th.fit_text(p.name, "big", cw - 240), "big", slot_rgb, "topleft", (x, y)
    )
    if is_winner:
        draw_chip(
            surface, th, "WINNER", "small", (rect.right - 24, name.centery), c["gold"], "midright"
        )
    th.blit_text(surface, f"HP {p.hp:.0f}", "small", c["dim"], "topleft", (x, name.bottom + 4))
    y = name.bottom + 44
    lines = stat_lines(p)
    if not lines:
        th.blit_text(surface, "no stats this round", "small", c["faint"], "topleft", (x, y))
    for label, value in lines[: (CARD_H - 150) // STAT_ROW_H]:
        th.blit_text(surface, label, "small", c["dim"], "midleft", (x, y + STAT_ROW_H // 2))
        th.blit_text(
            surface, value, "text", c["text"], "midright", (rect.right - 24, y + STAT_ROW_H // 2)
        )
        y += STAT_ROW_H
    if p.ready:
        ready_rgb = lerp_rgb(c["ok"], c["white"], 0.3 * pulse(t, 6.0))
        th.blit_text(
            surface,
            "READY FOR A REMATCH!",
            "small",
            ready_rgb,
            "midbottom",
            (rect.centerx, rect.bottom - 14),
        )
    else:
        th.blit_text(
            surface,
            "RAISE BOTH HANDS FOR A REMATCH",
            "small",
            c["faint"],
            "midbottom",
            (rect.centerx, rect.bottom - 14),
        )


def _chronicle(surface, style: SceneStyle, view: GameView, area: pygame.Rect, t: float) -> None:
    th = style.theme
    assert th is not None
    c = th.c
    scfg = style.scene_cfg or {}
    cw = int(area.w * float(scfg.get("chronicle_w_frac", 0.7)))
    max_w = cw - 60
    title_h = th.font("small").get_linesize() + 14
    avail = area.h - title_h - 36
    font_name, lines = "text", ["the bards are writing" + "." * (1 + int(t * 2) % 3)]
    if view.chronicle:
        for font_name in ("big", "text", "small", "tiny"):
            lines = wrap_text(view.chronicle, th.font(font_name), max_w)
            if len(lines) * th.font(font_name).get_linesize() <= avail:
                break
    font = th.font(font_name)
    max_lines = max(1, avail // font.get_linesize())
    if len(lines) > max_lines:
        rest = " ".join(lines[max_lines - 1 :])
        lines = lines[: max_lines - 1] + [th.fit_text(rest, font_name, max_w)]
    rect = pygame.Rect(
        area.centerx - cw // 2, area.y, cw, title_h + 36 + len(lines) * font.get_linesize()
    )
    card(surface, style, rect, edge=c["panel_edge"])
    title = th.blit_text(
        surface, "THE DUEL CHRONICLE", "small", c["gold"], "midtop", (rect.centerx, rect.y + 14)
    )
    color = c["text"] if view.chronicle else c["dim"]
    y = title.bottom + 12
    for line in lines:
        th.blit_text(surface, line, font_name, color, "midtop", (rect.centerx, y))
        y += font.get_linesize()
