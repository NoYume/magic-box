"""Lobby scene: a card per player (name, mic check, TRACKED, ready) and the class pick.

Owner: Adetola

P1's card is on the left half, P2's on the right (each player reads their own side). Each card
shows the name (said into the mic), the last heard transcript as a mic check, TRACKED, the class
options with their spells (the pick highlighted) and a hands-up ready indicator.
"""

import pygame

from magic_box.core.contracts import ClassView, GameView, PlayerView
from magic_box.render.hud import class_label
from magic_box.render.scenes import SceneStyle, card
from magic_box.render.style import draw_chip, draw_mark, lerp_rgb, pulse

CARD_TOP = 200
CLASS_ROW_H = 78


def class_keyword(cv: ClassView) -> str:
    """The word to say for a class: the first word of its name (Fire, Lightning, Holy)."""
    return (cv.name.split() or [cv.id])[0].upper()


def draw(surface, view: GameView, style: SceneStyle, t: float = 0.0) -> None:
    th = style.theme
    assert th is not None
    w, _ = surface.get_size()
    th.blit_text(
        surface,
        "MAGIC BOX",
        th.font_px(th.title_px["lobby"], display=True),
        th.c["gold"],
        "midtop",
        (w // 2, 8),
    )
    half = w // 2
    for p in view.players:
        _draw_card(surface, style, p, view, p.slot * half, half, t)


def _draw_card(
    surface, style: SceneStyle, p: PlayerView, view: GameView, x0: int, hw: int, t: float
) -> None:
    th = style.theme
    assert th is not None
    c = th.c
    scfg = style.scene_cfg or {}
    cw = int(hw * float(scfg.get("card_w_frac", 0.86)))
    classes = view.classes
    rows = len(classes) if classes else 1
    ch = 330 + rows * CLASS_ROW_H
    rect = pygame.Rect(x0 + (hw - cw) // 2, CARD_TOP, cw, ch)
    slot_rgb = th.slot_rgb(p.slot)
    card(surface, style, rect, edge=slot_rgb)
    x, y = rect.x + 24, rect.y + 18
    tag = draw_chip(surface, th, f"P{p.slot + 1}", "small", (x, y + 6), slot_rgb)
    th.blit_text(
        surface,
        th.fit_text(p.name, "huge", rect.right - tag.right - 40),
        "huge",
        c["text"],
        "topleft",
        (tag.right + 16, y - 4),
    )
    y += 80
    r = draw_chip(
        surface,
        th,
        "TRACKED" if p.tracking_ok else "STEP INTO VIEW",
        "small",
        (x, y),
        c["ok"] if p.tracking_ok else c["bad"],
    )
    draw_chip(
        surface,
        th,
        "MIC OK" if p.mic_ok else "MIC OFF",
        "small",
        (r.right + 12, y),
        c["ok"] if p.mic_ok else c["bad"],
    )
    y += 54
    heard = f"“{p.heard}”" if p.heard else "say your name…"
    lab = th.blit_text(surface, "HEARD", "small", c["dim"], "topleft", (x, y + 6))
    th.blit_text(
        surface,
        th.fit_text(heard, "text", rect.right - lab.right - 48),
        "text",
        c["text"] if p.heard else c["faint"],
        "topleft",
        (lab.right + 14, y + 2),
    )
    y += 50
    if classes:
        hint = "SAY A CLASS: " + " · ".join(class_keyword(cv) for cv in classes)
        th.blit_text(
            surface, th.fit_text(hint, "small", rect.w - 48), "small", c["gold"], "topleft", (x, y)
        )
        y += 36
        for cv in classes:
            _class_row(
                surface,
                style,
                pygame.Rect(x, y, rect.w - 48, CLASS_ROW_H - 8),
                cv,
                cv.id == p.class_id,
                slot_rgb,
            )
            y += CLASS_ROW_H
    else:
        th.blit_text(surface, "CLASS", "small", c["dim"], "topleft", (x, y + 8))
        r = th.blit_text(surface, class_label(p, classes), "big", slot_rgb, "topleft", (x + 110, y))
        spells = " · ".join(s.name for s in p.spells)
        th.blit_text(
            surface,
            th.fit_text(spells, "small", rect.w - 158),
            "small",
            c["gold"],
            "topleft",
            (x + 110, r.bottom + 4),
        )
        y += CLASS_ROW_H
    _ready(surface, style, p, rect.centerx, rect.bottom - 52, t)


def _class_row(
    surface, style: SceneStyle, rect: pygame.Rect, cv: ClassView, picked: bool, slot_rgb
) -> None:
    th = style.theme
    assert th is not None
    c = th.c
    card(surface, style, rect, edge=slot_rgb if picked else None, hi=picked)
    if picked:
        pygame.draw.circle(surface, slot_rgb, (rect.x + 30, rect.centery), 20)
        draw_mark(surface, (rect.x + 30, rect.centery), 24, True, c["ink"], 5)
    name = th.blit_text(
        surface,
        cv.name.upper(),
        "text",
        c["text"] if picked else c["dim"],
        "topleft",
        (rect.x + 64, rect.y + 6),
    )
    spells = " · ".join(cv.spells)
    th.blit_text(
        surface,
        th.fit_text(spells, "tiny", rect.right - rect.x - 80),
        "tiny",
        c["gold"] if picked else c["faint"],
        "topleft",
        (rect.x + 64, name.bottom + 2),
    )


def _ready(surface, style: SceneStyle, p: PlayerView, cx: int, cy: int, t: float) -> None:
    th = style.theme
    assert th is not None
    c = th.c
    if p.ready:
        col = lerp_rgb(c["ok"], c["white"], 0.3 * pulse(t, 6.0))
        text = "READY!"
    else:
        col, text = c["dim"], "RAISE BOTH HANDS"
    r = th.blit_text(surface, text, "big", col, "midleft", (cx - 140, cy))
    _hands_icon(surface, (r.x - 50, cy), col, raised=p.ready)


def _hands_icon(surface, center, color, raised: bool) -> None:
    """A stick figure with arms up (ready) or down."""
    cx, cy = center
    pygame.draw.circle(surface, color, (round(cx), round(cy - 18)), 9)
    pygame.draw.line(surface, color, (cx, cy - 8), (cx, cy + 16), 5)
    for side in (-1, 1):
        if raised:
            end = (cx + side * 18, cy - 34)
        else:
            end = (cx + side * 16, cy + 12)
        pygame.draw.line(surface, color, (cx, cy - 4), end, 5)
