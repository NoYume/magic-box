"""Sound effects: synthesized with numpy at startup, played on `GameView.events`.

Owner: Adetola

Sounds: cast whoosh, hit thump, dodge swish, block clang, heal chime, buff shimmer, KO boom,
countdown tick and match-start fanfare. Ticks play each second of the loading countdown and of
the last `render.audio.tick_last_s` seconds of the fight. If the mixer cannot open (no audio
device, the SDL dummy audio driver in tests, headless runs) or `render.audio.enabled` is false,
sound is silently off. `Sound.play()` never blocks the game loop.
"""

import math
import os
from collections.abc import Mapping

import numpy as np
import pygame

from magic_box.core.contracts import GameView

EVENT_SOUNDS = {
    "match_start": "start",
    "cast": "cast",
    "hit": "hit",
    "dodge": "dodge",
    "block": "block",
    "heal": "heal",
    "buff": "buff",
    "ko": "ko",
}
SOUND_NAMES = ("cast", "hit", "dodge", "block", "heal", "buff", "ko", "tick", "start")


def _t(rate: int, seconds: float) -> np.ndarray:
    return np.arange(int(rate * seconds), dtype=np.float32) / rate


def _sweep(rate: int, seconds: float, f0: float, f1: float) -> np.ndarray:
    t = _t(rate, seconds)
    f = f0 * (f1 / f0) ** (t / seconds)  # exponential glide
    return np.sin(2 * np.pi * np.cumsum(f) / rate).astype(np.float32)


def _noise(rate: int, seconds: float, smooth: int, rng: np.random.Generator) -> np.ndarray:
    n = rng.uniform(-1.0, 1.0, int(rate * seconds)).astype(np.float32)
    if smooth > 1:
        n = np.convolve(n, np.ones(smooth, np.float32) / smooth, mode="same")
    return n


def _decay(rate: int, seconds: float, tau: float) -> np.ndarray:
    return np.exp(-_t(rate, seconds) / tau).astype(np.float32)


def _swell(rate: int, seconds: float) -> np.ndarray:
    t = _t(rate, seconds)
    return (np.sin(np.pi * t / seconds) ** 2).astype(np.float32)


def _tone(rate: int, seconds: float, freq: float, tau: float, harmonics=(1.0,)) -> np.ndarray:
    t = _t(rate, seconds)
    wave = sum(a * np.sin(2 * np.pi * freq * (k + 1) * t) for k, a in enumerate(harmonics))
    return (wave * np.exp(-t / tau)).astype(np.float32)


def _place(total: np.ndarray, part: np.ndarray, start_s: float, rate: int) -> None:
    i = int(start_s * rate)
    n = min(len(part), len(total) - i)
    if n > 0:
        total[i : i + n] += part[:n]


def _normalize(wave: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(wave))) if wave.size else 0.0
    return (wave * (peak / m)).astype(np.float32) if m > 0 else wave


