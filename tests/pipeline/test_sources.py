import time
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.core.contracts import VoiceEvent
from magic_box.pipeline.frame_bus import FrameBus
from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource, LiveSources, ReplaySources
from magic_box.pipeline.streams import DropOldestQueue
from magic_box.replay.record import SessionRecorder
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
SPELLS = {0: ["fireball", "flame_wall", "inferno"], 1: ["bolt", "chain", "static_field"]}


def test_fake_sources_poll():
    inputs = FakeSources(CFG).poll(frozenset(), now=0.0, dt=0.0)
    assert sorted(s.slot for s in inputs.states) == [0, 1]
    assert inputs.voice == [] and inputs.frame is not None


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
            time.sleep(0.001)  # multiprocessing.Queue feeder flushes asynchronously
        assert got == [make_state()]
        assert src.poll(frozenset(), 0.0, 0.0).frame is None
    finally:
        bus.close()
        bus.unlink()


def test_replay_sources_feed_recorded_contracts(tmp_path):
    recorder = SessionRecorder(tmp_path, CFG)
    recorder.write_state(make_state(t=10.0))
    recorder.write_voice(VoiceEvent(0, 10.0, "incantation", "embers burn", "fireball", 90.0))
    recorder.close()
    inputs = ReplaySources(tmp_path).poll(frozenset(), now=100.0, dt=0.0)
    assert inputs.states == [make_state(t=10.0)]
    assert [event.spell_id for event in inputs.voice] == ["fireball"]


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
