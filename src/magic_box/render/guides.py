"""On-screen guidance drawn over the scenes: whose side is whose, a live mic wave, and the cast cue.

Owner: Adetola + Nikhil

Three things players asked for, drawn by `Window.render` after the scene, so no scene file changes:

- **Side:** every half gets a border in its player's color and a tag "YOU · P1 · LEFT SIDE" (each
  half shows the *opponent*, so this says whose screen it is). Lobby, loading and fight only.
- **Mic wave:** bars that move while the player speaks, from `Window.mic_levels` (the voice
  process's per-slot RMS). Nothing is drawn when no levels are wired (fake mode, replay).
- **Cast cue:** when a spell is charged, a pulsing pictogram and plain words for its release
  (punch toward the screen, both hands, one arm overhead, hands together).

The sizes and thresholds below are module constants for now; they belong in `render.guides` in
config.yaml with the rest of the render tunables.
"""

import math
from collections import deque
from collections.abc import Sequence

import pygame

from magic_box.core.contracts import GameView, PlayerView
from magic_box.render.layout import HalfLayout
from magic_box.render.style import Theme, draw_chip

SIDE_NAMES = ("LEFT SIDE", "RIGHT SIDE")
CAST_TEXT = {
    "push": "PUNCH TOWARD THE SCREEN!",
    "two_hand_push": "PUNCH WITH BOTH HANDS!",
    "arm_overhead": "RAISE ONE ARM OVERHEAD!",
    "hands_together": "BRING YOUR HANDS TOGETHER!",
}
SCENES_WITH_SIDES = ("lobby", "loading", "fight")
BORDER_PX = 6
TAG_Y = 14
WAVE_BARS = 36
WAVE_STEP_S = 0.04  # one new bar every 40 ms
WAVE_QUIET_DB = -58.0  # at or below: no bar
WAVE_LOUD_DB = -18.0  # at or above: a full bar
WAVE_SPEAKING = 0.18  # bars above this are drawn in the player's color
CUE_SIZE = (580, 112)
CUE_Y = 120  # below the enemy bar and its effect icons
WAVE_W = 190
LOADING_TAG_Y = 90
LOADING_MARGIN_PX = 67  # the loading cards sit 7% in from the half edge


def level_to_unit(level: float) -> float:
    """RMS (0..1 of full scale) as a 0..1 bar height, on a dB scale."""
    if level <= 0:
        return 0.0
    db = 20.0 * math.log10(level)
    return min(1.0, max(0.0, (db - WAVE_QUIET_DB) / (WAVE_LOUD_DB - WAVE_QUIET_DB)))


def release_icon(surface: pygame.Surface, release: str, rect: pygame.Rect, rgb, now: float) -> None:
    """A small animated picture of how a spell is released, inside `rect`."""
    s = min(rect.w, rect.h)
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    cx, cy = rect.w // 2, rect.h // 2
    body = (*rgb, 255)

    def fist(x: float, y: float, r: float, rings: bool) -> None:
        if rings:  # rings growing outward: the fist coming at you
            for k in range(3):
                phase = (now * 1.3 + k / 3) % 1.0
                pygame.draw.circle(
                    layer, (*rgb, int(210 * (1 - phase))), (x, y), r * (1.1 + 1.6 * phase), 3
                )
        pygame.draw.rect(
            layer, body, pygame.Rect(x - r, y - r, 2 * r, 2 * r), border_radius=int(r * 0.6)
        )
        pygame.draw.rect(
            layer,
            (255, 255, 255, 120),
            pygame.Rect(x - r * 0.6, y - r * 0.55, r * 1.2, r * 0.35),
            0,
        )

    if release == "two_hand_push":
        fist(cx - s * 0.24, cy, s * 0.14, True)
        fist(cx + s * 0.24, cy, s * 0.14, True)
    elif release == "arm_overhead":
        bob = math.sin(now * 5) * s * 0.03
        pygame.draw.circle(layer, body, (cx, cy - s * 0.12), s * 0.11)  # head
        pygame.draw.line(layer, body, (cx, cy - s * 0.01), (cx, cy + s * 0.34), 5)  # body
        pygame.draw.line(layer, body, (cx, cy + s * 0.04), (cx - s * 0.2, cy + s * 0.2), 5)
        pygame.draw.line(layer, body, (cx, cy + s * 0.04), (cx + s * 0.18, cy - s * 0.3 + bob), 5)
        fist(cx + s * 0.18, cy - s * 0.38 + bob, s * 0.09, False)
    elif release == "hands_together":
        gap = s * (0.08 + 0.16 * (0.5 + 0.5 * math.sin(now * 5)))
        fist(cx - gap - s * 0.1, cy, s * 0.11, False)
        fist(cx + gap + s * 0.1, cy, s * 0.11, False)
        if gap < s * 0.12:
            pygame.draw.circle(layer, (255, 255, 255, 200), (cx, cy), s * 0.07)
    else:  # push
        fist(cx, cy, s * 0.17, True)
    surface.blit(layer, rect.topleft)


