"""Fuses voice matches and perception into Actions (spec section 8, intent/).

Owner: Nikhil
"""

from collections.abc import Sequence

from magic_box.core.config import Config
from magic_box.core.contracts import Action, PlayerState, VoiceEvent


class Intent:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def update(
        self, states: Sequence[PlayerState], voice: Sequence[VoiceEvent], now: float
    ) -> list[Action]:
        # TODO(Nikhil): charge/push/pose/dodge fusion. Placeholder emits nothing.
        return []
