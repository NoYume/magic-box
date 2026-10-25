import time
from dataclasses import replace
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.health import BootChecks, CameraWatch, probe_host
from magic_box.pipeline.loop import GameLoop
from magic_box.pipeline.perf import PerfStats
from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource
from tests.pipeline.test_loop import ScriptedDisplay

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_not_live_is_always_ok():
    w = CameraWatch(1.5, 5.0, live=False)
    assert w.update(0.0, None) and w.update(100.0, None)


def test_live_goes_stale_and_recovers():
    w = CameraWatch(1.5, 5.0, live=True)
    assert w.update(0.0, None)  # waiting for the first frame, within the boot timeout
    assert w.update(0.5, 1) and w.seen_frame
    assert w.update(1.9, 1)  # 1.4 s since the last new frame
    assert not w.update(2.1, 1)  # 1.6 s: stale
    assert w.update(2.2, 2)


def test_no_first_frame_fails_after_boot_timeout():
    w = CameraWatch(1.5, 5.0, live=True)
    assert w.update(0.0, None) and w.update(4.9, None)
    assert not w.update(5.1, None) and not w.seen_frame


def test_dead_perception_is_not_ok_even_with_fresh_frames():
    alive = [True]
    w = CameraWatch(1.5, 5.0, live=True, perception_alive=lambda: alive[0])
    assert w.update(0.0, 1)
    alive[0] = False
    assert not w.update(0.1, 2)
    alive[0] = True
    assert w.update(0.2, 3)


def _checks(cfg, env, probe):
    got = {}
    bc = BootChecks(cfg, lambda n, ok, d: got.update({n: (ok, d)}), env=env, probe=probe)
    return bc, got


def _wait(bc, got, name):
    end = time.monotonic() + 2
    while name not in got and time.monotonic() < end:
        bc.poll(False, True)
        time.sleep(0.01)


def test_api_key_check_never_leaks_the_key():
    env = {CFG["ai"]["api_key_env"]: "sk-secret"}
    bc, got = _checks(CFG, env, lambda u, t: (True, "h"))
    bc.poll(False, True)
    assert got["api key"] == (True, "")
    assert "sk-secret" not in repr(got)
    bc2, got2 = _checks(CFG, {}, lambda u, t: (True, "h"))
    bc2.poll(False, True)
    assert got2["api key"] == (False, "not set")


def test_network_probe_runs_off_thread_and_reports():
    bc, got = _checks(CFG, {}, lambda u, t: (False, "boom"))
    _wait(bc, got, "network")
    assert got["network"] == (False, "boom")


def test_probe_exception_becomes_failed_check():
    def bad(u, t):
        raise RuntimeError("x")

    bc, got = _checks(CFG, {}, bad)
    _wait(bc, got, "network")
    assert got["network"] == (False, "RuntimeError")


def test_ai_disabled_skips_probe():
    cfg = {**CFG, "ai": {**CFG["ai"], "enabled": False}}
    bc, got = _checks(cfg, {}, lambda u, t: 1 / 0)
    bc.poll(False, True)
    assert got["network"][0] and got["api key"][0]


def test_camera_check_reports_on_first_frame_and_on_boot_failure():
    bc, got = _checks(CFG, {}, lambda u, t: (True, ""))
    bc.poll(False, True)
    assert "camera" not in got
    bc.poll(False, False)
    assert got["camera"] == (False, "no frames")
    bc.poll(True, True)
    assert got["camera"] == (True, "")


def test_probe_host_rejects_bad_url():
    assert probe_host("nonsense", 0.1) == (False, "bad ai.base_url")


def test_perf_window_and_overlay_text():
    p = PerfStats(1.0)
    assert not p.add_tick(0.0, {"poll": 0.001, "draw": 0.004}, 0.02)
    assert p.add_tick(1.1, {"poll": 0.003, "draw": 0.006}, None)
    assert p.last["poll_ms"] == 2.0 and p.last["draw_ms"] == 5.0
    assert "lat 20 ms" in p.short()
    p2 = PerfStats(1.0)
    p2.add_tick(0.0, {}, 0.02)
    p2.add_tick(1.1, {}, 0.02)
    assert "lat 20 ms" in p2.short() and "worst tick" in p2.long()


