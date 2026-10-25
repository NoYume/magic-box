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


def test_victory_draws_a_draw_without_banner():
    w = Window(CFG, headless=True)
    try:
        w.render(make_full_view("victory", banner=None, winner_slot=None), None, {}, 1.0)
    finally:
        w.close()
