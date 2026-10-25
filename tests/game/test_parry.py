from pathlib import Path

import pytest

from magic_box.ai.incantations import fallback_incantations
from magic_box.core.config import load_config
from magic_box.core.contracts import Action, Push, VoiceEvent
from magic_box.game.engine import Engine
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
GAME = CFG["game"]
STATES = {0: make_state(slot=0), 1: make_state(slot=1)}
FIREBALL = next(s for s in GAME["classes"]["fire_mage"]["spells"] if s["id"] == "fireball")


def _knight_vs_mage() -> Engine:
    """P1 Holy Knight, P2 Fire Mage, fight scene entered at t = loading_s."""
    engine = Engine(CFG)
    engine.step([], {}, now=0.0)
    engine.accept_voice(
        [
            VoiceEvent(0, 0.0, "transcript", "holy knight", None, 0.0),
            VoiceEvent(1, 0.0, "transcript", "fire mage", None, 0.0),
        ]
    )
    ready = [Action(kind="pose", slot=slot, t=0.0, pose="hands_up", dist=2.0) for slot in (0, 1)]
    engine.step(ready, STATES, now=0.0)
    engine.provide_incantations(fallback_incantations(engine.classes, CFG))
    view, _ = engine.step([], STATES, now=GAME["loading_s"])
    assert view.scene == "fight" and engine.classes == {0: "holy_knight", 1: "fire_mage"}
    return engine


def _push(slot: int, t: float) -> Action:
    return Action(kind="push", slot=slot, t=t, push=Push("R", 2.0, (300.0, 200.0)), dist=2.0)


def _guard(slot: int, t: float) -> Action:
    return Action(kind="pose", slot=slot, t=t, pose="guard", dist=2.0)


def _mage_fireball(engine: Engine, t: float) -> float:
    """P2 casts a fireball at P1; returns the impact time."""
    charge = Action(kind="charge", slot=1, t=t, spell_id="fireball", match_score=85.0)
    engine.step([charge, _push(1, t + 0.01)], STATES, now=t + 0.01)
    return t + 0.01 + FIREBALL["travel_s"]


def test_timed_guard_parries_the_hit_and_arms_a_riposte():
    engine = _knight_vs_mage()
    impact = _mage_fireball(engine, 2.0)
    engine.step([_guard(0, impact - 0.1)], STATES, now=impact - 0.1)
    view, events = engine.step([], STATES, now=impact)
    assert [(e.kind, e.slot, e.data.get("parry")) for e in events] == [("block", 0, True)]
    knight = view.players[0]
    assert knight.hp == GAME["hp_max"] and knight.can_parry and not view.players[1].can_parry
    assert knight.riposte_s == pytest.approx(GAME["riposte_window_s"])
    assert knight.parry_flash_s == pytest.approx(GAME["parry_flash_s"]) and knight.guard_cooldown_s > 0

    view, events = engine.step([_push(0, impact + 0.2)], STATES, now=impact + 0.2)
    assert [(e.kind, e.data["spell_id"]) for e in events] == [("cast", "riposte")]
    assert [p.spell_id for p in view.projectiles] == ["riposte"]
    land = impact + 0.2 + GAME["riposte_travel_s"]
    view, events = engine.step([], STATES, now=land)
    assert [(e.kind, e.data["spell_id"]) for e in events] == [("hit", "riposte")]
    assert view.players[1].hp < GAME["hp_max"] - GAME["basic_attack_damage"] * 2


def test_early_guard_does_not_parry():
    engine = _knight_vs_mage()
    impact = _mage_fireball(engine, 2.0)
    early = impact - GAME["parry_window_s"] - 0.1
    engine.step([_guard(0, early)], STATES, now=early)
    view, events = engine.step([], STATES, now=impact)
    assert [e.kind for e in events] == ["hit"] and view.players[0].hp < GAME["hp_max"]


def test_guard_cooldown_blocks_spamming():
    engine = _knight_vs_mage()
    impact = _mage_fireball(engine, 2.0)
    first = impact - GAME["parry_window_s"] - 0.1
    retry = impact - 0.05
    assert retry < first + GAME["parry_cooldown_s"]
    engine.step([_guard(0, first)], STATES, now=first)
    engine.step([_guard(0, retry)], STATES, now=retry)
    _, events = engine.step([], STATES, now=impact)
    assert [e.kind for e in events] == ["hit"]


def test_riposte_expires_and_mages_cannot_parry():
    engine = _knight_vs_mage()
    impact = _mage_fireball(engine, 2.0)
    engine.step([_guard(0, impact - 0.1)], STATES, now=impact - 0.1)
    engine.step([], STATES, now=impact)
    late = impact + GAME["riposte_window_s"] + 0.1
    _, events = engine.step([_push(0, late)], STATES, now=late)
    assert [(e.kind, e.data["spell_id"]) for e in events] == [("cast", "basic_attack")]

    land = late + GAME["basic_attack_travel_s"]
    engine.step([_guard(1, land - 0.1)], STATES, now=land - 0.1)
    _, events = engine.step([], STATES, now=land)
    assert [e.kind for e in events] == ["hit"]
