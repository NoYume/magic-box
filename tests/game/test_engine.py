import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Action, CheckView, ClassView, Push
from magic_box.game.engine import Engine
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
G = CFG["game"]
UP = frozenset({"hands_up"})
HOLD = G["hands_up_hold_s"]
DT = 0.05
LOBBY_BANNER = "SAY NAME · SAY FIRE, LIGHTNING OR HOLY · HANDS UP"


def states(up=(False, False), ok=(True, True)):
    return {
        s: make_state(s, pose_flags=UP if up[s] else frozenset(), tracking_ok=ok[s]) for s in (0, 1)
    }


def run(engine, t0, t1, st, actions=(), dt=DT):
    """Step from t0 to t1 inclusive; returns (last view, all events)."""
    events, view, t, first = [], None, t0, True
    while t <= t1 + 1e-9:
        view, ev = engine.step(list(actions) if first else [], st, t)
        events += ev
        first, t = False, t + dt
    return view, events


def boot(e, t=0.0):
    """Report a camera frame (as BootChecks does) and step through boot; returns the next t."""
    e.provide_camera_status(True)
    e.provide_check("camera", True)
    view, _ = run(e, t, t + G["boot_min_s"], states())
    assert view.scene == "lobby"
    return t + G["boot_min_s"] + DT


def hold_hands(e, t, up=(True, True)):
    """Hold hands up (one tick past the debounce); returns (view, events, next time)."""
    view, events = run(e, t, t + HOLD + DT, states(up=up))
    return view, events, t + HOLD + 2 * DT


def to_lobby(e):
    return boot(e)


def to_fight(e, t=None):
    """Boot, raise hands, load with one provided incantation; returns (view, events, next t)."""
    t = boot(e) if t is None else t
    view, _, t = hold_hands(e, t)
    assert view.scene == "loading"
    e.provide_incantations({0: {"fireball": "a b c"}, 1: {}})
    view, events = run(e, t, t + G["loading_min_s"] + 0.1, states())
    assert view.scene == "fight"
    return view, events, t + G["loading_min_s"] + 0.15


