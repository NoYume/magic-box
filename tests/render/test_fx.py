from pathlib import Path

import pygame
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import GameEvent
from magic_box.render.fx import Fx, event_target
from magic_box.render.layout import compute_layout
from magic_box.render.style import Theme
from tests.factories import make_full_events, make_full_view, make_view

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


@pytest.fixture
def fx():
    pygame.init()
    theme = Theme(CFG["render"])
    yield Fx(CFG, theme, compute_layout(1920, 1080, CFG["render"]))
    pygame.quit()


def test_event_target_prefers_data_then_opponent():
    assert event_target(GameEvent(0.0, "hit", 0, {"target": 0})) == 0
    assert event_target(GameEvent(0.0, "hit", 0, {})) == 1
    assert event_target(GameEvent(0.0, "hit", None, {})) is None


def test_particle_and_text_caps_hold(fx):
    events = tuple(make_full_events()) * 30
    fx.update(make_full_view(events=events), 0.016)
    assert len(fx.particles) <= CFG["render"]["fx"]["max_particles"]
    assert len(fx.texts) <= CFG["render"]["fx"]["max_texts"]
    surf = pygame.Surface((1920, 1080))
    fx.draw(surf)
    fx.draw_overlay(surf)


def test_hit_shakes_only_the_target_half(fx):
    fx.update(make_view(events=(GameEvent(0.0, "hit", 0, {"target": 1, "damage": 12}),)), 0.0)
    assert fx.halves[1].shake_left > 0 and fx.halves[0].shake_left == 0
    assert fx.shake_offset(0, 1.0) == (0, 0)
    assert fx.shake_offset(1, 1.0) != (0, 0)
    for _ in range(90):
        fx.update(make_view(), 0.016)
    assert fx.shake_offset(1, 1.0) == (0, 0) and not fx.particles


def test_ko_runs_fx_in_slow_motion(fx):
    assert fx.timescale == 1.0
    fx.update(make_view(events=(GameEvent(0.0, "ko", None, {"winner": 1}),)), 0.0)
    assert fx.timescale == CFG["render"]["fx"]["ko_slowmo"]
    fx.update(make_view(), CFG["render"]["fx"]["ko_s"] + 0.1)
    assert fx.timescale == 1.0


def test_events_with_missing_data_are_ignored_quietly(fx):
    odd = (
        GameEvent(0.0, "hit", None, {}),
        GameEvent(0.0, "hit", 1, {"damage": "lots"}),
        GameEvent(0.0, "dodge", None, {}),
        GameEvent(0.0, "block", None, {}),
        GameEvent(0.0, "heal", 0, {}),
        GameEvent(0.0, "buff", None, {}),
        GameEvent(0.0, "cast", 1, {"spell_id": None}),
        GameEvent(0.0, "match_end", None, {}),
    )
    fx.update(make_view(events=odd), 0.016)
    fx.draw(pygame.Surface((1920, 1080)))
