"""Scene state machine boot -> lobby -> loading -> fight -> victory (spec section 10).

Owner: Adetola
"""

from collections.abc import Mapping, Sequence

from magic_box.core.config import Config
from magic_box.core.contracts import Action, PlayerState


class SceneMachine:
    scene: str

    def __init__(self, cfg: Config) -> None:
        raise NotImplementedError("TODO(Adetola): scene state machine")

    def update(
        self, actions: Sequence[Action], states: Mapping[int, PlayerState], now: float
    ) -> str:
        raise NotImplementedError("TODO(Adetola): scene transitions")
