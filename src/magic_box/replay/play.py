"""Session playback with original timing (spec section 8, replay/).

Owner: Nikhil
"""

from pathlib import Path

from magic_box.core.contracts import Frame, PlayerState, VoiceEvent


class SessionPlayer:
    def __init__(self, session_dir: Path) -> None:
        raise NotImplementedError("TODO(Nikhil): session player")

    def poll(self, now: float) -> tuple[list[PlayerState], list[VoiceEvent], Frame | None]:
        raise NotImplementedError("TODO(Nikhil): replay items due at `now`")
