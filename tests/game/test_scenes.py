import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.game.scenes import Hold, SceneMachine, parse_lobby_speech, parse_name

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
G = CFG["game"]


def update(sm, t, ready=False, inc=False, over=False, camera=False):
    return sm.update(t, both_ready=ready, incantations_ready=inc, match_over=over, camera_ok=camera)


def test_boot_waits_for_min_time_and_camera():
    sm = SceneMachine(CFG)
    assert sm.scene == "boot" and sm.elapsed(100.0) == 0.0
    assert not update(sm, 100.0, camera=True)  # stamps entered_at
    assert not update(sm, 100.0 + G["boot_min_s"] - 0.01, camera=True)
    assert not update(sm, 100.0 + G["boot_min_s"], camera=False)
    assert update(sm, 100.0 + G["boot_min_s"] + 0.05, camera=True)
    assert sm.scene == "lobby"


def test_boot_gives_up_at_max_time_and_first_lobby_is_armed():
    sm = SceneMachine(CFG, now=0.0)
    assert not update(sm, G["boot_max_s"] - 0.01, ready=True)
    assert update(sm, G["boot_max_s"], ready=True)
    assert sm.scene == "lobby"
    assert update(sm, G["boot_max_s"] + 0.05, ready=True)  # hands already up: armed
    assert sm.scene == "loading"


def test_hold_debounces_both_edges():
    h = Hold(0.3)
    assert not h.update(True, 0.0)
    assert not h.update(False, 0.1)  # flicker: the hold restarts
    assert not h.update(True, 0.2)
    assert not h.update(True, 0.49)
    assert h.update(True, 0.5)
    assert h.update(False, 0.6)  # one dropped frame doesn't lower it
    assert h.update(True, 0.65)
    assert h.update(False, 0.7)
    assert not h.update(False, 1.0)
    instant = Hold(0.0)
    assert instant.update(True, 0.0) and not instant.update(False, 0.0)


def test_scene_transitions():
    sm = SceneMachine(CFG, now=0.0)
    assert update(sm, G["boot_min_s"], camera=True)
    assert sm.scene == "lobby"
    assert not sm.update(1.0, both_ready=False, incantations_ready=False, match_over=False)
    assert sm.update(1.0, both_ready=True, incantations_ready=False, match_over=False)
    assert sm.scene == "loading"
    assert not sm.update(
        1.0 + G["loading_min_s"] - 0.01, both_ready=False, incantations_ready=True, match_over=False
    )
    assert not sm.update(
        1.0 + G["loading_min_s"], both_ready=False, incantations_ready=False, match_over=False
    )
    assert sm.update(
        1.0 + G["loading_min_s"], both_ready=False, incantations_ready=True, match_over=False
    )
    assert sm.scene == "fight"
    assert sm.update(50.0, both_ready=False, incantations_ready=True, match_over=True)
    assert sm.scene == "victory"
    assert not sm.update(
        50.0 + G["victory_min_s"] - 0.1, both_ready=True, incantations_ready=True, match_over=True
    )
    assert sm.update(
        50.0 + G["victory_min_s"], both_ready=True, incantations_ready=True, match_over=True
    )
    assert sm.scene == "lobby"


def test_victory_times_out_to_lobby():
    sm = SceneMachine(CFG, now=0.0)
    sm.scene, sm.entered_at = "victory", 0.0
    assert sm.update(
        G["victory_max_s"], both_ready=False, incantations_ready=False, match_over=True
    )
    assert sm.scene == "lobby"


def test_hands_held_from_victory_wait_in_lobby_until_lowered():
    sm = SceneMachine(CFG, now=0.0)
    sm.scene, sm.entered_at = "victory", 0.0
    t = G["victory_min_s"]
    assert sm.update(t, both_ready=True, incantations_ready=False, match_over=True)
    assert sm.scene == "lobby"
    for i in range(1, 100):  # hands still up from victory: no new match
        assert not sm.update(
            t + 0.05 * i, both_ready=True, incantations_ready=False, match_over=False
        )
    assert sm.scene == "lobby"
    assert not sm.update(t + 5.0, both_ready=False, incantations_ready=False, match_over=False)
    assert sm.update(t + 5.05, both_ready=True, incantations_ready=False, match_over=False)
    assert sm.scene == "loading"


@pytest.mark.parametrize(
    "text,name",
    [
        ("my name is ada lovelace!", "Ada Lovelace"),
        ("I'm Bo.", "Bo"),
        ("my name's Cy", "Cy"),
        ("hi my name is ada", "Ada"),
        ("hi, my name is Ada", "Ada"),
        ("call me Ada Lovelace", "Ada Lovelace"),
        ("call me ada lovelace the third", "Ada Lovelace"),
        ("call me maximilian bartholomew", "Maximilian B"),  # name_max_chars (12)
        ("call me maximilian the great", "Maximilian"),
        ("ok so i am bo", "Bo"),
        ("Bob", "Bob"),
        ("Ada Lovelace", "Ada Lovelace"),
        ("ada's", "Ada's"),
        ("Zoë!", "Zoë"),
        ("It's Zoë", None),  # "it's" is no prefix, and a stop word
        ("this is cool", None),
        ("it's working", None),
        ("I'm ready", None),
        ("i am not ready", None),
        ("so what do I do now", None),
        ("Ada Lovelace Byron", None),  # no prefix: 1 or 2 words only
        ("hello", None),
        ("hi", None),
        ("okay", None),
        ("   ", None),
        ("my name is", None),
        ("'", None),
        ("my name is -", None),
        ("myname is ada", None),  # word boundaries
    ],
)
def test_parse_name(text, name):
    assert parse_name(text, CFG) == name


@pytest.mark.parametrize(
    "text,name,class_id",
    [
        ("ada", "Ada", None),
        ("Bob", "Bob", None),
        ("hello", None, None),
        ("I'm ready", None, None),
        ("fire", None, "fire_mage"),
        ("lightning", None, "lightning_mage"),
        ("My name is Ada, fire", "Ada", "fire_mage"),
        ("hi, my name is Ada, fire", "Ada", "fire_mage"),
        ("my name is Ada and I choose lightning", "Ada", "lightning_mage"),
        ("I'm Zoë the holy knight", "Zoë", "holy_knight"),
        ("I want to be a knight", None, "holy_knight"),
        ("I am a fire mage", None, "fire_mage"),
        ("my name is knight", None, "holy_knight"),
        ("fire is my name", None, "fire_mage"),
        ("Ada fire", None, "fire_mage"),  # a keyword is never part of a short-reply name
    ],
)
def test_parse_lobby_speech(text, name, class_id):
    assert parse_lobby_speech(text, CFG) == (name, class_id)


def test_stop_words_come_from_config():
    cfg = copy.deepcopy(CFG)
    cfg["game"]["name_stop_words"] = ["bob"]
    assert parse_name("Bob", cfg) is None
    assert parse_name("hello", cfg) == "Hello"


def test_victory_hands_up_waits_for_the_chronicle():
    sm = SceneMachine(CFG, now=0.0)
    sm.scene, sm.entered_at = "victory", 0.0
    t = G["victory_min_s"] + 1.0
    kw = dict(both_ready=True, incantations_ready=False, match_over=True)
    assert not sm.update(t, chronicle_ready=False, **kw)
    assert sm.update(t, chronicle_ready=True, **kw) and sm.scene == "lobby"
