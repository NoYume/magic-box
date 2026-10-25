import pytest

from magic_box.perception.kinematics import WindowedVelocity


def _filled(window_s, samples):
    v = WindowedVelocity(window_s)
    for t, x in samples:
        v.add(t, x)
    return v


def test_velocity_and_travel_over_the_window():
    v = _filled(0.15, [(0.0, 0.0), (0.05, 0.1), (0.1, 0.2)])
    assert v.velocity() == pytest.approx(2.0) and v.travel() == pytest.approx(0.2)


def test_old_samples_leave_the_window():
    v = _filled(
        0.15, [(0.0, 0.0), (0.06, 0.1), (0.1, 0.2), (0.2, 0.2)]
    )  # t=0 is older than 0.2-0.15
    assert v.travel() == pytest.approx(0.1) and v.velocity() == pytest.approx(0.1 / 0.14)


def test_too_few_samples_or_zero_dt_give_zero():
    v = WindowedVelocity(0.15)
    assert v.velocity() == v.travel() == 0.0
    v.add(1.0, 5.0)
    assert v.velocity() == 0.0
    v.add(1.0, 6.0)
    assert v.velocity() == 0.0


def test_time_going_backwards_restarts_window():  # Review Focus 1: an SVO loop rewinds cam_t
    v = _filled(0.15, [(10.0, 0.0), (10.05, 0.0)])
    v.add(0.0, -1.0)
    assert v.velocity() == 0.0 and v.travel() == 0.0
    v.add(0.05, -1.0)
    assert v.velocity() == 0.0


def test_clear():
    v = _filled(0.15, [(0.0, 0.0), (0.05, 0.1)])
    v.clear()
    assert v.velocity() == 0.0
