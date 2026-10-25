"""Windowed step and duck dodge detection (spec section 8, intent/).

Owner: Nikhil
"""

from collections import deque

from magic_box.core.config import Config
from magic_box.core.contracts import PlayerState

_EPS = 1e-9  # float slack so a step or duck of exactly the threshold counts


class DodgeDetector:
    def __init__(self, cfg: Config) -> None:
        intent = cfg["intent"]
        self.step_m: float = intent["dodge_step_m"]
        self.duck_m: float = intent["dodge_duck_m"]
        self.lookback_s: float = intent["dodge_lookback_s"]
        # per slot: (t, root.x, head.y)
        self._windows: dict[int, deque[tuple[float, float, float]]] = {}

    def update(self, state: PlayerState) -> str | None:
        """Returns "step", "duck" or None. A report clears that slot's window."""
        window = self._windows.setdefault(state.slot, deque())
        window.append((state.t, state.root[0], state.head[1]))
        while window and window[0][0] < state.t - self.lookback_s:
            window.popleft()
        x, head_y = state.root[0], state.head[1]
        # +Y is down: a duck is head.y increasing; standing up is not a duck.
        stepped = any(abs(x - w[1]) >= self.step_m - _EPS for w in window)
        ducked = head_y - min(w[2] for w in window) >= self.duck_m - _EPS
        if not (stepped or ducked):
            return None
        window.clear()
        return "step" if stepped else "duck"
