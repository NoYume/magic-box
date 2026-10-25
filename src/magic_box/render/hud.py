"""Fight HUD: the viewer's panel, the opponent's bar and the round timer (spec section 9).

Owner: Adetola

Per half: the viewer's own panel at the bottom (name, MIC and TRACKED, distance with a zone
meter, basic-attack cooldown, eased HP and mana bars with a damage ghost, the spell list with
costs, incantations and release cues, a charge ring on the charged spell, effect icons), and the
opponent's HP bar at the top with their effects and a "CHARGING" warning. Draws only the
`GameView`; colors and sizes come from `cfg.render.hud` and `cfg.render.theme`.
"""

import math
from collections.abc import Mapping

import pygame

from magic_box.core.contracts import GameView, PlayerView, SpellView
from magic_box.render.layout import Rect
from magic_box.render.style import (
    Theme,
    draw_bar,
    draw_chip,
    draw_effect_icon,
    draw_ring,
    lerp_rgb,
    pretty_id,
    pulse,
    rgb,
)

RELEASE_CUES = {
    "push": "PUSH!",
    "two_hand_push": "TWO-HAND PUSH!",
    "arm_overhead": "RAISE ARM!",
    "hands_together": "HANDS TOGETHER!",
}
EFFECT_LABELS = {"shield": "SHIELD", "empowered": "POWER", "mana_slow": "MANA-", "slow": "SLOW"}
LEFT_COL_W = 300
DIST_MIN_M, DIST_MAX_M = 0.8, 3.5  # zone meter span


def release_cue(release: str) -> str:
    return RELEASE_CUES.get(release, release.upper() + "!")


def spell_line(spell: SpellView) -> str:
    if spell.charged:
        return f"{spell.name}  CHARGED: {release_cue(spell.release)}"
    return f'{spell.name}: "{spell.incantation}"'


def name_line(me: PlayerView) -> str:
    return f"{me.name} · {me.class_id} · {'MIC OK' if me.mic_ok else 'MIC OFF'}"


def affordable(me: PlayerView, spell: SpellView) -> bool:
    return spell.charged or me.mana + 1e-6 >= spell.cost


def charged_spell(me: PlayerView) -> SpellView | None:
    return next((s for s in me.spells if s.charged), None)


def frac(value: float, maximum: float) -> float:
    return max(0.0, min(1.0, value / maximum)) if maximum > 0 else 0.0


class BarAnim:
    """Eases a shown fraction toward its target and keeps a ghost of recent damage."""

    def __init__(self) -> None:
        self.shown: float | None = None
        self.ghost = 0.0
        self.hold = 0.0
        self.target = 0.0

    def update(
        self, target: float, dt: float, ease: float, hold_s: float, ghost_rate: float
    ) -> None:
        if self.shown is None:
            self.shown = self.ghost = self.target = target
            return
        if target < self.target - 1e-6:
            self.ghost = max(self.ghost, self.shown)
            self.hold = hold_s
        self.target = target
        self.shown += (target - self.shown) * (1.0 - math.exp(-ease * dt))
        if self.hold > 0:
            self.hold -= dt
        else:
            self.ghost += (self.shown - self.ghost) * (1.0 - math.exp(-ghost_rate * dt))
        if self.ghost < self.shown:
            self.ghost = self.shown


