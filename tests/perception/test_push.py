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
    assert len(pushes) == 1
    assert next(i for i, (p, _) in enumerate(out) if p) <= 5
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
    out = _run(det, [(0.0, -0.1 * i) for i in range(6)])
    assert len(_pushes(out)) == 1
    det.clear_windows()
    later = [
        det.update((6 + i) * DT, _wrists(r_dz=-0.4 - 0.1 * i), PX, 2.0) for i in range(6)
    ]  # still fast, well inside push_cooldown_s
    assert not _pushes(later)


def _punch(peak_dz_per_frame, ramp=4, hold=0, tail=12):
    """R wrist accelerates to a per-frame step, holds it, then stops."""
    z, frames = 0.0, []
    for i in range(ramp):
        z -= peak_dz_per_frame * (i + 1) / ramp
        frames.append((0.0, z))
    for _ in range(hold):
        z -= peak_dz_per_frame
        frames.append((0.0, z))
    frames += [(0.0, z)] * tail
    return frames


def test_fast_punch_reports_a_higher_speed_than_a_slow_one():
    slow = _pushes(_run(PushDetector(CFG), _punch(0.08, ramp=5, hold=3)))
    fast = _pushes(_run(PushDetector(CFG), _punch(0.2, ramp=5, hold=3)))
    assert len(slow) == len(fast) == 1
    assert fast[0].speed > slow[0].speed + 1.0
    assert fast[0].speed > 4.0


def test_speed_is_the_peak_not_the_threshold_crossing():
    pushes = _pushes(_run(PushDetector(CFG), _punch(0.2, ramp=5, hold=3)))
    assert pushes[0].speed > P["push_speed_mps"] * 2


def test_extra_latency_is_at_most_push_peak_wait():
    # accelerating the whole time, so the peak never arrives: the timeout must emit
    frames = [(0.0, -0.01 * i * i) for i in range(20)]
    out = _run(PushDetector(CFG), frames)
    fire = next(i for i, (p, _) in enumerate(out) if p)
    # detection frame: first frame where the unmodified detector would have fired
    ref = PushDetector(CFG)
    ref._peak_wait_s = 0.0
    ref_out = _run(ref, frames)
    ref_fire = next(i for i, (p, _) in enumerate(ref_out) if p)
    assert (fire - ref_fire) * DT <= P["push_peak_wait_s"] + 1e-9


def test_emits_on_the_first_falling_frame():
    out = _run(PushDetector(CFG), _punch(0.2, ramp=4, hold=0, tail=12))
    fire = next(i for i, (p, _) in enumerate(out) if p)
    speeds = [-vz["R"] for _, vz in out]
    assert speeds[fire] < speeds[fire - 1]  # the frame where the speed first fell


def test_two_quick_punches_respect_the_cooldown():
    # punch, retract, punch again: the second thrust starts inside push_cooldown_s (0.4 s)
    zs = [-0.05, -0.15, -0.35, -0.6, -0.6, -0.3, 0.0, 0.0, -0.3, -0.9, -0.9, -0.9, -0.9, -0.9]
    out = _run(PushDetector(CFG), [(0.0, z) for z in zs] + [(0.0, -0.9)] * 6)
    pushes = _pushes(out)
    assert len(pushes) == 1
    # and after the cooldown a second punch fires again
    zs2 = zs + [0.0] * 8 + [-0.05, -0.15, -0.35, -0.6, -0.6]
    assert len(_pushes(_run(PushDetector(CFG), [(0.0, z) for z in zs2]))) == 2


def test_origin_px_is_the_wrist_at_detection():
    px_seq = [{"L": (700.0, 200.0), "R": (540.0 + 10 * i, 210.0)} for i in range(20)]
    det = PushDetector(CFG)
    out = []
    for i, (ldz, rdz) in enumerate(_punch(0.2, ramp=4, hold=2)):
        out.append(det.update(i * DT, _wrists(ldz, rdz), px_seq[i], 2.0))
    push = _pushes(out)[0]
    assert push.origin_px[0] < px_seq[next(i for i, (p, _) in enumerate(out) if p)]["R"][0]


def test_reset_drops_a_pending_push():
    det = PushDetector(CFG)
    out = _run(det, _punch(0.2, ramp=5, hold=3)[:3])
    assert not _pushes(out)
    det.reset()
    assert not _pushes(_run(det, [(0.0, -0.9)] * 6))
