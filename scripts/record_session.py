"""Record a camera session to disk for offline replay.

Owner: Enoch + Nikhil
"""

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--out", default="recordings/session", help="output path")
    parser.add_argument("--seconds", type=float, default=30.0, help="how long to record")
    parser.parse_args(argv)
    raise NotImplementedError("TODO(Enoch, Nikhil): record a session to --out")


if __name__ == "__main__":
    raise SystemExit(main())
