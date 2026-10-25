import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception.tracker import PlayerTracker
from tests.perception.fakes import make_body, make_capture

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def _one(body, **kw):
    return PlayerTracker(CFG).step(make_capture([body], **kw), 0.0)[0]


def test_two_bodies_give_two_states_in_slot_order():
    b7, b9 = make_body(7, x=0.6), make_body(9, x=-0.6)
    states = PlayerTracker(CFG).step(make_capture([b9, b7], frame_idx=4, cam_t=1.5), now=100.0)
    assert [s.slot for s in states] == [0, 1] and [s.player_id for s in states] == [7, 9]
    s = states[0]
    assert s.tracking_ok and (s.t, s.cam_t, s.frame_idx) == (100.0, 1.5, 4)
    assert s.root == b7.kp3d["pelvis"] and s.head == b7.kp3d["head"]
    assert s.wrists == {"L": b7.kp3d["l_wrist"], "R": b7.kp3d["r_wrist"]}
    assert s.zone == "neutral" and s.push is None and s.pose_flags == frozenset()
    assert s.bbox_px == b7.bbox_px and s.keypoints_px == b7.kp2d
    assert s.finger_gesture == {"L": None, "R": None} and s.wrist_vz == {"L": 0.0, "R": 0.0}


def test_partial_body_still_tracked():  # Review Focus 3: legs and pelvis out of frame
    b = make_body(7, x=0.3, z=1.0, drop=("pelvis", "l_ankle", "r_ankle", "head"))
    s = _one(b)
    assert s.tracking_ok and s.root == b.position and s.head == b.kp3d["neck"]
    assert "pelvis" not in s.keypoints_px and s.zone == "danger"


def test_wrists_hold_only_valid_points():
    s = _one(make_body(7, drop=("l_wrist",)))
    assert set(s.wrists) == {"R"} and set(s.wrist_vz) == {"L", "R"}


@pytest.mark.parametrize("z,zone", [(1.2, "danger"), (2.0, "neutral"), (3.0, "far")])
def test_zone_from_root_depth(z, zone):
    assert _one(make_body(7, z=z)).zone == zone


def test_hands_up_flag_flows_through():
    assert "hands_up" in _one(make_body(7, overrides={"r_wrist": (0.25, -1.0, 2.0)})).pose_flags


def _punch(tracker, n=8, drop=()):
    """Slot 0 punches its right wrist toward the camera at 3 m/s."""
    out = []
    for i in range(n):
        b = make_body(7, x=0.6, overrides={"r_wrist": (0.25, -0.5, 2.0 - 0.1 * i)}, drop=drop)
        out += tracker.step(make_capture([b], frame_idx=i, cam_t=i / 30), now=float(i))
    return [s.push for s in out if s.push]


def test_push_reaches_the_player_state():
    pushes = _punch(PlayerTracker(CFG))
    assert len(pushes) == 1 and pushes[0].hand == "R" and pushes[0].speed == pytest.approx(3.0)


def test_missing_neck_uses_root_for_push():
    assert len(_punch(PlayerTracker(CFG), drop=("neck",))) == 1


def test_reference_switch_does_not_fire_push():  # Review Focus 2: the neck flickers
    tracker, out = PlayerTracker(CFG), []
    for i in range(12):
        b = make_body(
            7, x=0.6, overrides={"neck": (0.6, -0.6, 1.85)}, drop=("neck",) if i % 2 else ()
        )  # the neck reads 15 cm closer than the pelvis
        out += tracker.step(make_capture([b], frame_idx=i, cam_t=i / 30), now=float(i))
    assert not any(s.push for s in out)


def test_lost_player_is_republished_untracked():
    tracker = PlayerTracker(CFG)
    tracker.step(make_capture([make_body(7, x=0.6), make_body(9, x=-0.6)]), 0.0)
    states = tracker.step(make_capture([make_body(9, x=-0.6)], frame_idx=1, cam_t=1 / 30), 1.0)
    lost = states[0]
    assert [s.slot for s in states] == [0, 1] and not lost.tracking_ok and states[1].tracking_ok
    assert (lost.t, lost.frame_idx, lost.push, lost.root_vx, lost.player_id) == (
        1.0,
        1,
        None,
        0.0,
        7,
    )
    assert lost.wrist_vz == {"L": 0.0, "R": 0.0}


def test_a_slot_never_seen_publishes_nothing():
    assert [s.slot for s in PlayerTracker(CFG).step(make_capture([make_body(9, x=-0.6)]), 0.0)] == [
        1
    ]


def test_new_id_in_a_slot_starts_fresh_history():
    cfg = copy.deepcopy(CFG)
    cfg["perception"]["slot_hold_s"] = 0.0
    tracker = PlayerTracker(cfg)
    tracker.step(make_capture([make_body(7, x=0.6)]), 0.0)
    b8 = make_body(8, x=0.6, overrides={"r_wrist": (0.25, -0.5, 1.7)})  # a different person
    s = tracker.step(make_capture([b8], frame_idx=1, cam_t=1 / 30), 1.0)[0]
    assert s.player_id == 8 and s.push is None


def test_bound_ids():
    tracker = PlayerTracker(CFG)
    tracker.step(make_capture([make_body(7, x=0.6)]), 0.0)
    assert tracker.bound_ids == {0: 7, 1: None}


def test_neck_dropping_mid_punch_fires_once():
    tracker, out = PlayerTracker(CFG), []
    for i in range(6):
        b = make_body(
            7,
            x=0.6,
            overrides={"r_wrist": (0.25, -0.5, 2.0 - 0.1 * i)},
            drop=("neck",) if i >= 3 else (),
        )
        out += tracker.step(make_capture([b], frame_idx=i, cam_t=i / 30), now=float(i))
    assert len([s for s in out if s.push]) == 1
