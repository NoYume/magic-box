import dataclasses
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import ProjectileView
from magic_box.render.window import Window
from magic_box.replay.fake_input import FakePlayers
from tests.factories import make_full_view, make_view

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_draw_fight_view_with_fake_frame():
    w = Window(CFG, headless=True)
    try:
        states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
        w.draw(make_view(), frame, {s.slot: s for s in states}, fps=60.0)
        assert w.screen.get_size() == (1920, 1080)
        assert tuple(w.screen.get_at((960, 540)))[:3] == tuple(CFG["render"]["divider_rgb"])
    finally:
        w.close()


def test_draw_without_frame_or_states_and_pump():
    w = Window(CFG, headless=True)
    try:
        w.draw(make_view(), None, {}, fps=60.0)
        assert w.pump() == (frozenset(), False)
    finally:
        w.close()


def test_all_key_codes_include_arrows_and_function_keys():
    import pygame

    from magic_box.render.window import ALL_KEY_CODES

    assert pygame.K_UP in ALL_KEY_CODES and pygame.K_F1 in ALL_KEY_CODES


def test_draw_with_the_debug_overlay_on():
    w = Window(CFG, headless=True)
    try:
        w.debug = True
        states, frame = FakePlayers(CFG).step(
            frozenset({CFG["keys"]["fake"][0]["push"]}), 0.0, 0.016
        )
        w.draw(make_view(), frame, {s.slot: s for s in states}, fps=60.0, dropped=1)
    finally:
        w.close()


@pytest.mark.parametrize("scene", ["boot", "lobby", "loading", "victory"])
def test_draw_each_scene_with_default_fields(scene):
    w = Window(CFG, headless=True)
    try:
        w.draw(
            make_view(scene=scene, chronicle="A long tale. " * 40, timer_s=2.0), None, {}, fps=60.0
        )
    finally:
        w.close()


def test_draw_fight_with_projectiles():
    w = Window(CFG, headless=True)
    try:
        states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
        view = make_view(projectiles=(ProjectileView("fireball", 0, (480.0, 300.0), 0.5, True),))
        w.draw(view, frame, {s.slot: s for s in states}, fps=60.0)
    finally:
        w.close()


@pytest.mark.parametrize("scene", ["boot", "lobby", "loading", "fight", "victory"])
def test_draw_each_scene_fully_populated(scene):
    w = Window(CFG, headless=True)
    try:
        states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
        smap = {s.slot: s for s in states}
        view = make_full_view(scene)
        quiet = dataclasses.replace(view, events=())
        for i in range(5):
            w.render(view if i == 0 else quiet, frame, smap, 10 + i / 60)
        w.draw(view, frame, smap, fps=60.0)
    finally:
        w.close()


def test_draw_scenes_with_empty_lists_and_long_names():
    w = Window(CFG, headless=True)
    try:
        long = "W" * 40
        for scene in ("boot", "lobby", "loading", "victory", "fight"):
            view = make_full_view(scene, checks=(), classes=(), events=(), chronicle="word " * 400)
            p0 = dataclasses.replace(
                view.players[0], name=long, heard=long * 3, effects=(), stats={}
            )
            w.render(dataclasses.replace(view, players=(p0, view.players[1])), None, {}, 1.0)
    finally:
        w.close()


def test_ko_overlay_and_fx_stop_when_victory_starts():
    from magic_box.core.contracts import GameEvent

    w = Window(CFG, headless=True)
    try:
        ko = (GameEvent(0.0, "hit", 0, {"target": 1, "damage": 30}), GameEvent(0.0, "ko", None, {}))
        w.render(make_full_view("fight", events=ko), None, {}, 1.0)
        assert w.fx.ko_left > 0
        w.render(make_full_view("victory", events=()), None, {}, 1.02)
        assert w.fx.ko_left == 0 and not w.fx.particles
    finally:
        w.close()


def test_glow_tints_are_built_at_startup_and_stay_bounded():
    from magic_box.core.contracts import GameEvent
    from tests.factories import make_full_events

    w = Window(CFG, headless=True)
    try:
        built = len(w.theme._glows)
        assert w.theme.glow_bytes() < 40 * 1024 * 1024
        states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
        smap = {s.slot: s for s in states}
        spells = [*CFG["render"]["projectiles"]["family"], "mystery"]
        n = 0
        for spell in spells:
            for i in range(0, 61, 3):
                p = ProjectileView(spell, i % 2, (480.0, 300.0), i / 60, i > 45)
                hit = GameEvent(0.0, "hit", 0, {"target": 1, "damage": 9, "spell_id": spell})
                events = (hit, *make_full_events()) if i == 60 else ()
                view = make_full_view("fight", projectiles=(p,), events=events)
                w.render(view, frame, smap, 10 + n / 60)
                n += 1
        for scene in ("victory", "lobby", "loading", "boot"):
            w.render(make_full_view(scene, events=()), None, {}, 20 + n / 60)
            n += 1
        assert len(w.theme._glows) == built  # nothing new built on the frame path
    finally:
        w.close()


def test_victory_draws_a_draw_without_banner():
    w = Window(CFG, headless=True)
    try:
        w.render(make_full_view("victory", banner=None, winner_slot=None), None, {}, 1.0)
    finally:
        w.close()


def _hints_drawn(banner, monkeypatch):
    """How many halves draw the STEP INTO VIEW hint (nobody tracked) under `banner`."""
    w = Window(CFG, headless=True)
    calls = []
    monkeypatch.setattr(w, "_step_into_view", lambda half, now: calls.append(half))
    try:
        w.render(make_view(banner=banner), None, {}, 0.0)
    finally:
        w.close()
    return len(calls)


def test_pause_banner_with_its_countdown_replaces_the_step_hint(monkeypatch):
    assert _hints_drawn(None, monkeypatch) == 2
    assert _hints_drawn("STEP INTO VIEW · 12", monkeypatch) == 0


def test_camera_banner_shows_alone_without_the_step_hint(monkeypatch):
    """While perception restarts nobody is tracked; only CAMERA RECONNECTING should show."""
    assert _hints_drawn("CAMERA RECONNECTING", monkeypatch) == 0
    assert _hints_drawn("FIGHT!", monkeypatch) == 2