def synth_all(rate: int, seed: int = 11) -> dict[str, np.ndarray]:
    """Mono float32 waves in [-1, 1] at `rate` Hz, one per name in SOUND_NAMES."""
    rng = np.random.default_rng(seed)
    out: dict[str, np.ndarray] = {}
    d = 0.4
    out["cast"] = _swell(rate, d) * (
        0.7 * _noise(rate, d, 6, rng) + 0.3 * _sweep(rate, d, 260.0, 900.0)
    )
    d = 0.35
    thump = _sweep(rate, d, 150.0, 40.0) * _decay(rate, d, 0.09)
    crack = _noise(rate, d, 2, rng) * _decay(rate, d, 0.02)
    out["hit"] = thump + 0.6 * crack
    d = 0.22
    out["dodge"] = _swell(rate, d) * (
        0.6 * _noise(rate, d, 3, rng) + 0.4 * _sweep(rate, d, 900, 2000)
    )
    d = 0.6
    out["block"] = sum(
        _tone(rate, d, f, 0.12 + 0.05 * i) * a
        for i, (f, a) in enumerate(((523.0, 1.0), (1307.0, 0.6), (2091.0, 0.4), (2930.0, 0.3)))
    ) + 0.4 * _noise(rate, d, 1, rng) * _decay(rate, d, 0.01)
    heal = np.zeros(int(rate * 0.8), np.float32)
    for i, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
        _place(heal, _tone(rate, 0.5, f, 0.18, (1.0, 0.3)), i * 0.08, rate)
    out["heal"] = heal
    d = 0.6
    trem = 0.6 + 0.4 * np.sin(2 * np.pi * 14 * _t(rate, d))
    out["buff"] = (
        _swell(rate, d) * trem * (_sweep(rate, d, 660, 1320) + 0.5 * _sweep(rate, d, 990, 1980))
    )
    d = 1.4
    boom = _sweep(rate, d, 70.0, 28.0) * _decay(rate, d, 0.45)
    fall = _sweep(rate, d, 440.0, 90.0) * _decay(rate, d, 0.5) * 0.5
    out["ko"] = boom + fall + 0.5 * _noise(rate, d, 8, rng) * _decay(rate, d, 0.15)
    out["tick"] = _tone(rate, 0.08, 1000.0, 0.02, (1.0, 0.2))
    start = np.zeros(int(rate * 0.9), np.float32)
    brass = (1.0, 0.5, 0.33, 0.25)
    _place(start, _tone(rate, 0.3, 392.0, 0.2, brass), 0.0, rate)
    _place(start, _tone(rate, 0.6, 523.25, 0.35, brass), 0.18, rate)
    out["start"] = start
    return {name: _normalize(np.asarray(w, np.float32)) for name, w in out.items()}


def _to_sound(wave: np.ndarray, channels: int, volume: float) -> pygame.mixer.Sound:
    pcm = np.clip(wave * volume, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    if channels > 1:
        pcm = np.repeat(pcm[:, None], channels, axis=1)
    return pygame.mixer.Sound(buffer=np.ascontiguousarray(pcm).tobytes())


class Audio:
    """Event sounds. `enabled` is False (and every call a no-op) when the mixer is unavailable."""

    def __init__(self, cfg: Mapping, enabled: bool = True) -> None:
        a = cfg["render"]["audio"]
        self.enabled = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.tick_last_s = float(a["tick_last_s"])
        self._last_secs: tuple[str, int] | None = None
        if not (enabled and a["enabled"]) or os.environ.get("SDL_AUDIODRIVER") == "dummy":
            return
        try:
            if pygame.mixer.get_init() is not None:
                pygame.mixer.quit()
            pygame.mixer.init(
                frequency=int(a["sample_rate"]), size=-16, channels=2, buffer=int(a["buffer"])
            )
            init = pygame.mixer.get_init()
            if init is None or init[1] != -16:
                pygame.mixer.quit()
                return
            freq, _, channels = init
            vol = max(0.0, min(1.0, float(a["volume"])))
            self.sounds = {n: _to_sound(w, channels, vol) for n, w in synth_all(freq).items()}
            pygame.mixer.set_num_channels(int(a["mix_channels"]))
            self.enabled = True
        except (pygame.error, OSError, ValueError, NotImplementedError):
            self.sounds = {}
            self.enabled = False

    def play(self, name: str) -> None:
        sound = self.sounds.get(name)
        if sound is None:
            return
        try:
            sound.play()
        except pygame.error:
            pass

    def update(self, view: GameView) -> None:
        """Play this tick's event sounds and the countdown ticks."""
        if not self.enabled:
            return
        for e in view.events:
            name = EVENT_SOUNDS.get(e.kind)
            if name is not None:
                self.play(name)
        if view.timer_s is None or view.scene not in ("loading", "fight"):
            self._last_secs = None
            return
        secs = math.ceil(view.timer_s)
        key = (view.scene, secs)
        if self._last_secs is not None and key != self._last_secs and secs > 0:
            if view.scene == "loading" or view.timer_s <= self.tick_last_s:
                self.play("tick")
        self._last_secs = key
