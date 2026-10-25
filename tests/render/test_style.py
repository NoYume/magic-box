import copy
from pathlib import Path

import pygame
import pytest

from magic_box.core.config import load_config
from magic_box.render.style import Theme, lerp_rgb, pretty_id, pulse, ring_points

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


@pytest.fixture
def theme():
    pygame.init()
    cfg = copy.deepcopy(CFG)
    cfg["render"]["theme"]["text_cache_max"] = 8
    yield Theme(cfg["render"])
    pygame.quit()


def test_text_cache_reuses_and_stays_bounded(theme):
    a = theme.text("HP 72", "text", (255, 255, 255))
    assert theme.text("HP 72", "text", (255, 255, 255)) is a
    for i in range(50):
        theme.text(f"n{i}", "small", (200, 200, 200))
    assert len(theme._text) <= 8


def test_glow_is_cached_per_radius_step(theme):
    assert theme.glow(17, (255, 0, 0)) is theme.glow(23, (255, 0, 0))
    g = theme.glow(17, (255, 0, 0), core=False)
    assert g.get_size() == (48, 48)
    center, edge = g.get_at((24, 24)), g.get_at((0, 0))
    assert center[0] > 200 and center[1] == 0 and tuple(edge)[:3] == (0, 0, 0)
    assert theme.glow(17, (255, 0, 0)).get_at((24, 24))[1] > 200  # white core on top
    theme.prewarm([((0, 255, 0), False, 30)])
    assert (theme.glow_steps[-1], "fall") in theme._glows and (8, "core") in theme._glows
    assert (32, (0, 255, 0), False) in theme._glows and (40, (0, 255, 0), False) not in theme._glows


def test_scaled_images_are_cached_per_quantized_scale(theme):
    img = theme.text("K.O.!", "huge", (255, 0, 0))
    a = theme.scaled(img, 1.2)
    assert a is theme.scaled(img, 1.2) and a is theme.scaled(img, 1.201)
    assert a.get_width() == round(img.get_width() * 1.2)
    assert theme.scaled(img, 1.0) is img
    for i in range(200):
        theme.scaled(img, 1.0 + (i + 1) * 0.05)
    assert len(theme._scaled) <= 64


def test_glow_steps_are_bounded_by_glow_max(theme):
    steps = theme.glow_steps
    assert steps == sorted(steps) and steps[-1] == CFG["render"]["projectiles"]["glow_max_px"]
    assert theme.glow_step(10_000) == steps[-1] and theme.glow_step(1) == steps[0]
    assert all(theme.glow_step(r) >= min(r, steps[-1]) for r in range(1, 400))


def test_display_font_resolves_and_falls_back(theme):
    from magic_box.render.style import display_font_path

    assert theme.display_path is not None and Path(theme.display_path).is_file()
    assert display_font_path("assets/fonts/missing.ttf") is None
    assert display_font_path(None) is None
    assert theme.font_px(40, display=True) is not theme.font_px(40)
    assert (Path(theme.display_path).parent / "CinzelDecorative-OFL.txt").is_file()


def test_helpers():
    assert pretty_id("holy_knight") == "Holy Knight"
    assert lerp_rgb((0, 0, 0), (200, 100, 50), 0.5) == (100, 50, 25)
    assert all(pulse(t / 10, 3.0) in {i / 8 for i in range(9)} for t in range(100))
    pts = ring_points((0, 0), 10, 5, 0.25)
    assert pts[0] == pytest.approx((0.0, -10.0)) and len(pts) >= 4


def test_fit_lines_is_cached_per_text_fonts_and_box(theme, monkeypatch):
    import magic_box.render.style as style

    calls = []
    real = style.wrap_text
    monkeypatch.setattr(style, "wrap_text", lambda *a: calls.append(a) or real(*a))
    fonts = ("big", "text", "small", "tiny")
    first = theme.fit_lines("embers of the forty acres burn", fonts, 400, 120, 2)
    n = len(calls)
    assert theme.fit_lines("embers of the forty acres burn", fonts, 400, 120, 2) == first
    assert len(calls) == n  # second call: no re-wrapping
    theme.fit_lines("embers of the forty acres burn", fonts, 300, 120, 2)
    assert len(calls) > n  # another box is fitted again
    for i in range(style.FIT_CACHE_MAX + 10):
        theme.fit_lines(f"words {i}", fonts, 400, 120, 2)
    assert len(theme._fits) <= style.FIT_CACHE_MAX
