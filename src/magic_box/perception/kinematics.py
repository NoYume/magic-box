"""Time-windowed velocity of a scalar signal.

Owner: Enoch
"""

from collections import deque


class WindowedVelocity:
    """Velocity and signed travel of a value over the last `window_s` seconds."""

    def __init__(self, window_s: float) -> None:
        self.window_s = window_s
        self._samples: deque[tuple[float, float]] = deque()

    def add(self, t: float, value: float) -> None:
        if self._samples and t < self._samples[-1][0]:
            self._samples.clear()  # time rewound (e.g. an SVO loop)
        self._samples.append((t, value))
        while self._samples[0][0] < t - self.window_s:
            self._samples.popleft()

    def velocity(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        (t0, v0), (t1, v1) = self._samples[0], self._samples[-1]
        dt = t1 - t0
        return (v1 - v0) / dt if dt > 0 else 0.0

    def travel(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        return self._samples[-1][1] - self._samples[0][1]

    def clear(self) -> None:
        self._samples.clear()
