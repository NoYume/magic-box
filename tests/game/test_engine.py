import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Action, Push
from magic_box.game.engine import Engine
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
G = CFG["game"]
UP = frozenset({"hands_up"})


def states(up=(False, False), ok=(True, True)):
    return {
        s: make_state(s, pose_flags=UP if up[s] else frozenset(), tracking_ok=ok[s]) for s in (0, 1)
    }


def run(engine, t0, t1, st, actions=(), dt=0.05):
    """Step from t0 to t1 inclusive; returns (last view, all events)."""
    events, view, t, first = [], None, t0, True
    while t <= t1 + 1e-9:
        view, ev = engine.step(list(actions) if first else [], st, t)
        events += ev
        first, t = False, t + dt
    return view, events


def to_fight(engine):
    engine.step([], states(up=(True, True)), 0.0)
    engine.provide_incantations({0: {"fireball": "a b c"}, 1: {}})
    view, events = run(engine, 0.05, G["loading_min_s"] + 0.1, states())
    assert view.scene == "fight"
    return view, events


def test_lobby_view():
    view, events = Engine(CFG).step([], states(), 0.0)
    assert (view.scene, view.banner, view.timer_s) == (
        "lobby",
        "SAY YOUR NAME · BOTH RAISE YOUR HANDS",
        None,
    )
    assert [p.name for p in view.players] == ["P1", "P2"] and events == []
    assert all(s.incantation == "" for s in view.players[0].spells)


def test_speech_sets_names_in_lobby():
    view, _ = Engine(CFG).step(
        [Action("speech", 0, 0.0, text="My name is ada lovelace!")], states(), 0.0
    )
    assert view.players[0].name == "Ada Lovelace"


def test_one_player_ready_is_not_enough():
    assert Engine(CFG).step([], states(up=(True, False)), 0.0)[0].scene == "lobby"


def test_absent_slot_is_untracked():
    view, _ = Engine(CFG).step([], {0: make_state(0)}, 0.0)
    assert (view.players[0].tracking_ok, view.players[1].tracking_ok) == (True, False)


def test_loading_countdown_then_fight_with_provided_and_fallback_incantations():
    e = Engine(CFG)
    view, _ = e.step([], states(up=(True, True)), 0.0)
    assert view.scene == "loading" and view.timer_s == pytest.approx(G["loading_min_s"])
    e.provide_incantations({0: {"fireball": "a b c"}, 1: {}})
    view, events = run(e, 0.05, G["loading_min_s"] + 0.1, states())
    assert (
        view.scene == "fight"
        and view.banner == "FIGHT!"
        and view.timer_s == pytest.approx(G["round_s"], abs=0.2)
    )
    inc0 = {s.id: s.incantation for s in view.players[0].spells}
    assert inc0["fireball"] == "a b c" and inc0["inferno"] == "let the whole sky catch fire"
    assert view.players[1].spells[0].incantation == "lightning answer my call"
    assert [ev.kind for ev in events] == ["match_start"]


def test_loading_falls_back_at_max_time():
    e = Engine(CFG)
    e.step([], states(up=(True, True)), 0.0)
    view, _ = run(e, 0.05, G["loading_max_s"] + 0.1, states(), dt=0.25)
    assert view.scene == "fight"
    assert view.players[0].spells[0].incantation == "embers of the forty acres burn"


def test_late_incantations_ignored():
    e = Engine(CFG)
    to_fight(e)
    e.provide_incantations({0: {"fireball": "late words here"}, 1: {}})
    view, _ = e.step([], states(), G["loading_min_s"] + 0.2)
    assert view.players[0].spells[0].incantation == "a b c"


