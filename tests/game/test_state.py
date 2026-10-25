import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Action, Push
from magic_box.game.state import MatchState
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
CFG0 = copy.deepcopy(CFG)
CFG0["game"]["mana_regen_per_s"] = 0

NAMES = {0: "Ada", 1: "Bo"}
STATES = {0: make_state(0, root=(0.6, 0.0, 2.0)), 1: make_state(1, root=(-0.6, 0.0, 2.0))}


def charge(slot, spell, score=90.0):
    return Action("charge", slot, 0.0, spell_id=spell, match_score=score, dist=2.0)


def push(slot, two=False, speed=2.0):
    return Action("push", slot, 0.0, push=Push("R", speed, (480.0, 300.0)), two_hand=two, dist=2.0)


def new(cfg=CFG0):
    ms = MatchState(cfg, NAMES, now=5.0)
    ms.take_events()
    return ms


def test_match_starts_full_and_logs_match_start():
    ms = MatchState(CFG, NAMES, now=5.0)
    p0, p1 = ms.players
    assert (p0.hp, p0.mana, p0.class_id, p1.class_id) == (100, 100, "fire_mage", "holy_knight")
    assert ms.time_left == 90 and ms.banner() == "FIGHT!"
    [ev] = ms.take_events()
    assert (ev.kind, ev.t) == ("match_start", 5.0)
    assert ev.data == {
        "names": {0: "Ada", 1: "Bo"},
        "classes": {0: "fire_mage", 1: "holy_knight"},
    }


def test_charge_reserves_then_expires_with_refund():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    assert ms.players[0].mana == 75 and ms.players[0].charge.spell.id == "fireball"
    ms.advance(CFG["game"]["charge_window_s"] + 0.01, STATES, 0.0)
    assert ms.players[0].charge is None and ms.players[0].mana == 100


def test_new_charge_replaces_and_refunds():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(charge(0, "inferno"), STATES, 0.0)
    assert ms.players[0].mana == 40 and ms.players[0].charge.spell.id == "inferno"


def test_charge_needs_own_class_and_mana():
    ms = new()
    ms.apply(charge(0, "bolt"), STATES, 0.0)
    ms.players[0].mana = 10
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    assert ms.players[0].charge is None and ms.players[0].mana == 10


def test_push_releases_charged_spell_as_projectile():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    [p] = ms.projectiles
    assert (p.spell_id, p.attacker, p.target, p.origin_px) == ("fireball", 0, 1, (480.0, 300.0))
    assert ms.players[0].charge is None
    [ev] = ms.take_events()
    assert ev.kind == "cast" and ev.data == {
        "spell_id": "fireball",
        "release": "push",
        "two_hand": False,
    }


def test_two_hand_spell_needs_two_hands_single_push_is_basic():
    ms = new()
    ms.apply(charge(0, "flame_wall"), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    assert [p.spell_id for p in ms.projectiles] == ["basic"]
    assert ms.players[0].charge.spell.id == "flame_wall"
    ms.apply(push(0, two=True), STATES, 0.0)
    assert ms.players[0].charge is None and ms.banner() == "FLAME WALL!"
    assert [p.spell_id for p in ms.projectiles] == ["basic"]  # no projectile for 0-damage spells


def test_two_hand_push_releases_push_spell():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(push(0, two=True), STATES, 0.0)
    assert [p.spell_id for p in ms.projectiles] == ["fireball"]


def test_pose_releases_matching_spell_only():
    cfg = copy.deepcopy(CFG0)
    cfg["game"]["default_classes"][0] = "holy_knight"
    ms = new(cfg)
    ms.apply(charge(0, "heal"), STATES, 0.0)
    ms.apply(Action("pose", 0, 0.0, pose="hands_up"), STATES, 0.0)
    assert ms.players[0].charge is not None
    ms.apply(Action("pose", 0, 0.0, pose="hands_together"), STATES, 0.0)
    assert ms.players[0].charge is None and ms.banner() == "HEAL!"


def test_pose_released_damage_spell_starts_at_wrist():
    cfg = copy.deepcopy(CFG0)
    cfg["game"]["default_classes"][0] = "holy_knight"
    cfg["game"]["classes"]["holy_knight"]["spells"][0].update(damage=10, travel_s=1.0)
    ms = new(cfg)
    ms.apply(charge(0, "holy_light"), STATES, 0.0)
    ms.apply(Action("pose", 0, 0.0, pose="hands_up"), STATES, 0.0)
    assert ms.projectiles[0].origin_px == STATES[0].keypoints_px["r_wrist"]


def test_basic_attack_cooldown():
    ms = new()
    ms.apply(push(0), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    assert len(ms.projectiles) == 1
    ms.advance(CFG["game"]["basic_attack_cooldown_s"], STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    # the first basic (0.7 s travel) lands during the 0.8 s cooldown wait, so count casts
    assert [e.kind for e in ms.take_events()].count("cast") == 2


def test_projectile_progress_window_and_hit():
    ms = new()
    ms.apply(push(0, speed=2.0), STATES, 0.0)
    travel = CFG["game"]["basic_attack_travel_s"]
    ms.advance(travel / 2, STATES, 0.0)
    [view] = ms.projectile_views()
    assert view.progress == pytest.approx(0.5) and view.target_slot == 1
    assert view.in_dodge_window is (travel / 2 <= CFG["game"]["dodge_window_s"])
    ms.take_events()
    ms.advance(travel / 2 + 0.001, STATES, 9.0)
    assert ms.projectiles == [] and ms.players[1].hp == pytest.approx(100 - 8.82)
    [hit] = ms.take_events()
    assert (hit.kind, hit.slot, hit.t) == ("hit", 0, 9.0)
    assert hit.data == {"spell_id": "basic", "damage": 8.8, "target": 1, "hp_left": 91.2}


def test_dodge_in_window_avoids_hit_and_before_window_does_nothing():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    ms.apply(Action("dodge", 1, 0.0, dodge="step"), STATES, 0.0)  # too early
    assert len(ms.projectiles) == 1
    ms.advance(1.6 - 0.3, STATES, 0.0)
    ms.take_events()
    ms.apply(Action("dodge", 1, 0.0, dodge="duck"), STATES, 0.0)
    assert ms.projectiles == []
    [ev] = ms.take_events()
    assert (ev.kind, ev.slot, ev.data) == ("dodge", 1, {"spell_id": "fireball", "dodge": "duck"})


def test_perfect_incantation_bonus():
    ms = new()
    ms.apply(charge(0, "fireball", score=96.0), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    ms.advance(1.61, STATES, 0.0)
    assert ms.players[1].hp == pytest.approx(100 - 18 * 1.05 * 1.05 * 1.15)


def test_ko_ends_match():
    ms = new()
    ms.players[1].hp = 5
    ms.apply(push(0), STATES, 0.0)
    ms.take_events()
    ms.advance(1.0, STATES, 3.0)
    assert ms.players[1].hp == 0 and ms.result() == (0, "ko")
    kinds = [e.kind for e in ms.take_events()]
    assert kinds == ["hit", "ko", "match_end"]


def test_time_out_winner_and_draw():
    ms = new()
    ms.players[0].hp = 50
    ms.advance(91.0, STATES, 0.0)
    assert ms.result() == (1, "time")
    draw = new()
    draw.advance(91.0, STATES, 0.0)
    assert draw.result() == (None, "time")


def test_regen_is_capped():
    ms = MatchState(CFG, NAMES, now=0.0)
    ms.players[0].mana = 90
    ms.advance(10.0, STATES, 0.0)
    assert ms.players[0].mana == 100
