"""Windowed step and duck dodge detection (spec section 8, intent/).

Owner: Nikhil
"""

from collections import deque

from magic_box.core.config import Config
from magic_box.core.contracts import PlayerState


class DodgeDetector:
    """Detect one dodge edge from movement over a configured lookback window."""

    def __init__(self, cfg: Config) -> None:
        self._step_m = float(cfg["intent"]["dodge_step_m"])
        self._duck_m = float(cfg["intent"]["dodge_duck_m"])
        self._lookback_s = float(cfg["intent"]["dodge_lookback_s"])
        self._history: dict[int, deque[tuple[float, float, float]]] = {
            0: deque(),
            1: deque(),
        }
        self._armed = {0: True, 1: True}

    def update(self, state: PlayerState) -> str | None:
        """Return ``step`` or ``duck`` on a rising edge, otherwise ``None``."""
        history = self._history[state.slot]
        if not state.tracking_ok:
            history.clear()
            self._armed[state.slot] = True
            return None
        history.append((state.t, state.root[0], state.head[1]))
        while history and state.t - history[0][0] > self._lookback_s:
            history.popleft()
        if len(history) < 2:
            return None
        _, old_x, old_head_y = history[0]
        step = abs(state.root[0] - old_x)
        duck = state.head[1] - old_head_y
        if not self._armed[state.slot]:
            if step < self._step_m and duck < self._duck_m:
                self._armed[state.slot] = True
            return None
        kind = "step" if step >= self._step_m else "duck" if duck >= self._duck_m else None
        if kind is not None:
            self._armed[state.slot] = False
        return kind
