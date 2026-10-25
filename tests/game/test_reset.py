"""Back to the lobby from the end screen ("main menu") or any scene (the operator's key)."""

import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config, validate
from magic_box.core.contracts import Action
from magic_box.game.engine import Engine
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
DT = 0.05
UP = frozenset({"hands_up"})


def _states(flags=frozenset()):
    return {s: make_state(s, pose_flags=flags) for s in (0, 1)}


def _to(e, scene):
    """Step until `scene`, raising hands in the lobby; returns the time."""
    e.provide_check("camera", True)
    t = 0.0
    for _ in range(4000):
        view, _ = e.step([], _states(UP if view_scene(e) == "lobby" else frozenset()), t)
        if view.scene == "loading":
            e.provide_incantations({0: {}, 1: {}})
        if view.scene == scene:
            return t
        t += DT
    raise AssertionError(f"never reached {scene}")


def view_scene(e):
    return e._scenes.scene


def _ko(e, t):
    e._match.players[1].hp = 0.0  # the next hit is a KO; simplest: end by time instead
    e._match.time_left = 0.0
    while e.step([], _states(), t)[0].scene != "victory":
        t += DT
    return t


@pytest.mark.parametrize("said", ["Main menu!", "let's play again", "reset", "REMATCH"])
def test_saying_main_menu_on_the_end_screen_goes_to_the_lobby(said):
    e = Engine(copy.deepcopy(CFG))
    e.step([Action("speech", 0, 0.0, text="my name is Ada, holy")], _states(), 0.0)
    t = _ko(e, _to(e, "fight"))
    view, _ = e.step([Action("speech", 1, t, text=said)], _states(), t + DT)
    assert view.scene == "lobby"
    assert view.winner_slot is None


def test_other_victory_speech_does_not_leave():
    e = Engine(copy.deepcopy(CFG))
    t = _ko(e, _to(e, "fight"))
    view, _ = e.step([Action("speech", 1, t, text="good game")], _states(), t + DT)
    assert view.scene == "victory"


def test_reset_key_from_the_fight_keeps_names_and_needs_hands_lowered():
    e = Engine(copy.deepcopy(CFG))
    t = _to(e, "fight")
    names = [p.name for p in e.step([], _states(), t)[0].players]
    for _ in range(20):  # both hands already up (debounced) when the operator resets
        t += DT
        e.step([], _states(UP), t)
    e.request_lobby()
    view, _ = e.step([], _states(UP), t + DT)
    assert view.scene == "lobby" and [p.name for p in view.players] == names
    for i in range(20):  # hands still up from before the reset: no new match
        view, _ = e.step([], _states(UP), t + (2 + i) * DT)
    assert view.scene == "lobby"


def test_reset_in_the_lobby_or_boot_is_ignored():
    e = Engine(copy.deepcopy(CFG))
    e.request_lobby()
    assert e.step([], _states(), 0.0)[0].scene == "boot"


def test_menu_words_are_validated():
    cfg = copy.deepcopy(CFG)
    cfg["game"]["menu_words"] = "main menu"
    assert any("game.menu_words" in p for p in validate(cfg))
