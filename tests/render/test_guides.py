"""On-screen guidance: side frames and tags, the mic wave, the cast cue (render/guides.py).

Owner: Adetola + Nikhil
"""

import dataclasses
import time
from pathlib import Path

import pygame
import pytest

from magic_box.core.config import load_config
from magic_box.render.guides import CAST_TEXT, level_to_unit, release_icon
from magic_box.render.window import Window
from magic_box.replay.fake_input import FakePlayers
from tests.factories import make_full_view

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


@pytest.fixture
def window():
    w = Window(CFG, headless=True)
    yield w
    w.close()


def drawn(window, view, levels=None):
    window.mic_levels = (lambda: levels) if levels is not None else None
    states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
    now = time.monotonic()
    window.render(view, frame, {s.slot: s for s in states}, now)
    return window.screen


def test_level_to_unit_is_a_db_scale():
    assert level_to_unit(0.0) == 0.0
    assert level_to_unit(10 ** (-60 / 20)) == 0.0
    assert level_to_unit(10 ** (-18 / 20)) == pytest.approx(1.0)
    assert level_to_unit(10 ** (-38 / 20)) == pytest.approx(0.5)
    assert level_to_unit(1.0) == 1.0


@pytest.mark.parametrize("scene", ["lobby", "loading", "fight"])
def test_each_half_gets_its_players_color_and_the_divider_survives(window, scene):
    view = make_full_view(scene)
    if scene == "fight":  # the KO overlay tints the whole screen: check the frame without it
        view = dataclasses.replace(view, events=(), banner=None)
    screen = drawn(window, view)
    th = window.theme
    assert tuple(screen.get_at((2, 500)))[:3] == th.slot_rgb(0)  # P1's outer edge
    assert tuple(screen.get_at((window.width - 3, 500)))[:3] == th.slot_rgb(1)
    if scene == "fight":  # only the fight scene has the gold divider; the frame must not cover it
        assert tuple(screen.get_at((window.width // 2, 540)))[:3] == tuple(
            CFG["render"]["divider_rgb"]
        )


@pytest.mark.parametrize("scene", ["boot", "victory"])
def test_no_sides_on_scenes_where_they_mean_nothing(window, scene):
    screen = drawn(window, make_full_view(scene))
    assert tuple(screen.get_at((2, 500)))[:3] != window.theme.slot_rgb(0)


def test_the_how_to_screen_has_no_side_frame(window):
    view = dataclasses.replace(make_full_view("loading"), howto_s=4.0)
    assert tuple(drawn(window, view).get_at((2, 500)))[:3] != window.theme.slot_rgb(0)


def test_wave_moves_with_the_mic_and_is_absent_without_levels(window):
    quiet = [0.0, 0.0]
    loud = [0.2, 0.2]
    drawn(window, make_full_view("fight"))
    assert not window.guides._has_levels
    start = time.monotonic()
    for i in range(12):  # the wave takes one bar per WAVE_STEP_S
        window.guides.update(loud, start + i * 0.05)
    assert max(window.guides.history[0]) > 0.5
    for i in range(60):
        window.guides.update(quiet, start + 1 + i * 0.05)
    assert max(window.guides.history[0]) == 0.0
    drawn(window, make_full_view("fight"), levels=loud)
    assert window.guides._has_levels


def test_a_charged_spell_shows_how_to_release_it(window):
    view = make_full_view("fight")
    charged = [s for p in view.players for s in p.spells if s.charged]
    assert charged, "the fixture should have a charged spell"
    plain = drawn(window, dataclasses.replace(view, banner=None, events=())).copy()
    uncharged = dataclasses.replace(
        view,
        banner=None,
        events=(),
        players=tuple(
            dataclasses.replace(
                p, spells=tuple(dataclasses.replace(s, charged=False) for s in p.spells)
            )
            for p in view.players
        ),
    )
    quiet = drawn(window, uncharged)
    cue_area = pygame.Rect(30, 70, 440, 100)
    assert pygame.image.tobytes(plain.subsurface(cue_area), "RGB") != pygame.image.tobytes(
        quiet.subsurface(cue_area), "RGB"
    )


@pytest.mark.parametrize("release", sorted(CAST_TEXT))
def test_every_release_has_an_icon(release):
    surface = pygame.Surface((120, 120), pygame.SRCALPHA)
    release_icon(surface, release, pygame.Rect(0, 0, 120, 120), (255, 160, 60), 0.3)
    assert pygame.mask.from_surface(surface).count() > 200
