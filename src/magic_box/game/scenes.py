"""Scene state machine boot -> lobby -> loading -> fight -> victory (spec section 10).

Owner: Adetola
"""

from collections.abc import Mapping, Sequence

from magic_box.core.config import Config
from magic_box.core.contracts import Action, PlayerState


class SceneMachine:
    """Small deterministic scene machine; game rules decide when a fight is over."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.scene = "boot"
        self.entered_at = 0.0
        self.ready_slots: set[int] = set()
        self.loading_ready = False
        self.victory_ready: set[int] = set()

    def enter(self, scene: str, now: float) -> None:
        self.scene = scene
        self.entered_at = now
        if scene == "lobby":
            self.ready_slots.clear()
        if scene == "loading":
            self.loading_ready = False
        if scene == "victory":
            self.victory_ready.clear()

    def complete_loading(self) -> None:
        self.loading_ready = True

    def update(
        self, actions: Sequence[Action], states: Mapping[int, PlayerState], now: float
    ) -> str:
        if self.scene == "boot":
            self.enter("lobby", now)
        if self.scene == "lobby":
            for action in actions:
                if action.kind == "pose" and action.pose == "hands_up":
                    self.ready_slots.add(action.slot)
            if self.ready_slots == {0, 1} and all(
                states.get(slot) is not None and states[slot].tracking_ok for slot in (0, 1)
            ):
                self.enter("loading", now)
        elif (
            self.scene == "loading"
            and self.loading_ready
            and now - self.entered_at >= float(self.cfg["game"]["loading_s"])
        ):
            self.enter("fight", now)
        elif self.scene == "victory":
            for action in actions:
                if action.kind == "pose" and action.pose == "hands_up":
                    self.victory_ready.add(action.slot)
            if self.victory_ready == {0, 1}:
                self.enter("lobby", now)
        return self.scene
