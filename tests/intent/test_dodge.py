from pathlib import Path

from magic_box.core.config import load_config
from magic_box.intent.dodge import DodgeDetector
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def st(t, x=0.6, head_y=-0.7, slot=0):
    return make_state(slot, t=t, root=(x, 0.0, 2.0), head=(x, head_y, 2.0))


def test_step_detected_once_then_rearmed():
    d = DodgeDetector(CFG)
    out = [d.update(st(t, x)) for t, x in [(0.0, 0.6), (0.1, 0.65), (0.2, 0.75), (0.3, 0.95)]]
    assert out == [None, None, None, "step"]
    assert d.update(st(0.4, 0.96)) is None  # window cleared after a report


def test_slow_drift_is_not_a_step():
    d = DodgeDetector(CFG)
    assert all(d.update(st(0.1 * i, 0.6 + 0.05 * i)) is None for i in range(20))


def test_duck_detected_and_standing_up_is_not():
    d = DodgeDetector(CFG)
    assert d.update(st(0.0, head_y=-0.7)) is None
    assert d.update(st(0.2, head_y=-0.42)) == "duck"
    d2 = DodgeDetector(CFG)
    d2.update(st(0.0, head_y=-0.4))
    assert d2.update(st(0.2, head_y=-0.7)) is None


def test_step_wins_over_duck_and_slots_are_independent():
    d = DodgeDetector(CFG)
    d.update(st(0.0))
    d.update(st(0.0, slot=1, x=-0.6))
    assert d.update(st(0.2, x=1.0, head_y=-0.3)) == "step"
    assert d.update(st(0.2, slot=1, x=-0.6)) is None


def test_out_and_back_move_is_a_step():
    d = DodgeDetector(CFG)
    out = [d.update(st(t, x)) for t, x in [(0.0, 0.6), (0.1, 0.4), (0.2, 0.7)]]
    assert out == [None, None, "step"]


def test_duck_of_exactly_the_threshold_counts_despite_float_error():
    d = DodgeDetector(CFG)
    assert CFG["intent"]["dodge_duck_m"] == 0.25 and -0.45 - -0.7 < 0.25  # float rounding
    assert d.update(st(0.0, head_y=-0.7)) is None
    assert d.update(st(0.2, head_y=-0.45)) == "duck"
