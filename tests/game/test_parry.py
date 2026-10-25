"""The Holy Knight's guard, parry and riposte (Adetola's PR #2, ported onto the new engine)."""

import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Action, Push
from magic_box.game.engine import Engine
from magic_box.game.state import MatchState
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
G = CFG["game"]
NAMES = {0: "Ada", 1: "Bo"}
STATES = {0: make_state(0), 1: make_state(1)}


def _match(classes=None, mic_ok=None) -> MatchState:
    cfg = copy.deepcopy(CFG)
    cfg["game"]["default_classes"] = classes or {0: "holy_knight", 1: "fire_mage"}
    match = MatchState(cfg, NAMES, now=0.0, mic_ok=mic_ok)
    match.take_events()
    return match


def _push(slot: int, t: float = 0.0) -> Action:
    return Action("push", slot, t, push=Push("R", 2.0, (300.0, 200.0)), dist=2.0)


def _guard(slot: int, t: float) -> Action:
    return Action("pose", slot, t, pose="guard")


def _launch(match: MatchState, spell_id: str = "fireball") -> float:
    match.apply(Action("charge", 1, 0.0, spell_id=spell_id, match_score=85.0), STATES, 0.0)
    match.apply(_push(1), STATES, 0.0)
    match.take_events()
    return match.projectiles[0].travel_s


def test_timed_guard_parries_hit_and_next_push_ripostes():
    match = _match()
    travel = _launch(match)
    match.advance(travel - 0.1, STATES, travel - 0.1)
    match.apply(_guard(0, travel - 0.1), STATES, travel - 0.1)
    match.advance(0.1 + 1e-6, STATES, travel)

    [block] = match.take_events()
    knight = match.players[0]
    assert (block.kind, block.slot, block.data) == (
        "block",
        0,
        {"spell_id": "fireball", "attacker": 1, "parry": True},
    )
    assert knight.hp == G["hp_max"]
    assert knight.stats["blocks"] == 1
    assert match.riposte_left(0) == pytest.approx(G["riposte_window_s"])
    assert match.guard_left(0) == 0.0  # the parry spends the guard

    match.apply(_push(0), STATES, travel + 0.1)
    [cast] = match.take_events()
    assert cast.kind == "cast" and cast.data["spell_id"] == "riposte"
    assert match.projectiles[0].spell_id == "riposte"
    assert knight.stats["casts"] == 0  # a riposte, like a basic, isn't a charged spell
    assert match.riposte_left(0) == 0.0

    match.advance(G["riposte_travel_s"] + 1e-6, STATES, travel + 0.6)
    [hit] = match.take_events()
    assert hit.kind == "hit" and hit.data["spell_id"] == "riposte"
    assert match.players[1].hp < G["hp_max"] - G["basic_attack_damage"]


def test_early_guard_cooldown_and_mage_guard_do_not_parry():
    match = _match()
    match.apply(_guard(0, 0.0), STATES, 0.0)
    first_guard = match.players[0].guard_at
    match.advance(G["parry_window_s"] + 0.1, STATES, 0.5)
    match.apply(_guard(0, 0.5), STATES, 0.5)
    assert match.players[0].guard_at == first_guard  # still on cooldown
    assert match.guard_cooldown_left(0) > 0

    travel = _launch(match)
    match.advance(travel, STATES, 2.1)
    assert [event.kind for event in match.take_events()] == ["hit"]
    assert match.players[0].hp < G["hp_max"]

    mage = match.players[1]
    match.apply(_guard(1, 2.1), STATES, 2.1)
    assert mage.guard_at == float("-inf")


def test_riposte_expires_into_basic_attack():
    match = _match()
    match.players[0].riposte_until = match.clock + G["riposte_window_s"]
    match.advance(G["riposte_window_s"] + 0.01, STATES, 2.0)
    match.apply(_push(0), STATES, 2.0)
    [cast] = match.take_events()
    assert cast.data["spell_id"] == "basic"


def test_riposte_fires_at_once_with_the_mic_on():
    """No release grace: the riposte is what the push is for."""
    match = _match(mic_ok={0: True, 1: True})
    match.players[0].riposte_until = match.clock + G["riposte_window_s"]
    match.apply(_push(0), STATES, 0.0)
    [cast] = match.take_events()
    assert cast.data["spell_id"] == "riposte"
    assert match.players[0].held is None


def test_riposte_ignores_the_basic_cooldown():
    match = _match()
    match.players[0].basic_ready_at = match.clock + 10.0
    match.players[0].riposte_until = match.clock + G["riposte_window_s"]
    match.apply(_push(0), STATES, 0.0)
    assert [e.data["spell_id"] for e in match.take_events()] == ["riposte"]


def test_a_charged_push_spell_releases_before_the_riposte():
    match = _match()
    match.players[0].riposte_until = match.clock + G["riposte_window_s"]
    match.apply(Action("charge", 0, 0.0, spell_id="judgment", match_score=85.0), STATES, 0.0)
    match.apply(_push(0), STATES, 0.0)
    assert [e.data["spell_id"] for e in match.take_events()] == ["judgment"]
    assert match.riposte_left(0) > 0  # still armed for the next push


def test_one_guard_parries_only_the_first_chain_bolt():
    match = _match(classes={0: "holy_knight", 1: "lightning_mage"})
    travel = _launch(match, "chain")
    match.advance(travel - 0.1, STATES, travel - 0.1)
    match.apply(_guard(0, travel - 0.1), STATES, travel - 0.1)
    for i in range(60):  # frame by frame, so each bolt lands on time
        match.advance(1 / 60, STATES, travel + i / 60)
    kinds = [(e.kind, e.data.get("parry", False)) for e in match.take_events()]
    assert kinds == [("block", True), ("hit", False), ("hit", False)]


def test_parry_view_fields():
    eng = Engine(copy.deepcopy(CFG))
    view, _ = eng.step([], {}, 0.0)
    knight = next(p for p in view.players if p.class_id == "holy_knight")
    other = next(p for p in view.players if p.class_id != "holy_knight")
    assert knight.can_parry and not other.can_parry
    assert (knight.guard_s, knight.guard_cooldown_s, knight.riposte_s) == (0.0, 0.0, 0.0)


def test_riposte_drops_a_push_held_from_before_the_parry():
    match = _match(mic_ok={0: True, 1: True})
    match.apply(_push(0), STATES, 0.0)  # held: Judgment is affordable, the charge may be late
    assert match.players[0].held is not None
    match.players[0].riposte_until = match.clock + G["riposte_window_s"]
    match.apply(_push(0, 0.1), STATES, 0.1)
    match.advance(G["release_grace_s"] + 0.1, STATES, 1.0)
    assert [e.data["spell_id"] for e in match.take_events() if e.kind == "cast"] == ["riposte"]
