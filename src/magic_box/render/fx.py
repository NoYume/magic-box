"""Event-driven effects: hit flash and shake, damage numbers, dodge, block, heal, buff, KO.

Owner: Adetola

`Fx.update(view, dt)` reads `GameView.events` (this tick's GameEvents) and spawns effects;
`draw` paints them over the halves, `shake_offset` tells the window how far to shift a half, and
`draw_overlay` paints the KO banner over everything. FX live only in the fight scene: they are
cleared when the scene changes, so the engine holds the fight for the KO (`game.ko_hold_s`).
Particles and floating texts are capped (`render.fx.max_particles`, `max_texts`): the oldest go
first. Event data is read with `.get()` because older recordings and the thin engine carry less.
"""

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pygame

from magic_box.core.contracts import GameEvent, GameView
from magic_box.render.layout import HalfLayout
from magic_box.render.style import RGB, Theme, blit_glow, edge_glow, rgb


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: RGB
    size: float
    gravity: float = 0.0


@dataclass
class FloatText:
    surf: pygame.Surface
    x: float
    y: float
    age: float
    life: float
    rise: float


@dataclass
class HalfFx:
    flash_rgb: RGB | None = None
    flash_left: float = 0.0
    flash_total: float = 1.0
    shake_left: float = 0.0
    glow_rgb: RGB | None = None
    glow_left: float = 0.0
    glow_total: float = 1.0


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


EFFECT_TEXT = {
    "shield": "SHIELD UP!",
    "empowered": "EMPOWERED!",
    "mana_slow": "MANA SLOWED!",
    "slow": "SLOWED!",
}


def affected_slot(e: GameEvent) -> int | None:
    """Heal and buff: the affected player is `data["target"]`, else the caster (`slot`)."""
    target = e.data.get("target") if isinstance(e.data, Mapping) else None
    if target in (0, 1):
        return int(target)
    return e.slot if e.slot in (0, 1) else None


def event_target(e: GameEvent) -> int | None:
    """The slot an event lands on: `data["target"]`, else the opponent of `slot`."""
    target = e.data.get("target") if isinstance(e.data, Mapping) else None
    if target in (0, 1):
        return int(target)
    if e.slot in (0, 1):
        return 1 - e.slot
    return None


