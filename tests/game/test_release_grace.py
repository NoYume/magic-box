"""Release grace: a push with no charge waits for a late voice charge (mic on only)."""

import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Action, Push
from magic_box.game.engine import Engine
from magic_box.game.state import MatchState
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
CFG0 = copy.deepcopy(CFG)
CFG0["game"]["mana_regen_per_s"] = 0
G = CFG["game"]
GRACE = G["release_grace_s"]
NAMES = {0: "Ada", 1: "Bo"}
STATES = {0: make_state(0), 1: make_state(1)}


def new(mic=(True, True), classes=("fire_mage", "lightning_mage")):
    ms = MatchState(
        CFG0, NAMES, now=0.0, classes=dict(enumerate(classes)), mic_ok=dict(enumerate(mic))
    )
    ms.take_events()
    return ms


def push(slot, two=False, speed=2.0, dist=2.0, origin=(480.0, 300.0)):
    return Action("push", slot, 0.0, push=Push("R", speed, origin), two_hand=two, dist=dist)


def charge(slot, spell):
    return Action("charge", slot, 0.0, spell_id=spell, match_score=90.0, dist=2.0)


def spell_ids(ms):
    return [p.spell_id for p in ms.projectiles]


def test_grace_is_configured():
    assert GRACE == pytest.approx(0.6)


def test_charge_within_the_grace_releases_the_spell_with_the_held_push():
    ms = new()
    ms.apply(push(0, speed=3.0, dist=1.3, origin=(400.0, 250.0)), STATES, 0.0)
    assert ms.projectiles == [] and ms.take_events() == []
    ms.advance(GRACE / 2, STATES, 0.0)
    ms.apply(charge(0, "fireball"), STATES, 4.0)
    [proj] = ms.projectiles
    assert (proj.spell_id, proj.speed, proj.atk_dist, proj.origin_px) == (
        "fireball",
        3.0,
        1.3,
        (400.0, 250.0),
    )
    assert ms.players[0].charge is None and ms.players[0].mana == G["mana_max"] - 25
    [ev] = ms.take_events()
    assert (ev.kind, ev.t, ev.data["spell_id"]) == ("cast", 4.0, "fireball")
    ms.advance(GRACE, STATES, 0.0)
    assert spell_ids(ms) == ["fireball"]  # no basic attack after the hold


def test_no_charge_fires_the_basic_attack_when_the_grace_ends():
    ms = new()
    ms.apply(push(0, speed=2.5), STATES, 0.0)
    ms.advance(GRACE - 0.05, STATES, 0.0)
    assert ms.projectiles == []
    ms.advance(0.1, STATES, 7.0)
    [proj] = ms.projectiles
    assert (proj.spell_id, proj.speed) == ("basic", 2.5)
    [ev] = ms.take_events()
    assert (ev.kind, ev.t, ev.data["spell_id"]) == ("cast", 7.0, "basic")
    assert ms.cooldown_left(0) == pytest.approx(G["basic_attack_cooldown_s"])


def test_mic_off_fires_the_basic_attack_at_once():
    ms = new(mic=(False, True))
    ms.apply(push(0), STATES, 0.0)
    assert spell_ids(ms) == ["basic"]


def test_a_charged_spell_still_releases_at_once():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    assert spell_ids(ms) == ["fireball"]


def test_two_hand_spell_does_not_release_from_a_held_plain_push():
    ms = new()
    ms.apply(push(0), STATES, 0.0)
    ms.apply(charge(0, "flame_wall"), STATES, 0.0)
    assert ms.projectiles == [] and ms.players[0].charge.spell.id == "flame_wall"
    ms.advance(GRACE + 0.05, STATES, 0.0)
    assert spell_ids(ms) == ["basic"] and ms.players[0].charge.spell.id == "flame_wall"


def test_held_two_hand_push_releases_a_two_hand_spell():
    ms = new()
    ms.apply(push(0, two=True), STATES, 0.0)
    ms.apply(charge(0, "flame_wall"), STATES, 0.0)
    assert ms.players[0].charge is None
    assert [fx.kind for fx in ms.effect_views(0)] == ["shield"]


def test_second_push_during_the_hold_is_ignored():
    ms = new()
    ms.apply(push(0, speed=2.0), STATES, 0.0)
    ms.advance(0.1, STATES, 0.0)
    ms.apply(push(0, speed=4.0), STATES, 0.0)
    ms.advance(GRACE, STATES, 0.0)
    [proj] = ms.projectiles
    assert proj.speed == 2.0


def casts(ms):
    return [e.data["spell_id"] for e in ms.take_events() if e.kind == "cast"]


def test_push_on_cooldown_is_held_for_a_late_spell():
    """Ruling (QA 1): during the basic cooldown a push still waits for a charge."""
    ms = new(mic=(False, True))
    ms.apply(push(0), STATES, 0.0)  # basic fires; cooldown starts
    ms.mic_ok[0] = True
    ms.apply(push(0, speed=3.0), STATES, 0.0)
    ms.advance(GRACE / 2, STATES, 0.0)
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    assert casts(ms) == ["basic", "fireball"] and ms.players[0].charge is None
    assert ms.projectiles[-1].speed == 3.0


def test_push_on_cooldown_with_no_charge_is_dropped_not_a_basic():
    ms = new(mic=(False, True))
    ms.apply(push(0), STATES, 0.0)
    ready_at = ms.players[0].basic_ready_at
    ms.mic_ok[0] = True
    ms.apply(push(0), STATES, 0.0)
    ms.advance(GRACE + 0.05, STATES, 0.0)
    assert casts(ms) == ["basic"]
    assert ms.players[0].held is None and ms.players[0].basic_ready_at == ready_at


def test_without_advance_the_hold_never_expires_and_clearing_drops_it():
    ms = new()
    ms.apply(push(0), STATES, 0.0)
    ms.advance(0.0, STATES, 0.0)  # a paused tick never reaches advance with dt > 0
    assert ms.projectiles == []
    ms.clear_in_flight()
    ms.advance(1.0, STATES, 0.0)
    assert ms.projectiles == []


# -- through the engine ----------------------------------------------------


def _states():
    return {s: make_state(s) for s in (0, 1)}


def _to_fight(e):
    e.provide_check("camera", True)
    t = 0.0
    while e.step([], _states(), t)[0].scene != "lobby":
        t += 0.05
    up = {s: make_state(s, pose_flags=frozenset({"hands_up"})) for s in (0, 1)}
    while e.step([], up, t)[0].scene != "loading":
        t += 0.05
    e.provide_incantations({0: {}, 1: {}})
    while e.step([], _states(), t)[0].scene != "fight":
        t += 0.05
    return t + 0.05


def test_engine_holds_a_push_only_while_the_mic_is_ok():
    e = Engine(CFG)
    e.provide_mic_status(0, True)
    t = _to_fight(e)
    p = Push("R", 2.0, (480.0, 300.0))
    view, _ = e.step([Action("push", 0, t, push=p, dist=2.0)], _states(), t)
    assert view.projectiles == ()
    view, _ = e.step([Action("charge", 0, t, spell_id="fireball", dist=2.0)], _states(), t + 0.3)
    assert [pr.spell_id for pr in view.projectiles] == ["fireball"]
    view, _ = e.step([Action("push", 1, t, push=p, dist=2.0)], _states(), t + 0.35)
    assert sorted(pr.spell_id for pr in view.projectiles) == ["basic", "fireball"]  # P2 mic off
