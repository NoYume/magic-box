from pathlib import Path

from magic_box.core.config import load_config
from magic_box.render.window import Window
from magic_box.replay.fake_input import FakePlayers
from tests.factories import make_view

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