def test_push_hits_opponent_and_charged_view():
    e = Engine(CFG)
    to_fight(e)
    t = G["loading_min_s"] + 0.2
    view, _ = e.step(
        [Action("charge", 0, t, spell_id="fireball", match_score=90.0, dist=2.0)], states(), t
    )
    fb = view.players[0].spells[0]
    assert fb.charged and fb.release == "push"
    view, _ = e.step(
        [Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t + 0.05
    )
    assert [p.spell_id for p in view.projectiles] == ["fireball"]
    view, events = run(e, t + 0.1, t + 2.0, states())
    assert view.players[1].hp < G["hp_max"] and "hit" in [ev.kind for ev in events]


def test_pause_freezes_projectile_and_resumes():
    cfg = copy.deepcopy(CFG)
    cfg["game"]["pause_after_s"] = 0.1  # shorter than the basic attack's flight
    e = Engine(cfg)
    to_fight(e)
    t = G["loading_min_s"] + 0.2
    e.step([Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t)
    e.step([], states(ok=(True, False)), t + 0.1)  # P2 just left
    view, _ = e.step([], states(ok=(True, False)), t + 0.3)  # gone 0.2 s > 0.1 s: paused
    assert view.banner == "STEP INTO VIEW"
    frozen, left = view.projectiles[0].progress, view.timer_s
    view, events = run(e, t + 0.35, t + 3.0, states(ok=(True, False)))
    assert view.projectiles[0].progress == pytest.approx(frozen)
    assert view.timer_s == pytest.approx(left)
    assert "hit" not in [ev.kind for ev in events]
    view, events = run(e, t + 3.05, t + 4.0, states())
    assert "hit" in [ev.kind for ev in events]


def test_ko_to_victory_chronicle_and_back_to_lobby():
    e = Engine(CFG)
    e.step([Action("speech", 0, 0.0, text="ada")], states(), 0.0)
    to_fight(e)
    e._match.players[1].hp = 1  # noqa: SLF001 (white-box shortcut to a KO)
    t = G["loading_min_s"] + 0.2
    e.step([Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t)
    view, events = run(e, t + 0.05, t + 1.0, states())
    assert view.scene == "victory" and view.banner == "ADA WINS" and view.chronicle is None
    assert view.projectiles == ()
    assert [ev.kind for ev in events][-2:] == ["ko", "match_end"]
    e.provide_chronicle("A tale.")
    t2 = t + 1.05
    view, _ = e.step([], states(up=(True, True)), t2)
    assert view.chronicle == "A tale." and view.scene == "victory"
    view, _ = e.step([], states(up=(True, True)), t2 + G["victory_min_s"])
    assert view.scene == "lobby" and view.players[0].name == "Ada"


def test_hands_held_from_victory_wait_in_lobby_and_names_can_change():
    e = Engine(CFG)
    to_fight(e)
    e._match.players[1].hp = 1  # noqa: SLF001 (white-box shortcut to a KO)
    t = G["loading_min_s"] + 0.2
    e.step([Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t)
    view, _ = run(e, t + 0.05, t + 1.0, states())
    assert view.scene == "victory"
    t2 = t + 1.05 + G["victory_min_s"]
    view, _ = run(e, t2, t2 + 2.0, states(up=(True, True)))  # hands held into the lobby
    assert view.scene == "lobby"
    t3 = t2 + 2.05
    view, _ = e.step([Action("speech", 1, t3, text="call me cy")], states(up=(True, True)), t3)
    assert view.scene == "lobby" and view.players[1].name == "Cy"
    assert e.step([], states(), t3 + 0.05)[0].scene == "lobby"  # hands down
    assert e.step([], states(up=(True, True)), t3 + 0.1)[0].scene == "loading"


def test_mic_status_reaches_player_view():
    e = Engine(CFG)
    e.provide_mic_status(1, True)
    view, _ = e.step([], states(), 0.0)
    assert (view.players[0].mic_ok, view.players[1].mic_ok) == (False, True)


def test_spell_keys_outside_fight_do_nothing():
    view, _ = Engine(CFG).step(
        [Action("charge", 0, 0.0, spell_id="fireball", match_score=100.0)], states(), 0.0
    )
    assert view.scene == "lobby" and not view.players[0].spells[0].charged
