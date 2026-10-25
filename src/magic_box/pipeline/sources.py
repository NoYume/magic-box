"""Input sources behind one polling interface: fake, live, replay, keyboard voice.

The game loop polls one `Sources` per tick. Keys arrive as a frozenset of
pygame key names, so this module never imports pygame.

Owner: Nikhil
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from magic_box.core.config import Config
from magic_box.core.contracts import Frame, PlayerState, VoiceEvent
from magic_box.pipeline.frame_bus import FrameBus
from magic_box.pipeline.streams import DropOldestQueue
from magic_box.replay.fake_input import FakePlayers
from magic_box.replay.play import SessionPlayer

_KEYBOARD_MATCH_SCORE = 100.0


@dataclass
class Inputs:
    states: list[PlayerState]
    voice: list[VoiceEvent]
    frame: Frame | None
    dropped: int = 0  # items dropped by overflowing queues so far


class Sources(Protocol):
    def poll(self, keys: frozenset[str], now: float, dt: float) -> Inputs: ...

    def close(self) -> None: ...


class FakeSources:
    def __init__(self, cfg: Config) -> None:
        self._players = FakePlayers(cfg)

    def poll(self, keys: frozenset[str], now: float, dt: float) -> Inputs:
        states, frame = self._players.step(keys, now, dt)
        return Inputs(states, [], frame)

    def close(self) -> None:
        pass


class LiveSources:
    """Reads the perception/voice queues and the shared frame bus; non-blocking."""

    def __init__(
        self, state_q: DropOldestQueue, voice_q: DropOldestQueue, frame_bus: FrameBus
    ) -> None:
        self._state_q = state_q
        self._voice_q = voice_q
        self._frame_bus = frame_bus

    def poll(self, keys: frozenset[str], now: float, dt: float) -> Inputs:
        return Inputs(
            self._state_q.drain(),
            self._voice_q.drain(),
            self._frame_bus.read_latest(),
            self._state_q.dropped + self._voice_q.dropped,
        )

    def close(self) -> None:
        pass  # the live runtime owns cleanup


class ReplaySources:
    def __init__(self, session_dir: Path, cfg: Config) -> None:
        self._player = SessionPlayer(session_dir, cfg)

    def poll(self, keys: frozenset[str], now: float, dt: float) -> Inputs:
        states, voice, frame = self._player.poll(now)
        return Inputs(states, voice, frame)

    def close(self) -> None:
        pass


class KeyboardVoiceSource:
    """Edge-triggered spell keys that become incantation events (always-on fallback)."""

    def __init__(self, cfg: Config) -> None:
        self._keys: dict[int, list[str]] = {
            int(slot): list(names) for slot, names in cfg["keys"]["spells"].items()
        }
        self._spells: Mapping[int, Sequence[str]] = {}
        self._prev: frozenset[str] = frozenset()

    def set_spells(self, spells: Mapping[int, Sequence[str]]) -> None:
        self._spells = spells

    def poll(self, keys: frozenset[str], now: float) -> list[VoiceEvent]:
        pressed = keys - self._prev
        self._prev = keys
        events: list[VoiceEvent] = []
        for slot, names in self._keys.items():
            slot_spells = self._spells.get(slot, ())
            for index, key in enumerate(names):
                if key in pressed and index < len(slot_spells):
                    events.append(
                        VoiceEvent(
                            slot,
                            now,
                            "incantation",
                            f"<key {key}>",
                            slot_spells[index],
                            _KEYBOARD_MATCH_SCORE,
                        )
                    )
        return events
