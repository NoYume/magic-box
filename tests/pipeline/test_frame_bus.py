import os
import subprocess
import sys
import time
from multiprocessing.shared_memory import SharedMemory

import numpy as np
import pytest

from magic_box.core.contracts import Frame
from magic_box.pipeline.frame_bus import FrameBus
from magic_box.pipeline.streams import spawn_context
from tests.helpers import write_frames, write_frames_forever

W, H = 64, 48


def _frame(i):
    return Frame(frame_idx=i, cam_t=i / 30, image=np.full((H, W, 4), i % 256, np.uint8))


@pytest.fixture
def bus():
    b = FrameBus.create(W, H)
    yield b
    b.close()
    b.unlink()


def test_read_before_write_is_none(bus):
    assert bus.read_latest() is None


def test_write_then_read(bus):
    bus.write(_frame(7))
    f = bus.read_latest()
    assert f.frame_idx == 7 and f.cam_t == pytest.approx(7 / 30) and (f.image == 7).all()


def test_read_returns_copy(bus):
    bus.write(_frame(1))
    f = bus.read_latest()
    bus.write(_frame(2))
    assert (f.image == 1).all()


def test_wrong_shape_rejected(bus):
    with pytest.raises(ValueError):
        bus.write(Frame(0, 0.0, np.zeros((H, W, 3), np.uint8)))


def test_slot_left_odd_by_interrupted_write_recovers(bus):
    for slot in bus._slots:  # as if a writer was killed mid-copy into each slot
        slot.seq[...] = 1
    for i in (1, 2):
        bus.write(_frame(i))
        f = bus.read_latest()
        assert f is not None and f.frame_idx == i and (f.image == i).all()


def test_child_writer_no_torn_reads_and_segment_survives(bus):
    ctx = spawn_context()
    proc = ctx.Process(target=write_frames, args=(bus.name, W, H, 300))
    proc.start()
    seen = []
    deadline = time.monotonic() + 10
    try:
        while proc.is_alive() and time.monotonic() < deadline:
            f = bus.read_latest()
            if f is not None:
                assert (f.image == f.frame_idx % 256).all()  # never half of two frames
                seen.append(f.frame_idx)
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(10)
    assert proc.exitcode == 0, "writer child crashed or timed out"
    assert seen
    assert seen == sorted(seen)
    bus.write(_frame(999))  # child exit must not have unlinked the segment
    assert bus.read_latest().frame_idx == 999


STRESS_W, STRESS_H, STRESS_S = 1280, 720, 3.0


@pytest.mark.skipif(os.environ.get("MAGIC_BOX_STRESS") != "1", reason="set MAGIC_BOX_STRESS=1")
def test_stress_full_size_free_running_writer_no_torn_reads():
    stress_bus = FrameBus.create(STRESS_W, STRESS_H)
    proc = spawn_context().Process(
        target=write_frames_forever, args=(stress_bus.name, STRESS_W, STRESS_H, STRESS_S)
    )
    reads = 0
    try:
        proc.start()
        deadline = time.monotonic() + STRESS_S + 15
        while proc.is_alive() and time.monotonic() < deadline:
            f = stress_bus.read_latest()
            if f is not None:
                reads += 1
                assert (f.image == f.frame_idx % 256).all(), f"torn frame {f.frame_idx}"
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(10)
        stress_bus.close()
        stress_bus.unlink()
    assert reads > 0


_UNRELATED_READER = """
import sys
from magic_box.pipeline.frame_bus import FrameBus
bus = FrameBus.attach(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
print(bus.read_latest().frame_idx)
bus.close()
"""


def test_unrelated_process_exit_keeps_segment(bus):
    bus.write(_frame(5))
    # Not a multiprocessing child, so it runs its own resource tracker, which unlinks
    # anything still registered when the process exits. The tracker inherits the
    # child's stderr, so capture_output also waits for the tracker to finish.
    r = subprocess.run(
        [sys.executable, "-c", _UNRELATED_READER, bus.name, str(W), str(H)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert r.returncode == 0 and r.stderr == "", r.stderr
    assert r.stdout.strip() == "5"
    SharedMemory(name=bus.name).close()  # FileNotFoundError if the segment was unlinked
