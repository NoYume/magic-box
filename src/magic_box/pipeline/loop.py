"""The game-process loop: poll inputs, fuse intent, step the engine, draw.

Owner: Nikhil
"""

import dataclasses
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Protocol

from magic_box.ai.chronicle import write_chronicle
from magic_box.ai.incantations import generate_incantations
from magic_box.ai.spark_client import SparkClient
from magic_box.core.config import Config
from magic_box.core.contracts import Frame, PlayerState, VoiceConfig
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.sources import KeyboardVoiceSource, Sources
from magic_box.replay.record import SessionRecorder

_FPS_SMOOTHING = 0.1


def latest_states(
    prev: Mapping[int, PlayerState],
    new: Sequence[PlayerState],
    now: float,
    stale_s: float,
) -> dict[int, PlayerState]:
    """Newest state per slot; states older than ``stale_s`` are marked tracking lost."""
    merged = dict(prev)
    for state in new:
        current = merged.get(state.slot)
        if current is None or state.t >= current.t:
            merged[state.slot] = state
    return {
        slot: dataclasses.replace(state, tracking_ok=False) if now - state.t > stale_s else state
        for slot, state in merged.items()
    }


class Display(Protocol):
    def pump(self) -> tuple[frozenset[str], bool]: ...

    def tick(self) -> float: ...

    def draw(self, view, frame, states, fps: float, dropped: int = 0) -> None: ...

    def close(self) -> None: ...


class ControlQueue(Protocol):
    def put(self, item) -> None: ...


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
        camera_ok: Callable[[], bool] | None = None,
        control_q: ControlQueue | None = None,
        recorder: SessionRecorder | None = None,
    ) -> None:
        self._cfg = cfg
        self._stale_s = cfg["pipeline"]["stale_state_s"]
        self._sources = sources
        self._display = display
        self._intent = intent
        self._engine = engine
        self._keyboard_voice = keyboard_voice
        self._on_tick = on_tick
        self._camera_ok = camera_ok
        self._control_q = control_q
        self._recorder = recorder

    def run(self, max_ticks: int | None = None) -> int:
        """Run until quit or ``max_ticks``; returns the number of ticks run."""
        latest: dict[int, PlayerState] = {}
        last_frame: Frame | None = None
        recorded_frame_idx: int | None = None
        fps = 0.0
        ticks = 0
        previous_scene: str | None = None
        incantations: dict[int, dict[str, str]] | None = None
        incantation_job: Future | None = None
        chronicle_job: Future | None = None
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spark")
        client = SparkClient(self._cfg)
        try:
            while max_ticks is None or ticks < max_ticks:
                keys, quit_requested = self._display.pump()
                if quit_requested:
                    break
                dt = self._display.tick()
                now = time.monotonic()
                if dt > 0:
                    inst = 1.0 / dt
                    fps = inst if fps == 0.0 else fps + _FPS_SMOOTHING * (inst - fps)
                inputs = self._sources.poll(keys, now, dt)
                voice = inputs.voice + self._keyboard_voice.poll(keys, now)
                latest = latest_states(latest, inputs.states, now, self._stale_s)
                self._engine.accept_voice(voice)
                actions = self._intent.update(inputs.states, voice, now)
                view, events = self._engine.step(actions, latest, now)

                if view.scene != previous_scene:
                    previous_scene = view.scene
                    if view.scene == "lobby":
                        class_names = {
                            str(class_id): str(row["name"])
                            for class_id, row in self._cfg["game"]["classes"].items()
                        }
                        self._send_voice(
                            VoiceConfig(
                                mode="transcript",
                                incantations={slot: dict(class_names) for slot in (0, 1)},
                            )
                        )
                    elif view.scene == "loading" and incantation_job is None:
                        incantation_job = executor.submit(
                            generate_incantations, client, self._engine.classes, self._cfg
                        )
                    elif view.scene == "victory" and chronicle_job is None:
                        chronicle_job = executor.submit(
                            write_chronicle,
                            client,
                            self._engine.event_log,
                            self._engine.names,
                        )
                if incantation_job is not None and incantation_job.done():
                    incantations = incantation_job.result()
                    self._engine.provide_incantations(incantations)
                    self._send_voice(VoiceConfig(mode="incantation", incantations=incantations))
                    incantation_job = None
                if chronicle_job is not None and chronicle_job.done():
                    self._engine.provide_chronicle(chronicle_job.result())
                    chronicle_job = None

                self._keyboard_voice.set_spells(
                    {player.slot: [spell.id for spell in player.spells] for player in view.players}
                )
                if inputs.frame is not None:
                    last_frame = inputs.frame
                if self._recorder is not None:
                    for state in inputs.states:
                        self._recorder.write_state(state)
                    for event in voice:
                        self._recorder.write_voice(event)
                    for event in events:
                        self._recorder.write_event(event)
                    if inputs.frame is not None and inputs.frame.frame_idx != recorded_frame_idx:
                        self._recorder.write_frame(inputs.frame)
                        recorded_frame_idx = inputs.frame.frame_idx
                if self._camera_ok is not None and not self._camera_ok():
                    view = dataclasses.replace(view, banner="CAMERA RECONNECTING")
                self._display.draw(view, last_frame, latest, fps, dropped=inputs.dropped)
                if self._on_tick is not None:
                    self._on_tick()
                ticks += 1
            return ticks
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

    def _send_voice(self, config: VoiceConfig) -> None:
        if self._control_q is not None:
            self._control_q.put(config)
