"""The game-process loop: poll inputs, fuse intent, step the engine, draw.

Owner: Nikhil
"""

import dataclasses
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from magic_box.ai.worker import AiWorker
from magic_box.core.config import Config
from magic_box.core.contracts import Frame, GameEvent, PlayerState, VoiceConfig
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.health import BootChecks, CameraWatch
from magic_box.pipeline.perf import PerfStats
from magic_box.pipeline.sources import KeyboardVoiceSource, Sources
from magic_box.replay.record import SessionRecorder

_FPS_SMOOTHING = 0.1


def latest_states(
    prev: Mapping[int, PlayerState],
    new: Sequence[PlayerState],
    now: float,
    stale_s: float,
) -> dict[int, PlayerState]:
    """Newest state per slot; states older than `stale_s` are marked tracking lost."""
    merged = dict(prev)
    for state in new:
        current = merged.get(state.slot)
        if current is None or state.t >= current.t:
            merged[state.slot] = state
    return {
        slot: dataclasses.replace(s, tracking_ok=False) if now - s.t > stale_s else s
        for slot, s in merged.items()
    }


class Display(Protocol):
    def pump(self) -> tuple[frozenset[str], bool]: ...

    def tick(self) -> float: ...

    def draw(self, view, frame, states, fps: float, dropped: int = 0) -> None: ...

    def close(self) -> None: ...


