import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_env_laptop_mode_passes():
    assert _load("check_env").main(["--laptop"]) == 0


def test_check_env_jetson_checks_optional_on_laptop():
    checks = {c.name: c for c in _load("check_env").run_checks(laptop=True, network=False)}
    assert {"python", "arch", "jetpack", "pyzed", "numpy", "cuda", "sounddevice", "api_key"} <= set(
        checks
    )
    assert checks["python"].required and checks["python"].ok
    assert not any(
        checks[n].required for n in ("arch", "jetpack", "pyzed", "sounddevice", "api_key")
    )


@pytest.mark.parametrize("name", ["bench_tracking", "record_session"])
def test_stub_scripts_have_help(name):
    with pytest.raises(SystemExit) as err:
        _load(name).main(["--help"])
    assert err.value.code == 0


def test_cuda_check_is_info_only():
    checks = {c.name: c for c in _load("check_env").run_checks(laptop=False, network=False)}
    assert not checks["cuda"].required


def test_sync_script_preserves_per_machine_config():
    assert "--exclude config.local.yaml" in (SCRIPTS / "sync_to_jetson.sh").read_text()


def test_sync_script_syntax():
    assert subprocess.run(["bash", "-n", str(SCRIPTS / "sync_to_jetson.sh")]).returncode == 0


def test_meta_api_unset_key_reports_not_ok_without_network(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("network call made")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    checks = {c.name: c for c in _load("check_env").run_checks(laptop=True, network=True)}
    assert not checks["meta_api"].ok
    assert not checks["meta_api"].required
    assert "META_MODEL_API_KEY" in checks["meta_api"].detail


def test_bench_tracking_default_body_format_from_config():
    from magic_box.core.config import load_config

    mod = _load("bench_tracking")
    cfg = load_config(SCRIPTS.parent / "config.yaml")
    assert mod.resolve_body_format(None, cfg) == cfg["camera"]["body_format"]
    assert mod.resolve_body_format("BODY_38", cfg) == "BODY_38"