def ko(e, t):
    """White-box shortcut to a P1 KO win, through the KO hold; returns (view, events, next t)."""
    e._match.players[1].hp = 1  # noqa: SLF001
    e.step([Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t)
    end = t + 1.0 + G["ko_hold_s"]
    view, events = run(e, t + DT, end, states())
    assert view.scene == "victory"
    return view, events, end + DT


def ko_tick(e, t, st=None):
    """Land a KO on P2 with a basic attack; returns (KO tick view, its events, KO time)."""
    e._match.players[1].hp = 1  # noqa: SLF001
    push = Push("R", 2.0, (480.0, 300.0))
    e.step([Action("push", 0, t, push=push, dist=2.0)], st or states(), t)
    now = t
    while True:
        now += DT
        view, events = e.step([], st or states(), now)
        if any(ev.kind == "ko" for ev in events):
            return view, events, now


# -- boot ------------------------------------------------------------------


def test_starts_in_boot_with_every_check_unknown():
    view, events = Engine(CFG).step([], states(), 100.0)
    assert (view.scene, view.banner, events) == ("boot", None, [])
    assert view.timer_s == pytest.approx(G["boot_max_s"])
    assert view.checks == tuple(
        CheckView(n, False, "checking")
        for n in ("camera", "mic P1", "mic P2", "network", "api key")
    )


def test_boot_leaves_at_min_time_once_the_camera_is_ok():
    e = Engine(CFG)
    view, _ = run(e, 100.0, 100.0 + G["boot_min_s"] + 1.0, states())
    assert view.scene == "boot"  # no camera report yet
    e.provide_check("camera", True)
    assert e.step([], states(), 101.0 + G["boot_min_s"] + 0.05)[0].scene == "lobby"


def test_camera_status_alone_does_not_pass_boot():
    """The loop reports status ok before the first frame (CameraWatch's boot timeout)."""
    e = Engine(CFG)
    e.provide_camera_status(True)
    view, _ = run(e, 0.0, G["boot_max_s"] - 0.1, states(), dt=0.25)
    assert view.scene == "boot"
    assert view.checks[0] == CheckView("camera", False, "checking")
    e.provide_check("camera", True)  # BootChecks: a frame arrived
    assert e.step([], states(), G["boot_max_s"] - 0.05)[0].scene == "lobby"


def test_boot_does_not_leave_before_min_time():
    e = Engine(CFG)
    e.provide_check("camera", True)
    view, _ = run(e, 0.0, G["boot_min_s"] - 0.1, states())
    assert view.scene == "boot"


def test_boot_countdown_shows_the_real_start_once_the_camera_is_ok():
    """'STARTING IN 8' must not show when boot will leave at boot_min_s."""
    e = Engine(CFG)
    view, _ = run(e, 0.0, 0.5, states())
    assert view.timer_s == pytest.approx(G["boot_max_s"] - 0.5)
    e.provide_check("camera", True)
    view, _ = e.step([], states(), 0.75)
    assert view.timer_s == pytest.approx(G["boot_min_s"] - 0.75)


def test_boot_gives_up_at_max_time_with_no_reports():
    e = Engine(CFG)
    view, _ = run(e, 0.0, G["boot_max_s"] - 0.1, states(), dt=0.25)
    assert view.scene == "boot"
    view, _ = e.step([], states(), G["boot_max_s"])
    assert view.scene == "lobby"


def test_checks_from_reports_and_mic_status():
    e = Engine(CFG)
    e.provide_check("network", True, "wifi")
    e.provide_check("api key", False, "no META_MODEL_API_KEY")
    e.provide_mic_status(1, True)
    e.provide_check("mic P1", False, "no mic")
    e.provide_mic_status(0, False)  # same ok: keeps the richer detail
    e.provide_camera_status(False)
    e.provide_check("svo", True, "playback")
    view, _ = e.step([], states(), 0.0)
    assert view.checks == (
        CheckView("camera", False, "no frames"),
        CheckView("mic P1", False, "no mic"),
        CheckView("mic P2", True, "connected"),
        CheckView("network", True, "wifi"),
        CheckView("api key", False, "no META_MODEL_API_KEY"),
        CheckView("svo", True, "playback"),
    )
    e.provide_camera_status(True)  # a status never makes the line ok
    assert e.step([], states(), 0.05)[0].checks[0] == CheckView("camera", False, "no frames")
    e.provide_check("camera", True)  # BootChecks: a frame arrived
    assert e.step([], states(), 0.1)[0].checks[0] == CheckView("camera", True, "")


def test_perception_dying_at_startup_does_not_pass_boot_on_a_later_ok_status():
    e = Engine(CFG)
    e.provide_camera_status(False)  # perception died before the first frame
    run(e, 0.0, 1.0, states(), dt=0.25)
    e.provide_camera_status(True)  # restarted, still no frame
    view, _ = run(e, 1.25, G["boot_max_s"] - 0.25, states(), dt=0.25)
    assert view.scene == "boot"
    assert view.checks[0] == CheckView("camera", False, "no frames")
    e.provide_check("camera", True)  # BootChecks re-reports once a frame arrives
    assert e.step([], states(), G["boot_max_s"] - 0.2)[0].scene == "lobby"


def test_camera_outage_after_a_frame_leaves_the_camera_line_ok():
    e = Engine(CFG)
    t = boot(e)
    e.provide_camera_status(False)
    view, _ = e.step([], states(), t)
    assert view.banner == "CAMERA RECONNECTING"
    assert view.checks[0] == CheckView("camera", True, "")  # frames were seen; not stale later


def test_camera_check_counts_for_boot():
    e = Engine(CFG)
    e.provide_check("camera", True, "ZED X SVGA")
    view, _ = run(e, 0.0, G["boot_min_s"], states())
    assert view.scene == "lobby"


# -- lobby -----------------------------------------------------------------


def test_lobby_view():
    e = Engine(CFG)
    view, _ = e.step([], states(), to_lobby(e))
    assert (view.scene, view.banner, view.timer_s, view.winner_slot) == (
        "lobby",
        LOBBY_BANNER,
        None,
        None,
    )
    assert [p.name for p in view.players] == ["P1", "P2"]
    assert [p.class_id for p in view.players] == ["fire_mage", "lightning_mage"]
    assert all(s.incantation == "" for s in view.players[0].spells)
    assert view.classes == (
        ClassView("fire_mage", "Fire Mage", ("Fireball", "Flame Wall", "Inferno")),
        ClassView("lightning_mage", "Lightning Mage", ("Bolt", "Chain", "Static Field")),
        ClassView("holy_knight", "Holy Knight", ("Holy Light", "Heal", "Judgment")),
    )
    assert all(p.stats == {} and p.effects == () for p in view.players)


def speak(e, t, slot, text):
    return e.step([Action("speech", slot, t, text=text)], states(), t)[0]


def test_speech_sets_names_in_lobby():
    e = Engine(CFG)
    view = speak(e, to_lobby(e), 0, "My name is ada lovelace!")
    assert view.players[0].name == "Ada Lovelace"
    assert view.players[0].heard == "My name is ada lovelace!" and view.players[1].heard == ""


@pytest.mark.parametrize(
    "text,class_id,name",
    [
        ("fire", "fire_mage", "P1"),
        ("Holy!", "holy_knight", "P1"),
        ("I want to be a knight", "holy_knight", "P1"),
        ("lightning please", "lightning_mage", "P1"),
        ("fire, no wait, lightning", "lightning_mage", "P1"),
        ("call me Cy", "fire_mage", "Cy"),
        ("i am bo", "fire_mage", "Bo"),
        ("firefly", "fire_mage", "Firefly"),  # whole words only
        ("My name is Ada, fire", "fire_mage", "Ada"),
        ("my name is ada and i pick holy", "holy_knight", "Ada"),
        ("call me Bo the lightning mage", "lightning_mage", "Bo"),
        ("this is Cy playing lightning", "lightning_mage", "P1"),  # "this is": no prefix
        ("so what do I do now", "fire_mage", "P1"),
        ("hi my name is ada", "fire_mage", "Ada"),
        ("I'm ready", "fire_mage", "P1"),
        ("I am a fire mage", "fire_mage", "P1"),
        ("my name is knight", "holy_knight", "P1"),  # the name is the keyword: class only
    ],
)
def test_lobby_speech_picks_class_by_keyword_else_name(text, class_id, name):
    e = Engine(CFG)
    view = speak(e, to_lobby(e), 0, text)
    assert (view.players[0].class_id, view.players[0].name) == (class_id, name)
    assert view.players[1].class_id == "lightning_mage"


def test_lobby_chatter_keeps_the_name():
    e = Engine(CFG)
    t = to_lobby(e)
    speak(e, t, 0, "call me ada")
    for i, chatter in enumerate(["so what do I do now", "this is cool", "hello", "I'm ready"]):
        view = speak(e, t + (i + 1) * DT, 0, chatter)
        assert view.players[0].name == "Ada" and view.players[0].heard == chatter


def test_keyword_as_name_keeps_the_old_name():
    e = Engine(CFG)
    t = to_lobby(e)
    speak(e, t, 1, "call me cy")
    view = speak(e, t + DT, 1, "my name is knight")
    assert (view.players[1].name, view.players[1].class_id) == ("Cy", "holy_knight")


def test_picked_class_is_used_for_the_match():
    e = Engine(CFG)
    t = to_lobby(e)
    speak(e, t, 0, "holy")
    speak(e, t + DT, 1, "fire")
    view, events, t = to_fight(e, t + 2 * DT)
    assert [p.class_id for p in view.players] == ["holy_knight", "fire_mage"]
    assert [s.id for s in view.players[0].spells] == ["holy_light", "heal", "judgment"]
    assert view.players[0].spells[0].incantation == "light of the tower guide my blade"
    assert view.players[1].spells[0].incantation == "ignite the longhorn flame"
    [start] = [ev for ev in events if ev.kind == "match_start"]
    assert start.data["classes"] == {0: "holy_knight", 1: "fire_mage"}


def test_speech_outside_lobby_is_only_heard():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    view = speak(e, t, 0, "lightning")
    assert view.players[0].class_id == "fire_mage" and view.players[0].heard == "lightning"


def test_one_player_ready_is_not_enough():
    e = Engine(CFG)
    view, _, _ = hold_hands(e, to_lobby(e), up=(True, False))
    assert view.scene == "lobby"
    assert (view.players[0].ready, view.players[1].ready) == (True, False)


def test_hands_up_must_be_held_to_start():
    e = Engine(CFG)
    t = to_lobby(e)
    view, _ = run(e, t, t + HOLD - DT, states(up=(True, True)))
    assert view.scene == "lobby" and not view.players[0].ready
    view, _ = e.step([], states(), t + HOLD)  # a flicker down restarts the hold
    view, _ = run(e, t + HOLD + DT, t + 2 * HOLD, states(up=(True, True)))
    assert view.scene == "lobby"
    view, _ = run(e, t + 2 * HOLD + DT, t + 2 * HOLD + 2 * DT, states(up=(True, True)))
    assert view.scene == "loading"
    assert not view.players[0].ready  # ready shows in lobby and victory only


def test_absent_slot_is_untracked():
    e = Engine(CFG)
    view, _ = e.step([], {0: make_state(0)}, to_lobby(e))
    assert (view.players[0].tracking_ok, view.players[1].tracking_ok) == (True, False)


def test_mic_status_reaches_player_view():
    e = Engine(CFG)
    e.provide_mic_status(1, True)
    view, _ = e.step([], states(), 0.0)
    assert (view.players[0].mic_ok, view.players[1].mic_ok) == (False, True)


def test_spell_keys_outside_fight_do_nothing():
    e = Engine(CFG)
    t = to_lobby(e)
    view, _ = e.step([Action("charge", 0, t, spell_id="fireball", match_score=100.0)], states(), t)
    assert view.scene == "lobby" and not view.players[0].spells[0].charged


# -- loading and fight -----------------------------------------------------


def test_loading_countdown_then_fight_with_provided_and_fallback_incantations():
    e = Engine(CFG)
    view, _, t = hold_hands(e, to_lobby(e))
    assert view.scene == "loading"
    assert G["loading_min_s"] - DT - 1e-9 <= view.timer_s <= G["loading_min_s"]
    e.provide_incantations({0: {"fireball": "a b c"}, 1: {}})
    view, events = run(e, t, t + G["loading_min_s"], states())
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
    _, _, t = hold_hands(e, to_lobby(e))
    view, _ = run(e, t, t + G["loading_max_s"] + 0.1, states(), dt=0.25)
    assert view.scene == "fight"
    assert view.players[0].spells[0].incantation == "embers of the forty acres burn"


def test_late_incantations_ignored():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    e.provide_incantations({0: {"fireball": "late words here"}, 1: {}})
    view, _ = e.step([], states(), t)
    assert view.players[0].spells[0].incantation == "a b c"


def test_push_hits_opponent_and_charged_view():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    view, _ = e.step(
        [Action("charge", 0, t, spell_id="fireball", match_score=90.0, dist=2.0)], states(), t
    )
    fb = view.players[0].spells[0]
    assert fb.charged and fb.release == "push"
    assert view.players[0].charge_s == pytest.approx(G["charge_window_s"] - DT)  # dt ticked
    view, events = e.step(
        [Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t + DT
    )
    assert [p.spell_id for p in view.projectiles] == ["fireball"]
    assert view.events == tuple(events) and [ev.kind for ev in events] == ["cast"]
    assert view.players[0].charge_s == 0
    view, events = run(e, t + 0.1, t + 2.0, states())
    assert view.players[1].hp < G["hp_max"] and "hit" in [ev.kind for ev in events]
    stats = view.players[0].stats
    assert stats["casts"] == 1 and stats["hits"] == 1 and stats["best_push_mps"] == 2.0
    assert stats["damage"] == pytest.approx(G["hp_max"] - view.players[1].hp, abs=0.05)


def test_basic_attack_cooldown_in_view():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    view, _ = e.step(
        [Action("push", 1, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t
    )
    assert view.players[1].cooldown_s == pytest.approx(G["basic_attack_cooldown_s"] - DT)
    assert view.players[0].cooldown_s == 0


def test_effects_show_in_player_view():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    e.step([Action("charge", 0, t, spell_id="flame_wall", match_score=90.0, dist=2.0)], states(), t)
    push = Push("R", 2.0, (480.0, 300.0))
    view, events = e.step(
        [Action("push", 0, t, push=push, two_hand=True, dist=2.0)], states(), t + DT
    )
    assert [ev.kind for ev in events] == ["cast", "buff"]
    [fx] = view.players[0].effects
    assert fx.kind == "shield" and fx.remaining_s == pytest.approx(4.0 - DT)


def test_pause_freezes_projectile_and_resumes():
    cfg = copy.deepcopy(CFG)
    cfg["game"]["pause_after_s"] = 0.1  # shorter than the basic attack's flight
    e = Engine(cfg)
    _, _, t = to_fight(e)
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


# -- abandon ---------------------------------------------------------------


def test_abandon_after_a_long_pause_gives_the_tracked_player_the_win():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    gone = states(ok=(True, False))
    end = t + G["pause_after_s"] + G["abandon_after_s"]
    view, events = run(e, t, end - 0.2, gone, dt=0.1)
    assert view.scene == "fight" and view.banner == "STEP INTO VIEW"
    view, events = run(e, end - 0.1, end + 0.3, gone, dt=0.1)
    assert view.scene == "victory" and view.winner_slot == 0 and view.banner == "P1 WINS"
    [end_ev] = [ev for ev in events if ev.kind == "match_end"]
    assert end_ev.data["reason"] == "abandon" and end_ev.data["winner"] == 0


def test_abandon_with_both_gone_is_a_draw():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    end = t + G["pause_after_s"] + G["abandon_after_s"] + 0.5
    view, _ = run(e, t, end, states(ok=(False, False)), dt=0.1)
    assert view.scene == "victory" and view.winner_slot is None and view.banner == "DRAW"


def test_returning_before_abandon_resumes_the_match():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    mid = t + G["pause_after_s"] + G["abandon_after_s"] - 1.0
    run(e, t, mid, states(ok=(True, False)), dt=0.1)
    view, _ = run(e, mid + 0.1, mid + 0.5, states(), dt=0.1)
    assert view.scene == "fight" and view.banner is None
    view, _ = run(e, mid + 0.6, mid + G["pause_after_s"] + 1.5, states(ok=(True, False)), dt=0.1)
    assert view.scene == "fight"  # the abandon clock started over


# -- camera ----------------------------------------------------------------


def test_camera_reconnecting_freezes_the_fight_and_never_abandons():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    e.step([Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t)
    e.provide_camera_status(False)
    view, _ = e.step([], states(ok=(False, False)), t + DT)
    assert view.banner == "CAMERA RECONNECTING"
    frozen, left = view.projectiles[0].progress, view.timer_s
    view, events = run(e, t + 0.1, t + 40.0, states(ok=(False, False)), dt=0.25)
    assert view.scene == "fight" and view.banner == "CAMERA RECONNECTING"
    assert view.projectiles[0].progress == pytest.approx(frozen)
    assert view.timer_s == pytest.approx(left)
    assert events == []
    e.provide_camera_status(True)
    view, events = run(e, t + 40.05, t + 41.0, states())
    assert view.banner is None and "hit" in [ev.kind for ev in events]


def test_camera_recovery_pauses_whoever_is_still_untracked_at_once():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    e.provide_camera_status(False)
    run(e, t, t + 5.0, states(ok=(False, False)), dt=0.25)
    e.provide_camera_status(True)
    rec = t + 5.25
    view, _ = e.step([], states(ok=(True, False)), rec)  # P2 not re-acquired yet
    assert view.banner == "STEP INTO VIEW"
    left = view.timer_s
    view, _ = run(
        e, rec + 0.25, rec + G["abandon_after_s"] - 0.25, states(ok=(True, False)), dt=0.25
    )
    assert view.scene == "fight" and view.timer_s == pytest.approx(left)
    view, events = e.step([], states(ok=(True, False)), rec + G["abandon_after_s"])
    assert view.scene == "victory" and view.winner_slot == 0  # abandon timed from recovery
    assert [ev.data["reason"] for ev in events if ev.kind == "match_end"] == ["abandon"]


def test_camera_recovery_resumes_once_both_are_tracked_again():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    e.provide_camera_status(False)
    run(e, t, t + 1.0, states(ok=(False, False)), dt=0.25)
    e.provide_camera_status(True)
    view, _ = e.step([], states(ok=(False, False)), t + 1.25)
    assert view.banner == "STEP INTO VIEW"
    view, _ = e.step([], states(ok=(True, False)), t + 1.5)
    assert view.banner == "STEP INTO VIEW"
    left = view.timer_s
    view, _ = e.step([], states(), t + 1.75)  # both seen: the clock runs again
    assert view.banner != "STEP INTO VIEW"
    assert view.timer_s == pytest.approx(left - 0.25)


def test_camera_recovery_with_both_tracked_does_not_pause():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    e.provide_camera_status(False)
    run(e, t, t + 1.0, states(ok=(False, False)), dt=0.25)
    e.provide_camera_status(True)
    view, _ = e.step([], states(), t + 1.25)
    assert view.banner not in ("STEP INTO VIEW", "CAMERA RECONNECTING")


def test_camera_reconnecting_banner_in_lobby():
    e = Engine(CFG)
    t = to_lobby(e)
    e.provide_camera_status(False)
    assert e.step([], states(), t)[0].banner == "CAMERA RECONNECTING"
    e.provide_camera_status(True)
    assert e.step([], states(), t + DT)[0].banner == LOBBY_BANNER


# -- victory ---------------------------------------------------------------


def test_ko_to_victory_chronicle_and_back_to_lobby():
    e = Engine(CFG)
    t = to_lobby(e)
    speak(e, t, 0, "ada")
    _, _, t = to_fight(e, t + DT)
    view, events, t = ko(e, t)
    assert view.banner == "ADA WINS" and view.winner_slot == 0 and view.chronicle is None
    assert view.projectiles == () and view.players[0].stats["hits"] == 1
    assert [ev.kind for ev in events][-2:] == ["ko", "match_end"]
    e.provide_chronicle("A tale.")
    view, _ = e.step([], states(up=(True, True)), t)
    assert view.chronicle == "A tale." and view.scene == "victory"
    t2 = t + G["victory_min_s"]
    view, _ = e.step([], states(up=(True, True)), t2)  # held since t: counts
    assert view.scene == "lobby" and view.players[0].name == "Ada"
    assert view.winner_slot is None and view.players[0].stats == {}


def test_ko_holds_the_fight_scene_then_goes_to_victory():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    view, events, t_ko = ko_tick(e, t)
    assert view.scene == "fight" and view.events == tuple(events)
    assert [ev.kind for ev in events][-2:] == ["ko", "match_end"]
    assert view.winner_slot == 0 and view.projectiles == ()
    hold = G["ko_hold_s"]
    view, later = run(e, t_ko + DT, t_ko + hold - DT, states())
    assert view.scene == "fight" and later == []
    view, later = e.step([], states(), t_ko + hold + 1e-6)  # float slack on the boundary
    assert view.scene == "victory" and view.banner == "P1 WINS" and view.winner_slot == 0
    assert [ev.kind for ev in later] == []  # ko and match_end fired once, on the KO tick


def test_ko_hold_freezes_the_match():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    e._match.players[0].mana = 40.0  # noqa: SLF001
    e.step([Action("charge", 1, t, spell_id="bolt", match_score=90.0, dist=2.0)], states(), t)
    view, _, t_ko = ko_tick(e, t + DT)
    hp, mana, left = [p.hp for p in view.players], [p.mana for p in view.players], view.timer_s
    push = Push("R", 3.0, (480.0, 300.0))
    acts = [
        Action("push", 1, t_ko, push=push, dist=2.0),
        Action("charge", 0, t_ko, spell_id="fireball", match_score=90.0, dist=2.0),
    ]
    view, events = run(e, t_ko + DT, t_ko + G["ko_hold_s"] - DT, states(), actions=acts)
    assert view.scene == "fight" and events == [] and view.projectiles == ()
    assert [p.hp for p in view.players] == hp and [p.mana for p in view.players] == mana
    assert view.timer_s == left and not view.players[0].spells[0].charged


def test_ko_hold_ignores_pause_abandon_and_camera():
    cfg = copy.deepcopy(CFG)
    cfg["game"]["ko_hold_s"] = 30.0  # longer than pause_after_s + abandon_after_s
    e = Engine(cfg)
    _, _, t = to_fight(e)
    _, _, t_ko = ko_tick(e, t)
    e.provide_camera_status(False)
    view, events = run(e, t_ko + DT, t_ko + 29.0, states(ok=(False, False)), dt=0.25)
    assert view.scene == "fight" and events == []
    assert view.banner not in ("STEP INTO VIEW", "CAMERA RECONNECTING")
    view, _ = e.step([], states(ok=(False, False)), t_ko + 30.0)
    assert view.scene == "victory" and view.winner_slot == 0


def test_time_out_goes_to_victory_without_a_hold():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    e._match.time_left = 0.01  # noqa: SLF001
    view, events = e.step([], states(), t)
    assert view.scene == "victory" and "match_end" in [ev.kind for ev in events]


def test_ko_hold_0_goes_to_victory_on_the_ko_tick():
    cfg = copy.deepcopy(CFG)
    cfg["game"]["ko_hold_s"] = 0.0
    e = Engine(cfg)
    _, _, t = to_fight(e)
    view, events, _ = ko_tick(e, t)
    assert view.scene == "victory" and [ev.kind for ev in events][-2:] == ["ko", "match_end"]


def test_victory_hands_up_must_be_held():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    _, _, t = ko(e, t)
    t2 = t + G["victory_min_s"]
    run(e, t, t2, states())
    view, _ = e.step([], states(up=(True, True)), t2 + DT)  # a one-tick hands up
    assert view.scene == "victory" and not view.players[0].ready
    view, _ = run(e, t2 + 2 * DT, t2 + HOLD + 2 * DT, states(up=(True, True)))
    assert view.scene == "lobby"


def test_hands_held_from_victory_wait_in_lobby_and_names_can_change():
    e = Engine(CFG)
    _, _, t = to_fight(e)
    _, _, t = ko(e, t)
    t2 = t + G["victory_min_s"]
    view, _ = run(e, t, t2 + 2.0, states(up=(True, True)))  # hands held into the lobby
    assert view.scene == "lobby"
    t3 = t2 + 2.05
    view, _ = e.step([Action("speech", 1, t3, text="call me cy")], states(up=(True, True)), t3)
    assert view.scene == "lobby" and view.players[1].name == "Cy"
    view, _ = run(e, t3 + DT, t3 + HOLD + 2 * DT, states())  # hands down, held
    assert view.scene == "lobby"
    view, _, _ = hold_hands(e, t3 + HOLD + 3 * DT)
    assert view.scene == "loading"
