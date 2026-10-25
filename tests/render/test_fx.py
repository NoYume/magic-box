from pathlib import Path

import pygame
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import GameEvent
from magic_box.render.fx import Fx, affected_slot, event_target
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


def test_affected_slot_prefers_target_then_caster():
    assert affected_slot(GameEvent(0.0, "buff", 1, {"target": 0})) == 0
    assert affected_slot(GameEvent(0.0, "heal", 1, {})) == 1
    assert affected_slot(GameEvent(0.0, "buff", None, {})) is None


def test_zero_damage_hit_does_not_flash_or_shake(fx):
    fx.update(make_view(events=(GameEvent(0.0, "hit", 1, {"target": 0, "damage": 0}),)), 0.0)
    assert fx.halves[0].shake_left == 0 and fx.halves[0].flash_left == 0 and not fx.texts


def test_debuff_glows_on_the_target_half_in_the_effect_color(fx):
    ev = GameEvent(0.0, "buff", 1, {"spell_id": "static_field", "target": 0})
    fx.update(make_view(events=(ev,)), 0.0)
    assert fx.halves[0].glow_left > 0 and fx.halves[1].glow_left == 0
    assert fx.halves[0].glow_rgb == tuple(CFG["render"]["hud"]["effect_rgb"]["mana_slow"])
    assert len(fx.texts) == 1


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


def test_ko_banner_covers_the_engine_ko_hold(fx):
    """The engine freezes the fight for game.ko_hold_s after a KO. The K.O. banner is what
    says why, so it lasts until victory (and no longer: FX are cleared when the fight ends)."""
    hold = CFG["game"]["ko_hold_s"]
    assert CFG["render"]["fx"]["ko_s"] <= hold
    fx.update(make_view(events=(GameEvent(0.0, "ko", None, {"winner": 0}),)), 0.0)
    for _ in range(round(hold * 60) - 1):
        fx.update(make_view(), 1 / 60)
    assert fx.ko_left > 0


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


def test_particle_motion_and_glow_times_come_from_config():
    import copy

    cfg = copy.deepcopy(CFG)
    f = cfg["render"]["fx"]
    f["particle_gravity_px"], f["speed_px"]["hit"], f["glow_heal_s"] = 0.0, 0.0, 0.9
    pygame.init()
    try:
        fx = Fx(cfg, Theme(cfg["render"]), compute_layout(1920, 1080, cfg["render"]))
        fx.on_event(GameEvent(0.0, "hit", 0, {"target": 1}), make_view())
        assert fx.particles and all(p.gravity == 0 and p.vx == 0 for p in fx.particles)
        fx.on_event(GameEvent(0.0, "heal", 0, {"target": 0, "amount": 5}), make_view())
        assert fx.halves[0].glow_left == 0.9
        assert max(p.size for p in fx.particles) <= max(f["burst_size_px"])
    finally:
        pygame.quit()


def test_fx_clears_when_the_scene_leaves_fight(fx):
    ko = (
        GameEvent(0.0, "hit", 0, {"target": 1, "damage": 30}),
        GameEvent(0.0, "ko", None, {"winner": 0}),
    )
    fx.update(make_view(events=ko), 0.016)
    assert fx.ko_left > 0 and fx.particles and fx.texts and fx.halves[1].shake_left > 0
    fx.update(make_view(scene="victory"), 0.016)
    assert fx.ko_left == 0 and not fx.particles and not fx.texts
    assert all(h.shake_left == 0 and h.flash_left == 0 and h.glow_left == 0 for h in fx.halves)


def test_events_outside_the_fight_spawn_nothing(fx):
    fx.update(make_full_view("victory"), 0.016)
    assert fx.ko_left == 0 and not fx.particles and not fx.texts