class Guides:
    """Overlay state: the mic wave history for both players."""

    def __init__(self, theme: Theme, layout: Sequence[HalfLayout]) -> None:
        self.th = theme
        self.layout = layout
        self.history = [deque([0.0] * WAVE_BARS, maxlen=WAVE_BARS) for _ in (0, 1)]
        self._last_bar = 0.0
        self._has_levels = False

    def update(self, levels: Sequence[float] | None, now: float) -> None:
        self._has_levels = levels is not None
        if levels is None or now - self._last_bar < WAVE_STEP_S:
            return
        self._last_bar = now
        for slot in (0, 1):
            self.history[slot].append(level_to_unit(float(levels[slot])))

    def draw(self, surface: pygame.Surface, view: GameView, now: float) -> None:
        if view.scene not in SCENES_WITH_SIDES or view.howto_s is not None:
            return
        for half in self.layout:
            slot = half.viewer_slot
            rgb = self.th.slot_rgb(slot)
            self._frame(surface, half, rgb)
            # Outer corners (P1 top-left, P2 top-right) keep clear of the round timer in the
            # middle; loading puts the tag on the class-label row, clear of its title.
            if view.scene == "loading":
                pos = (half.half.x + half.half.w - LOADING_MARGIN_PX, LOADING_TAG_Y)
                anchor = "topright"
            elif slot == 0:
                pos, anchor = (half.half.x + 18, TAG_Y), "topleft"
            else:
                pos, anchor = (half.half.x + half.half.w - 18, TAG_Y), "topright"
            side = SIDE_NAMES[slot]
            if view.scene == "fight":  # the corners are tight there
                side = side.removesuffix(" SIDE")
            tag = draw_chip(
                surface, self.th, f"YOU · P{slot + 1} · {side}", "small", pos, rgb, anchor
            )
            if view.scene == "fight":
                if self._has_levels:  # under the self-view: your own mic
                    sv = half.selfview
                    self._wave(surface, pygame.Rect(sv.x, sv.y + sv.h + 8, sv.w, 36), slot, rgb)
                self._cast_cue(surface, half, view.players[slot], now)
            elif self._has_levels:  # beside the tag, on the side facing the middle
                x = tag.right + 10 if anchor == "topleft" else tag.x - 10 - WAVE_W
                self._wave(surface, pygame.Rect(x, tag.y, WAVE_W, tag.h), slot, rgb)

    def _frame(self, surface: pygame.Surface, half: HalfLayout, rgb) -> None:
        """A bar of the player's color on the top, bottom and outer edge (the inner edge keeps
        the gold divider)."""
        r = half.half
        pygame.draw.rect(surface, rgb, (r.x, r.y, r.w, BORDER_PX))
        pygame.draw.rect(surface, rgb, (r.x, r.y + r.h - BORDER_PX, r.w, BORDER_PX))
        edge_x = r.x if half.viewer_slot == 0 else r.x + r.w - BORDER_PX
        pygame.draw.rect(surface, rgb, (edge_x, r.y, BORDER_PX, r.h))

    def _wave(
        self, surface: pygame.Surface, box: pygame.Rect, slot: int, rgb, label: str = "MIC"
    ) -> None:
        th = self.th
        surface.blit(th.panel(box.w, box.h, th.c["panel"], 200), box.topleft)
        left = box.x + 10
        if label:
            left = (
                th.blit_text(
                    surface, label, "tiny", th.c["dim"], "midleft", (left, box.centery)
                ).right
                + 8
            )
        bars = self.history[slot]
        width = box.right - 10 - left
        step = width / len(bars)
        for i, v in enumerate(bars):
            h = max(3, int(v * (box.h - 8)))
            color = rgb if v > WAVE_SPEAKING else th.c["faint"]
            pygame.draw.rect(
                surface,
                color,
                pygame.Rect(left + i * step, box.centery - h // 2, max(2, step - 2), h),
                border_radius=2,
            )

    def _cast_cue(
        self, surface: pygame.Surface, half: HalfLayout, me: PlayerView, now: float
    ) -> None:
        spell = next((s for s in me.spells if s.charged), None)
        if spell is None:
            return
        th, c = self.th, self.th.c
        rgb = th.slot_rgb(me.slot)
        w, h = CUE_SIZE
        box = pygame.Rect(half.half.x + 18, CUE_Y, w, h)
        throb = 0.5 + 0.5 * math.sin(now * 8)
        surface.blit(th.panel(w, h, c["panel"], 215, edge=c["gold"]), box.topleft)
        release_icon(
            surface, spell.release, pygame.Rect(box.x + 8, box.y + 8, 96, h - 16), rgb, now
        )
        text_color = tuple(round(g + (255 - g) * throb) for g in c["gold"])
        x = box.x + 116
        th.blit_text(
            surface,
            f"{spell.name.upper()} IS CHARGED",
            "small",
            c["dim"],
            "topleft",
            (x, box.y + 14),
        )
        label = CAST_TEXT.get(spell.release, spell.release.upper() + "!")
        th.blit_text(
            surface,
            th.fit_text(label, "text", w - 128),
            "text",
            text_color,
            "topleft",
            (x, box.y + 50),
        )
