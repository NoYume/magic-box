"""Non-fight scene drawing, dispatched on GameView.scene (pipeline spec section 12).

Owner: Adetola

`draw_scene` picks boot, lobby, loading or victory. Shared here: `SceneStyle` (fonts, colors and
the theme, from `render.scenes` and `render.theme`), the text-line helpers the scenes and tests
use, `wrap_text`, and small card widgets.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import pygame

from magic_box.core.contracts import GameView, PlayerView
from magic_box.render.hud import release_cue
from magic_box.render.style import Theme, rgb

STAT_LABELS = (
    ("damage", "DAMAGE DEALT", "{:.0f}"),
    ("hits", "HITS", "{:.0f}"),
    ("casts", "SPELLS CAST", "{:.0f}"),
    ("dodges", "DODGES", "{:.0f}"),
    ("blocks", "BLOCKS", "{:.0f}"),
    ("heals", "HEALS", "{:.0f}"),
    ("best_push_mps", "FASTEST PUSH", "{:.1f} m/s"),
)


@dataclass(frozen=True)
class SceneStyle:
    title_font: pygame.font.Font
    text_font: pygame.font.Font
    text_rgb: tuple[int, int, int]
    dim_rgb: tuple[int, int, int]
    theme: Theme | None = None
    scene_cfg: Mapping | None = None
    family: Mapping | None = None  # spell id -> fire | lightning | holy | basic


def make_style(
    scene_cfg: Mapping, theme: Theme | None = None, cfg: Mapping | None = None
) -> SceneStyle:
    """Build fonts and colors from `render.scenes`; call after `pygame.init()`."""
    family = None
    if cfg is not None:
        family = cfg["render"]["projectiles"].get("family", {})
    return SceneStyle(
        title_font=pygame.font.Font(None, int(scene_cfg["title_px"])),
        text_font=pygame.font.Font(None, int(scene_cfg["text_px"])),
        text_rgb=rgb(scene_cfg["text_rgb"]),
        dim_rgb=rgb(scene_cfg["dim_rgb"]),
        theme=theme,
        scene_cfg=scene_cfg,
        family=family,
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


def stat_lines(p: PlayerView) -> list[tuple[str, str]]:
    """(label, value) for each stat key present, in a fixed order."""
    out = []
    for key, label, fmt in STAT_LABELS:
        if key in p.stats:
            try:
                out.append((label, fmt.format(float(p.stats[key]))))
            except (TypeError, ValueError):
                continue
    return out


def headline(view: GameView) -> str:
    """Victory headline: the engine's banner if any, else from `winner_slot`."""
    if view.banner:
        return view.banner
    if view.winner_slot is None:
        return "DRAW"
    return f"{view.players[view.winner_slot].name.upper()} WINS"


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


def family_rgb(style: SceneStyle, spell_id: str) -> tuple[int, int, int]:
    th = style.theme
    assert th is not None
    fam = (style.family or {}).get(spell_id, "basic")
    return th.c.get(fam, th.c["gold"])


def card(surface, style: SceneStyle, rect: pygame.Rect, edge=None, hi: bool = False) -> None:
    th = style.theme
    assert th is not None
    color = th.c["card_hi"] if hi else th.c["card"]
    surface.blit(th.panel(rect.w, rect.h, color, 225, edge), rect.topleft)


def draw_scene(surface, view: GameView, style: SceneStyle, t: float = 0.0) -> None:
    from magic_box.render.scenes import boot, loading, lobby, victory

    drawers = {
        "boot": boot.draw,
        "lobby": lobby.draw,
        "loading": loading.draw,
        "victory": victory.draw,
    }
    drawer = drawers.get(view.scene)
    if drawer is not None:
        drawer(surface, view, style, t)
