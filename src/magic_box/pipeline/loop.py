"""The game-process loop: poll inputs, fuse intent, step the engine, draw.

Owner: Nikhil
"""

import dataclasses
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from magic_box.core.config import Config
from magic_box.core.contracts import Frame, PlayerState
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.sources import KeyboardVoiceSource, Sources

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
    ) -> None:
        self._stale_s = cfg["pipeline"]["stale_state_s"]
        self._sources = sources
        self._display = display
        self._intent = intent
        self._engine = engine
        self._keyboard_voice = keyboard_voice
        self._on_tick = on_tick

    def run(self, max_ticks: int | None = None) -> int:
        """Run until quit or `max_ticks`; returns the number of ticks run."""
        latest: dict[int, PlayerState] = {}
        last_frame: Frame | None = None
        fps = 0.0
        ticks = 0
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
            actions = self._intent.update(inputs.states, voice, now)
            view, _events = self._engine.step(actions, latest, now)
            # TODO(Nikhil): submit Spark jobs on loading/victory (spec §6)
            # TODO(Nikhil): send VoiceConfig on scene changes via runtime.control_q (spec §6)
            self._keyboard_voice.set_spells(
                {p.slot: [s.id for s in p.spells] for p in view.players}
            )
            if inputs.frame is not None:
                last_frame = inputs.frame
            self._display.draw(view, last_frame, latest, fps, dropped=inputs.dropped)
            if self._on_tick is not None:
                self._on_tick()
            ticks += 1
        return ticks
