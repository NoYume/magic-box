import math

import numpy as np
import pytest

from magic_box.core.contracts import KEYPOINT_NAMES
from magic_box.perception.keypoints import PART_NAMES, SOURCES, map_keypoints, part_indices


@pytest.mark.parametrize("fmt,n", [("BODY_18", 18), ("BODY_34", 34), ("BODY_38", 38)])
def test_part_tables_cover_every_keypoint(fmt, n):
    assert len(PART_NAMES[fmt]) == n == len(set(PART_NAMES[fmt]))
    assert set(SOURCES[fmt]) == set(KEYPOINT_NAMES) == set(part_indices(fmt))


def test_known_indices():
    b34 = part_indices("BODY_34")  # the beta tracker used these on the device
    assert [
        b34[k] for k in ("pelvis", "neck", "l_shoulder", "l_wrist", "r_shoulder", "r_wrist", "head")
    ] == [
        (0,),
        (3,),
        (5,),
        (7,),
        (12,),
        (14,),
        (26,),
    ]
    b18 = part_indices("BODY_18")
    assert [b18[k] for k in ("head", "neck", "pelvis", "r_wrist", "l_wrist")] == [
        (0,),
        (1,),
        (11, 8),
        (4,),
        (7,),
    ]
    b38 = part_indices("BODY_38")
    assert [b38[k] for k in ("head", "neck", "l_wrist", "r_wrist", "l_ankle")] == [
        (5,),
        (4,),
        (16,),
        (17,),
        (22,),
    ]


def _arrays(n):
    kp3d = np.arange(n * 3, dtype=np.float32).reshape(n, 3) / 10 + 1.0
    kp2d = np.arange(n * 2, dtype=np.float32).reshape(n, 2) + 5.0
    return kp3d, kp2d


def test_map_keypoints_returns_float_tuples_by_name():
    kp3d, kp2d = _arrays(34)
    pts3, pts2 = map_keypoints("BODY_34", kp3d, kp2d)
    assert pts3["neck"] == pytest.approx(tuple(kp3d[3])) and pts2["neck"] == pytest.approx(
        tuple(kp2d[3])
    )
    assert all(type(v) is float for v in pts3["neck"] + pts2["neck"])


@pytest.mark.parametrize(
    "bad3,bad2", [((math.nan, 0, 0), None), ((math.inf, 0, 0), None), (None, (-1.0, 5.0))]
)
def test_invalid_points_are_dropped(bad3, bad2):
    kp3d, kp2d = _arrays(34)
    if bad3:
        kp3d[7] = bad3
    if bad2:
        kp2d[7] = bad2
    pts3, pts2 = map_keypoints("BODY_34", kp3d, kp2d)
    assert "l_wrist" not in pts3 and "l_wrist" not in pts2 and "r_wrist" in pts3


def test_body18_pelvis_is_the_hip_mean_and_needs_both_hips():
    kp3d, kp2d = _arrays(18)
    pts3, _ = map_keypoints("BODY_18", kp3d, kp2d)
    assert pts3["pelvis"] == pytest.approx(tuple((kp3d[11] + kp3d[8]) / 2))
    kp3d[8] = (math.nan, 0, 0)
    pts3, pts2 = map_keypoints("BODY_18", kp3d, kp2d)
    assert "pelvis" not in pts3 and "pelvis" not in pts2
