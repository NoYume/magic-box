from pathlib import Path

import pytest

from magic_box.ai.incantations import fallback_incantations
from magic_box.core.config import load_config
from magic_box.core.contracts import Action, Push, VoiceEvent
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def _start_fight(engine: Engine) -> None:
    states = {0: make_state(slot=0), 1: make_state(slot=1)}
    ready = [Action(kind="pose", slot=slot, t=0.0, pose="hands_up", dist=2.0) for slot in (0, 1)]
    view, _ = engine.step(ready, states, now=0.0)
    assert view.scene == "loading"
    engine.provide_incantations(fallback_incantations(engine.classes, CFG))
    view, events = engine.step([], states, now=CFG["game"]["loading_s"])
    assert view.scene == "fight"
    assert [event.kind for event in events] == ["match_start"]


def test_engine_runs_original_scene_flow_and_uses_state_in_view():
    engine = Engine(CFG)
    state = make_state(slot=0, zone="danger", root=(0.6, 0.0, 1.2))
    view, events = engine.step([], {0: state}, now=0.0)
    p1, p2 = view.players
    cls = CFG["game"]["default_classes"][0]
    assert view.scene == "lobby" and events == [] and view.timer_s is None
    assert p1.hp == p1.hp_max == CFG["game"]["hp_max"]
    assert p1.zone == "danger" and p1.dist == pytest.approx(1.2) and p1.tracking_ok
    assert p2.tracking_ok is False
    assert [spell.incantation for spell in p1.spells] == [
        spell["fallback"][0] for spell in CFG["game"]["classes"][cls]["spells"]
    ]


def test_lobby_transcripts_set_names_and_classes_and_survive_match_reset():
    engine = Engine(CFG)
    engine.step([], {}, now=0.0)
    engine.accept_voice(
        [
            VoiceEvent(0, 0.1, "transcript", "my name is", None, 0.0),
            VoiceEvent(0, 0.2, "transcript", "my name is ada lovelace", None, 0.0),
            VoiceEvent(0, 0.3, "transcript", "choose holy knight", None, 0.0),
            VoiceEvent(1, 0.2, "transcript", "call me nik", None, 0.0),
            VoiceEvent(1, 0.3, "transcript", "fire mage", None, 0.0),
        ]
    )
    view, _ = engine.step([], {}, now=0.4)
    assert [(player.name, player.class_id, player.mic_ok) for player in view.players] == [
        ("Ada Lovelace", "holy_knight", True),
        ("Nik", "fire_mage", True),
    ]

    _start_fight(engine)
    assert engine.names == {0: "Ada Lovelace", 1: "Nik"}
    assert engine.classes == {0: "holy_knight", 1: "fire_mage"}


def test_intent_marks_two_hand_pushes_and_engine_requires_them():
    intent = Intent(CFG)
    intent.update([make_state(t=0.0, cam_t=0.0)], [], 0.0)
    pushed = make_state(
        t=0.1,
        cam_t=0.1,
        push=Push("R", 2.0, (100.0, 200.0)),
        wrist_vz={"L": -2.0, "R": -2.0},
    )
    push_action = next(
        action for action in intent.update([pushed], [], 0.1) if action.kind == "push"
    )
    assert push_action.pose == "two_hand_push"

    engine = Engine(CFG)
    _start_fight(engine)
    states = {0: make_state(slot=0), 1: make_state(slot=1)}
    charge = Action(kind="charge", slot=0, t=2.0, spell_id="flame_wall", match_score=90.0)
    one_hand = Action(kind="push", slot=0, t=2.1, push=Push("R", 2.0, (100.0, 200.0)))
    _, events = engine.step([charge, one_hand], states, now=2.1)
    assert events == [] and engine.state.players[0].charge is not None

    two_hand = Action(
        kind="push",
        slot=0,
        t=2.2,
        push=Push("R", 2.0, (100.0, 200.0)),
        pose="two_hand_push",
    )
    _, events = engine.step([two_hand], states, now=2.2)
    assert [event.kind for event in events] == ["buff"]


def test_charge_then_push_launches_and_resolves_projectile():
    engine = Engine(CFG)
    _start_fight(engine)
    states = {0: make_state(slot=0), 1: make_state(slot=1)}
    charge = Action(kind="charge", slot=0, t=2.0, spell_id="fireball", match_score=80.0, dist=2.0)
    push = Action(
        kind="push",
        slot=0,
        t=2.1,
        push=Push("R", 2.0, (320.0, 240.0)),
        dist=2.0,
    )
    view, events = engine.step([charge, push], states, now=2.1)
    assert [event.kind for event in events] == ["cast"]
    assert len(view.projectiles) == 1
    view, events = engine.step([], states, now=4.0)
    assert [event.kind for event in events] == ["hit"]
    assert view.players[1].hp < view.players[1].hp_max


def test_intent_converts_voice_push_and_pose_to_actions():
    intent = Intent(CFG)
    state = make_state(
        t=1.0,
        push=Push("R", 2.0, (100.0, 200.0)),
        pose_flags=frozenset({"hands_up"}),
    )
    voice = VoiceEvent(0, 0.9, "incantation", "embers burn", "fireball", 91.0)
    actions = intent.update([state], [voice], 1.0)
    assert [action.kind for action in actions] == ["charge", "push", "pose"]
    assert intent.update([state], [], 1.1)[-1].kind == "push"
