"""Per-tick timing and camera-to-screen latency, summarized over a window.

Owner: Nikhil
"""

STAGES = ("poll", "intent", "engine", "draw")


class PerfStats:
    """Accumulates stage times (seconds) and latency; `last` is the last full window."""

    def __init__(self, window_s: float) -> None:
        self._window_s = window_s
        self._start_t: float | None = None
        self._reset()
        self.last: dict[str, float] = {}

    def _reset(self) -> None:
        self._sum = dict.fromkeys(STAGES, 0.0)
        self._max_tick = 0.0
        self._ticks = 0
        self._lat_sum = 0.0
        self._lat_n = 0
        self._lat_max = 0.0

    def add_tick(self, now: float, stages: dict[str, float], latency_s: float | None) -> bool:
        """Record one tick. True when a window just closed (`last` was refreshed)."""
        if self._start_t is None:
            self._start_t = now
        for k in STAGES:
            self._sum[k] += stages.get(k, 0.0)
        self._max_tick = max(self._max_tick, sum(stages.get(k, 0.0) for k in STAGES))
        self._ticks += 1
        if latency_s is not None:
            self._lat_sum += latency_s
            self._lat_n += 1
            self._lat_max = max(self._lat_max, latency_s)
        if now - self._start_t < self._window_s:
            return False
        n = max(self._ticks, 1)
        self.last = {f"{k}_ms": 1000 * self._sum[k] / n for k in STAGES}
        self.last["tick_max_ms"] = 1000 * self._max_tick
        if self._lat_n:
            self.last["latency_ms"] = 1000 * self._lat_sum / self._lat_n
            self.last["latency_max_ms"] = 1000 * self._lat_max
        self._start_t = now
        self._reset()
        return True

    def short(self) -> str:
        """One line for the overlay header; empty before the first window closes."""
        if not self.last:
            return ""
        s = self.last
        text = (
            f"poll {s['poll_ms']:.1f} intent {s['intent_ms']:.1f} "
            f"engine {s['engine_ms']:.1f} draw {s['draw_ms']:.1f} ms"
        )
        if "latency_ms" in s:
            text += f" | lat {s['latency_ms']:.0f} ms"
        return text

    def long(self) -> str:
        if not self.last:
            return ""
        s = self.last
        text = f"perf: {self.short()} | worst tick {s['tick_max_ms']:.1f} ms"
        if "latency_max_ms" in s:
            text += f" | worst lat {s['latency_max_ms']:.0f} ms"
        return text
