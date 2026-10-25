"""Shared render style: theme colors and fonts, a text cache, glow sprites and small widgets.

Owner: Adetola

Everything here is built once and cached, so the 60 fps path allocates little: text renders are
keyed by (text, font, color), panels by size and color, glow sprites by radius step and color.
"""

import math
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pygame

RGB = tuple[int, int, int]
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

    def glow(self, radius: int, color: RGB, core: bool = True) -> pygame.Surface:
        """An additive radial glow (black outside), cached per 8 px radius step."""
        r = max(4, int(math.ceil(radius / 8.0)) * 8)
        key = (r, color, core)
        surf = self._glows.get(key)
        if surf is None:
            surf = make_glow(r, color, core)
            surf = to_display(surf, alpha=False)
            self._glows[key] = surf
        return surf


def make_glow(radius: int, color: RGB, core: bool = True) -> pygame.Surface:
    """Radial glow, with a hot white core if `core`; blit with `BLEND_RGB_ADD`."""
    size = radius * 2
    axis = np.arange(size, dtype=np.float32) - radius + 0.5
    d = np.sqrt(axis[:, None] ** 2 + axis[None, :] ** 2) / radius
    fall = np.clip(1.0 - d, 0.0, 1.0) ** 2
    col = np.array(color, dtype=np.float32)
    px = fall[:, :, None] * col[None, None, :]
    if core:
        px = px + (np.clip(1.0 - d * 3.0, 0.0, 1.0) ** 2)[:, :, None] * 255.0
    surf = pygame.Surface((size, size))
    pygame.surfarray.blit_array(surf, np.clip(px, 0, 255).astype(np.uint8))
    return surf


def blit_glow(
    surface: pygame.Surface, theme: Theme, center, radius: float, color: RGB, core: bool = True
) -> None:
    if radius < 2:
        return
    g = theme.glow(int(radius), color, core)
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
    rng = np.random.default_rng(seed)
    for _ in range(140):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        b = int(rng.integers(40, 140))
        surf.set_at((x, y), (b, b, min(255, b + 40)))
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
