from pathlib import Path

import numpy as np
import pytest

from magic_box.core.config import load_config
from magic_box.perception.webcam_source import WebcamPoseEstimator, _anchors

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_mediapipe_anchor_layout():
    anchors = _anchors()
    assert anchors.shape == (2254, 2)
    assert tuple(anchors[0]) == tuple(anchors[1])
    assert np.all((anchors > 0) & (anchors < 1))


def test_pose_landmarks_become_approximate_metric_body():
    estimator = WebcamPoseEstimator.__new__(WebcamPoseEstimator)
    estimator._landmark_threshold = 0.45
    estimator._shoulder_m = 0.38
    estimator._focal = 525.0
    estimator._min_z = 0.8
    estimator._max_z = 3.5
    landmarks = np.zeros((39, 5), dtype=np.float32)
    world = np.zeros((39, 3), dtype=np.float32)
    coords = {
        0: (480, 100),
        11: (430, 200),
        12: (530, 200),
        15: (380, 300),
        16: (580, 300),
        23: (450, 400),
        24: (510, 400),
        27: (440, 580),
        28: (520, 580),
    }
    for index, xy in coords.items():
        landmarks[index, :2] = xy
        landmarks[index, 3:] = 0.9
    world[15, 2] = -0.2
    body = estimator._raw_body((landmarks, world, 0.8), 960, 600)
    assert body is not None
    assert body.position[2] == pytest.approx(525 * 0.38 / 100)
    assert body.kp3d["l_wrist"][2] < body.kp3d["neck"][2]
    assert {"head", "neck", "pelvis", "l_wrist", "r_wrist"} <= body.kp2d.keys()
