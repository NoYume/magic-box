import json

import pytest

from magic_box.core.contracts import (
    Action,
    GameEvent,
    ProjectileView,
    Push,
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
