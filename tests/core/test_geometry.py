import pytest

from magic_box.core.geometry import project_point, zone_for_distance

ZONES = {"danger_max_m": 1.6, "far_min_m": 2.4}


@pytest.mark.parametrize(
    "z,zone", [(1.0, "danger"), (1.6, "neutral"), (2.0, "neutral"), (2.4, "far")]
)
def test_zone_for_distance(z, zone):
    assert zone_for_distance(z, ZONES) == zone


def test_project_point():
    assert project_point((0.0, 0.0, 2.0), 700, 700, 640, 360) == (640.0, 360.0)
    assert project_point((1.0, 0.0, 2.0), 700, 700, 640, 360) == (990.0, 360.0)
