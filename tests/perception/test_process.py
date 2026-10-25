import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception import process
from magic_box.perception.process import run_loop
from magic_box.perception.tracker import PlayerTracker
from magic_box.perception.zed_source import CameraError
from tests.perception.fakes import (
    FakeBus,
    FakeSource,
    FakeStop,
    ListQueue,
    make_body,
    make_capture,
)

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
RETRY = CFG["perception"]["open_retry_s"]


def _cfg(**perception):
    cfg = copy.deepcopy(CFG)
    cfg["perception"].update(perception)
    return cfg


def _loop(src, stop, cfg=CFG, tracker=None, logs=None, clock=None):
    events = []
    kw = {"clock": clock} if clock else {}
    run_loop(
        src,
        tracker or PlayerTracker(cfg),
        lambda f: events.append(("frame", f.frame_idx)),
        lambda s: events.append(("state", s.slot)),
        stop,
        cfg,
        log=(logs.append if logs is not None else lambda m: None),
        **kw,
    )
    return events


def test_frame_is_written_before_its_states():
    stop = FakeStop()
    cap = make_capture([make_body(7, x=0.6), make_body(9, x=-0.6)], frame_idx=3)
    assert _loop(FakeSource(stop, [cap]), stop) == [("frame", 3), ("state", 0), ("state", 1)]


def test_open_retries_after_camera_error():
    stop, logs = FakeStop(), []
    src = FakeSource(stop, [make_capture([])], opens=[CameraError("not detected")] * 2 + [None])
    _loop(src, stop, logs=logs)
    assert src.open_calls == 3 and stop.waits == [RETRY, RETRY]
    assert sum("not detected" in m for m in logs) == 2
    assert any(m.startswith("opened ZED_X serial 1 960x600@30") for m in logs)


def test_reopens_after_max_grab_failures():
    stop = FakeStop()
    src = FakeSource(stop, [None, None, None, make_capture([], frame_idx=1)])
    assert _loop(src, stop, cfg=_cfg(max_grab_failures=3)) == [("frame", 1)]
    assert (src.open_calls, src.close_calls) == (2, 1)


def test_failure_count_resets_after_a_good_grab():
    stop = FakeStop()
    grabs = [None, None, make_capture([]), None, None, make_capture([], frame_idx=1)]
    src = FakeSource(stop, grabs)
    _loop(src, stop, cfg=_cfg(max_grab_failures=3))
    assert (src.open_calls, src.close_calls) == (1, 0)


def test_camera_lost_mid_run_retries_until_back():  # Review Focus 5
    stop = FakeStop()
    grabs = [make_capture([]), None, None, make_capture([], frame_idx=1)]
    src = FakeSource(stop, grabs, opens=[None, CameraError("gone"), CameraError("gone"), None])
    assert _loop(src, stop, cfg=_cfg(max_grab_failures=2)) == [("frame", 0), ("frame", 1)]
    assert src.open_calls == 4 and stop.waits == [RETRY, RETRY]


def test_returns_at_once_when_stop_is_set():
    stop = FakeStop()
    stop.set()
    src = FakeSource(stop, [make_capture([])])
    assert _loop(src, stop) == [] and src.open_calls == 0


def test_tracker_errors_propagate():
    class Boom:
        bound_ids = {0: None, 1: None}

        def step(self, capture, now):
            raise ValueError("bug")

    stop = FakeStop()
    with pytest.raises(ValueError):
        _loop(FakeSource(stop, [make_capture([])]), stop, tracker=Boom())


def test_logs_stats_every_period():
    stop, logs = FakeStop(), []
    caps = [make_capture([make_body(7, x=0.6)], frame_idx=i, cam_t=i / 30) for i in range(60)]
    times = iter([i / 10 for i in range(60)])
    _loop(FakeSource(stop, caps), stop, logs=logs, clock=lambda: next(times))
    assert "10.0 fps, 1 bodies, P1=7 P2=-" in logs


def test_run_wires_camera_tracker_bus_and_queue(monkeypatch):
    stop = FakeStop()
    src = FakeSource(stop, [make_capture([make_body(7, x=0.6)])])
    monkeypatch.setattr(process, "ZedSource", lambda cfg: src)
    monkeypatch.setattr(process, "FrameBus", FakeBus)
    q = ListQueue()
    process.run(CFG, q, "bus-name", stop)
    bus = FakeBus.instances[-1]
    assert (bus.name, bus.size, bus.closed) == ("bus-name", (960, 600), True)
    assert [f.frame_idx for f in bus.frames] == [0] and [s.slot for s in q.items] == [0]
    assert src.close_calls >= 1
    assert q.cancel_join_calls == 1  # never hang at exit on unread states
