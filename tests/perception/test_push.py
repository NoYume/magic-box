from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception.push import PushDetector

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
P = CFG["perception"]
DT = 1 / 30
PX = {"L": (700.0, 200.0), "R": (540.0, 210.0)}


def _wrists(l_dz=0.0, r_dz=0.0, z=2.0):
    return {"L": (0.95, -0.5, z + l_dz), "R": (0.25, -0.5, z + r_dz)}


def _run(det, frames, ref_z=2.0):
    """frames: (l_dz, r_dz) per camera frame -> [(push, wrist_vz)]."""
    return [det.update(i * DT, _wrists(ldz, rdz), PX, ref_z) for i, (ldz, rdz) in enumerate(frames)]


def _pushes(out):
    return [p for p, _ in out if p]


def test_fast_push_fires_once():
    out = _run(PushDetector(CFG), [(0.0, -0.1 * i) for i in range(8)] + [(0.0, -0.7)] * 10)
    pushes = _pushes(out)
    assert len(pushes) == 1 and out[2][0] is pushes[0]  # fires once travel passes 0.12 m
    assert pushes[0].hand == "R" and pushes[0].speed == pytest.approx(3.0)
    assert pushes[0].origin_px == PX["R"]


def test_slow_reach_does_not_fire():
    out = _run(PushDetector(CFG), [(0.0, -0.02 * i) for i in range(15)])
    assert not _pushes(out) and out[-1][1]["R"] == pytest.approx(-0.6)


def test_walking_toward_the_camera_does_not_fire():
    det = PushDetector(CFG)
    out = [det.update(i * DT, _wrists(z=2.0 - 0.1 * i), PX, 2.0 - 0.1 * i) for i in range(10)]
    assert not _pushes(out) and out[-1][1] == {"L": 0.0, "R": 0.0}


def test_one_long_push_fires_once_even_past_the_cooldown():
    assert len(_pushes(_run(PushDetector(CFG), [(0.0, -0.1 * i) for i in range(20)]))) == 1


def test_fires_again_after_rearm_and_cooldown():
    frames = [(0.0, -0.1 * i) for i in range(8)] + [(0.0, -0.7)] * 20
    frames += [(0.0, -0.7 - 0.1 * i) for i in range(8)]
    assert len(_pushes(_run(PushDetector(CFG), frames))) == 2


def test_cooldown_spans_both_hands():
    frames = [(0.0, -0.1 * i) for i in range(4)] + [(-0.1 * i, -0.3) for i in range(1, 6)]
    assert [p.hand for p in _pushes(_run(PushDetector(CFG), frames))] == ["R"]


def test_other_hand_fires_after_the_cooldown():
    frames = [(0.0, -0.1 * i) for i in range(4)] + [(0.0, -0.3)] * 12
    frames += [(-0.1 * i, -0.3) for i in range(8)]
    assert [p.hand for p in _pushes(_run(PushDetector(CFG), frames))] == ["R", "L"]


def test_both_hands_on_one_frame_report_the_faster_and_both_disarm():
    out = _run(PushDetector(CFG), [(-0.13 * i, -0.15 * i) for i in range(20)])
    hits = [(p, vz) for p, vz in out if p]
    assert len(hits) == 1
    push, vz = hits[0]
    assert push.hand == "R" and vz["L"] < -P["push_speed_mps"] and vz["R"] < -P["push_speed_mps"]


def test_missing_wrist_adds_no_sample_and_both_keys_present():
    det = PushDetector(CFG)
    push, vz = det.update(0.0, {"L": (0.9, -0.5, 2.0)}, {"L": (700.0, 200.0)}, 2.0)
    assert push is None and vz == {"L": 0.0, "R": 0.0}
    assert det.update(DT, {}, {}, 2.0)[1] == {"L": 0.0, "R": 0.0}


def test_reset_forgets_history():
    det = PushDetector(CFG)
    det.update(0.0, _wrists(), PX, 2.0)
    det.reset()
    assert det.update(DT, _wrists(r_dz=-0.3), PX, 2.0)[0] is None


def test_cam_t_rewind_does_not_lock_out_pushes():
    det = PushDetector(CFG)
    fired = []
    # push near t=5 s, then camera time rewinds to 0 (SVO loop), rest, push again
    segments = [
        (5.0, [(0.0, -0.1 * i) for i in range(8)] + [(0.0, -0.7)] * 5),
        (0.0, [(0.0, -0.7)] * 20),
        (0.0 + 20 * DT, [(0.0, -0.1 * i) for i in range(8)]),
    ]
    for start, frames in segments:
        out = [
            det.update(start + i * DT, _wrists(ldz, rdz), PX, 2.0)
            for i, (ldz, rdz) in enumerate(frames)
        ]
        fired.append(len(_pushes(out)))
    assert fired == [1, 0, 1]


def test_clear_windows_keeps_cooldown_and_arming():
    det = PushDetector(CFG)
    out = _run(det, [(0.0, -0.1 * i) for i in range(4)])
    assert len(_pushes(out)) == 1
    det.clear_windows()
    later = [
        det.update((4 + i) * DT, _wrists(r_dz=-0.4 - 0.1 * i), PX, 2.0) for i in range(6)
    ]  # still fast, well inside push_cooldown_s
    assert not _pushes(later)
