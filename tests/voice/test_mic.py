"""Tests for MicHub and resample (no real mic).

Owner: Nikhil
"""

import sys

import numpy as np
import pytest

from magic_box.voice.mic import MicError, MicHub, resample
from tests.voice.fake_sd import FakeSD

CHUNK = 1280  # 80 ms at 16 kHz


def hub(mics, sd, got):
    return MicHub(mics, 16000, 80, lambda slot, pcm: got.append((slot, pcm)), sd=sd)


def test_one_stream_per_device_and_channel_split():
    sd, got = FakeSD(), []
    h = hub(
        [{"slot": 0, "device": "rx", "channel": 0}, {"slot": 1, "device": "rx", "channel": 1}],
        sd,
        got,
    )
    h.start()
    [stream] = sd.streams
    assert (
        stream.kwargs["channels"] == 2
        and stream.kwargs["samplerate"] == 16000
        and stream.kwargs["dtype"] == "int16"
    )
    data = np.zeros((CHUNK, 2), np.int16)
    data[:, 0], data[:, 1] = 1, 2
    stream.feed(data)
    assert [(s, np.frombuffer(p, np.int16)[0], len(p)) for s, p in got] == [
        (0, 1, CHUNK * 2),
        (1, 2, CHUNK * 2),
    ]


def test_mic_entry_without_device_uses_the_system_default():
    sd, got = FakeSD(), []
    hub([{"slot": 0, "channel": 0}, {"slot": 1, "channel": 1}], sd, got).start()
    [stream] = sd.streams
    assert stream.kwargs["device"] is None and stream.kwargs["channels"] == 2


def test_two_devices_two_streams():
    sd, got = FakeSD(), []
    hub(
        [{"slot": 0, "device": "a", "channel": 0}, {"slot": 1, "device": "b", "channel": 0}],
        sd,
        got,
    ).start()
    assert [s.kwargs["device"] for s in sd.streams] == ["a", "b"]
    assert all(s.started for s in sd.streams)


def test_rate_fallback_resamples_to_16k():
    sd, got = FakeSD(reject_rates=(16000,), default_rate=48000.0), []
    hub([{"slot": 0, "device": None, "channel": 0}], sd, got).start()
    stream = sd.streams[-1]  # the retry at the device's default rate
    assert stream.kwargs["samplerate"] == 48000
    assert stream.kwargs["blocksize"] == 3840
    stream.feed(np.full((CHUNK * 3, 1), 7, np.int16))
    assert len(got) == 1 and got[0][0] == 0 and len(got[0][1]) == CHUNK * 2
    assert set(np.frombuffer(got[0][1], np.int16)) == {7}


def test_chunks_buffered_across_callbacks():
    sd, got = FakeSD(), []
    hub([{"slot": 0, "device": None, "channel": 0}], sd, got).start()
    sd.streams[0].feed(np.ones((CHUNK // 2, 1), np.int16))
    assert got == []
    sd.streams[0].feed(np.ones((CHUNK // 2, 1), np.int16))
    assert len(got) == 1


def test_missing_portaudio_raises_mic_error_and_stop_closes():
    with pytest.raises(MicError):
        hub([{"slot": 0, "device": None, "channel": 0}], FakeSD(fail_import=True), []).start()
    sd = FakeSD()
    h = hub([{"slot": 0, "device": None, "channel": 0}], sd, [])
    h.start()
    h.stop()
    h.stop()
    assert all(s.closed for s in sd.streams)


def test_one_dead_device_only_fails_its_own_slot():
    class Flaky(FakeSD):
        def InputStream(self, **kwargs):  # noqa: N802
            if kwargs["device"] == "b":
                raise OSError("boom")
            return super().InputStream(**kwargs)

    sd = Flaky()
    h = hub(
        [{"slot": 0, "device": "a", "channel": 0}, {"slot": 1, "device": "b", "channel": 0}], sd, []
    )
    h.start()
    assert h.failed_slots == {1}
    assert [s.started and not s.closed for s in sd.streams] == [True]  # slot 0 keeps listening


def test_all_devices_dead_still_raises_and_closes():
    class Dead(FakeSD):
        def InputStream(self, **kwargs):  # noqa: N802
            raise OSError("boom")

    h = hub(
        [{"slot": 0, "device": "a", "channel": 0}, {"slot": 1, "device": "b", "channel": 0}],
        Dead(),
        [],
    )
    with pytest.raises(MicError):
        h.start()


def test_sink_error_is_isolated_per_slot():
    sd, got = FakeSD(), []

    def sink(slot, pcm):
        if slot == 0:
            raise RuntimeError("x")
        got.append((slot, pcm))

    mics = [{"slot": 0, "device": "rx", "channel": 0}, {"slot": 1, "device": "rx", "channel": 1}]
    MicHub(mics, 16000, 80, sink, sd=sd).start()
    sd.streams[0].feed(np.ones((CHUNK, 2), np.int16))
    assert [s for s, _ in got] == [1]
    sd.streams[0].feed(np.ones((CHUNK, 2), np.int16))
    assert [s for s, _ in got] == [1, 1]  # slot 0's failed chunk was not re-sent


def test_start_failure_raises_mic_error_and_closes():
    sd = FakeSD(fail_start=True)
    with pytest.raises(MicError, match="cannot start"):
        hub([{"slot": 0, "device": "a", "channel": 0}], sd, []).start()
    assert sd.streams and all(s.closed for s in sd.streams)


def test_import_failure_raises_mic_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    with pytest.raises(MicError):
        hub([{"slot": 0, "device": None, "channel": 0}], None, []).start()


def test_resample():
    out = resample(np.full(4800, 5, np.int16), 48000, 16000)
    assert out.dtype == np.int16 and len(out) == 1600 and set(out) == {5}
    same = resample(np.arange(10, dtype=np.int16), 16000, 16000)
    assert same.dtype == np.int16 and list(same) == list(range(10))
