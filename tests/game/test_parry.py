import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Action, Push
from magic_box.game.state import MatchState
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
NAMES = {0: "Ada", 1: "Bo"}
STATES = {0: make_state(0), 1: make_state(1)}


def _match() -> MatchState:
    cfg = copy.deepcopy(CFG)
    cfg["game"]["default_classes"] = {0: "holy_knight", 1: "fire_mage"}
    match = MatchState(cfg, NAMES, now=0.0)
    match.take_events()
    return match


def _push(slot: int) -> Action:
    return Action("push", slot, 0.0, push=Push("R", 2.0, (300.0, 200.0)), dist=2.0)


def _launch_fireball(match: MatchState) -> float:
    match.apply(Action("charge", 1, 0.0, spell_id="fireball", match_score=85.0), STATES, 0.0)
    match.apply(_push(1), STATES, 0.0)
    match.take_events()
    return match.projectiles[0].travel_s


def test_timed_guard_parries_hit_and_next_push_ripostes():
    match = _match()
    travel = _launch_fireball(match)
    match.advance(travel - 0.1, STATES, travel - 0.1)
    match.apply(Action("pose", 0, travel - 0.1, pose="guard"), STATES, travel - 0.1)
    match.advance(0.1, STATES, travel)

    [block] = match.take_events()
    knight = match.players[0]
    assert (block.kind, block.slot, block.data) == (
        "block",
        0,
        {"spell_id": "fireball", "parry": True},
    )
    assert knight.hp == CFG["game"]["hp_max"]
    assert knight.riposte_until - match.clock == pytest.approx(CFG["game"]["riposte_window_s"])

    match.apply(_push(0), STATES, travel + 0.1)
    [cast] = match.take_events()
    assert cast.kind == "cast" and cast.data["spell_id"] == "riposte"
    assert match.projectiles[0].spell_id == "riposte"

    match.advance(CFG["game"]["riposte_travel_s"], STATES, travel + 0.6)
    [hit] = match.take_events()
    assert hit.kind == "hit" and hit.data["spell_id"] == "riposte"
    assert match.players[1].hp < CFG["game"]["hp_max"] - CFG["game"]["basic_attack_damage"]


def test_early_guard_and_mage_guard_do_not_parry():
    match = _match()
    match.apply(Action("pose", 0, 0.0, pose="guard"), STATES, 0.0)
    first_guard = match.players[0].guard_at
    match.advance(CFG["game"]["parry_window_s"] + 0.1, STATES, 0.5)
    match.apply(Action("pose", 0, 0.5, pose="guard"), STATES, 0.5)
    assert match.players[0].guard_at == first_guard  # still on cooldown

    travel = _launch_fireball(match)
    match.advance(travel, STATES, 2.1)
    assert [event.kind for event in match.take_events()] == ["hit"]
    assert match.players[0].hp < CFG["game"]["hp_max"]

    mage = match.players[1]
    match.apply(Action("pose", 1, 2.1, pose="guard"), STATES, 2.1)
    assert mage.guard_at == float("-inf")


def test_riposte_expires_into_basic_attack():
    match = _match()
    match.players[0].riposte_until = match.clock + CFG["game"]["riposte_window_s"]
    match.advance(CFG["game"]["riposte_window_s"] + 0.01, STATES, 2.0)
    match.apply(_push(0), STATES, 2.0)
    [cast] = match.take_events()
    assert cast.data["spell_id"] == "basic"
