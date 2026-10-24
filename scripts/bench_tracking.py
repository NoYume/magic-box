"""Run body tracking with two people and print the fps for the go/no-go call.

Owner: Enoch
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from magic_box.core.config import load_config

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_body_format(arg: str | None, cfg: dict) -> str:
    """The --body-format flag if given, else camera.body_format from config."""
    return arg or cfg["camera"]["body_format"]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--seconds", type=float, default=30.0, help="how long to run")
    parser.add_argument(
        "--body-format",
        default=None,
        help="ZED body format (default: camera.body_format from config.yaml)",
    )
    args = parser.parse_args(argv)
    cfg = load_config(REPO_ROOT / "config.yaml")
    body_format = resolve_body_format(args.body_format, cfg)  # noqa: F841
    raise NotImplementedError("TODO(Enoch): run two-person body tracking and print fps")


if __name__ == "__main__":
    raise SystemExit(main())
