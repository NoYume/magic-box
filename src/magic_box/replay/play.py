"""Session playback with original timing (spec section 8, replay/).

Owner: Nikhil
"""

import json
from pathlib import Path

from magic_box.core.contracts import Frame, PlayerState, VoiceEvent
from magic_box.core.serde import from_json


class SessionPlayer:
    def __init__(self, session_dir: Path) -> None:
        self.session_dir = Path(session_dir)
        if not self.session_dir.is_dir():
            raise ValueError(f"recording directory does not exist: {self.session_dir}")
        self._states = self._read("states.jsonl", PlayerState)
        self._voice = self._read("voice.jsonl", VoiceEvent)
        times = [item.t for item in (*self._states, *self._voice)]
        self._stream_origin = min(times) if times else 0.0
        self._state_index = 0
        self._voice_index = 0
        self._started_at: float | None = None
        meta_path = self.session_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        self._frames = list(meta.get("frames", []))
        self._frame_origin = self._frames[0]["cam_t"] if self._frames else 0.0
        self._frame_index = 0
        self._capture = None

    def _read(self, name: str, expected: type) -> list:
        path = self.session_dir / name
        if not path.exists():
            return []
        values = [from_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        if any(not isinstance(value, expected) for value in values):
            raise ValueError(f"{name} contains an unexpected contract type")
        return sorted(values, key=lambda item: item.t)

    def poll(self, now: float) -> tuple[list[PlayerState], list[VoiceEvent], Frame | None]:
        if self._started_at is None:
            self._started_at = now
        elapsed = now - self._started_at
        states = []
        while self._state_index < len(self._states):
            item = self._states[self._state_index]
            if item.t - self._stream_origin > elapsed:
                break
            states.append(item)
            self._state_index += 1
        voice = []
        while self._voice_index < len(self._voice):
            item = self._voice[self._voice_index]
            if item.t - self._stream_origin > elapsed:
                break
            voice.append(item)
            self._voice_index += 1
        frame = None
        while self._frame_index < len(self._frames):
            row = self._frames[self._frame_index]
            if row["cam_t"] - self._frame_origin > elapsed:
                break
            frame = self._read_frame(row)
            self._frame_index += 1
        return states, voice, frame

    def _read_frame(self, row: dict) -> Frame | None:
        import cv2

        if self._capture is None:
            self._capture = cv2.VideoCapture(str(self.session_dir / "frames.mp4"))
        ok, image = self._capture.read()
        if not ok:
            return None
        return Frame(
            frame_idx=int(row["frame_idx"]),
            cam_t=float(row["cam_t"]),
            image=cv2.cvtColor(image, cv2.COLOR_BGR2BGRA),
        )
