import copy
import time
from pathlib import Path

import numpy as np

from magic_box.core.config import load_config
from magic_box.pipeline.frame_bus import FrameBus
from magic_box.pipeline.sources import (
    FakeSources,
    KeyboardVoiceSource,
    LiveSources,
    ReplaySources,
    WebcamSources,
)
from magic_box.pipeline.streams import DropOldestQueue
from magic_box.replay.record import SessionRecorder
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
SPELLS = {0: ["fireball", "flame_wall", "inferno"], 1: ["bolt", "chain", "static_field"]}


def test_fake_sources_poll():
    inputs = FakeSources(CFG).poll(frozenset(), now=0.0, dt=0.0)
    assert sorted(s.slot for s in inputs.states) == [0, 1]
    assert inputs.voice == [] and inputs.frame is not None


def test_webcam_sources_replace_synthetic_frame_without_blocking():
    class Capture:
        def __init__(self):
            self.delivered = False
            self.released = False

        def isOpened(self):
            return True

        def set(self, prop, value):
            return True

        def read(self):
            if not self.delivered:
                self.delivered = True
                return True, np.full((10, 20, 3), 17, dtype=np.uint8)
            time.sleep(0.001)
            return False, None

        def release(self):
            self.released = True

    capture = Capture()
    cfg = copy.deepcopy(CFG)
    cfg["fake"]["webcam"]["pose_tracking"] = False

    class Cv2:
        CAP_PROP_FRAME_WIDTH = 1
        CAP_PROP_FRAME_HEIGHT = 2
        COLOR_BGR2BGRA = 3

        @staticmethod
        def VideoCapture(device):
            assert device == cfg["fake"]["webcam"]["device"]
            return capture

        @staticmethod
        def resize(image, size):
            return np.full((size[1], size[0], 3), image[0, 0, 0], dtype=np.uint8)

        @staticmethod
        def cvtColor(image, code):
            assert code == Cv2.COLOR_BGR2BGRA
            alpha = np.full((*image.shape[:2], 1), 255, dtype=np.uint8)
            return np.concatenate((image, alpha), axis=2)

    src = WebcamSources(cfg, cv2_module=Cv2)
    try:
        deadline = time.monotonic() + 1
        inputs = src.poll(frozenset(), now=0.0, dt=0.0)
        while inputs.frame.image[0, 0, 0] != 17 and time.monotonic() < deadline:
            time.sleep(0.005)
            inputs = src.poll(frozenset(), now=0.0, dt=0.0)
        assert inputs.frame.image.shape == (600, 960, 4)
        assert tuple(inputs.frame.image[0, 0]) == (17, 17, 17, 255)
        assert sorted(s.slot for s in inputs.states) == [0, 1]
    finally:
        src.close()
    assert capture.released


def test_keyboard_voice_edge_triggered():
    kb = KeyboardVoiceSource(CFG)
    kb.set_spells(SPELLS)
    first = kb.poll(frozenset({"1"}), now=1.0)
    assert [(e.slot, e.spell_id, e.match_score) for e in first] == [(0, "fireball", 100.0)]
    assert kb.poll(frozenset({"1"}), now=1.1) == []  # held: no repeat
    assert [e.spell_id for e in kb.poll(frozenset({"0"}), now=1.2)] == ["static_field"]


def test_keyboard_voice_without_spells_is_silent():
    assert KeyboardVoiceSource(CFG).poll(frozenset({"1"}), now=0.0) == []


def test_live_sources_read_queues_and_bus():
    bus = FrameBus.create(64, 48)
    try:
        state_q, voice_q = DropOldestQueue(8), DropOldestQueue(8)
        state_q.put(make_state())
        src = LiveSources(state_q, voice_q, bus)
        got = []
        for _ in range(200):
            got += src.poll(frozenset(), 0.0, 0.0).states
            if got:
                break
        assert got == [make_state()]
        assert src.poll(frozenset(), 0.0, 0.0).frame is None
    finally:
        bus.close()
        bus.unlink()


def test_replay_sources_poll_a_recording(tmp_path):
    rec = SessionRecorder(tmp_path / "s", CFG, "fake")
    rec.write_state(make_state(0, t=10.0))
    rec.close()
    inputs = ReplaySources(tmp_path / "s", CFG).poll(frozenset(), now=1.0, dt=0.0)
    assert [s.slot for s in inputs.states] == [0] and inputs.frame is not None


def test_live_sources_report_dropped_count():
    bus = FrameBus.create(64, 48)
    try:
        state_q, voice_q = DropOldestQueue(1), DropOldestQueue(1)
        for _ in range(3):
            state_q.put(make_state())
        src = LiveSources(state_q, voice_q, bus)
        assert src.poll(frozenset(), 0.0, 0.0).dropped > 0
    finally:
        bus.close()
        bus.unlink()


def test_fake_sources_report_no_drops():
    assert FakeSources(CFG).poll(frozenset(), now=0.0, dt=0.0).dropped == 0
