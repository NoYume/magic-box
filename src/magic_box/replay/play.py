"""Session playback: rebased timestamps, silhouettes redrawn from recorded states.

Events are not replayed (the engine regenerates them) and no video is stored.
See docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md section 13.

Owner: Nikhil
"""

import dataclasses
from pathlib import Path

import numpy as np

from magic_box.core.config import Config
from magic_box.core.contracts import Frame, PlayerState, VoiceEvent
from magic_box.core.serde import from_json
from magic_box.replay.fake_input import draw_silhouettes


def _load(path: Path) -> list:
    items = [from_json(line) for line in path.read_text().splitlines() if line.strip()]
    return sorted(items, key=lambda item: item.t)


class SessionPlayer:
    def __init__(self, session_dir: Path, cfg: Config) -> None:
        session_dir = Path(session_dir)
        self._states: list[PlayerState] = _load(session_dir / "states.jsonl")
        voice_path = session_dir / "voice.jsonl"
        self._voice: list[VoiceEvent] = _load(voice_path) if voice_path.exists() else []
        cam = cfg["camera"]
        self._w, self._h = int(cam["image_width"]), int(cam["image_height"])
        self._bg_bgr = tuple(reversed(cfg["render"]["background_rgb"]))
        self._focal = float(cfg["fake"]["focal_px"])
        self._offset: float | None = None
        self._si = 0
        self._vi = 0

    def poll(self, now: float) -> tuple[list[PlayerState], list[VoiceEvent], Frame | None]:
        if self._offset is None:
            starts = [items[0].t for items in (self._states, self._voice) if items]
            self._offset = now - min(starts) if starts else 0.0
        offset = self._offset
        states: list[PlayerState] = []
        while self._si < len(self._states) and self._states[self._si].t + offset <= now:
            states.append(self._states[self._si])
            self._si += 1
        voice: list[VoiceEvent] = []
        while self._vi < len(self._voice) and self._voice[self._vi].t + offset <= now:
            voice.append(
                dataclasses.replace(self._voice[self._vi], t=self._voice[self._vi].t + offset)
            )
            self._vi += 1
        if not states:
            return [], voice, None
        newest = {s.slot: s for s in states}  # sorted by t, so the last per slot wins
        image = np.empty((self._h, self._w, 4), dtype=np.uint8)
        image[:, :, :3] = self._bg_bgr
        image[:, :, 3] = 255
        draw_silhouettes(image, list(newest.values()), self._focal)
        last = states[-1]
        frame = Frame(frame_idx=last.frame_idx, cam_t=last.cam_t, image=image)
        return [dataclasses.replace(s, t=s.t + offset) for s in states], voice, frame
