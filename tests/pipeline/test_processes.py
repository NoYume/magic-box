import time
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.pipeline.processes import ProcSpec, Supervisor, start_live
from magic_box.pipeline.streams import spawn_context
from tests.helpers import crash_immediately, wait_for_stop

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def ignore_sigterm_forever(stop) -> None:
    import signal
    import time as _time

    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        _time.sleep(0.05)


def _poll_for(sup, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        sup.poll()
        time.sleep(0.02)


def test_crashing_process_restarted_up_to_limit():
    sup = Supervisor(
        [ProcSpec("crash", crash_immediately, ())], spawn_context(), backoff_s=0.05, max_restarts=2
    )
    sup.start()
    _poll_for(sup, 4.0)
    assert sup.restarts("crash") == 2 and not sup.alive("crash")
    sup.stop()


def test_stop_joins_well_behaved_process():
    sup = Supervisor(
        [ProcSpec("ok", wait_for_stop, ())], spawn_context(), backoff_s=0.05, max_restarts=0
    )
    sup.start()
    _poll_for(sup, 0.5)
    assert sup.alive("ok")
    sup.stop(timeout=5.0)
    assert not sup.alive("ok")


def test_start_live_wires_sources_with_stubbed_perception():
    cfg = {
        **CFG,
        "voice": {**CFG["voice"], "enabled": False},
        "pipeline": {**CFG["pipeline"], "max_restarts": 0},
    }
    rt = start_live(cfg)
    try:
        inputs = rt.sources.poll(frozenset(), 0.0, 0.0)
        assert inputs.states == [] and inputs.frame is None
    finally:
        rt.close()


def test_stop_kills_a_child_that_ignores_sigterm():
    sup = Supervisor(
        [ProcSpec("stubborn", ignore_sigterm_forever, ())],
        spawn_context(),
        backoff_s=0.05,
        max_restarts=0,
    )
    sup.start()
    _poll_for(sup, 1.0)  # let the child install its handler
    assert sup.alive("stubborn")
    sup.stop(timeout=0.2, terminate_timeout=0.2)
    assert not sup.alive("stubborn")


def test_runtime_close_uses_configured_timeouts():
    from magic_box.pipeline.processes import LiveRuntime

    calls = []

    class Sup:
        def stop(self, timeout, terminate_timeout):
            calls.append((timeout, terminate_timeout))

    class Bus:
        def close(self):
            pass

        def unlink(self):
            pass

    LiveRuntime(Sup(), None, None, Bus(), 1.25, 0.75).close()
    assert calls == [(1.25, 0.75)]


class _FakeProc:
    def __init__(self, alive):
        self.alive = alive

    def is_alive(self):
        return self.alive


def _bare_supervisor(reset_s=60.0, max_restarts=2):
    sup = Supervisor(
        [ProcSpec("p", wait_for_stop, ())], spawn_context(), 0.0, max_restarts, reset_s
    )
    sup._spawn = lambda spec: sup._procs.__setitem__(spec.name, _FakeProc(True))  # no real child
    return sup


def test_restart_count_resets_after_healthy_uptime():
    sup = _bare_supervisor(reset_s=0.05)
    sup._procs["p"] = _FakeProc(True)
    sup._spawned_at["p"] = time.monotonic()
    sup._restarts["p"] = 2
    sup.poll()
    assert sup.restarts("p") == 2  # not healthy long enough yet
    time.sleep(0.08)
    sup.poll()
    assert sup.restarts("p") == 0


def test_gave_up_only_when_dead_and_out_of_restarts():
    sup = _bare_supervisor()
    assert not sup.gave_up("p")  # never started
    sup._procs["p"] = _FakeProc(True)
    sup._restarts["p"] = 2
    assert not sup.gave_up("p")  # alive
    sup._procs["p"].alive = False
    assert sup.gave_up("p")
    sup._restarts["p"] = 1
    assert not sup.gave_up("p")  # a restart is still available


def write_level_and_wait(cfg, voice_q, control_q, stop, levels=None) -> None:
    """Stands in for voice.process.run: the voice process writes the mic level, then idles."""
    levels[1] = 0.25
    wait_for_stop(stop)


def test_mic_levels_cross_the_process_boundary(monkeypatch):
    # start_live gives the voice process a shared array; the game reads what voice writes.
    import magic_box.pipeline.processes as processes

    monkeypatch.setattr(processes, "voice_run", write_level_and_wait)
    cfg = {**CFG, "pipeline": {**CFG["pipeline"], "max_restarts": 0}}
    rt = start_live(cfg)
    try:
        assert len(rt.levels) == 2
        deadline = time.monotonic() + 15
        while rt.levels[1] != 0.25 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert tuple(rt.levels) == (0.0, 0.25)
    finally:
        rt.close()
