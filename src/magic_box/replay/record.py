"""Session recorder: states, voice, events, frames, meta (spec section 8, replay/).

Owner: Nikhil
"""

import json
from pathlib import Path

from magic_box.core.config import Config
from magic_box.core.contracts import Frame, GameEvent, PlayerState, VoiceEvent
from magic_box.core.serde import to_json


class SessionRecorder:
    def __init__(self, out_dir: Path, cfg: Config) -> None:
        self.out_dir = Path(out_dir)
        self._fps = float(cfg["camera"]["fps"])
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if any(self.out_dir.iterdir()):
            raise ValueError(f"recording directory is not empty: {self.out_dir}")
        self._files = {
            name: (self.out_dir / filename).open("w", encoding="utf-8")
            for name, filename in (
                ("state", "states.jsonl"),
                ("voice", "voice.jsonl"),
                ("event", "events.jsonl"),
            )
        }
        self._writer = None
        self._frame_meta: list[dict[str, float | int]] = []
        self._closed = False

    def _line(self, kind: str, value) -> None:
        self._files[kind].write(to_json(value) + "\n")
        self._files[kind].flush()

    def write_state(self, state: PlayerState) -> None:
        self._line("state", state)

    def write_voice(self, event: VoiceEvent) -> None:
        self._line("voice", event)

    def write_event(self, event: GameEvent) -> None:
        self._line("event", event)

    def write_frame(self, frame: Frame) -> None:
        import cv2

        if self._writer is None:
            height, width = frame.image.shape[:2]
            self._writer = cv2.VideoWriter(
                str(self.out_dir / "frames.mp4"),
                cv2.VideoWriter_fourcc(*"mp4v"),
                self._fps,
                (width, height),
            )
            if not self._writer.isOpened():
                raise RuntimeError("could not open frames.mp4 for recording")
        self._writer.write(frame.image[:, :, :3])
        self._frame_meta.append({"frame_idx": frame.frame_idx, "cam_t": frame.cam_t})

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for handle in self._files.values():
            handle.close()
        if self._writer is not None:
            self._writer.release()
        (self.out_dir / "meta.json").write_text(
            json.dumps({"frames": self._frame_meta}, indent=2), encoding="utf-8"
        )
