"""Spell effects: shield, mana_slow, slow, empowered, heal, chain (docs/game-design.md)."""

import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Action, EffectView, Push
from magic_box.game.effects import Effects
from magic_box.game.state import STAT_KEYS, MatchState
from tests.factories import make_state, pin_pre_venue_tuning

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
pin_pre_venue_tuning(CFG)
G = CFG["game"]
NAMES = {0: "Ada", 1: "Bo"}
STATES = {0: make_state(0, root=(0.6, 0.0, 2.0)), 1: make_state(1, root=(-0.6, 0.0, 2.0))}
DIST = 1.05 * 1.05  # both players at 2.0 m


def cfg_with(regen=0.0):
    cfg = copy.deepcopy(CFG)
    cfg["game"]["mana_regen_per_s"] = regen
    return cfg


def new(classes=("fire_mage", "lightning_mage"), cfg=None):
    ms = MatchState(cfg or cfg_with(), NAMES, now=0.0, classes=dict(enumerate(classes)))
    ms.take_events()
    return ms


def charge(slot, spell, score=90.0):
    return Action("charge", slot, 0.0, spell_id=spell, match_score=score, dist=2.0)


def push(slot, two=False, speed=2.0):
    return Action("push", slot, 0.0, push=Push("R", speed, (480.0, 300.0)), two_hand=two, dist=2.0)


def pose(slot, name):
    return Action("pose", slot, 0.0, pose=name)


def cast(ms, slot, spell, release):
    ms.apply(charge(slot, spell), STATES, 0.0)
    ms.apply(release, STATES, 0.0)


def kinds(ms):
    return [e.kind for e in ms.take_events()]


def land(ms, seconds):
    """Advance in 0.05 s steps so projectiles land in order."""
    steps = round(seconds / 0.05)
    for _ in range(steps):
        ms.advance(0.05, STATES, 0.0)


# -- Effects container -----------------------------------------------------


def test_effects_add_extend_consume_expire_and_views():
    fx = Effects()
    fx.add("shield", 0.0, 4.0)
    fx.add("shield", 1.0, 1.0)  # shorter re-cast doesn't cut it short
    assert fx.active("shield", 3.9) and not fx.active("shield", 4.0)
    fx.add("slow", 0.0, 3.0)
    assert fx.views(1.0) == (EffectView("shield", 3.0), EffectView("slow", 2.0))
    assert fx.consume("slow", 1.0) and not fx.consume("slow", 1.0)
    fx.expire(5.0)
    assert fx.views(5.0) == ()


# -- Flame Wall: shield ----------------------------------------------------


