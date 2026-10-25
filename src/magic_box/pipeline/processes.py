"""Process supervisor for perception/voice children, and live-mode wiring.

The game loop calls `Supervisor.poll()` every tick; it never blocks.

Owner: Nikhil
"""

import functools
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from multiprocessing.context import BaseContext

from magic_box.core.config import Config
from magic_box.perception.process import run as perception_run
from magic_box.pipeline.frame_bus import FrameBus
from magic_box.pipeline.sources import LiveSources
from magic_box.pipeline.streams import DropOldestQueue, spawn_context
from magic_box.voice.process import run as voice_run


@dataclass
class ProcSpec:
    """A child process: `target(*args, stop_event)`."""

    name: str
    target: Callable[..., None]
    args: tuple
    restart: bool = True


class Supervisor:
    def __init__(
        self,
        specs: Sequence[ProcSpec],
        ctx: BaseContext,
        backoff_s: float,
        max_restarts: int,
        reset_s: float = 60.0,
    ) -> None:
        self._specs = {s.name: s for s in specs}
        self._ctx = ctx
        self._backoff_s = backoff_s
        self._max_restarts = max_restarts
        self._reset_s = reset_s
        self._spawned_at: dict[str, float] = {}
        self.stop_event = ctx.Event()
        self._procs: dict[str, object] = {}
        self._restarts = {s.name: 0 for s in specs}
        self._died_at: dict[str, float] = {}

    def _spawn(self, spec: ProcSpec) -> None:
        proc = self._ctx.Process(
            target=spec.target, args=(*spec.args, self.stop_event), name=spec.name, daemon=True
        )
        proc.start()
        self._procs[spec.name] = proc
        self._spawned_at[spec.name] = time.monotonic()

    def start(self) -> None:
        for spec in self._specs.values():
            self._spawn(spec)

    def poll(self) -> None:
        if self.stop_event.is_set():
            return
        now = time.monotonic()
        for name, spec in self._specs.items():
            proc = self._procs.get(name)
            if proc is None:
                continue
            if proc.is_alive():
                # Healthy for a while: earlier deaths no longer count toward giving up.
                if self._restarts[name] and now - self._spawned_at[name] >= self._reset_s:
                    self._restarts[name] = 0
                continue
            if not spec.restart or self._restarts[name] >= self._max_restarts:
                continue
            died_at = self._died_at.setdefault(name, now)
            if now - died_at < self._backoff_s:
                continue
            del self._died_at[name]
            self._restarts[name] += 1
            print(
                f"supervisor: restarting {name} ({self._restarts[name]}/{self._max_restarts})",
                file=sys.stderr,
            )
            self._spawn(spec)

    def gave_up(self, name: str) -> bool:
        """True once `name` is dead and out of restarts (or is not restarted at all)."""
        proc = self._procs.get(name)
        if proc is None or proc.is_alive():
            return False
        return not self._specs[name].restart or self._restarts[name] >= self._max_restarts

    def restarts(self, name: str) -> int:
        return self._restarts[name]

    def alive(self, name: str) -> bool:
        proc = self._procs.get(name)
        return proc is not None and proc.is_alive()

    def stop(self, timeout: float = 2.0, terminate_timeout: float = 1.0) -> None:
        """Ask children to stop, SIGTERM stragglers, then SIGKILL so none outlives the game."""
        self.stop_event.set()
        deadline = time.monotonic() + timeout
        for proc in self._procs.values():
            proc.join(max(0.0, deadline - time.monotonic()))
        for proc in self._procs.values():
            if proc.is_alive():
                proc.terminate()
                proc.join(terminate_timeout)
        for proc in self._procs.values():
            if proc.is_alive():  # still holding the camera or mic: no orphans
                proc.kill()
                proc.join(0.5)


@dataclass
class LiveRuntime:
    supervisor: Supervisor
    sources: LiveSources
    control_q: DropOldestQueue
    frame_bus: FrameBus
    stop_timeout_s: float = 2.0
    terminate_timeout_s: float = 1.0
    levels: Sequence[float] | None = None  # per-slot mic RMS (0..1), written by the voice process

    def close(self) -> None:
        # The window is already closed when this runs, so the wait is not visible to players.
        self.supervisor.stop(self.stop_timeout_s, self.terminate_timeout_s)
        self.frame_bus.close()
        self.frame_bus.unlink()


def start_live(cfg: Config) -> LiveRuntime:
    ctx = spawn_context()
    pipe = cfg["pipeline"]
    state_q = DropOldestQueue(pipe["state_queue_size"], ctx)
    voice_q = DropOldestQueue(pipe["voice_queue_size"], ctx)
    control_q = DropOldestQueue(pipe["control_queue_size"], ctx)
    frame_bus = FrameBus.create(cfg["camera"]["image_width"], cfg["camera"]["image_height"])
    specs = [ProcSpec("perception", perception_run, (cfg, state_q, frame_bus.name))]
    levels = ctx.RawArray("d", 2)  # the voice process writes, the screen reads: no queue, no lock
    if cfg["voice"]["enabled"]:
        voice_target = functools.partial(voice_run, levels=levels)
        specs.append(ProcSpec("voice", voice_target, (cfg, voice_q, control_q)))
    supervisor = Supervisor(
        specs, ctx, pipe["restart_backoff_s"], pipe["max_restarts"], pipe["restart_reset_s"]
    )
    try:
        supervisor.start()
    except BaseException:
        frame_bus.close()
        frame_bus.unlink()
        raise
    return LiveRuntime(
        supervisor,
        LiveSources(state_q, voice_q, frame_bus),
        control_q,
        frame_bus,
        pipe["stop_timeout_s"],
        pipe["terminate_timeout_s"],
        levels,
    )
