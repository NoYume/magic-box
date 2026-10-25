"""Shared render style: theme colors and fonts, a text cache, glow sprites and small widgets.

Owner: Adetola

Everything here is built once and cached, so the 60 fps path allocates little: text renders are
keyed by (text, font, color), panels by size and color, glow sprites by radius step and color.
"""

import bisect
import math
from collections.abc import Iterable, Mapping
from pathlib import Path

import numpy as np
import pygame

RGB = tuple[int, int, int]
SCALE_STEP = 0.02  # pop and grow animations snap to this, so their frames are cached
SCALE_CACHE_MAX = 64
REPO_ROOT = Path(__file__).resolve().parents[3]  # src/magic_box/render/style.py -> repo


def rgb(value) -> RGB:
    return (int(value[0]), int(value[1]), int(value[2]))


def lerp_rgb(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def to_display(surf: pygame.Surface, alpha: bool) -> pygame.Surface:
    """Convert to the display's pixel format (much faster blits) once a video mode is set."""
    if pygame.display.get_init() and pygame.display.get_surface() is not None:
        return surf.convert_alpha() if alpha else surf.convert()
    return surf


def wrap_text(text: str, font, max_w: int) -> list[str]:
    """Greedy word wrap to `max_w` pixels (a single over-long word stays on its own line)."""
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


def display_font_path(name: str | None) -> str | None:
    """Resolve `render.theme.display_font` against the repo root; None if unset or missing."""
    if not name:
        return None
    path = Path(name)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return str(path) if path.is_file() else None


def pulse(t: float, speed: float, steps: int = 8) -> float:
    """0..1 sine pulse, quantized to `steps` levels so pulsing text stays in the text cache."""
    return round((0.5 + 0.5 * math.sin(t * speed)) * steps) / steps


def pretty_id(class_id: str) -> str:
    """`fire_mage` -> `Fire Mage` (fallback when no ClassView names it)."""
    return class_id.replace("_", " ").title()


class Theme:
    """Fonts, colors and caches from `cfg.render.theme`. Build after `pygame.init()`."""

    def __init__(self, render_cfg: Mapping) -> None:
        t = render_cfg["theme"]
        self.c: dict[str, RGB] = {name: rgb(v) for name, v in t["colors"].items()}
        self.fonts: dict[str, pygame.font.Font] = {
            name: pygame.font.Font(None, int(px)) for name, px in t["font_px"].items()
        }
        self.shadow_px = int(t["shadow_px"])
        self.panel_alpha = int(t["panel_alpha"])
        self.radius = int(t["radius_px"])
        self._cache_max = int(t["text_cache_max"])
        self._text: dict[tuple, pygame.Surface] = {}
        self._panels: dict[tuple, pygame.Surface] = {}
        self._glows: dict[tuple, pygame.Surface] = {}
        self._sized_fonts: dict[tuple, pygame.font.Font] = {}
        self.display_path = display_font_path(t.get("display_font"))
        self.title_px: dict[str, int] = {k: int(v) for k, v in t["title_px"].items()}
        self.glow_steps = glow_steps(render_cfg["projectiles"])
        self._scaled: dict[tuple, tuple[pygame.Surface, pygame.Surface]] = {}
        self.stars: Mapping = t["stars"]

    def slot_rgb(self, slot: int | None) -> RGB:
        if slot is None:
            return self.c["gold"]
        return self.c["p1"] if slot == 0 else self.c["p2"]

    def font(self, name: str) -> pygame.font.Font:
        return self.fonts[name]

    def font_px(self, px: int, display: bool = False) -> pygame.font.Font:
        """The default font at `px`, or the display font (titles, banners) if `display`."""
        path = self.display_path if display else None
        key = (px, path)
        font = self._sized_fonts.get(key)
        if font is None:
            font = self._sized_fonts[key] = pygame.font.Font(path, px)
        return font

    def text(
        self, text: str, font: str | pygame.font.Font, color: RGB, shadow: bool = True
    ) -> pygame.Surface:
        """Rendered text (with a drop shadow for reading over the camera), cached."""
        f = self.fonts[font] if isinstance(font, str) else font
        key = (text, id(f), color, shadow)
        surf = self._text.get(key)
        if surf is None:
            if len(self._text) >= self._cache_max:
                del self._text[next(iter(self._text))]  # evict the oldest entry
            fg = f.render(text, True, color)
            if shadow and self.shadow_px > 0:
                off = self.shadow_px
                bg = f.render(text, True, self.c["shadow"])
                surf = pygame.Surface(
                    (fg.get_width() + off, fg.get_height() + off), pygame.SRCALPHA
                )
                surf.blit(bg, (off, off))
                surf.blit(fg, (0, 0))
            else:
                surf = fg
            surf = to_display(surf, alpha=True)
            self._text[key] = surf
        return surf

    def blit_text(
        self,
        surface: pygame.Surface,
        text: str,
        font: str | pygame.font.Font,
        color: RGB,
        anchor: str,
        pos: tuple[float, float],
        shadow: bool = True,
    ) -> pygame.Rect:
        img = self.text(text, font, color, shadow)
        rect = img.get_rect(**{anchor: (round(pos[0]), round(pos[1]))})
        surface.blit(img, rect)
        return rect

    def scaled(self, img: pygame.Surface, scale: float) -> pygame.Surface:
        """`img` smoothscaled by `scale` (quantized to SCALE_STEP), cached; `img` itself at 1.0."""
        q = round(scale / SCALE_STEP) * SCALE_STEP
        if abs(q - 1.0) < 1e-9:
            return img
        key = (id(img), round(q, 6))
        hit = self._scaled.get(key)
        if hit is not None and hit[0] is img:
            return hit[1]
        if len(self._scaled) >= SCALE_CACHE_MAX:
            del self._scaled[next(iter(self._scaled))]
        size = (max(1, round(img.get_width() * q)), max(1, round(img.get_height() * q)))
        out = pygame.transform.smoothscale(img, size)
        self._scaled[key] = (img, out)
        return out

    def fit_lines(
        self, text: str, fonts: tuple[str, ...], max_w: int, max_h: int, max_lines: int
    ) -> tuple[str, list[str]]:
        """The first (largest) font in `fonts` whose wrapped lines fit `max_w` x `max_h` in at
        most `max_lines` lines. Only if none fits: the last font, cut with an ellipsis."""
        for name in fonts:
            f = self.fonts[name]
            lines = wrap_text(text, f, max_w)
            if (
                len(lines) <= max_lines
                and len(lines) * f.get_linesize() <= max_h
                and all(f.size(line)[0] <= max_w for line in lines)
            ):
                return name, lines
        name = fonts[-1]
        f = self.fonts[name]
        n = max(1, min(max_lines, max_h // max(1, f.get_linesize())))
        lines = wrap_text(text, f, max_w)
        if len(lines) > n:
            lines = lines[: n - 1] + [" ".join(lines[n - 1 :])]
        return name, [self.fit_text(line, name, max_w) for line in lines]

    def fit_text(self, text: str, font: str, max_w: int) -> str:
        """Clip `text` with an ellipsis so it fits `max_w` pixels."""
        f = self.fonts[font]
        if f.size(text)[0] <= max_w:
            return text
        while text and f.size(text + "…")[0] > max_w:
            text = text[:-1]
        return text + "…"

    def panel(
        self, w: int, h: int, color: RGB, alpha: int | None = None, edge: RGB | None = None
    ) -> pygame.Surface:
        """A translucent rounded panel, cached by size and color."""
        a = self.panel_alpha if alpha is None else alpha
        key = (w, h, color, a, edge)
        surf = self._panels.get(key)
        if surf is None:
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(surf, (*color, a), (0, 0, w, h), border_radius=self.radius)
            if edge is not None:
                pygame.draw.rect(surf, (*edge, 255), (0, 0, w, h), 3, border_radius=self.radius)
            surf = to_display(surf, alpha=True)
            self._panels[key] = surf
        return surf

    def glow_step(self, radius: float) -> int:
        """The cached radius for `radius`: the next step up, clamped to `glow_max_px`."""
        i = bisect.bisect_left(self.glow_steps, radius)
        return self.glow_steps[min(i, len(self.glow_steps) - 1)]

    def glow(self, radius: float, color: RGB, core: bool = True) -> pygame.Surface:
        """An additive radial glow (black outside), cached per radius step (`glow_steps`).

        A color is a tint of the cached gray falloff (copy + multiply) with the white core added
        on top. `prewarm` builds every tint the game uses at startup, so the frame path only
        reads the cache.
        """
        r = self.glow_step(radius)
        key = (r, color, core)
        surf = self._glows.get(key)
        if surf is None:
            surf = self._gray(r, "fall").copy()
            surf.fill(color, special_flags=pygame.BLEND_RGB_MULT)
            if core:
                surf.blit(self._gray(r, "core"), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            self._glows[key] = surf
        return surf

    def _gray(self, r: int, part: str) -> pygame.Surface:
        key = (r, part)
        surf = self._glows.get(key)
        if surf is None:
            surf = to_display(make_glow_part(r, part), alpha=False)
            self._glows[key] = surf
        return surf

    def prewarm(self, tints: Iterable[tuple[RGB, bool, float]] = ()) -> None:
        """Build the gray parts for every step, then each (color, core) tint up to its radius."""
        for r in self.glow_steps:
            self._gray(r, "fall")
            self._gray(r, "core")
        for color, core, max_radius in tints:
            top = self.glow_step(max_radius)
            for r in self.glow_steps:
                if r > top:
                    break
                self.glow(r, color, core)

    def glow_bytes(self) -> int:
        return sum(s.get_width() * s.get_height() * s.get_bytesize() for s in self._glows.values())


def glow_steps(proj_cfg: Mapping) -> list[int]:
    """Glow radius steps: every `glow_step_px` up to `glow_big_from_px`, then every
    `glow_big_step_px`, ending at `glow_max_px`."""
    small, big = int(proj_cfg["glow_step_px"]), int(proj_cfg["glow_big_step_px"])
    big_from, top = int(proj_cfg["glow_big_from_px"]), int(proj_cfg["glow_max_px"])
    steps = list(range(small, min(big_from, top) + 1, small))
    r = steps[-1] if steps else 0
    while r + big < top:
        r += big
        steps.append(r)
    if not steps or steps[-1] < top:
        steps.append(top)
    return steps


HEADLINE_GLOW_DIM = 0.55  # victory headline glow: the winner's color, darkened


def headline_glow_rgb(theme: Theme, color: RGB) -> RGB:
    return lerp_rgb(color, theme.c["black"], HEADLINE_GLOW_DIM)


def make_glow_part(radius: int, part: str) -> pygame.Surface:
    """Gray radial falloff (`fall`) or the hot white center (`core`), black outside."""
    size = radius * 2
    axis = np.arange(size, dtype=np.float32) - radius + 0.5
    d = np.sqrt(axis[:, None] ** 2 + axis[None, :] ** 2) / radius
    if part == "core":
        a = np.clip(1.0 - d * 3.0, 0.0, 1.0) ** 2
    else:
        a = np.clip(1.0 - d, 0.0, 1.0) ** 2
    px = np.repeat((a * 255.0).astype(np.uint8)[:, :, None], 3, axis=2)
    surf = pygame.Surface((size, size))
    pygame.surfarray.blit_array(surf, px)
    return surf


def blit_glow(
    surface: pygame.Surface, theme: Theme, center, radius: float, color: RGB, core: bool = True
) -> None:
    if radius < 2:
        return
    g = theme.glow(radius, color, core)
    surface.blit(
        g,
        g.get_rect(center=(round(center[0]), round(center[1]))),
        special_flags=pygame.BLEND_RGB_ADD,
    )


def draw_bar(
    surface: pygame.Surface,
    rect: pygame.Rect,
    frac: float,
    fill: RGB,
    back: RGB,
    ghost_frac: float = 0.0,
    ghost: RGB | None = None,
    radius: int = 8,
    outline: RGB | None = None,
    shine: RGB | None = None,
) -> None:
    """A rounded bar: back, a ghost segment up to `ghost_frac`, then the fill up to `frac`."""
    pygame.draw.rect(surface, back, rect, border_radius=radius)
    frac = max(0.0, min(1.0, frac))
    if ghost is not None and ghost_frac > frac:
        gw = round(rect.w * min(1.0, ghost_frac))
        pygame.draw.rect(surface, ghost, (rect.x, rect.y, gw, rect.h), border_radius=radius)
    fw = round(rect.w * frac)
    if fw > 0:
        pygame.draw.rect(surface, fill, (rect.x, rect.y, fw, rect.h), border_radius=radius)
        hi = lerp_rgb(fill, shine if shine is not None else fill, 0.35)
        pygame.draw.rect(
            surface,
            hi,
            (rect.x + 4, rect.y + 3, max(0, fw - 8), max(2, rect.h // 5)),
            border_radius=3,
        )
    if outline is not None:
        pygame.draw.rect(surface, outline, rect, 2, border_radius=radius)


def ring_points(center, r_out: float, r_in: float, frac: float, steps: int = 40) -> list:
    """Polygon for a ring segment starting at 12 o'clock, clockwise, `frac` of a turn."""
    frac = max(0.0, min(1.0, frac))
    n = max(2, int(steps * frac) + 1)
    cx, cy = center
    outer, inner = [], []
    for i in range(n):
        a = -math.pi / 2 + 2 * math.pi * frac * i / (n - 1)
        ca, sa = math.cos(a), math.sin(a)
        outer.append((cx + r_out * ca, cy + r_out * sa))
        inner.append((cx + r_in * ca, cy + r_in * sa))
    return outer + inner[::-1]


def draw_ring(surface, center, radius: float, width: float, frac: float, color: RGB, back: RGB):
    pygame.draw.circle(
        surface, back, (round(center[0]), round(center[1])), round(radius), round(width)
    )
    if frac >= 0.999:
        pygame.draw.circle(
            surface, color, (round(center[0]), round(center[1])), round(radius), round(width)
        )
    elif frac > 0.005:
        pygame.draw.polygon(surface, color, ring_points(center, radius, radius - width, frac))


def draw_mark(surface, center, size: int, ok: bool, color: RGB, width: int = 6) -> None:
    """A check mark (ok) or a cross, drawn with lines (the default font has no glyphs)."""
    cx, cy = center
    s = size / 2
    if ok:
        pts = [(cx - s * 0.8, cy), (cx - s * 0.2, cy + s * 0.6), (cx + s * 0.9, cy - s * 0.7)]
        pygame.draw.lines(surface, color, False, pts, width)
    else:
        pygame.draw.line(
            surface, color, (cx - s * 0.7, cy - s * 0.7), (cx + s * 0.7, cy + s * 0.7), width
        )
        pygame.draw.line(
            surface, color, (cx - s * 0.7, cy + s * 0.7), (cx + s * 0.7, cy - s * 0.7), width
        )


def draw_chip(
    surface, theme: Theme, text: str, font: str, pos, color: RGB, anchor: str = "topleft"
) -> pygame.Rect:
    """A pill-shaped status chip (MIC OK, TRACKED, ...)."""
    ink = theme.c["ink"] if sum(color) > 380 else theme.c["text"]
    img = theme.text(text, font, ink, shadow=False)
    w, h = img.get_width() + 24, img.get_height() + 10
    rect = pygame.Rect(0, 0, w, h)
    setattr(rect, anchor, (round(pos[0]), round(pos[1])))
    pygame.draw.rect(surface, color, rect, border_radius=h // 2)
    surface.blit(img, img.get_rect(center=rect.center))
    return rect


def draw_effect_icon(
    surface, kind: str, center, size: int, color: RGB, bg: RGB, slash: RGB
) -> None:
    """Procedural icon per effect kind: shield, star (empowered), drop (mana_slow), hourglass."""
    cx, cy = center
    s = size / 2
    pygame.draw.circle(surface, bg, (round(cx), round(cy)), round(s))
    pygame.draw.circle(surface, color, (round(cx), round(cy)), round(s), 3)
    i = s * 0.62
    if kind == "shield":
        pts = [
            (cx - i, cy - i * 0.8),
            (cx, cy - i),
            (cx + i, cy - i * 0.8),
            (cx + i * 0.8, cy + i * 0.3),
            (cx, cy + i),
            (cx - i * 0.8, cy + i * 0.3),
        ]
        pygame.draw.polygon(surface, color, pts)
    elif kind == "empowered":
        pts = []
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            r = i if k % 2 == 0 else i * 0.45
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        pygame.draw.polygon(surface, color, pts)
    elif kind == "mana_slow":
        pts = [(cx, cy - i), (cx + i * 0.65, cy + i * 0.25), (cx - i * 0.65, cy + i * 0.25)]
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.circle(surface, color, (round(cx), round(cy + i * 0.3)), round(i * 0.62))
        pygame.draw.line(surface, slash, (cx - i, cy + i), (cx + i, cy - i), 4)
    else:  # slow: hourglass
        pts = [
            (cx - i * 0.7, cy - i),
            (cx + i * 0.7, cy - i),
            (cx - i * 0.7, cy + i),
            (cx + i * 0.7, cy + i),
        ]
        pygame.draw.polygon(surface, color, pts)


def vertical_gradient(w: int, h: int, top: RGB, bottom: RGB) -> pygame.Surface:
    col = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    px = (
        np.array(top, np.float32)[None, :] * (1 - col) + np.array(bottom, np.float32)[None, :] * col
    )
    arr = np.repeat(px[None, :, :], w, axis=0)  # (w, h, 3)
    surf = pygame.Surface((w, h))
    pygame.surfarray.blit_array(surf, arr.astype(np.uint8))
    return surf


def make_background(w: int, h: int, theme: Theme, seed: int = 7) -> pygame.Surface:
    """Scene backdrop: vertical gradient, a soft vignette and a few faint stars."""
    surf = vertical_gradient(w, h, theme.c["bg_top"], theme.c["bg_bottom"])
    stars = theme.stars
    lo, hi = (int(v) for v in stars["brightness"])
    rng = np.random.default_rng(seed)
    for _ in range(int(stars["count"])):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        b = int(rng.integers(lo, hi))
        surf.set_at((x, y), (b, b, min(255, b + int(stars["blue"]))))
    return surf


def edge_glow(surface, rect, color: RGB, k: float, tint: float = 0.0) -> None:
    """Additive glow along the inside edges of `rect` (three bands), plus an optional tint.

    Built from `fill(..., BLEND_RGB_ADD)` strips, which is far cheaper than an alpha vignette.
    """
    x, y, w, h = rect
    if tint > 0:
        c = (int(color[0] * k * tint), int(color[1] * k * tint), int(color[2] * k * tint))
        surface.fill(c, (x, y, w, h), special_flags=pygame.BLEND_RGB_ADD)
    for width, share in ((90, 0.09), (44, 0.14), (16, 0.28)):
        c = (int(color[0] * k * share), int(color[1] * k * share), int(color[2] * k * share))
        if c == (0, 0, 0):
            continue
        for strip in (
            (x, y, w, width),
            (x, y + h - width, w, width),
            (x, y + width, width, h - 2 * width),
            (x + w - width, y + width, width, h - 2 * width),
        ):
            surface.fill(c, strip, special_flags=pygame.BLEND_RGB_ADD)
