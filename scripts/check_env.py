"""Environment check for the Jetson (or a laptop with --laptop).

Run this first on a fresh Jetson: it confirms Python, JetPack, RAM, pyzed, the
ZED X camera and its daemon, numpy, CUDA, cv2, audio input and the API key. Prints
one line per check and exits 1 if any required check failed.

Owner: Daniel
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEGRA_RELEASE = Path("/etc/nv_tegra_release")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    required: bool


def _load_config() -> dict:
    from magic_box.core.config import load_config

    return load_config(REPO_ROOT / "config.yaml")


def _load_ai_config() -> dict:
    return _load_config()["ai"]


def _python() -> tuple[bool, str]:
    v = sys.version_info
    return v[:2] == (3, 10), f"{v.major}.{v.minor}.{v.micro}"


def _arch() -> tuple[bool, str]:
    machine = platform.machine()
    return machine == "aarch64", machine


def _jetpack() -> tuple[bool, str]:
    return True, TEGRA_RELEASE.read_text().splitlines()[0].strip()


def _ram() -> tuple[bool, str]:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        kb = int(meminfo.read_text().split()[1])
    else:
        kb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 1024
    return True, f"{kb / 1024 / 1024:.1f} GiB"


def _pyzed() -> tuple[bool, str]:
    import pyzed.sl as sl

    return True, f"SDK {sl.Camera.get_sdk_version()}"


def _zed_camera() -> tuple[bool, str]:
    import pyzed.sl as sl

    devices = sl.Camera.get_device_list()
    if not devices:
        return False, "no ZED camera found (try: sudo systemctl restart zed_x_daemon)"
    d = devices[0]
    model = getattr(d.camera_model, "name", str(d.camera_model))
    expected = _load_config()["camera"]["model"]
    if model != expected:
        return False, f"found {model}, config expects {expected}"
    state = getattr(d.camera_state, "name", str(d.camera_state))
    return True, f"{model} serial {d.serial_number} ({state})"


def _zed_x_daemon() -> tuple[bool, str]:
    out = subprocess.run(
        ["systemctl", "is-active", "zed_x_daemon"], capture_output=True, text=True, timeout=5
    )
    state = out.stdout.strip() or "unknown"
    if state == "active":
        return True, "active"
    return False, f"{state} (sudo systemctl restart zed_x_daemon)"


def _numpy() -> tuple[bool, str]:
    import numpy

    return True, numpy.__version__


def _cv2() -> tuple[bool, str]:
    import cv2

    info = cv2.getBuildInformation()
    cuda_lines = [line for line in info.splitlines() if "NVIDIA CUDA" in line]
    cuda = bool(cuda_lines) and "YES" in cuda_lines[0]
    return True, f"{cv2.__version__} (CUDA: {'yes' if cuda else 'no'})"


def _cuda() -> tuple[bool, str]:
    version_json = Path("/usr/local/cuda/version.json")
    try:
        return True, json.loads(version_json.read_text())["cuda"]["version"]
    except (OSError, KeyError, TypeError, ValueError):
        pass
    try:
        out = subprocess.run(
            ["nvcc", "--version"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
        release = next(line for line in out.splitlines() if "release" in line)
        return True, release.strip()
    except (OSError, subprocess.SubprocessError, StopIteration):
        return False, "CUDA runtime not found"


def _sounddevice() -> tuple[bool, str]:
    import sounddevice as sd  # OSError without PortAudio

    inputs = [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]
    if not inputs:
        return False, "no input devices"
    return True, ", ".join(inputs)


def _api_key() -> tuple[bool, str]:
    env = _load_ai_config()["api_key_env"]
    if os.environ.get(env):
        return True, f"{env} is set"
    return False, f"{env} is not set"


def _meta_api() -> tuple[bool, str]:
    ai = _load_ai_config()
    env = ai["api_key_env"]
    key = os.environ.get(env)
    if not key:
        return False, f"{env} is not set, skipped probe"
    url = ai["base_url"].rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
        return True, f"GET {url} -> {resp.status}"


def _run(name: str, fn: Callable[[], tuple[bool, str]], required: bool) -> Check:
    try:
        ok, detail = fn()
    except Exception as exc:  # report, never crash the whole table
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return Check(name, ok, detail, required)


def run_checks(laptop: bool, network: bool) -> list[Check]:
    jetson_only = not laptop
    checks = [
        _run("python", _python, True),
        _run("arch", _arch, jetson_only),
        _run("jetpack", _jetpack, jetson_only),
        _run("ram", _ram, False),
        _run("pyzed", _pyzed, jetson_only),
        _run("zed_camera", _zed_camera, jetson_only),
        _run("zed_x_daemon", _zed_x_daemon, False),
        _run("numpy", _numpy, False),
        _run("cuda", _cuda, False),
        _run("cv2", _cv2, False),
        _run("sounddevice", _sounddevice, jetson_only),
        _run("api_key", _api_key, False),
    ]
    if network:
        checks.append(_run("meta_api", _meta_api, False))
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the magic-box environment.")
    parser.add_argument("--laptop", action="store_true", help="Jetson-only checks are optional")
    parser.add_argument("--network", action="store_true", help="also probe the Meta API")
    args = parser.parse_args(argv)

    checks = run_checks(laptop=args.laptop, network=args.network)
    for c in checks:
        status = "OK" if c.ok else ("FAIL" if c.required else "WARN")
        print(f"{c.name:<12} {status:<5} {c.detail}")
    return 1 if any(c.required and not c.ok for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
