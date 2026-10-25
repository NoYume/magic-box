"""Lav-mic crosstalk check for final transcripts: compare the two mics' chunk levels.

Both lav mics hear both players. In the lobby every final transcript is a name or a class
pick, so the other player's speech, picked up faintly by this player's mic, would rename this
player. The real speaker's own mic is much louder than the other mic, so a transcript whose
loudest moments were louder on the other mic is crosstalk.

`LevelHistory` keeps each slot's recent chunk levels (RMS in dBFS with `time.monotonic()`
stamps). It is fed and read only on the voice process's event loop, so it needs no lock.

Owner: Nikhil
"""

import math
from collections import deque
from collections.abc import Iterable

import numpy as np

LEVEL_HISTORY_S = 12.0  # level history kept per slot; must cover voice.crosstalk_window_s
SILENT_DBFS = -96.0  # an empty chunk; a digital-silence chunk is clamped near -90.3 dBFS
LOUD_PERCENTILE = 90  # this slot's chunks at or above this percentile are its speech
PAIR_TOLERANCE_CHUNKS = 2  # the other slot's chunk must lie within this many chunks in time


def chunk_dbfs(pcm: bytes) -> float:
    """RMS level of PCM16 LE mono samples in dBFS (0 = full scale)."""
    samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2")
    if samples.size == 0:
        return SILENT_DBFS
    rms = math.sqrt(float(np.mean(np.square(samples, dtype=np.float64))))
    return 20.0 * math.log10(max(rms, 1.0) / 32768.0)


class LevelHistory:
    """Per-slot (t, dBFS) chunk levels for about the last LEVEL_HISTORY_S seconds."""

    def __init__(self, slots: Iterable[int], chunk_ms: int) -> None:
        self._chunk_s = chunk_ms / 1000.0
        maxlen = math.ceil(LEVEL_HISTORY_S / self._chunk_s)
        self._levels: dict[int, deque[tuple[float, float]]] = {
            slot: deque(maxlen=maxlen) for slot in slots
        }

    def add(self, slot: int, t: float, pcm: bytes) -> None:
        levels = self._levels.get(slot)
        if levels is not None:
            levels.append((t, chunk_dbfs(pcm)))

    def _window(self, slot: int, start: float, end: float) -> np.ndarray:
        rows = [row for row in self._levels.get(slot, ()) if start <= row[0] <= end]
        return np.asarray(rows, dtype=np.float64).reshape(-1, 2)

    def excess_db(self, slot: int, other: int, start: float, end: float) -> float | None:
        """How much louder `other`'s mic was than `slot`'s while `slot`'s mic was loudest.

        Takes `slot`'s chunks in [start, end] at or above its LOUD_PERCENTILE level (the
        speech its transcript came from), pairs each with `other`'s nearest chunk in time, and
        returns the median of (other - slot) in dB. Positive means the other mic was louder.
        None when either slot has no level data in the window (one mic, or a dead one).
        """
        mine = self._window(slot, start, end)
        theirs = self._window(other, start, end)
        if len(mine) == 0 or len(theirs) == 0:
            return None
        loud = mine[mine[:, 1] >= np.percentile(mine[:, 1], LOUD_PERCENTILE)]
        their_t = theirs[:, 0]
        order = np.argsort(their_t)
        their_t, their_db = their_t[order], theirs[order, 1]
        diffs = []
        for t, db in loud:
            i = int(np.searchsorted(their_t, t))
            near = [j for j in (i - 1, i) if 0 <= j < len(their_t)]
            j = min(near, key=lambda k: abs(their_t[k] - t))
            if abs(their_t[j] - t) <= PAIR_TOLERANCE_CHUNKS * self._chunk_s:
                diffs.append(their_db[j] - db)
        if not diffs:
            return None
        return float(np.median(diffs))
