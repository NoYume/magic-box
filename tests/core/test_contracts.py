import json

import pytest

from magic_box.core.contracts import (
    RELEASE_KINDS,
    Action,
    GameEvent,
    ProjectileView,
    Push,
    SpellView,
    VoiceConfig,
    VoiceEvent,
)
from magic_box.core.serde import from_json, to_json
from tests.factories import make_state, make_view

ROUND_TRIP = [
    make_state(),
    make_state(
        slot=1,
        push=Push("L", 2.5, (100.0, 200.0)),
        pose_flags=frozenset({"hands_up", "hands_together"}),
    ),
    VoiceEvent(
        slot=0, t=1.0, kind="incantation", text="embers burn", spell_id="fireball", match_score=91.5
    ),
    VoiceEvent(slot=1, t=2.0, kind="transcript", text="priya", spell_id=None, match_score=0.0),
    Action(kind="push", slot=0, t=3.0, push=Push("R", 3.0, (1.0, 2.0)), dist=1.9),
    Action(kind="charge", slot=1, t=3.5, spell_id="bolt", match_score=88.0),
    GameEvent(t=4.0, kind="hit", slot=1, data={"spell_id": "fireball", "damage": 18.0}),
    VoiceConfig(
        mode="incantation",
        incantations={0: {"fireball": "embers burn"}, 1: {"bolt": "storm strike"}},
    ),
    make_view(),
    make_view(projectiles=(ProjectileView("fireball", 1, (640.0, 300.0), 0.5, False),)),
]


@pytest.mark.parametrize("obj", ROUND_TRIP, ids=lambda o: type(o).__name__)
def test_round_trip(obj):
    line = to_json(obj)
    assert "\n" not in line
    assert from_json(line) == obj


def test_envelope_and_sorted_frozenset():
    data = json.loads(to_json(make_state(pose_flags=frozenset({"b", "a"}))))
    assert data["type"] == "PlayerState"
    assert data["data"]["pose_flags"] == ["a", "b"]


def test_unknown_type_rejected():
    with pytest.raises(ValueError):
        from_json('{"type": "Nope", "data": {}}')


@pytest.mark.parametrize("kwargs", [{"slot": 2}, {"zone": "close"}])
def test_player_state_validates(kwargs):
    with pytest.raises(ValueError):
        make_state(**kwargs)


def test_action_kind_validated():
    with pytest.raises(ValueError):
        Action(kind="punch", slot=0, t=0.0)


def test_speech_and_two_hand_actions_round_trip():
    speech = Action("speech", 0, 1.0, text="my name is ada")
    push = Action("push", 1, 2.0, push=Push("R", 2.0, (1.0, 2.0)), two_hand=True, dist=1.8)
    assert from_json(to_json(speech)) == speech and from_json(to_json(push)) == push
    assert Action("push", 0, 0.0).two_hand is False and Action("push", 0, 0.0).text == ""


def test_status_voice_event_is_valid():
    ev = VoiceEvent(0, 1.0, "status", "connected", None, 0.0)
    assert from_json(to_json(ev)) == ev


def test_spell_view_release_default_and_validation():
    assert SpellView("bolt", "Bolt", "x", 20.0, False).release == "push"
    assert SpellView("heal", "Heal", "x", 40.0, True, "hands_together").release == "hands_together"
    with pytest.raises(ValueError, match="release"):
        SpellView("bolt", "Bolt", "x", 20.0, False, "wave")
    assert RELEASE_KINDS == ("push", "two_hand_push", "arm_overhead", "hands_together")
