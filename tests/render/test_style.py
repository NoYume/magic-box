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
    assert theme.glow(17, (255, 0, 0)).get_size() == (48, 48)


def test_helpers():
    assert pretty_id("holy_knight") == "Holy Knight"
    assert lerp_rgb((0, 0, 0), (200, 100, 50), 0.5) == (100, 50, 25)
    assert all(pulse(t / 10, 3.0) in {i / 8 for i in range(9)} for t in range(100))
    pts = ring_points((0, 0), 10, 5, 0.25)
    assert pts[0] == pytest.approx((0.0, -10.0)) and len(pts) >= 4
