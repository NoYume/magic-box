"""Input sources behind one polling interface: fake, live, replay, keyboard voice.

The game loop polls one `Sources` per tick. Keys arrive as a frozenset of
pygame key names, so this module never imports pygame.

Owner: Nikhil
"""

import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from magic_box.core.config import Config
from magic_box.core.contracts import Frame, PlayerState, VoiceEvent
from magic_box.perception.raw import Capture
from magic_box.perception.tracker import PlayerTracker
from magic_box.perception.webcam_source import WebcamPoseEstimator
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


class WebcamError(RuntimeError):
    """The laptop webcam backend could not be loaded or opened."""


class WebcamSources:
    """Laptop camera frames, monocular pose states, and Muse voice events.

    Capture and inference run on a daemon thread because neither may block the game loop.
    Keyboard fake states are used only before the first camera inference, or when pose
    tracking is explicitly disabled in config.
    """

    def __init__(
        self,
        cfg: Config,
        voice_q: DropOldestQueue | None = None,
        cv2_module: Any = None,
        pose_estimator: Any = None,
    ) -> None:
        if cv2_module is None:
            try:
                import cv2 as cv2_module
            except (ImportError, OSError) as exc:
                raise WebcamError(
                    "OpenCV is unavailable; run `uv sync --extra laptop` before using --webcam"
                ) from exc
        self._cv2 = cv2_module
        self._players = FakePlayers(cfg)  # immediate keyboard fallback until the first pose
        self._tracker = PlayerTracker(cfg)
        self._voice_q = voice_q
        self._width = int(cfg["camera"]["image_width"])
        self._height = int(cfg["camera"]["image_height"])
        webcam_cfg = cfg["fake"]["webcam"]
        device = webcam_cfg["device"]
        self._capture = cv2_module.VideoCapture(device)
        if not self._capture.isOpened():
            self._capture.release()
            raise WebcamError(
                f"cannot open webcam device {device!r}; set fake.webcam.device in config.local.yaml"
            )
        self._capture.set(cv2_module.CAP_PROP_FRAME_WIDTH, self._width)
        self._capture.set(cv2_module.CAP_PROP_FRAME_HEIGHT, self._height)
        self._pose = (
            pose_estimator
            if pose_estimator is not None
            else WebcamPoseEstimator(cfg, cv2_module)
            if webcam_cfg["pose_tracking"]
            else None
        )
        self._pose_error_logged = False
        self._lock = threading.Lock()
        self._latest: tuple[Frame, list[PlayerState]] | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._capture_loop, name="webcam", daemon=True)
        self._thread.start()

    def _capture_loop(self) -> None:
        frame_idx = 0
        while not self._stop.is_set():
            ok, image = self._capture.read()
            if not ok or image is None:
                self._stop.wait(0.05)
                continue
            if image.shape[:2] != (self._height, self._width):
                image = self._cv2.resize(image, (self._width, self._height))
            cam_t = time.monotonic()
            try:
                bodies = self._pose.estimate(image) if self._pose is not None else []
            except Exception as exc:
                bodies = []
                if not self._pose_error_logged:
                    print(f"webcam: pose inference failed: {exc}", file=sys.stderr, flush=True)
                    self._pose_error_logged = True
            bgra = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2BGRA)
            frame = Frame(frame_idx=frame_idx, cam_t=cam_t, image=bgra)
            states = (
                self._tracker.step(Capture(frame, bodies), cam_t) if self._pose is not None else []
            )
            with self._lock:
                self._latest = (frame, states)
            frame_idx += 1

    def poll(self, keys: frozenset[str], now: float, dt: float) -> Inputs:
        fallback_states, fallback_frame = self._players.step(keys, now, dt)
        with self._lock:
            latest = self._latest
        frame, states = latest if latest is not None else (fallback_frame, fallback_states)
        # No pose model is the explicit keyboard-only webcam fallback.
        if self._pose is None:
            states = fallback_states
        voice = self._voice_q.drain() if self._voice_q is not None else []
        dropped = self._voice_q.dropped if self._voice_q is not None else 0
        return Inputs(states, voice, frame, dropped)

    def close(self) -> None:
        self._stop.set()
        self._capture.release()
        self._thread.join(timeout=1.0)


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
