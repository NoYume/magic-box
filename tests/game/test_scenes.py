from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.game.scenes import SceneMachine, parse_name

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
G = CFG["game"]


def test_scene_transitions():
    sm = SceneMachine(CFG, now=0.0)
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
        ("It's Zoë", "Zoë"),
        ("call me maximilian the great", "Maximilian T"),
        ("   ", None),
        ("my name is", None),
        ("ada's", "Ada's"),
        ("'", None),
        ("my name is -", None),
    ],
)
def test_parse_name(text, name):
    assert parse_name(text, 12) == name
