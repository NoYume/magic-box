import importlib.util
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from tests.perception.fake_sl import install_fake_sl

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
def test_scripts_have_help(name):
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


def test_zed_checks_listed_and_only_the_camera_required_on_the_jetson():
    mod = _load("check_env")
    jetson = {c.name: c for c in mod.run_checks(laptop=False, network=False)}
    laptop = {c.name: c for c in mod.run_checks(laptop=True, network=False)}
    assert jetson["zed_camera"].required and not jetson["zed_x_daemon"].required
    assert not laptop["zed_camera"].required and not laptop["zed_x_daemon"].required
    names = list(jetson)
    assert names.index("zed_camera") == names.index("pyzed") + 1


@pytest.mark.parametrize(
    "devices,ok,text",
    [
        ([], False, "zed_x_daemon"),
        ([("ZED2", 1)], False, "ZED_X"),
        ([("ZED_X", 4242)], True, "ZED_X serial 4242"),
    ],
)
def test_zed_camera_check(monkeypatch, devices, ok, text):
    sl = install_fake_sl(monkeypatch)
    sl.Camera.devices = [sl.device(model, serial) for model, serial in devices]
    got_ok, detail = _load("check_env")._zed_camera()
    assert got_ok is ok and text in detail


def test_zed_x_daemon_check(monkeypatch):
    mod = _load("check_env")

    def fake_run(state, code):
        return lambda *a, **k: subprocess.CompletedProcess(a, code, stdout=f"{state}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run("inactive", 3))
    ok, detail = mod._zed_x_daemon()
    assert not ok and "inactive" in detail and "systemctl restart zed_x_daemon" in detail
    monkeypatch.setattr(subprocess, "run", fake_run("active", 0))
    assert mod._zed_x_daemon() == (True, "active")


def test_zed_x_daemon_check_without_systemd_reads_host_processes(monkeypatch, tmp_path):
    # The Docker image has no systemctl; compose.yaml shares the host pid namespace instead.
    mod = _load("check_env")

    def no_systemctl(*a, **k):
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr(subprocess, "run", no_systemctl)
    monkeypatch.setattr(mod, "PROC", tmp_path)
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "comm").write_text("systemd\n")
    ok, detail = mod._zed_x_daemon()
    assert not ok and "ZEDX_Daemon" in detail and "systemctl restart zed_x_daemon" in detail
    (tmp_path / "1928").mkdir()
    (tmp_path / "1928" / "comm").write_text("ZEDX_Daemon\n")
    assert mod._zed_x_daemon() == (True, "ZEDX_Daemon running (pid 1928)")
    # The image does ship systemctl, but with no systemd to ask it prints nothing.
    unreachable = subprocess.CompletedProcess([], 1, stdout="", stderr="not booted with systemd")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: unreachable)
    assert mod._zed_x_daemon() == (True, "ZEDX_Daemon running (pid 1928)")


def _samples(mod, n, bodies=2):
    return [mod.FrameSample(20.0, 2.0, bodies, min(bodies, 2)) for _ in range(n)]


def test_bench_summary_go():
    mod = _load("bench_tracking")
    s = mod.summarize(_samples(mod, 300), elapsed_s=10.0, min_fps=25.0, min_two=0.9)
    assert s.go and s.fps == pytest.approx(30.0) and s.two_share == 1.0
    assert s.grab_p95_ms == pytest.approx(20.0) and s.track_p50_ms == pytest.approx(2.0)
    assert mod.format_summary(s).splitlines()[-1] == "GO"


def test_bench_summary_no_go_reasons():
    mod = _load("bench_tracking")
    slow = mod.summarize(_samples(mod, 200), 10.0, 25.0, 0.9)
    lonely = mod.summarize(_samples(mod, 150) + _samples(mod, 150, bodies=1), 10.0, 25.0, 0.9)
    empty = mod.summarize([], 10.0, 25.0, 0.9)
    assert not slow.go and slow.reason.startswith("fps 20.0")
    assert not lonely.go and "two people" in lonely.reason
    assert not empty.go and empty.reason == "no frames"
    assert mod.format_summary(slow).splitlines()[-1].startswith("NO-GO: fps")


def test_bench_config_overrides_a_copy():
    from magic_box.core.config import load_config

    mod = _load("bench_tracking")
    cfg = load_config(SCRIPTS.parent / "config.yaml")
    cam = mod.bench_config(cfg, body_format="BODY_18", resolution="HD1200", svo="a.svo2")["camera"]
    assert (cam["body_format"], cam["resolution"], cam["image_width"], cam["image_height"]) == (
        "BODY_18",
        "HD1200",
        1920,
        1200,
    )
    assert cam["svo_path"] == "a.svo2" and cfg["camera"]["resolution"] == "SVGA"


def test_bench_main_runs_on_a_fake_camera(monkeypatch, capsys):
    install_fake_sl(monkeypatch)
    assert _load("bench_tracking").main(["--seconds", "0.05"]) in (0, 1)
    out = capsys.readouterr().out
    assert "fps" in out
    assert "ZED_X serial 4242 960x600@30 SDK 5.0.0 (live)" in out


def test_bench_rejects_unknown_body_format_and_resolution():
    for flag, value in (("--body-format", "BODY_70"), ("--resolution", "VGA9")):
        with pytest.raises(SystemExit) as err:
            _load("bench_tracking").main([flag, value])
        assert err.value.code == 2


def test_record_default_out_name():
    out = _load("record_session").default_out(datetime(2026, 10, 24, 14, 5, 9))
    assert out == SCRIPTS.parent / "recordings" / "session-20261024-140509.svo2"


def test_record_main_records_with_a_fake_camera(monkeypatch, tmp_path):
    sl = install_fake_sl(monkeypatch)
    out = tmp_path / "x.svo2"
    assert _load("record_session").main(["--seconds", "0.05", "--out", str(out)]) == 0
    assert sl.Camera.last.recording.video_filename == str(out) and sl.Camera.last.closed