class Hud:
    """Stateful HUD drawer: owns the bar animations; call `update` once per drawn frame."""

    def __init__(self, cfg: Mapping, theme: Theme) -> None:
        self.theme = theme
        self.h = cfg["render"]["hud"]
        game = cfg.get("game", {})
        self.charge_window_s = float(game.get("charge_window_s", 3.0))
        self.cooldown_max_s = float(game.get("basic_attack_cooldown_s", 0.8))
        zones = cfg.get("perception", {}).get("zones", {})
        self.danger_max_m = float(zones.get("danger_max_m", 1.6))
        self.far_min_m = float(zones.get("far_min_m", 2.4))
        self.hp = (BarAnim(), BarAnim())
        self.mana = (BarAnim(), BarAnim())
        self.zone_rgb = {k: rgb(v) for k, v in self.h["zone_rgb"].items()}
        self.effect_rgb = {k: rgb(v) for k, v in self.h["effect_rgb"].items()}
        self.c = {
            k: rgb(self.h[k])
            for k in (
                "hp_rgb",
                "hp_low_rgb",
                "ghost_rgb",
                "mana_rgb",
                "bar_back_rgb",
                "charge_rgb",
                "cooldown_rgb",
            )
        }

    # -- animation --------------------------------------------------------

    def update(self, view: GameView, dt: float) -> None:
        h = self.h
        for p in view.players:
            self.hp[p.slot].update(
                frac(p.hp, p.hp_max), dt, h["ease_per_s"], h["ghost_hold_s"], h["ghost_per_s"]
            )
            self.mana[p.slot].update(frac(p.mana, p.mana_max), dt, h["ease_per_s"], 0.0, 50.0)

    def _hp_fracs(self, p: PlayerView) -> tuple[float, float]:
        anim = self.hp[p.slot]
        if anim.shown is None:
            f = frac(p.hp, p.hp_max)
            return f, f
        return anim.shown, anim.ghost

    def _hp_color(self, shown: float, t: float) -> tuple[int, int, int]:
        if shown > self.h["low_hp_frac"]:
            return self.c["hp_rgb"]
        pulse_ = pulse(t, 10.0)
        return lerp_rgb(self.c["hp_low_rgb"], self.theme.c["white"], 0.35 * pulse_)

    def _bar(self, surface, rect, frac_, fill, back, ghost_frac=0.0, ghost=None, radius=8) -> None:
        c = self.theme.c
        draw_bar(
            surface, rect, frac_, fill, back, ghost_frac, ghost, radius, c["black"], c["white"]
        )

    # -- viewer panel -----------------------------------------------------

    def draw_panel(self, surface, rect: Rect, me: PlayerView, t: float) -> None:
        th, c = self.theme, self.theme.c
        pad = int(self.h["pad_px"])
        surface.blit(
            th.panel(rect.w, rect.h, c["panel"], edge=th.slot_rgb(me.slot)), (rect.x, rect.y)
        )
        x, y = rect.x + pad, rect.y + pad
        col_w = LEFT_COL_W - 2 * pad
        th.blit_text(
            surface,
            th.fit_text(me.name, "big", col_w),
            "big",
            th.slot_rgb(me.slot),
            "topleft",
            (x, y),
        )
        chip = draw_chip(
            surface,
            th,
            "MIC OK" if me.mic_ok else "MIC OFF",
            "tiny",
            (x, y + 46),
            c["ok"] if me.mic_ok else c["bad"],
        )
        draw_chip(
            surface,
            th,
            "TRACKED" if me.tracking_ok else "LOST",
            "tiny",
            (chip.right + 8, y + 46),
            c["ok"] if me.tracking_ok else c["bad"],
        )
        self._draw_distance(surface, x, y + 86, col_w, me)
        self._draw_cooldown(surface, x, rect.y + rect.h - pad - 40, col_w, me)
        rx = rect.x + LEFT_COL_W
        rw = rect.w - LEFT_COL_W - pad
        self._draw_bars(surface, rx, rect.y + pad, rw, me, t)
        row_h = int(self.h["spell_row_h_px"])
        sy = rect.y + pad + int(self.h["hp_bar_h_px"]) + int(self.h["mana_bar_h_px"]) + 18
        for spell in me.spells[:3]:
            self._draw_spell(surface, pygame.Rect(rx, sy, rw, row_h - 4), me, spell, t)
            sy += row_h
        self.draw_effects(surface, (rect.x + 4, rect.y - 8), me.effects, "bottomleft")

    def _draw_bars(self, surface, x: int, y: int, w: int, me: PlayerView, t: float) -> None:
        th, c = self.theme, self.c
        hp_h, mana_h = int(self.h["hp_bar_h_px"]), int(self.h["mana_bar_h_px"])
        shown, ghost = self._hp_fracs(me)
        hp_rect = pygame.Rect(x, y, w, hp_h)
        self._bar(
            surface,
            hp_rect,
            shown,
            self._hp_color(shown, t),
            c["bar_back_rgb"],
            ghost,
            c["ghost_rgb"],
        )
        th.blit_text(
            surface,
            f"HP {math.ceil(me.hp)}",
            "text",
            th.c["text"],
            "midleft",
            (x + 12, hp_rect.centery),
        )
        mana = self.mana[me.slot].shown
        mana = frac(me.mana, me.mana_max) if mana is None else mana
        mana_rect = pygame.Rect(x, y + hp_h + 6, w, mana_h)
        self._bar(surface, mana_rect, mana, c["mana_rgb"], c["bar_back_rgb"], radius=6)
        th.blit_text(
            surface,
            f"MANA {int(me.mana)}",
            "tiny",
            th.c["text"],
            "midleft",
            (x + 12, mana_rect.centery),
        )

    def _draw_distance(self, surface, x: int, y: int, w: int, me: PlayerView) -> None:
        th = self.theme
        zc = self.zone_rgb.get(me.zone, th.c["text"])
        dist = f"{me.dist:.1f} m" if me.dist > 0 else "-- m"
        r = th.blit_text(surface, dist, "huge", th.c["text"], "topleft", (x, y))
        th.blit_text(
            surface, me.zone.upper(), "small", zc, "bottomleft", (r.right + 12, r.bottom - 8)
        )
        # zone meter: three equal segments, marker placed piecewise-linearly by distance
        my, mh = r.bottom + 8, 18
        seg_w = w // 3
        for i, zone in enumerate(("danger", "neutral", "far")):
            col = self.zone_rgb[zone]
            if zone != me.zone:
                col = lerp_rgb(col, th.c["black"], 0.6)
            pygame.draw.rect(surface, col, (x + i * seg_w, my, seg_w - 3, mh), border_radius=5)
        if me.dist > 0:
            mx = x + self._zone_pos(me.dist) * (3 * seg_w - 3)
            pygame.draw.polygon(
                surface,
                th.c["text"],
                [(mx, my + mh + 2), (mx - 9, my + mh + 14), (mx + 9, my + mh + 14)],
            )
            pygame.draw.line(surface, th.c["text"], (mx, my - 3), (mx, my + mh + 2), 3)

    def _zone_pos(self, dist: float) -> float:
        edges = (DIST_MIN_M, self.danger_max_m, self.far_min_m, DIST_MAX_M)
        dist = max(edges[0], min(edges[-1], dist))
        for i in range(3):
            lo, hi = edges[i], edges[i + 1]
            if dist <= hi or i == 2:
                return (i + (dist - lo) / max(hi - lo, 1e-6)) / 3.0
        return 1.0

    def _draw_cooldown(self, surface, x: int, y: int, w: int, me: PlayerView) -> None:
        th, c = self.theme, self.c
        ready = me.cooldown_s <= 0
        label = "BASIC PUSH READY" if ready else f"BASIC PUSH {me.cooldown_s:.1f}s"
        th.blit_text(
            surface, label, "tiny", th.c["ok"] if ready else th.c["dim"], "topleft", (x, y)
        )
        f = 1.0 if ready else 1.0 - frac(me.cooldown_s, self.cooldown_max_s)
        self._bar(
            surface,
            pygame.Rect(x, y + 22, w, 12),
            f,
            th.c["ok"] if ready else c["cooldown_rgb"],
            c["bar_back_rgb"],
            radius=4,
        )

    def _draw_spell(
        self, surface, row: pygame.Rect, me: PlayerView, spell: SpellView, t: float
    ) -> None:
        th, c = self.theme, self.theme.c
        can = affordable(me, spell)
        cx, cy = row.x + 26, row.centery
        tx = row.x + 60
        max_w = row.right - tx - 8
        if spell.charged:
            edge = lerp_rgb(self.c["charge_rgb"], c["white"], pulse(t, 8.0) * 0.5)
            surface.blit(th.panel(row.w, row.h, c["card_hi"], 230, edge), row.topleft)
            ring = frac(me.charge_s, self.charge_window_s) if me.charge_s > 0 else 1.0
            draw_ring(surface, (cx, cy), 24, 7, ring, self.c["charge_rgb"], c["faint"])
            secs = f"{me.charge_s:.0f}" if me.charge_s > 0 else ""
            if secs:
                th.blit_text(surface, secs, "tiny", c["text"], "center", (cx, cy))
            name = th.blit_text(
                surface,
                spell.name.upper(),
                "tiny",
                self.c["charge_rgb"],
                "topleft",
                (tx, row.y + 3),
            )
            th.blit_text(surface, "CHARGED", "tiny", c["dim"], "bottomleft", (tx, row.bottom - 3))
            cue = release_cue(spell.release)
            cue_x = max(name.right, tx + th.font("tiny").size("CHARGED")[0]) + 16
            fits = [f for f in ("huge", "big") if th.font(f).size(cue)[0] <= row.right - cue_x - 10]
            font = fits[0] if fits else "text"
            th.blit_text(surface, cue, font, c["text"], "midleft", (cue_x, row.centery + 2))
            return
        badge = self.c["mana_rgb"] if can else c["faint"]
        pygame.draw.circle(surface, badge, (cx, cy), 22)
        pygame.draw.circle(surface, c["black"], (cx, cy), 22, 2)
        th.blit_text(
            surface,
            f"{spell.cost:.0f}",
            "small",
            c["text"] if can else c["dim"],
            "center",
            (cx, cy + 1),
            shadow=False,
        )
        name_rgb = c["gold"] if can else c["faint"]
        name = th.blit_text(surface, spell.name, "tiny", name_rgb, "topleft", (tx, row.y))
        cue = "then " + release_cue(spell.release)
        th.blit_text(
            surface,
            cue,
            "tiny",
            c["dim"] if can else c["faint"],
            "topleft",
            (name.right + 10, row.y),
        )
        inc = spell.incantation or "…"
        quoted = f"“{inc}”"
        font = "text" if th.font("text").size(quoted)[0] <= max_w else "small"
        th.blit_text(
            surface,
            th.fit_text(quoted, font, max_w),
            font,
            c["text"] if can else c["faint"],
            "bottomleft",
            (tx, row.bottom + 2),
        )

    # -- effects, enemy bar, timer -----------------------------------------

    def draw_effects(self, surface, pos, effects, anchor: str = "topleft") -> None:
        th = self.theme
        size = int(self.h["effect_icon_px"])
        x, y = pos
        if anchor == "bottomleft":
            y -= size
        for e in effects[:4]:
            col = self.effect_rgb.get(e.kind, th.c["gold"])
            w = size + 96
            surface.blit(th.panel(w, size, th.c["panel"], 190), (x, y))
            draw_effect_icon(
                surface,
                e.kind,
                (x + size // 2, y + size // 2),
                size - 6,
                col,
                th.c["icon_bg"],
                th.c["bad"],
            )
            th.blit_text(
                surface,
                EFFECT_LABELS.get(e.kind, e.kind.upper()),
                "tiny",
                col,
                "topleft",
                (x + size + 4, y + 2),
            )
            th.blit_text(
                surface,
                f"{e.remaining_s:.1f}s",
                "tiny",
                th.c["text"],
                "bottomleft",
                (x + size + 4, y + size - 1),
            )
            x += w + 8

    def draw_enemy(self, surface, bar: Rect, enemy: PlayerView, limit_x: int, t: float) -> None:
        th, c = self.theme, self.theme.c
        h = int(self.h["enemy_bar_h_px"])
        back = pygame.Rect(bar.x - 6, bar.y - 6, bar.w + 12, h + 12)
        surface.blit(
            th.panel(back.w, back.h, c["panel"], 200, th.slot_rgb(enemy.slot)), back.topleft
        )
        rect = pygame.Rect(bar.x, bar.y, bar.w, h)
        shown, ghost = self._hp_fracs(enemy)
        self._bar(
            surface,
            rect,
            shown,
            self._hp_color(shown, t),
            self.c["bar_back_rgb"],
            ghost,
            self.c["ghost_rgb"],
        )
        name = th.fit_text(enemy.name, "small", bar.w - 110)
        th.blit_text(surface, name, "small", c["text"], "midleft", (rect.x + 10, rect.centery))
        th.blit_text(
            surface,
            f"{math.ceil(enemy.hp)}",
            "small",
            c["text"],
            "midright",
            (rect.right - 10, rect.centery),
        )
        y = back.bottom + 6
        spell = charged_spell(enemy)
        if spell is not None:
            col = lerp_rgb(c["bad"], c["white"], 0.4 * pulse(t, 12.0))
            text = th.fit_text(f"CHARGING {spell.name.upper()}!", "text", limit_x - bar.x)
            r = th.blit_text(surface, text, "text", col, "topleft", (bar.x, y))
            y = r.bottom + 6
        if enemy.effects:
            self.draw_effects(surface, (bar.x, y), enemy.effects)

    def draw_timer(self, surface, center_x: int, timer_s: float | None, t: float) -> None:
        if timer_s is None:
            return
        th, c = self.theme, self.theme.c
        low = timer_s <= float(self.h["timer_low_s"])
        w, h = 124, 58
        edge = c["bad"] if low else c["panel_edge"]
        surface.blit(th.panel(w, h, c["panel"], 230, edge), (center_x - w // 2, 0))
        col = c["text"]
        if low:
            col = lerp_rgb(c["bad"], c["white"], pulse(t, 9.0))
        th.blit_text(
            surface, f"{math.ceil(max(0.0, timer_s))}", "big", col, "center", (center_x, h // 2 + 2)
        )


def class_label(p: PlayerView, classes) -> str:
    """Display name of `p.class_id` from `GameView.classes`, else a prettified id."""
    for cv in classes:
        if cv.id == p.class_id:
            return cv.name
    return pretty_id(p.class_id)
