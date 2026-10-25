from pathlib import Path

from magic_box.core.config import load_config
from magic_box.core.contracts import Action, Push, VoiceEvent
from magic_box.intent.fusion import Intent
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
THR = CFG["perception"]["push_speed_mps"]
W = CFG["intent"]["two_hand_window_s"]
PUSH = Push("R", 2.0, (300.0, 200.0))


def st(t, slot=0, push=None, vz=(0.0, 0.0), flags=(), ok=True, z=2.0):
    return make_state(
        slot,
        t=t,
        push=push,
        wrist_vz={"L": vz[0], "R": vz[1]},
        pose_flags=frozenset(flags),
        tracking_ok=ok,
        root=(0.6 if slot == 0 else -0.6, 0.0, z),
    )


def kinds(actions):
    return [(a.kind, a.slot, a.two_hand) for a in actions]


def test_single_push_released_after_window():
    it = Intent(CFG)
    assert it.update([st(1.0, push=PUSH, vz=(0.0, -2.0), z=1.8)], [], now=1.0) == []
    acts = it.update([], [], now=1.0 + W)
    assert kinds(acts) == [("push", 0, False)]
    assert acts[0].push == PUSH and acts[0].t == 1.0 and acts[0].dist == 1.8


def test_two_hand_when_other_hand_leads():
    it = Intent(CFG)
    it.update([st(0.95, vz=(-THR - 0.1, 0.0))], [], 0.95)
    assert kinds(it.update([st(1.0, push=PUSH, vz=(-0.5, -2.0))], [], 1.0)) == [("push", 0, True)]


def test_two_hand_when_other_hand_lags():
    it = Intent(CFG)
    assert it.update([st(1.0, push=PUSH, vz=(0.0, -2.0))], [], 1.0) == []
    assert kinds(it.update([st(1.05, vz=(-THR, -1.0))], [], 1.05)) == [("push", 0, True)]
    assert it.update([], [], 2.0) == []


def test_peak_speed_push_still_two_hand_when_the_other_hand_crossed_long_before():
    # Ruling 2026-10-25: Push.speed is the thrust's peak, so the push can be reported well
    # after both hands crossed. The other hand still past the threshold on the push frame counts.
    it = Intent(CFG)
    it.update([st(0.8, vz=(-THR - 0.5, -THR - 0.5))], [], 0.8)
    it.update([st(0.9, vz=(-THR - 1.0, -THR - 1.0))], [], 0.9)
    push = Push("R", 3.2, (300.0, 200.0))
    acts = it.update([st(1.0, push=push, vz=(-THR - 0.2, -3.2))], [], 1.0)
    assert kinds(acts) == [("push", 0, True)] and acts[0].push.speed == 3.2


def test_other_hand_outside_window_is_single():
    it = Intent(CFG)
    it.update([st(1.0 - W - 0.05, vz=(-THR - 1.0, 0.0))], [], 1.0 - W - 0.05)
    it.update([st(1.0, push=PUSH, vz=(0.0, -2.0))], [], 1.0)
    assert kinds(it.update([], [], 1.0 + W)) == [("push", 0, False)]
    assert it.update([st(1.0 + W + 0.05, vz=(-THR - 1.0, 0.0))], [], 1.0 + W + 0.05) == []


def test_second_push_while_pending_is_dropped():
    it = Intent(CFG)
    it.update([st(1.0, push=PUSH), st(1.03, push=PUSH)], [], 1.03)
    assert len(it.update([], [], 1.0 + W)) == 1


def test_pose_rising_edges_only():
    it = Intent(CFG)
    seq = [(), ("hands_up",), ("hands_up",), (), ("hands_up",)]
    acts = it.update([st(0.1 * i, flags=f) for i, f in enumerate(seq)], [], 0.5)
    assert [(a.kind, a.pose) for a in acts] == [("pose", "hands_up"), ("pose", "hands_up")]
    assert [a.dist for a in acts] == [2.0, 2.0]


def test_pose_edge_not_refired_after_tracking_gap():
    it = Intent(CFG)
    it.update([st(0.0, flags=("hands_up",))], [], 0.0)
    it.update([st(0.1, flags=("hands_up",), ok=False)], [], 0.1)
    assert it.update([st(0.2, flags=("hands_up",))], [], 0.2) == []


def test_charge_and_speech_from_voice_status_ignored():
    it = Intent(CFG)
    voice = [
        VoiceEvent(0, 1.1, "incantation", "embers", "fireball", 92.0),
        VoiceEvent(1, 1.1, "transcript", "my name is ada", None, 0.0),
        VoiceEvent(0, 1.1, "status", "connected", None, 0.0),
    ]
    acts = it.update([st(1.0, z=1.8)], voice, now=1.1)
    assert acts == [
        Action("charge", 0, 1.1, spell_id="fireball", match_score=92.0, dist=1.8),
        Action("speech", 1, 1.1, text="my name is ada"),
    ]


def test_untracked_states_never_act():
    it = Intent(CFG)
    it.update([st(1.0, push=PUSH, ok=False, flags=("hands_up",))], [], 1.0)
    assert it.update([], [], 2.0) == []


def test_dodge_becomes_action():
    it = Intent(CFG)
    states = [
        make_state(0, t=0.0, root=(0.6, 0.0, 2.0)),
        make_state(0, t=0.2, root=(0.95, 0.0, 2.0)),
    ]
    acts = it.update(states, [], 0.2)
    assert [(a.kind, a.dodge) for a in acts] == [("dodge", "step")]
    assert acts[0].dist == 2.0


def test_push_after_pending_deadline_releases_first_then_opens_new():
    it = Intent(CFG)
    t2 = 1.0 + W + 0.05
    acts = it.update([st(1.0, push=PUSH), st(t2, push=PUSH)], [], now=t2)
    assert [(a.kind, a.t, a.two_hand) for a in acts] == [("push", 1.0, False)]
    acts = it.update([], [], now=t2 + W)
    assert [(a.kind, a.t, a.two_hand) for a in acts] == [("push", t2, False)]
