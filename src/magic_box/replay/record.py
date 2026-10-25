"""Session recorder: states, voice and events as JSON lines plus meta.json.

The game loop only enqueues objects; a daemon writer thread serializes and
writes, so recording never touches the disk on the 60 fps path. Camera frames
are not recorded: replay redraws silhouettes from the recorded states.
See docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md section 13.

Owner: Nikhil
"""

import json
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from magic_box.core.config import Config
from magic_box.core.contracts import GameEvent, PlayerState, VoiceEvent
from magic_box.core.serde import to_json

_FILES = {"states": "states.jsonl", "voice": "voice.jsonl", "events": "events.jsonl"}


class SessionRecorder:
    def __init__(self, out_dir: Path, cfg: Config, mode: str) -> None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "version": 1,
            "mode": mode,
            "started_t": time.monotonic(),
            "started_wall": datetime.now().astimezone().isoformat(),
            "config": cfg,
        }
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
        self._files = {key: (out_dir / name).open("w") for key, name in _FILES.items()}
        self._queue: queue.SimpleQueue[tuple[str, Any] | None] = queue.SimpleQueue()
        self._closed = False
        self._thread = threading.Thread(target=self._drain, name="session-recorder", daemon=True)
        self._thread.start()

    def write_state(self, state: PlayerState) -> None:
        self._queue.put(("states", state))

    def write_voice(self, event: VoiceEvent) -> None:
        self._queue.put(("voice", event))

    def write_event(self, event: GameEvent) -> None:
        self._queue.put(("events", event))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join()
        for f in self._files.values():
            f.close()

    def _drain(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            key, obj = item
            try:
                self._files[key].write(to_json(obj) + "\n")
            except Exception as e:  # keep draining: a bad write must not crash the game
                print(f"record: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
