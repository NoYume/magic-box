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


def test_draw_parry_flash_riposte_and_blade_wave():
    import dataclasses

    from magic_box.core.contracts import ProjectileView

    w = Window(CFG, headless=True)
    try:
        states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
        plain = make_view()
        knight = dataclasses.replace(
            plain.players[0], can_parry=True, riposte_s=1.0, parry_flash_s=0.5
        )
        wave = ProjectileView("riposte", 1, (300.0, 200.0), 0.9, True)
        incoming = ProjectileView("fireball", 0, (600.0, 200.0), 0.9, True)
        view = dataclasses.replace(
            plain, players=(knight, plain.players[1]), projectiles=(wave, incoming)
        )
        w.draw(plain, frame, {s.slot: s for s in states}, fps=60.0)
        before = w.screen.copy()
        w.draw(view, frame, {s.slot: s for s in states}, fps=60.0)
        center = (480, 1080 // 3 + 80)
        assert tuple(w.screen.get_at(center)) != tuple(before.get_at(center))
    finally:
        w.close()
