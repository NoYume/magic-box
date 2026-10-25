from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception.motion import MotionTracker

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_root_vx_from_root_x_over_the_window():
    m = MotionTracker(CFG)
    assert m.update((0.0, 0.0, 2.0), 0.0) == 0.0
    for i in range(1, 6):
        vx = m.update((0.03 * i, 0.0, 2.0), i / 30)
    assert vx == pytest.approx(0.9)


def test_reset_forgets_history():
    m = MotionTracker(CFG)
    m.update((0.0, 0.0, 2.0), 0.0)
    m.reset()
    assert m.update((0.5, 0.0, 2.0), 1 / 30) == 0.0
