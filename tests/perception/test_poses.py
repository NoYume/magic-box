from pathlib import Path

from magic_box.core.config import load_config
from magic_box.perception.poses import detect_poses
from tests.perception.fakes import body_points

P = load_config(Path(__file__).resolve().parents[2] / "config.yaml")["perception"]
HEAD = (0.6, -0.75, 2.0)
BASE = body_points(0.6, 2.0)


def test_one_arm_overhead_is_hands_up():
    kp = BASE | {"r_wrist": (0.25, -0.75 - P["hands_up_margin_m"] - 0.01, 2.0)}
    assert detect_poses(kp, HEAD, P) == {"hands_up"}


def test_wrist_inside_the_margin_is_not_hands_up():
    kp = BASE | {"r_wrist": (0.25, -0.75 - P["hands_up_margin_m"] + 0.02, 2.0)}
    assert detect_poses(kp, HEAD, P) == frozenset()


def test_hands_together_at_the_chest():
    kp = BASE | {"l_wrist": (0.7, -0.4, 1.8), "r_wrist": (0.55, -0.4, 1.8)}
    assert detect_poses(kp, HEAD, P) == {"hands_together"}


def test_hands_together_needs_both_wrists_between_head_and_pelvis():
    overhead = BASE | {"l_wrist": (0.65, -0.9, 2.0), "r_wrist": (0.55, -0.9, 2.0)}
    low = BASE | {"l_wrist": (0.65, 0.1, 2.0), "r_wrist": (0.55, 0.1, 2.0)}
    one = {k: v for k, v in BASE.items() if k != "r_wrist"} | {"l_wrist": (0.6, -0.4, 2.0)}
    assert "hands_together" not in detect_poses(overhead, HEAD, P)
    assert detect_poses(low, HEAD, P) == frozenset()
    assert detect_poses(one, HEAD, P) == frozenset()


def test_without_a_pelvis_only_the_head_bounds_hands_together():
    kp = {k: v for k, v in BASE.items() if k != "pelvis"}
    kp |= {"l_wrist": (0.65, 0.1, 2.0), "r_wrist": (0.55, 0.1, 2.0)}
    assert detect_poses(kp, HEAD, P) == {"hands_together"}


def test_wrist_held_toward_the_camera_at_shoulder_height_is_guard():
    kp = BASE | {"r_wrist": (0.5, -0.55, 2.0 - P["guard_forward_m"] - 0.05)}
    assert detect_poses(kp, HEAD, P) == {"guard"}


def test_guard_needs_reach_and_height():
    short = BASE | {"r_wrist": (0.5, -0.55, 2.0 - P["guard_forward_m"] + 0.05)}
    low = BASE | {"r_wrist": (0.5, -0.2, 2.0 - P["guard_forward_m"] - 0.05)}
    no_neck = {k: v for k, v in BASE.items() if k != "neck"}
    no_neck |= {"r_wrist": (0.5, -0.55, 1.5)}
    assert detect_poses(short, HEAD, P) == frozenset()
    assert detect_poses(low, HEAD, P) == frozenset()
    assert "guard" not in detect_poses(no_neck, HEAD, P)
