"""Shared test helpers; top-level functions so spawned children can import them.

Owner: Nikhil
"""

import time

import numpy as np

from magic_box.core.contracts import Frame
from magic_box.pipeline.frame_bus import FrameBus


def drain_until(q, n, timeout=2.0):
    """Poll q.drain() until n items arrived or timeout passed."""
    items = []
    deadline = time.monotonic() + timeout
    while len(items) < n and time.monotonic() < deadline:
        items.extend(q.drain())
        if len(items) < n:
            time.sleep(0.005)
    return items


def produce_ints(q, n):
    """Put 0..n-1 on q."""
    for i in range(n):
        q.put(i)


def write_frames(name: str, w: int, h: int, n: int) -> None:
    """Attach to bus `name`, write frames 0..n-1 (pixels = i % 256), close without unlinking."""
    bus = FrameBus.attach(name, w, h)
    try:
        for i in range(n):
            bus.write(Frame(frame_idx=i, cam_t=i / 30, image=np.full((h, w, 4), i % 256, np.uint8)))
    finally:
        bus.close()


def write_frames_forever(name: str, w: int, h: int, duration_s: float) -> None:
    """Free-run full-size frames (pixels = frame_idx % 256) on bus `name` for `duration_s`."""
    bus = FrameBus.attach(name, w, h)
    try:
        end = time.monotonic() + duration_s
        i = 0
        while time.monotonic() < end:
            bus.write(Frame(frame_idx=i, cam_t=i / 30, image=np.full((h, w, 4), i % 256, np.uint8)))
            i += 1
    finally:
        bus.close()


def crash_immediately(stop) -> None:
    """Child target that exits at once with a failure code."""
    raise SystemExit(1)


def wait_for_stop(stop) -> None:
    """Child target that idles until the stop event is set."""
    stop.wait(10)


def flood_queue_then_exit(q, cancel) -> None:
    """Child target: queue far more than a pipe holds with no reader, then return."""
    if cancel:
        pass
    for _ in range(200):
        q.put(b"x" * 4096)
    if cancel:
        q.cancel_join()
