"""Non-fight scene drawing, dispatched on GameView.scene (pipeline spec section 12).

Owner: Adetola
Thin placeholder rules (2026-10-24 phase); replace freely.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import pygame

from magic_box.core.contracts import GameView
from magic_box.render.hud import release_cue


@dataclass(frozen=True)
class SceneStyle:
    title_font: pygame.font.Font
    text_font: pygame.font.Font
    text_rgb: tuple[int, int, int]
    dim_rgb: tuple[int, int, int]


def make_style(scene_cfg: Mapping) -> SceneStyle:
    """Build fonts and colors from `render.scenes`; call after `pygame.init()`."""
    return SceneStyle(
        title_font=pygame.font.Font(None, int(scene_cfg["title_px"])),
        text_font=pygame.font.Font(None, int(scene_cfg["text_px"])),
        text_rgb=tuple(scene_cfg["text_rgb"]),
        dim_rgb=tuple(scene_cfg["dim_rgb"]),
    )


def lobby_lines(view: GameView) -> list[str]:
    lines = ["MAGIC BOX"]
    for p in view.players:
        lines.append(f"{p.name}: {'TRACKED' if p.tracking_ok else 'STEP INTO VIEW'}")
    return lines


def loading_lines(view: GameView, slot: int) -> list[str]:
    me = view.players[slot]
    lines = [f"{me.name} · {me.class_id}"]
    for s in me.spells:
        lines.append(f'{s.name}: "{s.incantation or "…"}", then {release_cue(s.release)}')
    return lines


def victory_lines(view: GameView) -> list[str]:
    return [view.chronicle] if view.chronicle else ["writing the chronicle…"]


def wrap_text(text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and font.size(candidate)[0] > max_w:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def draw_scene(surface, view: GameView, style: SceneStyle) -> None:
    from magic_box.render.scenes import loading, lobby, victory

    drawers = {"lobby": lobby.draw, "loading": loading.draw, "victory": victory.draw}
    drawer = drawers.get(view.scene)
    if drawer is not None:
        drawer(surface, view, style)
