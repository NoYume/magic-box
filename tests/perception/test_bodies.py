import math
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception.bodies import SlotAssigner, filter_bodies
from tests.perception.fakes import make_body

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
HOLD = CFG["perception"]["slot_hold_s"]


def _ids(result):
    return {slot: body.id for slot, body in result.items()}


def _bound(a, t=0.0):
    a.assign([make_body(7, x=0.6), make_body(9, x=-0.6)], t)
    return a


def test_two_new_bodies_bind_by_image_x():
    assert _ids(SlotAssigner(CFG).assign([make_body(9, x=-0.6), make_body(7, x=0.6)], 0.0)) == {
        0: 7,
        1: 9,
    }


def test_ids_stick_when_players_cross():
    a = _bound(SlotAssigner(CFG))
    assert _ids(a.assign([make_body(7, x=-0.4), make_body(9, x=0.4)], 0.1)) == {0: 7, 1: 9}


@pytest.mark.parametrize("x,slot", [(0.2, 0), (-0.3, 1)])
def test_single_new_body_binds_by_side(x, slot):
    assert _ids(SlotAssigner(CFG).assign([make_body(5, x=x)], 0.0)) == {slot: 5}


def test_lost_id_is_held_then_freed():
    a = _bound(SlotAssigner(CFG))
    assert _ids(a.assign([make_body(9, x=-0.6)], HOLD / 2)) == {1: 9} and a.bound_id(0) == 7
    assert _ids(a.assign([make_body(7, x=0.6), make_body(9, x=-0.6)], HOLD * 0.8)) == {0: 7, 1: 9}
    a.assign([make_body(9, x=-0.6)], HOLD * 0.9 + HOLD + 0.01)
    assert a.bound_id(0) is None


def test_newcomer_takes_the_only_free_slot():
    a = _bound(SlotAssigner(CFG))
    a.assign([make_body(9, x=-0.6)], HOLD + 0.01)  # 7 is freed
    assert _ids(a.assign([make_body(9, x=-0.6), make_body(11, x=-0.2)], HOLD + 0.05)) == {
        0: 11,
        1: 9,
    }


def test_two_newcomers_and_one_free_slot_pick_by_that_side():
    a = SlotAssigner(CFG)
    a.assign([make_body(9, x=-0.6)], 0.0)  # 9 -> slot 1, then disappears (held)
    got = a.assign([make_body(11, x=0.5, z=2.0), make_body(12, x=-0.5, z=2.1)], 0.1)
    assert _ids(got) == {0: 11} and a.bound_id(1) == 9


def test_far_untracked_and_nan_bodies_ignored():  # Review Focus 4
    bodies = [
        make_body(1, z=4.0),
        make_body(2, tracking_ok=False),
        make_body(3, position=(math.nan, 0.0, math.nan)),
        make_body(4, position=(0.1, 0.0, math.inf)),
        make_body(5, position=(math.nan, 0.0, 2.0)),  # finite z: only isfinite catches it
        make_body(6, position=(math.inf, 0.0, 2.0)),
    ]
    assert SlotAssigner(CFG).assign(bodies, 0.0) == {}


def test_only_the_two_closest_bodies_count():
    bodies = [make_body(1, x=0.6, z=1.8), make_body(2, x=-0.6, z=2.0), make_body(3, x=0.0, z=3.0)]
    assert filter_bodies(bodies, 3.5) == [bodies[0], bodies[1]]
    assert set(_ids(SlotAssigner(CFG).assign(bodies, 0.0)).values()) == {1, 2}


def test_cam_t_rewind_does_not_break_hold():  # Review Focus 1
    a = _bound(SlotAssigner(CFG), t=10.0)
    a.assign([make_body(9, x=-0.6)], 0.5)  # the SVO looped: camera time jumped back
    a.assign([make_body(9, x=-0.6)], 0.5 + HOLD + 0.01)
    assert a.bound_id(0) is None and a.bound_id(1) == 9