class CamEngine(Engine):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.cam, self.chk = [], {}

    def provide_camera_status(self, ok):
        self.cam.append(ok)

    def provide_check(self, name, ok, detail=""):
        self.chk[name] = (ok, detail)


def test_loop_reports_camera_and_checks_in_fake_mode():
    engine = CamEngine(CFG)
    GameLoop(
        CFG, FakeSources(CFG), ScriptedDisplay([]), Intent(CFG), engine, KeyboardVoiceSource(CFG)
    ).run(max_ticks=5)
    assert engine.cam == [True]
    assert engine.chk["camera"] == (True, "") and "api key" in engine.chk


def test_loop_live_reports_camera_down_when_perception_dead():
    class NoFrames(FakeSources):
        def poll(self, keys, now, dt):
            return replace(super().poll(keys, now, dt), frame=None, states=[])

    engine = CamEngine(CFG)
    GameLoop(
        CFG,
        NoFrames(CFG),
        ScriptedDisplay([]),
        Intent(CFG),
        engine,
        KeyboardVoiceSource(CFG),
        live=True,
        perception_alive=lambda: False,
    ).run(max_ticks=3)
    assert engine.cam == [False] and engine.chk["camera"] == (False, "no frames")


def test_network_probe_that_never_returns_reports_timeout():
    import threading

    release = threading.Event()
    now = [0.0]
    got = {}
    bc = BootChecks(
        CFG,
        lambda n, ok, d: got.update({n: (ok, d)}),
        env={},
        probe=lambda u, t: (bool(release.wait(5)), "late"),
        clock=lambda: now[0],
    )
    bc.poll(False, True)
    assert "network" not in got
    now[0] = CFG["pipeline"]["network_probe_timeout_s"] + 0.5  # inside the margin
    bc.poll(False, True)
    assert "network" not in got
    now[0] = CFG["pipeline"]["network_probe_timeout_s"] + 1.5
    bc.poll(False, True)
    assert got["network"] == (False, "timeout")
    release.set()


def test_loop_exits_3_when_perception_gives_up_after_frames():
    gave_up = [False]

    class Ticker:
        n = 0

        def __call__(self):
            Ticker.n += 1
            gave_up[0] = Ticker.n >= 5

    engine = CamEngine(CFG)
    loop = GameLoop(
        CFG,
        FakeSources(CFG),  # delivers frames every tick
        ScriptedDisplay([]),
        Intent(CFG),
        engine,
        KeyboardVoiceSource(CFG),
        on_tick=Ticker(),
        perception_gave_up=lambda: gave_up[0],
    )
    assert loop.run(max_ticks=100) == 4 and loop.exit_code == 3


def test_loop_keeps_running_when_perception_never_delivered_a_frame():
    class NoFrames(FakeSources):
        def poll(self, keys, now, dt):
            return replace(super().poll(keys, now, dt), frame=None, states=[])

    loop = GameLoop(
        CFG,
        NoFrames(CFG),
        ScriptedDisplay([]),
        Intent(CFG),
        CamEngine(CFG),
        KeyboardVoiceSource(CFG),
        perception_gave_up=lambda: True,
    )
    assert loop.run(max_ticks=5) == 5 and loop.exit_code == 0


def test_dead_voice_process_reports_both_mics_off_once():
    alive = [True]
    mic = []

    class MicEngine(CamEngine):
        def provide_mic_status(self, slot, ok):
            mic.append((slot, ok))

    class Ticker:
        n = 0

        def __call__(self):
            Ticker.n += 1
            alive[0] = Ticker.n < 2

    GameLoop(
        CFG,
        FakeSources(CFG),
        ScriptedDisplay([]),
        Intent(CFG),
        MicEngine(CFG),
        KeyboardVoiceSource(CFG),
        on_tick=Ticker(),
        voice_alive=lambda: alive[0],
    ).run(max_ticks=6)
    assert mic == [(0, False), (1, False)]
