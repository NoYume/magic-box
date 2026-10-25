"""Perception process entry point (spec section 9, perception/).

Owner: Enoch
"""

import sys
import time
from collections.abc import Callable
from multiprocessing.synchronize import Event

from magic_box.core.config import Config
from magic_box.core.contracts import Frame, PlayerState
from magic_box.perception.tracker import PlayerTracker
from magic_box.perception.zed_source import CameraError, ZedSource
from magic_box.pipeline.frame_bus import FrameBus
from magic_box.pipeline.streams import DropOldestQueue, ParentAwareStop


def log_line(msg: str) -> None:
    print(f"perception: {msg}", file=sys.stderr, flush=True)


def run_loop(
    source,
    tracker,
    write_frame: Callable[[Frame], None],
    put_state: Callable[[PlayerState], None],
    stop,
    cfg: Config,
    clock: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = log_line,
) -> None:
    """Open the camera (retrying), grab, write each frame, then publish its states."""
    pcfg = cfg["perception"]
    retry = pcfg["open_retry_s"]
    max_failures = pcfg["max_grab_failures"]
    stats_every = pcfg["stats_every_s"]
    failures = 0
    ref: float | None = None
    frames = 0
    while not stop.is_set():
        if not source.is_open:
            try:
                source.open()
            except CameraError as err:
                log(f"camera open failed: {err}; retrying in {retry:g} s")
                stop.wait(retry)
                continue
            i = source.info
            log(
                f"opened {i.model} serial {i.serial} {i.width}x{i.height}@{i.fps:g} "
                f"SDK {i.sdk_version} ({i.source})"
            )
        capture = source.grab()
        if capture is None:
            failures += 1
            if failures >= max_failures:
                log(f"{failures} grab failures in a row; reopening the camera")
                source.close()
                failures = 0
            continue
        failures = 0
        now = clock()
        write_frame(capture.frame)
        for state in tracker.step(capture, now):
            put_state(state)
        if ref is None:
            ref = now
            continue
        frames += 1
        if now - ref >= stats_every:
            ids = tracker.bound_ids
            p1, p2 = (ids[s] if ids[s] is not None else "-" for s in (0, 1))
            log(f"{frames / (now - ref):.1f} fps, {len(capture.bodies)} bodies, P1={p1} P2={p2}")
            ref = now
            frames = 0


def run(cfg: Config, state_q: DropOldestQueue, frame_bus_name: str, stop: Event) -> None:
    """Grab frames, publish them on the frame bus and PlayerStates on state_q until stop is set."""
    cam = cfg["camera"]
    bus = FrameBus.attach(frame_bus_name, cam["image_width"], cam["image_height"])
    source = ZedSource(cfg)
    try:
        run_loop(source, PlayerTracker(cfg), bus.write, state_q.put, ParentAwareStop(stop), cfg)
    finally:
        state_q.cancel_join()  # the game may be gone; never hang at exit on unread states
        source.close()
        bus.close()
