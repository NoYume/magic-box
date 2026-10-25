import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_demo.sh"


def run(args, env=None, timeout=60):
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=timeout,
        cwd=ROOT,
    )


@pytest.fixture
def clean_recordings():
    before = set((ROOT / "recordings").glob("2*"))
    yield
    for d in set((ROOT / "recordings").glob("2*")) - before:
        shutil.rmtree(d, ignore_errors=True)


def test_script_is_executable_with_usage_header():
    assert os.access(SCRIPT, os.X_OK)
    assert "Usage: scripts/run_demo.sh" in SCRIPT.read_text()


def test_dry_run_passes_fake_record_and_extra_args():
    out = run(["--dry-run", "--fake", "--", "--debug"]).stdout
    assert "python -m magic_box --fake --record recordings/" in out
    assert out.strip().endswith("--debug")
    assert "--env-file" not in out  # fake mode needs no key


def test_dry_run_no_record_and_unknown_flag():
    assert "--record" not in run(["--dry-run", "--no-record"]).stdout
    bad = run(["--bogus"])
    assert bad.returncode == 2 and "unknown argument" in bad.stderr


def test_clean_exit_stops_without_restart(clean_recordings):
    done = run(["--no-record"], env={"GAME_CMD": "true"})
    assert done.returncode == 0 and "restarting" not in done.stderr


def test_crash_restarts_then_gives_up(clean_recordings):
    done = run(
        ["--no-record"],
        env={"GAME_CMD": "false", "MAX_RESTARTS": "2", "RESTART_DELAY_S": "0"},
    )
    assert done.returncode == 1
    assert done.stderr.count("restarting") == 3 and "giving up" in done.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_shellcheck_clean():
    assert subprocess.run(["shellcheck", str(SCRIPT)]).returncode == 0
