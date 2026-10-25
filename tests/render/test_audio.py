import copy
from pathlib import Path

import numpy as np
import pygame

from magic_box.core.config import load_config
from magic_box.render.audio import EVENT_SOUNDS, SOUND_NAMES, Audio, synth_all
from tests.factories import make_full_view

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_synth_all_makes_every_sound_in_range():
    waves = synth_all(22050)
    assert set(waves) == set(SOUND_NAMES)
    assert set(EVENT_SOUNDS.values()) <= set(SOUND_NAMES)
    for name, w in waves.items():
        assert w.dtype == np.float32 and w.ndim == 1 and len(w) > 100, name
        assert np.isfinite(w).all() and np.max(np.abs(w)) <= 0.9 + 1e-5, name


def test_audio_is_silently_off_under_the_dummy_driver():
    pygame.init()
    try:
        audio = Audio(CFG)
        assert audio.enabled is False and audio.sounds == {}
        audio.update(make_full_view("fight"))
        audio.update(make_full_view("loading"))
        audio.play("hit")
    finally:
        pygame.quit()


def test_audio_off_when_disabled_in_config():
    cfg = copy.deepcopy(CFG)
    cfg["render"]["audio"]["enabled"] = False
    audio = Audio(cfg)
    assert audio.enabled is False
    audio.update(make_full_view("fight"))
