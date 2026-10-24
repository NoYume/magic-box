"""Session recorder: states, voice, events, frames, meta (spec section 8, replay/).

Owner: Nikhil
"""

from pathlib import Path

from magic_box.core.contracts import Frame, GameEvent, PlayerState, VoiceEvent


class SessionRecorder:
    def __init__(self, out_dir: Path) -> None:
        raise NotImplementedError("TODO(Nikhil): session recorder")

    def write_state(self, state: PlayerState) -> None:
        raise NotImplementedError("TODO(Nikhil): record a PlayerState")

    def write_voice(self, event: VoiceEvent) -> None:
        raise NotImplementedError("TODO(Nikhil): record a VoiceEvent")

    def write_event(self, event: GameEvent) -> None:
        raise NotImplementedError("TODO(Nikhil): record a GameEvent")

    def write_frame(self, frame: Frame) -> None:
        raise NotImplementedError("TODO(Nikhil): record a Frame")

    def close(self) -> None:
        raise NotImplementedError("TODO(Nikhil): close the recording")