class GameLoop:
    def __init__(
        self,
        cfg: Config,
        sources: Sources,
        display: Display,
        intent: Intent,
        engine: Engine,
        keyboard_voice: KeyboardVoiceSource,
        on_tick: Callable[[], None] | None = None,
        *,
        ai: AiWorker | None = None,
        voice_control: Any = None,
        clock: Callable[[], float] = time.monotonic,
        recorder: SessionRecorder | None = None,
        live: bool = False,
        perception_alive: Callable[[], bool] | None = None,
        debug_print: bool = False,
        boot_checks: BootChecks | None = None,
        perception_gave_up: Callable[[], bool] | None = None,
        voice_alive: Callable[[], bool] | None = None,
    ) -> None:
        self._stale_s = cfg["pipeline"]["stale_state_s"]
        self._reset_key = cfg["keys"].get("reset")
        self._sources = sources
        self._display = display
        self._intent = intent
        self._engine = engine
        self._keyboard_voice = keyboard_voice
        self._on_tick = on_tick
        self._ai = ai
        self._voice_control = voice_control
        self._last_voice_config: VoiceConfig | None = None
        self._clock = clock
        self._recorder = recorder
        pipe = cfg["pipeline"]
        self._watch = CameraWatch(
            pipe["camera_stale_s"], pipe["camera_boot_timeout_s"], live, perception_alive
        )
        self._checks = (
            boot_checks if boot_checks is not None else BootChecks(cfg, self._engine.provide_check)
        )
        self._perf = PerfStats(pipe["perf_window_s"])
        self._debug_print = debug_print
        self._camera_ok: bool | None = None
        self._perception_gave_up = perception_gave_up
        self._voice_alive = voice_alive
        self._voice_was_alive: bool | None = None
        self._incantations_delivered = False
        self.exit_code = 0  # 3: perception gave up after delivering frames (relaunch the box)

    def _send_voice_config(self, config: VoiceConfig) -> None:
        if config == self._last_voice_config:
            return
        self._last_voice_config = config
        self._voice_control.put(config)

    def _send_incantation_config(self, view) -> None:
        if self._voice_control is None:
            return
        sets = {p.slot: {s.id: s.incantation for s in p.spells} for p in view.players}
        self._send_voice_config(VoiceConfig(mode="incantation", incantations=sets))

    def _on_scene_entered(self, view, match_events: list[GameEvent], now: float) -> None:
        names = {p.slot: p.name for p in view.players}
        self._incantations_delivered = False  # a delivery only counts within its own loading
        if view.scene in ("loading", "victory") and self._ai is not None:
            # Dead Wi-Fi: skip Spark so loading doesn't wait out its timeout.
            set_offline = getattr(self._ai, "set_offline", None)
            if set_offline is not None:
                set_offline(self._checks.network_ok is False)
        if view.scene == "lobby" and self._voice_control is not None:
            self._send_voice_config(VoiceConfig(mode="transcript", incantations={}))
        elif view.scene == "loading" and self._ai is not None:
            classes = {p.slot: p.class_id for p in view.players}
            self._ai.start_incantations(classes, names, now)
        elif view.scene == "fight" and self._voice_control is not None:
            self._send_incantation_config(view)
        elif view.scene == "victory" and self._ai is not None:
            self._ai.start_chronicle(list(match_events), names, now)

    def _record_perf(self, t_done: float, stages: dict[str, float], state_ts: list[float]) -> None:
        latency = time.monotonic() - max(state_ts) if state_ts else None
        if self._perf.add_tick(t_done, stages, latency) and self._debug_print:
            print(self._perf.long(), file=sys.stderr, flush=True)
        overlay = getattr(self._display, "_debug_overlay", None)
        if overlay is not None:
            overlay.perf_text = self._perf.short()

    def run(self, max_ticks: int | None = None) -> int:
        """Run until quit or `max_ticks`; returns the number of ticks run."""
        latest: dict[int, PlayerState] = {}
        last_frame: Frame | None = None
        fps = 0.0
        ticks = 0
        prev_scene: str | None = None
        match_events: list[GameEvent] = []
        while max_ticks is None or ticks < max_ticks:
            keys, quit_requested = self._display.pump()
            if quit_requested:
                break
            dt = self._display.tick()
            now = self._clock()
            if dt > 0:
                inst = 1.0 / dt
                fps = inst if fps == 0.0 else fps + _FPS_SMOOTHING * (inst - fps)
            t_poll = time.perf_counter()
            inputs = self._sources.poll(keys, now, dt)
            voice = inputs.voice + self._keyboard_voice.poll(keys, now)
            latest = latest_states(latest, inputs.states, now, self._stale_s)
            statuses = [e for e in voice if e.kind == "status"]
            for e in statuses:
                self._engine.provide_mic_status(e.slot, e.text == "connected")
            if statuses and self._last_voice_config is not None:
                # A restarted voice child starts in transcript mode; it ignores an equal config.
                self._voice_control.put(self._last_voice_config)
            if self._voice_alive is not None:
                alive = self._voice_alive()
                if self._voice_was_alive and not alive:
                    # The dead voice process cannot report; its mics are not listening.
                    for slot in (0, 1):
                        self._engine.provide_mic_status(slot, False)
                self._voice_was_alive = alive
            camera_ok = self._watch.update(
                now, inputs.frame.frame_idx if inputs.frame is not None else None
            )
            if camera_ok != self._camera_ok:
                self._camera_ok = camera_ok
                self._engine.provide_camera_status(camera_ok)
            self._checks.poll(self._watch.seen_frame, camera_ok)
            t_intent = time.perf_counter()
            actions = self._intent.update(inputs.states, voice, now)
            t_engine = time.perf_counter()
            if self._reset_key in keys:
                self._engine.request_lobby()
            view, events = self._engine.step(actions, latest, now)
            t_engine_done = time.perf_counter()
            if self._recorder is not None:
                for state in inputs.states:
                    self._recorder.write_state(state)
                for voice_event in voice:
                    self._recorder.write_voice(voice_event)
                for game_event in events:
                    self._recorder.write_event(game_event)
            for event in events:
                if event.kind == "match_start":
                    match_events = []
                match_events.append(event)
            if view.scene != prev_scene:
                self._on_scene_entered(view, match_events, now)
                prev_scene = view.scene
            if self._incantations_delivered and view.scene == "loading":
                # The engine took the incantations on an earlier tick, so this view has them:
                # open the Muse sessions now so the handshake is done by the time of the fight.
                self._incantations_delivered = False
                self._send_incantation_config(view)
            if self._ai is not None:
                for kind, result in self._ai.poll(now):
                    if kind == "incantations":
                        self._engine.provide_incantations(result)  # type: ignore[arg-type]
                        self._incantations_delivered = view.scene == "loading"
                    else:
                        self._engine.provide_chronicle(result)  # type: ignore[arg-type]
            self._keyboard_voice.set_spells(
                {p.slot: [s.id for s in p.spells] for p in view.players}
            )
            if inputs.frame is not None:
                last_frame = inputs.frame
            t_draw = time.perf_counter()
            self._display.draw(view, last_frame, latest, fps, dropped=inputs.dropped)
            t_done = time.perf_counter()
            self._record_perf(
                t_done,
                {
                    "poll": t_intent - t_poll,
                    "intent": t_engine - t_intent,
                    "engine": t_engine_done - t_engine,
                    "draw": t_done - t_draw,
                },
                [s.t for s in inputs.states],
            )
            if self._on_tick is not None:
                self._on_tick()
            if (
                self._perception_gave_up is not None
                and self._watch.seen_frame
                and self._perception_gave_up()
            ):
                print("perception gave up", file=sys.stderr, flush=True)
                self.exit_code = 3
                break
            ticks += 1
        return ticks