def test_flame_wall_shield_blocks_the_next_hit_then_ends():
    ms = new(classes=("lightning_mage", "fire_mage"))
    cast(ms, 1, "flame_wall", push(1, two=True))
    assert kinds(ms) == ["cast", "buff"]
    assert ms.effect_views(1) == (EffectView("shield", 4.0),)
    ms.apply(push(0), STATES, 0.0)  # basic attack, 0.7 s
    ms.take_events()
    land(ms, 0.75)
    [ev] = ms.take_events()
    assert (ev.kind, ev.slot, ev.data) == ("block", 1, {"spell_id": "basic", "attacker": 0})
    assert ms.players[1].hp == G["hp_max"] and ms.effect_views(1) == ()
    assert ms.stats(1)["blocks"] == 1
    ms.advance(G["basic_attack_cooldown_s"], STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    land(ms, 0.75)
    assert "hit" in kinds(ms) and ms.players[1].hp < G["hp_max"]


def test_shield_expires_after_its_time():
    ms = new(classes=("lightning_mage", "fire_mage"))
    cast(ms, 1, "flame_wall", push(1, two=True))
    land(ms, 4.05)
    assert ms.effect_views(1) == ()
    ms.apply(push(0), STATES, 0.0)
    ms.take_events()
    land(ms, 0.75)
    assert kinds(ms) == ["hit"]


def test_shield_blocks_only_one_chain_bolt():
    ms = new(classes=("lightning_mage", "fire_mage"))
    cast(ms, 1, "flame_wall", push(1, two=True))
    cast(ms, 0, "chain", push(0))
    ms.take_events()
    land(ms, 1.8)
    assert kinds(ms) == ["block", "hit", "hit"]


# -- Static Field: mana_slow -----------------------------------------------


def test_static_field_is_a_projectile_that_slows_mana_regen_on_hit():
    ms = new(cfg=cfg_with(regen=8.0))
    cast(ms, 0, "static_field", push(0, two=True))  # P1 is fire_mage: a basic attack instead
    assert [p.spell_id for p in ms.projectiles] == ["basic"]
    ms = new(classes=("lightning_mage", "fire_mage"), cfg=cfg_with(regen=8.0))
    cast(ms, 0, "static_field", push(0, two=True))
    [proj] = ms.projectile_views()
    assert proj.spell_id == "static_field" and proj.target_slot == 1
    ms.take_events()
    land(ms, 1.4)
    events = ms.take_events()
    assert [e.kind for e in events] == ["hit", "buff"]
    assert events[0].data["damage"] == 0 and ms.players[1].hp == G["hp_max"]
    assert events[1].slot == 0 and events[1].data == {
        "spell_id": "static_field",
        "effect": "mana_slow",
        "target": 1,
        "duration_s": 5,
    }
    [fx] = ms.effect_views(1)
    assert fx.kind == "mana_slow" and fx.remaining_s == pytest.approx(5.0)
    ms.players[1].mana = ms.players[0].mana = 0.0
    ms.advance(1.0, STATES, 0.0)
    assert ms.players[1].mana == pytest.approx(8.0 * G["mana_slow_mult"])
    assert ms.players[0].mana == pytest.approx(8.0)
    land(ms, 4.05)
    assert ms.effect_views(1) == ()
    ms.players[1].mana = 0.0
    ms.advance(1.0, STATES, 0.0)
    assert ms.players[1].mana == pytest.approx(8.0)


def test_dodged_static_field_has_no_effect():
    ms = new(classes=("lightning_mage", "fire_mage"))
    cast(ms, 0, "static_field", push(0, two=True))
    land(ms, 1.0)
    ms.apply(Action("dodge", 1, 0.0, dodge="step"), STATES, 0.0)
    land(ms, 1.0)
    assert ms.effect_views(1) == () and ms.stats(1)["dodges"] == 1


# -- Inferno: slow ---------------------------------------------------------


def test_inferno_damage_and_slow_shortens_the_next_charge_only():
    ms = new(classes=("fire_mage", "lightning_mage"))
    cast(ms, 0, "inferno", push(0))
    ms.take_events()
    land(ms, 2.2)
    events = ms.take_events()
    assert [e.kind for e in events] == ["hit", "buff"]
    assert ms.players[1].hp == pytest.approx(G["hp_max"] - 35 * DIST)
    assert events[1].data["effect"] == "slow"
    assert [fx.kind for fx in ms.effect_views(1)] == ["slow"]
    ms.apply(charge(1, "bolt"), STATES, 0.0)
    window = G["charge_window_s"] * G["slow_charge_mult"]
    assert ms.charge_left(1) == pytest.approx(window)
    assert ms.effect_views(1) == ()  # used up by the charge
    ms.apply(charge(1, "chain"), STATES, 0.0)
    assert ms.charge_left(1) == pytest.approx(G["charge_window_s"])


def test_slow_wears_off_unused():
    ms = new()
    cast(ms, 0, "inferno", push(0))
    land(ms, 2.2 + 3.05)
    assert ms.effect_views(1) == ()
    ms.apply(charge(1, "bolt"), STATES, 0.0)
    assert ms.charge_left(1) == pytest.approx(G["charge_window_s"])


# -- Holy Light: empowered -------------------------------------------------


def test_holy_light_empowers_spells_released_while_it_lasts():
    ms = new(classes=("holy_knight", "fire_mage"))
    cast(ms, 0, "holy_light", pose(0, "hands_up"))
    events = ms.take_events()
    assert [e.kind for e in events] == ["cast", "buff"]
    assert events[1].data == {
        "spell_id": "holy_light",
        "effect": "empowered",
        "target": 0,
        "duration_s": 6,
    }
    assert ms.banner() == "HOLY LIGHT!" and ms.projectiles == []
    assert ms.effect_views(0) == (EffectView("empowered", 6.0),)
    ms.apply(push(0), STATES, 0.0)  # basic attack while empowered
    land(ms, 0.75)
    expected = G["basic_attack_damage"] * DIST * G["empowered_mult"]
    assert ms.players[1].hp == pytest.approx(G["hp_max"] - expected)
    land(ms, 5.5)
    assert ms.effect_views(0) == ()
    hp = ms.players[1].hp
    ms.apply(push(0), STATES, 0.0)
    land(ms, 0.75)
    assert hp - ms.players[1].hp == pytest.approx(G["basic_attack_damage"] * DIST)


# -- Heal ------------------------------------------------------------------


def test_heal_adds_hp_capped_at_max():
    ms = new(classes=("holy_knight", "fire_mage"))
    ms.players[0].hp = 60.0
    cast(ms, 0, "heal", pose(0, "hands_together"))
    events = ms.take_events()
    assert [e.kind for e in events] == ["cast", "heal"]
    assert events[1].slot == 0 and events[1].data == {"spell_id": "heal", "amount": 25, "hp": 85}
    assert ms.players[0].hp == 85
    ms.players[0].mana = 100
    ms.players[0].hp = 90.0
    cast(ms, 0, "heal", pose(0, "hands_together"))
    assert ms.players[0].hp == G["hp_max"]
    assert ms.take_events()[1].data["amount"] == 10
    assert ms.stats(0)["heals"] == 2


# -- Chain -----------------------------------------------------------------


def test_chain_fires_three_spaced_bolts():
    ms = new(classes=("lightning_mage", "fire_mage"))
    cast(ms, 0, "chain", push(0))
    assert len(ms.projectiles) == 3
    assert [p.spell_id for p in ms.projectile_views()] == ["chain"]  # the rest not yet launched
    ms.advance(0.25, STATES, 0.0)
    assert len(ms.projectile_views()) == 2
    ms.take_events()
    land(ms, 1.5)
    hits = [e for e in ms.take_events() if e.kind == "hit"]
    assert len(hits) == 3 and all(e.data["spell_id"] == "chain" for e in hits)
    assert ms.players[1].hp == pytest.approx(G["hp_max"] - 3 * 7 * DIST)
    assert ms.stats(0)["hits"] == 3 and ms.stats(0)["casts"] == 1


def test_chain_bolts_are_dodged_one_window_at_a_time():
    ms = new(classes=("lightning_mage", "fire_mage"))
    cast(ms, 0, "chain", push(0))
    land(ms, 0.6)  # bolt 1 enters its dodge window; bolts 2 and 3 are still early
    ms.take_events()
    ms.apply(Action("dodge", 1, 0.0, dodge="duck"), STATES, 0.0)
    assert kinds(ms) == ["dodge"]
    land(ms, 1.5)
    assert kinds(ms) == ["hit", "hit"]


def test_one_dodge_avoids_only_the_earliest_chain_bolt():
    ms = new(classes=("lightning_mage", "fire_mage"))
    cast(ms, 0, "chain", push(0))
    land(ms, 1.15)  # all three bolts are inside their dodge windows now
    ms.take_events()
    assert all(p.in_dodge_window for p in ms.projectile_views())
    ms.apply(Action("dodge", 1, 0.0, dodge="duck"), STATES, 0.0)
    assert kinds(ms) == ["dodge"] and len(ms.projectiles) == 2
    ms.apply(Action("dodge", 1, 0.0, dodge="step"), STATES, 0.0)
    assert kinds(ms) == ["dodge"] and len(ms.projectiles) == 1
    land(ms, 1.0)
    assert kinds(ms) == ["hit"] and ms.stats(1)["dodges"] == 2


def test_one_dodge_still_avoids_every_other_cast_in_its_window():
    ms = new()
    cast(ms, 0, "fireball", push(0))  # 1.6 s
    land(ms, 0.9)
    ms.apply(push(0), STATES, 0.0)  # basic, 0.7 s: both land at about 1.6 s
    land(ms, 0.3)
    ms.take_events()
    ms.apply(Action("dodge", 1, 0.0, dodge="step"), STATES, 0.0)
    assert kinds(ms) == ["dodge", "dodge"] and ms.projectiles == []


# -- Stats and views -------------------------------------------------------


def test_stats_keys_and_totals():
    ms = new()
    assert set(ms.stats(0)) == set(STAT_KEYS)
    cast(ms, 0, "fireball", push(0, speed=3.1))
    ms.players[1].hp = 5
    land(ms, 1.6)
    s = ms.stats(0)
    assert s["casts"] == 1 and s["hits"] == 1 and s["best_push_mps"] == 3.1
    assert s["damage"] == 5  # overkill doesn't count


def test_charge_and_cooldown_left():
    ms = new()
    assert ms.charge_left(0) == 0 and ms.cooldown_left(0) == 0
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.advance(1.0, STATES, 0.0)
    assert ms.charge_left(0) == pytest.approx(G["charge_window_s"] - 1.0)
    ms.apply(push(1), STATES, 0.0)
    assert ms.cooldown_left(1) == pytest.approx(G["basic_attack_cooldown_s"])


def test_abandon_ends_the_match_once():
    ms = new()
    ms.abandon(1.0, 1)
    ms.abandon(2.0, 0)
    assert ms.result() == (1, "abandon")
    [ev] = ms.take_events()
    assert ev.kind == "match_end" and ev.data["reason"] == "abandon"


def test_ko_clears_projectiles_still_in_flight():
    ms = new()
    ms.players[1].hp = 5
    cast(ms, 0, "fireball", push(0))  # 1.6 s
    ms.apply(push(0), STATES, 0.0)  # basic, 0.7 s: lands first and KOs
    land(ms, 0.75)
    assert ms.result() == (0, "ko") and ms.projectiles == []
    assert [e.kind for e in ms.take_events()][-2:] == ["ko", "match_end"]


def test_a_knockout_blow_puts_no_effect_on_the_loser():
    """A lethal Inferno ends the match: no "slow" buff event or badge on the KO'd player."""
    ms = new()
    ms.players[1].hp = 10.0
    cast(ms, 0, "inferno", push(0))
    land(ms, 2.4)
    assert kinds(ms) == ["cast", "hit", "ko", "match_end"]
    assert ms.effect_views(1) == ()


def holding(flag):
    held = dict(STATES)
    held[0] = make_state(0, root=(0.6, 0.0, 2.0), pose_flags=frozenset({flag}))
    return held


def casts(ms):
    return [e.data["spell_id"] for e in ms.take_events() if e.kind == "cast"]


@pytest.mark.parametrize(
    ("spell", "flag"), [("holy_light", "hands_up"), ("heal", "hands_together")]
)
def test_a_charge_landing_soon_after_its_pose_rose_releases_it(spell, flag):
    """The voice charge lands ~0.4 s (worst ~0.8 s) after speech; an arm raised on the last
    word (the pose edge came first) still releases the spell, once."""
    ms = new(classes=("holy_knight", "lightning_mage"))
    ms.players[0].hp = 50.0
    held = holding(flag)
    ms.apply(pose(0, flag), held, 0.0)  # the rise: no charge yet
    ms.advance(0.5, held, 0.0)
    ms.apply(charge(0, spell), held, 0.0)
    assert ms.players[0].charge is None
    assert casts(ms) == [spell]
    ms.advance(0.5, held, 0.0)
    assert casts(ms) == []


def test_a_pose_held_longer_than_the_pose_grace_does_not_release_a_charge():
    """Hands still up from the lobby, or held through the whole incantation, don't fire;
    lowering and raising again (a new edge) does."""
    ms = new(classes=("holy_knight", "lightning_mage"))
    held = holding("hands_up")
    ms.apply(pose(0, "hands_up"), held, 0.0)
    ms.advance(G["pose_grace_s"] + 1.0, held, 0.0)
    ms.apply(charge(0, "holy_light"), held, 0.0)
    assert ms.players[0].charge is not None and casts(ms) == []
    ms.apply(pose(0, "hands_up"), held, 0.0)  # lowered and raised again
    assert casts(ms) == ["holy_light"] and ms.players[0].charge is None


def test_a_pose_held_since_before_the_match_does_not_release_a_charge():
    ms = new(classes=("holy_knight", "lightning_mage"))
    ms.apply(charge(0, "holy_light"), holding("hands_up"), 0.0)  # no rise seen this match
    assert ms.players[0].charge is not None and casts(ms) == []


@pytest.mark.parametrize("pose_first", [True, False])
def test_a_charge_and_its_pose_edge_on_the_same_tick_cast_once(pose_first):
    ms = new(classes=("holy_knight", "lightning_mage"))
    held = holding("hands_up")
    actions = [charge(0, "holy_light"), pose(0, "hands_up")]
    for a in reversed(actions) if pose_first else actions:
        ms.apply(a, held, 0.0)
    assert casts(ms) == ["holy_light"]


def test_pose_grace_is_configured():
    assert G["pose_grace_s"] == pytest.approx(1.0)


def test_a_held_pose_does_not_release_a_spell_it_does_not_match():
    ms = new(classes=("holy_knight", "lightning_mage"))
    held = dict(STATES)
    held[0] = make_state(0, root=(0.6, 0.0, 2.0), pose_flags=frozenset({"hands_together"}))
    ms.apply(pose(0, "hands_together"), held, 0.0)
    ms.apply(charge(0, "holy_light"), held, 0.0)
    assert ms.players[0].charge is not None and kinds(ms) == []


def test_a_lost_player_pose_flags_do_not_release_a_charge():
    ms = new(classes=("holy_knight", "lightning_mage"))
    held = dict(STATES)
    held[0] = make_state(
        0, root=(0.6, 0.0, 2.0), pose_flags=frozenset({"hands_up"}), tracking_ok=False
    )
    ms.apply(pose(0, "hands_up"), holding("hands_up"), 0.0)
    ms.apply(charge(0, "holy_light"), held, 0.0)
    assert ms.players[0].charge is not None
