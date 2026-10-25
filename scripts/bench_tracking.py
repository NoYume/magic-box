"""Run two-person body tracking on the ZED X and print GO or NO-GO.

Owner: Enoch
"""

import argparse
import copy
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from magic_box.core.config import BODY_FORMATS, CAMERA_MODES, load_config
from magic_box.perception.bodies import filter_bodies
from magic_box.perception.tracker import PlayerTracker
from magic_box.perception.zed_source import CameraError, ZedSource

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class FrameSample:
    grab_ms: float
    track_ms: float
    bodies: int
    slots: int


@dataclass
class Summary:
    frames: int
    elapsed_s: float
    fps: float
    grab_p50_ms: float
    grab_p95_ms: float
    track_p50_ms: float
    track_p95_ms: float
    two_share: float
    go: bool
    reason: str


def resolve_body_format(arg: str | None, cfg: dict) -> str:
    """The --body-format flag if given, else camera.body_format from config."""
    return arg or cfg["camera"]["body_format"]


def bench_config(
    cfg: dict,
    body_format: str | None = None,
    resolution: str | None = None,
    svo: str | None = None,
) -> dict:
    """A deep copy of cfg with the benchmark flags applied."""
    out = copy.deepcopy(cfg)
    cam = out["camera"]
    cam["body_format"] = resolve_body_format(body_format, cfg)
    if resolution:
        cam["resolution"] = resolution
        cam["image_width"], cam["image_height"] = CAMERA_MODES[resolution]
    if svo:
        cam["svo_path"] = svo
    return out


def summarize(samples: Sequence[FrameSample], elapsed_s: float, min_fps: float, min_two: float):
    n = len(samples)
    if n == 0:
        return Summary(0, elapsed_s, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, "no frames")
    grab = [s.grab_ms for s in samples]
    track = [s.track_ms for s in samples]
    fps = n / elapsed_s
    two_share = sum(s.bodies >= 2 for s in samples) / n
    reason = ""
    if fps < min_fps:
        reason = f"fps {fps:.1f} < {min_fps:g}"
    elif two_share < min_two:
        reason = f"two people in {two_share:.0%} of frames < {min_two:.0%}"
    return Summary(
        n,
        elapsed_s,
        fps,
        float(np.percentile(grab, 50)),
        float(np.percentile(grab, 95)),
        float(np.percentile(track, 50)),
        float(np.percentile(track, 95)),
        two_share,
        not reason,
        reason,
    )


def format_summary(s: Summary) -> str:
    return "\n".join(
        [
            f"frames {s.frames} in {s.elapsed_s:.1f} s: {s.fps:.1f} fps",
            f"grab+retrieve p50 {s.grab_p50_ms:.1f} ms, p95 {s.grab_p95_ms:.1f} ms",
            f"tracker p50 {s.track_p50_ms:.1f} ms, p95 {s.track_p95_ms:.1f} ms",
            f"two people in {s.two_share:.0%} of frames",
            "GO" if s.go else f"NO-GO: {s.reason}",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--seconds", type=float, default=30.0, help="how long to run")
    parser.add_argument(
        "--body-format",
        default=None,
        choices=BODY_FORMATS,
        help="ZED body format (default: camera.body_format from config.yaml)",
    )
    parser.add_argument("--resolution", default=None, choices=list(CAMERA_MODES))
    parser.add_argument("--svo", default=None, help="play this .svo2 instead of the live camera")
    parser.add_argument("--min-fps", type=float, default=25.0, help="GO needs at least this fps")
    parser.add_argument(
        "--min-two", type=float, default=0.9, help="GO needs two people in this share of frames"
    )
    args = parser.parse_args(argv)

    cfg = bench_config(
        load_config(REPO_ROOT / "config.yaml"), args.body_format, args.resolution, args.svo
    )
    source = ZedSource(cfg)
    tracker = PlayerTracker(cfg)
    try:
        source.open()
    except CameraError as exc:
        print(exc)
        return 2
    i = source.info
    print(
        f"opened {i.model} serial {i.serial} {i.width}x{i.height}@{i.fps:g} "
        f"SDK {i.sdk_version} ({i.source})"
    )

    max_range = cfg["camera"]["max_range_m"]
    samples: list[FrameSample] = []
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.seconds:
            t0 = time.perf_counter()
            capture = source.grab()
            t1 = time.perf_counter()
            if capture is None:
                continue
            states = tracker.step(capture, time.monotonic())
            t2 = time.perf_counter()
            samples.append(
                FrameSample(
                    (t1 - t0) * 1000,
                    (t2 - t1) * 1000,
                    len(filter_bodies(capture.bodies, max_range)),
                    len(states),
                )
            )
        elapsed = time.monotonic() - start
    finally:
        source.close()

    summary = summarize(samples, elapsed, args.min_fps, args.min_two)
    print(format_summary(summary))
    return 0 if summary.go else 1


if __name__ == "__main__":
    raise SystemExit(main())