class Fx:
    def __init__(
        self, cfg: Mapping, theme: Theme, layout: Sequence[HalfLayout], seed: int = 3
    ) -> None:
        self.f = cfg["render"]["fx"]
        self.theme = theme
        self.layout = tuple(layout)
        self.family = cfg["render"]["projectiles"].get("family", {})
        self.end_y_frac = float(cfg["render"]["projectiles"]["end_y_frac"])
        self.spell_effect = dict(self.f.get("spell_effect", {}))
        self.effect_rgb = {k: rgb(v) for k, v in cfg["render"]["hud"]["effect_rgb"].items()}
        self.max_particles = int(self.f["max_particles"])
        self.max_texts = int(self.f["max_texts"])
        self.particles: list[Particle] = []
        self.texts: list[FloatText] = []
        self.halves = [HalfFx(), HalfFx()]
        self.ko_left = 0.0
        self.ko_rgb = rgb(self.f["ko_rgb"])
        self.rng = random.Random(seed)

    # -- update ---------------------------------------------------------------

    @property
    def timescale(self) -> float:
        return float(self.f["ko_slowmo"]) if self.ko_left > 0 else 1.0

    def clear(self) -> None:
        """Drop every effect (the scene left the fight)."""
        self.particles, self.texts = [], []
        self.halves = [HalfFx(), HalfFx()]
        self.ko_left = 0.0

    def update(self, view: GameView, dt: float) -> None:
        """Spawn this tick's effects and advance them; only the fight scene has FX."""
        if view.scene != "fight":
            if (
                self.ko_left > 0
                or self.particles
                or self.texts
                or any(h.flash_left > 0 or h.shake_left > 0 or h.glow_left > 0 for h in self.halves)
            ):
                self.clear()
            return
        for e in view.events:
            self.on_event(e, view)
        real_dt = dt
        dt *= self.timescale
        self.ko_left = max(0.0, self.ko_left - real_dt)
        for h in self.halves:
            h.flash_left = max(0.0, h.flash_left - dt)
            h.shake_left = max(0.0, h.shake_left - dt)
            h.glow_left = max(0.0, h.glow_left - dt)
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life > 0:
                p.vy += p.gravity * dt
                p.x += p.vx * dt
                p.y += p.vy * dt
                alive.append(p)
        self.particles = alive
        texts = []
        for t in self.texts:
            t.age += dt
            if t.age < t.life:
                texts.append(t)
        self.texts = texts

    def on_event(self, e: GameEvent, view: GameView) -> None:
        f, c = self.f, self.theme.c
        data = e.data if isinstance(e.data, Mapping) else {}
        kind = e.kind
        if kind == "hit":
            target = event_target(e)
            if target is None:
                return
            color = self._spell_rgb(data.get("spell_id"))
            dmg = _num(data.get("damage"))
            if dmg is not None and dmg <= 0:  # e.g. Static Field: its buff event shows the rest
                cx, cy = self._impact_point(target)
                self._burst(cx, cy, color, int(f["burst_count"]) // 2, self._speed("graze"))
                return
            self._flash(target, rgb(f["hit_rgb"]))
            self.halves[target].shake_left = float(f["shake_s"])
            cx, cy = self._impact_point(target)
            self._burst(cx, cy, color, int(f["burst_count"]), self._speed("hit"))
            if dmg is not None:
                hud = self.layout[target].hud
                self._text(
                    f"-{dmg:.0f}", "huge", rgb(f["hit_rgb"]), hud.x + hud.w * 0.55, hud.y - 30
                )
                ox, oy = self._opponent_point(1 - target)
                self._text(f"{dmg:.0f}", "huge", rgb(f["damage_rgb"]), ox, oy)
                self._burst(ox, oy, color, int(f["burst_count"]) // 2, self._speed("hit_side"))
        elif kind == "dodge":
            slot = e.slot if e.slot in (0, 1) else None
            if slot is None:
                return
            cx, cy = self._impact_point(slot)
            self._text("DODGE!", "huge", rgb(f["dodge_rgb"]), cx, cy - 120)
            self._ring(
                cx, cy, rgb(f["dodge_rgb"]), int(f["ring_count"]["dodge"]), self._speed("dodge")
            )
            ox, oy = self._opponent_point(1 - slot)
            self._text("MISS", "big", c["dim"], ox, oy)
        elif kind == "block":
            slot = e.slot if e.slot in (0, 1) else event_target(e)
            if slot is None:
                return
            parry = bool(data.get("parry"))
            col = c["gold"] if parry else rgb(f["block_rgb"])
            self._flash(slot, col)
            cx, cy = self._impact_point(slot)
            self._ring(cx, cy, col, int(f["ring_count"]["block"]), self._speed("block"))
            self._text("PARRIED!" if parry else "BLOCKED!", "huge", col, cx, cy - 120)
            ox, oy = self._opponent_point(1 - slot)
            self._text("PARRIED" if parry else "BLOCKED", "big", col, ox, oy)
        elif kind == "heal":
            slot = affected_slot(e)
            if slot is None:
                return
            col = rgb(f["heal_rgb"])
            hud = self.layout[slot].hud
            self._sparkles(hud.x, hud.y - 40, hud.w, 120, col, int(f["sparkle_count"]))
            amount = next((_num(data.get(k)) for k in ("amount", "hp", "heal") if k in data), None)
            label = f"+{amount:.0f}" if amount is not None else "HEAL"
            self._text(label, "huge", col, hud.x + hud.w * 0.55, hud.y - 30)
            self._glow(slot, col, float(f["glow_heal_s"]))
        elif kind == "buff":
            slot = affected_slot(e)
            if slot is None:
                return
            effect = self._effect_kind(data)
            col = self.effect_rgb.get(effect, rgb(f["buff_rgb"])) if effect else rgb(f["buff_rgb"])
            self._glow(slot, col, float(f["glow_s"]))
            half = self.layout[slot].half
            if effect in EFFECT_TEXT:
                self._text(EFFECT_TEXT[effect], "huge", col, half.x + half.w / 2, half.h * 0.6)
            self._sparkles(
                half.x, half.y + half.h * 0.3, half.w, half.h * 0.5, col, int(f["sparkle_count"])
            )
        elif kind == "cast":
            slot = e.slot if e.slot in (0, 1) else None
            if slot is None:
                return
            self._glow(slot, self._spell_rgb(data.get("spell_id")), float(f["glow_cast_s"]))
        elif kind == "ko":
            self.ko_left = float(f["ko_s"])
            winner = data.get("winner")
            self.ko_rgb = self.theme.slot_rgb(winner) if winner in (0, 1) else rgb(f["ko_rgb"])
            for slot in (0, 1):
                self._flash(slot, c["white"])
        elif kind == "match_start":
            for slot in (0, 1):
                self._glow(slot, c["gold"], float(f["glow_start_s"]))

    def glow_tints(self) -> list[tuple[RGB, bool, float]]:
        """Every particle glow tint (both core styles), for `Theme.prewarm`."""
        c, f = self.theme.c, self.f
        colors = {self._spell_rgb(s) for s in self.family} | {self._spell_rgb(None), c["gold"]}
        colors |= {rgb(f[k]) for k in ("dodge_rgb", "block_rgb", "heal_rgb", "buff_rgb")}
        colors |= set(self.effect_rgb.values())
        top = self.particle_size_max() * 1.6
        return [(col, core, top) for col in sorted(colors) for core in (True, False)]

    def particle_size_max(self) -> float:
        """Largest particle radius at spawn (drawn up to 1.6x that)."""
        f = self.f
        sizes = (*f["burst_size_px"], f["ring_size_px"], *f["sparkle_size_px"])
        return float(max(sizes))

    def _speed(self, kind: str) -> float:
        return float(self.f["speed_px"][kind])

    # -- spawners ---------------------------------------------------------------

    def _effect_kind(self, data: Mapping) -> str | None:
        for key in ("effect", "kind", "effect_kind"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        spell = data.get("spell_id")
        return self.spell_effect.get(spell) if isinstance(spell, str) else None

    def _spell_rgb(self, spell_id) -> RGB:
        fam = self.family.get(spell_id, "basic") if isinstance(spell_id, str) else "basic"
        return self.theme.c.get(fam, self.theme.c["gold"])

    def _impact_point(self, slot: int) -> tuple[float, float]:
        half = self.layout[slot].half
        return half.x + half.w / 2, half.y + self.end_y_frac * half.h

    def _opponent_point(self, slot: int) -> tuple[float, float]:
        """Over the opponent's body on `slot`'s half (where the attacker sees the hit land)."""
        half = self.layout[slot].half
        return half.x + half.w / 2, half.y + half.h * 0.26

    def _flash(self, slot: int, color: RGB) -> None:
        h = self.halves[slot]
        h.flash_rgb, h.flash_left = color, float(self.f["flash_s"])
        h.flash_total = max(h.flash_left, 1e-6)

    def _glow(self, slot: int, color: RGB, seconds: float) -> None:
        h = self.halves[slot]
        h.glow_rgb, h.glow_left, h.glow_total = color, seconds, max(seconds, 1e-6)

    def _add_particles(self, new: list[Particle]) -> None:
        self.particles.extend(new)
        overflow = len(self.particles) - self.max_particles
        if overflow > 0:
            del self.particles[:overflow]

    def _burst(self, x: float, y: float, color: RGB, n: int, speed: float) -> None:
        life = float(self.f["particle_s"])
        r = self.rng
        out = []
        for _ in range(n):
            a = r.uniform(0, 2 * math.pi)
            s = r.uniform(0.3, 1.0) * speed
            out.append(
                Particle(
                    x,
                    y,
                    s * math.cos(a),
                    s * math.sin(a),
                    life * r.uniform(0.5, 1.0),
                    life,
                    color,
                    r.uniform(*self.f["burst_size_px"]),
                    float(self.f["particle_gravity_px"]),
                )
            )
        self._add_particles(out)

    def _ring(self, x: float, y: float, color: RGB, n: int, speed: float) -> None:
        life = float(self.f["particle_s"]) * 0.7
        out = []
        for i in range(n):
            a = 2 * math.pi * i / n
            out.append(
                Particle(
                    x,
                    y,
                    speed * math.cos(a),
                    speed * math.sin(a) * 0.6,
                    life,
                    life,
                    color,
                    float(self.f["ring_size_px"]),
                )
            )
        self._add_particles(out)

    def _sparkles(self, x: float, y: float, w: float, h: float, color: RGB, n: int) -> None:
        life = float(self.f["particle_s"]) * 1.4
        r = self.rng
        drift, rise = float(self.f["sparkle_drift_px"]), self.f["sparkle_rise_px"]
        out = []
        for _ in range(n):
            out.append(
                Particle(
                    x + r.uniform(0, w),
                    y + r.uniform(0, h),
                    r.uniform(-drift, drift),
                    -r.uniform(*rise),
                    life * r.uniform(0.6, 1.0),
                    life,
                    color,
                    r.uniform(*self.f["sparkle_size_px"]),
                )
            )
        self._add_particles(out)

    def _text(self, text: str, font: str, color: RGB, x: float, y: float) -> None:
        surf = self.theme.text(text, font, color).copy()
        self.texts.append(
            FloatText(surf, x, y, 0.0, float(self.f["number_s"]), float(self.f["number_rise_px"]))
        )
        if len(self.texts) > self.max_texts:
            del self.texts[: len(self.texts) - self.max_texts]

    # -- draw -------------------------------------------------------------------

    def shake_offset(self, slot: int, t: float) -> tuple[int, int]:
        h = self.halves[slot]
        if h.shake_left <= 0:
            return (0, 0)
        amp = float(self.f["shake_px"]) * h.shake_left / max(float(self.f["shake_s"]), 1e-6)
        return (round(amp * math.sin(t * 91.0)), round(amp * math.cos(t * 77.0)))

    def draw(self, surface: pygame.Surface) -> None:
        """Flashes and glows per half, then particles and floating numbers."""
        for slot, h in enumerate(self.halves):
            half = self.layout[slot].half.as_tuple()
            if h.glow_left > 0 and h.glow_rgb is not None:
                edge_glow(surface, half, h.glow_rgb, h.glow_left / h.glow_total)
            if h.flash_left > 0 and h.flash_rgb is not None:
                k = h.flash_left / h.flash_total * float(self.f["flash_alpha"]) / 255.0
                edge_glow(surface, half, h.flash_rgb, k * 1.6, tint=0.16)
        for p in self.particles:
            k = p.life / p.max_life
            blit_glow(surface, self.theme, (p.x, p.y), p.size * (0.6 + k), p.color, core=k > 0.5)
        for t in self.texts:
            k = t.age / t.life
            pop = 1.0 + 0.6 * max(0.0, 1.0 - k * 6.0)
            img = self.theme.scaled(t.surf, pop)
            img.set_alpha(round(255 * min(1.0, 2.0 * (1.0 - k))))
            surface.blit(img, img.get_rect(center=(round(t.x), round(t.y - t.rise * k))))

    def draw_overlay(self, surface: pygame.Surface) -> None:
        """Draw one cinematic KO banner across the center of the full screen."""
        if self.ko_left <= 0:
            return
        total = float(self.f["ko_s"])
        k = 1.0 - self.ko_left / max(total, 1e-6)
        w, h = surface.get_size()
        cx, cy = w // 2, h // 2
        alpha = round(float(self.f["ko_back_alpha"]) * min(1.0, k * 5.0))
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((*self.theme.c["black"], alpha))
        surface.blit(veil, (0, 0))

        band_h = round(h * float(self.f["ko_band_h_frac"]))
        band = pygame.Rect(0, cy - band_h // 2, w, band_h)
        band_layer = pygame.Surface((w, band_h), pygame.SRCALPHA)
        band_layer.fill((*self.theme.c["panel"], min(255, alpha + 45)))
        surface.blit(band_layer, band.topleft)
        line_px = round(float(self.f["ko_line_px"]))
        line_alpha = round(255 * min(1.0, k * 12.0))
        line_layer = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in (band.top, band.bottom - line_px):
            pygame.draw.line(line_layer, (*self.ko_rgb, line_alpha), (0, y), (w, y), line_px)
        ornament_r = band_h // 18
        for x in (w // 4, 3 * w // 4):
            points = (
                (x, band.top - ornament_r),
                (x + ornament_r, band.top),
                (x, band.top + ornament_r),
                (x - ornament_r, band.top),
            )
            pygame.draw.polygon(line_layer, (*self.ko_rgb, line_alpha), points)
            points = (
                (x, band.bottom - ornament_r),
                (x + ornament_r, band.bottom),
                (x, band.bottom + ornament_r),
                (x - ornament_r, band.bottom),
            )
            pygame.draw.polygon(line_layer, (*self.ko_rgb, line_alpha), points)
        surface.blit(line_layer, (0, 0))

        font = self.theme.font_px(self.theme.title_px["ko"], display=True)
        glow = self.theme.text("K.O.!", font, self.theme.c["white"])
        base = self.theme.text("K.O.!", font, self.ko_rgb)
        scale = 0.72 + 0.48 * min(1.0, k * 2.0)
        glow_img = self.theme.scaled(glow, scale * 1.04).copy()
        glow_img.set_alpha(round(90 * min(1.0, k * 12.0)))
        img = self.theme.scaled(base, scale).copy()
        img.set_alpha(round(255 * min(1.0, k * 12.0)))
        surface.blit(glow_img, glow_img.get_rect(center=(cx, cy)))
        surface.blit(img, img.get_rect(center=(cx, cy)))
