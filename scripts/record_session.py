"""Record an SVO2 from the ZED X for offline replay on the Jetson.

Owner: Enoch
"""

import argparse
import copy
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.perception.zed_source import CameraError, ZedSource

REPO_ROOT = Path(__file__).resolve().parent.parent


def default_out(now: datetime) -> Path:
    return REPO_ROOT / "recordings" / f"session-{now:%Y%m%d-%H%M%S}.svo2"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--out", default=None, help="output .svo2 path (default: recordings/)")
    parser.add_argument("--seconds", type=float, default=30.0, help="how long to record")
    args = parser.parse_args(argv)

    out = Path(args.out) if args.out else default_out(datetime.now())
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = copy.deepcopy(load_config(REPO_ROOT / "config.yaml"))
    cfg["camera"]["record_svo"] = str(out)
    cfg["camera"]["svo_path"] = None
    source = ZedSource(cfg)
    try:
        source.open()
    except (CameraError, RuntimeError) as exc:  # RuntimeError: pyzed missing
        print(f"camera error: {exc}")
        return 2

    frames = 0
    start = time.monotonic()
    try:
        while time.monotonic() - start < args.seconds:
            if source.grab() is not None:
                frames += 1
    except KeyboardInterrupt:
        print("interrupted, closing the recording")
    finally:
        source.close()
    print(f"recorded {frames} frames to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
