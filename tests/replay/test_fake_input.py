from pathlib import Path

import numpy as np
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import KEYPOINT_NAMES
from magic_box.replay.fake_input import FakePlayers

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
K0 = CFG["keys"]["fake"][0]
FAKE = CFG["fake"]


def _p1(states):
    return next(s for s in states if s.slot == 0)


def test_initial_layout_p1_on_image_right():
    states, frame = FakePlayers(CFG).step(frozenset(), now=0.0, dt=0.0)
    p1, p2 = _p1(states), next(s for s in states if s.slot == 1)
    assert p1.root[0] > 0 > p2.root[0]
    assert p1.bbox_px[0] > CFG["camera"]["image_width"] / 2 > p2.bbox_px[0] + p2.bbox_px[2]
    assert (
        frame.image.shape
        == (
            CFG["camera"]["image_height"],
            CFG["camera"]["image_width"],
            4,
        )
        and frame.image.dtype == np.uint8
    )
    assert set(p1.keypoints_px) == set(KEYPOINT_NAMES) and p1.tracking_ok


def test_closer_moves_toward_camera_and_grows():
    fp = FakePlayers(CFG)
    before = _p1(fp.step(frozenset(), 0.0, 0.0)[0])
    for i in range(10):
        states, _ = fp.step(frozenset({K0["closer"]}), now=0.1 * (i + 1), dt=0.1)
    assert _p1(states).root[2] == pytest.approx(FAKE["start_z_m"] - FAKE["move_speed_mps"])
    assert _p1(states).bbox_px[3] > before.bbox_px[3]


def test_distance_clamped():
    fp = FakePlayers(CFG)
    for i in range(100):
        states, _ = fp.step(frozenset({K0["farther"]}), now=0.1 * i, dt=0.1)
    assert _p1(states).root[2] == pytest.approx(FAKE["max_z_m"])


def test_push_is_edge_triggered():
    fp = FakePlayers(CFG)
    first = _p1(fp.step(frozenset({K0["push"]}), 0.0, 0.016)[0])
    held = _p1(fp.step(frozenset({K0["push"]}), 0.016, 0.016)[0])
    assert first.push is not None and first.push.speed == FAKE["push_speed_mps"]
    assert first.wrist_vz["R"] < 0
    assert held.push is None


def test_duck_and_pose_flags():
    fp = FakePlayers(CFG)
    start = _p1(fp.step(frozenset(), 0.0, 0.0)[0])
    s = _p1(fp.step(frozenset({K0["duck"], K0["hands_up"]}), 0.1, 0.1)[0])
    assert s.head[1] == pytest.approx(start.head[1] + FAKE["duck_m"])
    assert "hands_up" in s.pose_flags


def test_frame_idx_and_time_advance():
    fp = FakePlayers(CFG)
    s0, f0 = fp.step(frozenset(), 0.0, 0.0)
    s1, f1 = fp.step(frozenset(), 0.5, 0.5)
    assert (f0.frame_idx, f1.frame_idx) == (0, 1)
    assert _p1(s1).frame_idx == 1 and _p1(s1).t == 0.5


def test_two_hand_key_pushes_with_both_wrists():
    fp = FakePlayers(CFG)
    states, _ = fp.step(frozenset({K0["two_hand_push"]}), now=0.0, dt=0.016)
    p1 = _p1(states)
    assert p1.push is not None
    assert p1.wrist_vz == {"L": -FAKE["push_speed_mps"], "R": -FAKE["push_speed_mps"]}
    states, _ = fp.step(frozenset({K0["two_hand_push"]}), now=0.016, dt=0.016)
    assert _p1(states).push is None  # edge-triggered


def test_each_frame_is_a_fresh_buffer_on_the_background():
    fp = FakePlayers(CFG)
    _, first = fp.step(frozenset(), 0.0, 0.0)
    first.image[0, 0] = (1, 2, 3, 4)  # the window may still hold the previous frame
    _, second = fp.step(frozenset(), 1 / 60, 1 / 60)
    assert second.image is not first.image
    bg = tuple(reversed(CFG["render"]["background_rgb"])) + (255,)
    assert tuple(second.image[0, 0]) == bg


def test_guard_key_holds_right_wrist_toward_camera():
    fp = FakePlayers(CFG)
    p1 = _p1(fp.step(frozenset({K0["guard"]}), now=0.0, dt=0.0)[0])
    assert "guard" in p1.pose_flags
    assert p1.wrists["R"][2] == pytest.approx(FAKE["start_z_m"] - FAKE["guard_reach_m"])
    assert "guard" not in _p1(fp.step(frozenset(), now=0.1, dt=0.1)[0]).pose_flags
