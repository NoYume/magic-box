"""Tests for the voice sender's real-time pacer, the audio-path health log and the mic levels.

Muse closes a session with 1008 when its audio arrives slower than real time, so the sender
keeps the audio it has sent at wall-clock pace by adding silence. No network and no real mic.

Owner: Nikhil
"""

import asyncio
import threading
import time
from types import SimpleNamespace

import numpy as np

from magic_box.voice.mic import MicHub
from magic_box.voice.process import (
    HEALTH_LOG_S,
    PACE_MAX_PAD_S,
    _Health,
    _Sessions,
    chunk_rms,
    run,
    serve,
)
from tests.voice.fake_sd import FakeSD
from tests.voice.test_process import (
    CFG,
    SILENCE,
    FakeMic,
    FakeStream,
    ListQueue,
    Run,
    StreamFactory,
    fast_cfg,
    run_async,
    until,
)

CHUNK_S = 0.08
LONG = 3600.0  # silence_after_s so large that only chunks, never the quiet-mic timer, are sent


def real_chunk(n: int) -> bytes:
    """A distinct non-silent 80 ms chunk, so order and presence can be checked."""
    return bytes([n % 250 + 1]) * len(SILENCE)


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def make_sender(clock, **voice):
    """(sessions, stream, queue) for slot 0 with a fake clock and no real quiet-mic timer."""
    cfg = fast_cfg(silence_after_s=voice.pop("silence_after_s", LONG), **voice)
    queue = asyncio.Queue(maxsize=cfg["voice"]["audio_queue_chunks"])
    sessions = _Sessions(
        cfg, "k", lambda e: None, lambda s, k: None, {0: queue}, asyncio.sleep, clock
    )
    return sessions, FakeStream(), queue


async def settle(rounds=6):
    for _ in range(rounds):
        await asyncio.sleep(0)


async def push(queue, clock, chunk, advance=0.0):
    """Advance the fake wall clock, then hand the sender one real chunk and let it run."""
    clock.advance(advance)
    queue.put_nowait(chunk)
    await settle()


def audio_seconds(stream):
    return sum(len(pcm) for pcm in stream.audio) / 2 / 16000


def real_only(stream):
    return [pcm for pcm in stream.audio if pcm != SILENCE]


def drive(sender_scenario):
    """Run `sender_scenario(sessions, stream, queue, clock)` with the sender task alive."""

    async def main():
        clock = FakeClock()
        sessions, stream, queue = make_sender(clock)
        task = asyncio.ensure_future(sessions._send(0, stream))
        try:
            await sender_scenario(sessions, stream, queue, clock)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    run_async(main)


def test_on_time_chunks_are_forwarded_untouched():
    chunks = [real_chunk(n) for n in range(10)]

    async def scenario(sessions, stream, queue, clock):
        for chunk in chunks:
            await push(queue, clock, chunk, advance=CHUNK_S)
        assert stream.audio == chunks, "padding was added although the audio kept pace"

    drive(scenario)


def test_a_stall_is_made_up_with_silence_and_real_audio_is_never_lost_or_reordered():
    first, second, third = real_chunk(1), real_chunk(2), real_chunk(3)

    async def scenario(sessions, stream, queue, clock):
        await push(queue, clock, first)
        await push(queue, clock, second, advance=1.0)  # the mic or the socket stalled for 1 s
        wall_s = 1.0
        assert audio_seconds(stream) >= wall_s - sessions._pace_slack_s
        assert real_only(stream) == [first, second]
        padding = [pcm for pcm in stream.audio if pcm == SILENCE]
        assert 0 < len(padding) <= int(PACE_MAX_PAD_S / CHUNK_S)
        assert stream.audio[-1] == second, "silence goes before the real chunk, never after"
        await push(queue, clock, third, advance=CHUNK_S)
        assert real_only(stream) == [first, second, third]
        assert stream.audio[-1] == third

    drive(scenario)


def test_catch_up_never_puts_the_timeline_ahead_and_a_long_stall_is_capped():
    async def scenario(sessions, stream, queue, clock):
        await push(queue, clock, real_chunk(1))
        await push(queue, clock, real_chunk(2), advance=10.0)
        wall_s = 10.0
        # One catch-up adds at most PACE_MAX_PAD_S of silence, and silence alone cannot put the
        # audio sent ahead of the wall clock.
        padded_s = (len(stream.audio) - 2) * CHUNK_S
        assert padded_s <= PACE_MAX_PAD_S + 1e-9
        assert audio_seconds(stream) <= wall_s + CHUNK_S
        # The next real chunk keeps catching up, again by at most the cap.
        await push(queue, clock, real_chunk(3), advance=CHUNK_S)
        assert audio_seconds(stream) <= wall_s + 2 * CHUNK_S
        assert real_only(stream) == [real_chunk(1), real_chunk(2), real_chunk(3)]

    drive(scenario)


def test_a_chunk_burst_after_a_stall_is_forwarded_whole_and_padding_stops():
    burst = [real_chunk(n) for n in range(20)]

    async def scenario(sessions, stream, queue, clock):
        await push(queue, clock, real_chunk(99))
        clock.advance(1.6)  # the sender was blocked; 20 chunks (1.6 s) queued up meanwhile
        for chunk in burst:
            queue.put_nowait(chunk)
        for _ in range(500):  # each chunk takes several loop turns; wait for all of them
            if len(real_only(stream)) == 1 + len(burst):
                break
            await asyncio.sleep(0)
        assert real_only(stream) == [real_chunk(99), *burst]
        assert audio_seconds(stream) >= 1.6 - sessions._pace_slack_s
        assert audio_seconds(stream) <= 1.6 + 21 * CHUNK_S, "the burst was padded on top"

    drive(scenario)


def test_a_quiet_mic_still_runs_at_real_time():
    """The old quiet-mic timer alone sent 80 ms of zeros per 200 ms: 40% of real time."""

    async def main():
        clock = FakeClock()
        sessions, stream, queue = make_sender(clock, silence_after_s=0.01)
        task = asyncio.ensure_future(sessions._send(0, stream))
        try:
            await asyncio.sleep(0.05)  # the first silence chunk starts the session's clock
            assert stream.audio and set(stream.audio) == {SILENCE}
            clock.advance(2.0)  # two seconds of wall clock pass with no mic audio at all
            await asyncio.sleep(0.05)
            assert audio_seconds(stream) >= 2.0 - sessions._pace_slack_s
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    run_async(main)


def test_pace_slack_is_configurable():
    async def main():
        clock = FakeClock()
        sessions, stream, queue = make_sender(clock, pace_slack_s=5.0)
        task = asyncio.ensure_future(sessions._send(0, stream))
        try:
            await push(queue, clock, real_chunk(1))
            await push(queue, clock, real_chunk(2), advance=1.0)
            assert stream.audio == [real_chunk(1), real_chunk(2)], "inside the slack: no padding"
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    run_async(main)


def test_padding_and_drops_are_logged_at_most_every_ten_seconds(capsys):
    clock = FakeClock()
    health = _Health(clock)
    health.maybe_log(0)  # first call only sets the baseline
    health.dropped[0] += 3
    health.padded_s[0] += 0.64
    health.mic = SimpleNamespace(overflows=2)
    clock.advance(HEALTH_LOG_S - 1)
    health.maybe_log(0)
    assert capsys.readouterr().err == "", "logged too early"
    clock.advance(1.5)
    health.maybe_log(0)
    line = capsys.readouterr().err
    assert "slot 0" in line and "3 chunk(s) dropped" in line
    assert "0.64 s of silence" in line and "2 mic input overflow(s)" in line
    clock.advance(HEALTH_LOG_S + 1)
    health.maybe_log(0)
    assert capsys.readouterr().err == "", "nothing new happened, so nothing is logged"


def test_a_full_audio_queue_is_counted_as_dropped_chunks(capsys):
    """serve() drops a chunk when the sender is behind; the health log counts it."""
    cfg = fast_cfg(audio_queue_chunks=1, silence_after_s=LONG)
    mic = FakeMic()
    factory = StreamFactory()

    async def driver(r):
        await until(lambda: r.sessions(0) == 1)
        # Stop the sender from draining by flooding faster than it can run.
        mic.feed([(0, real_chunk(n)) for n in range(200)])
        await asyncio.sleep(0.1)

    r = Run(cfg=cfg, mic=mic, factory=factory)
    health_seen = {}
    real_init = _Health.__init__

    def spy(self, clock):
        real_init(self, clock)
        health_seen["health"] = self

    _Health.__init__ = spy
    try:

        async def main():
            task = asyncio.create_task(
                serve(
                    r.cfg,
                    r.publish,
                    r.drain,
                    lambda: r.stopped,
                    env=r.env,
                    stream_factory=r.factory,
                    mic_factory=r.mic,
                    sleep=r.sleep,
                    clock=r.clock,
                )
            )
            try:
                await driver(r)
            finally:
                r.stopped = True
                await task

        run_async(main)
    finally:
        _Health.__init__ = real_init
    assert health_seen["health"].dropped[0] > 0
    assert health_seen["health"].dropped[1] == 0


def test_mic_hub_counts_input_overflows_and_dropped_blocks():
    sd = FakeSD()
    got = []
    hub = MicHub(
        [{"slot": 0, "device": None, "channel": 0}], 16000, 80, lambda s, b: got.append(b), sd
    )
    hub.start()
    stream = sd.streams[0]
    block = np.ones((1280, 1), dtype=np.int16)
    stream.kwargs["callback"](block, 1280, None, SimpleNamespace(input_overflow=True))
    stream.kwargs["callback"](block, 1280, None, SimpleNamespace(input_overflow=False))
    stream.kwargs["callback"](block, 1280, None, 0)  # sounddevice passes a flags object; 0 is fine
    assert hub.overflows == 1 and len(got) == 3

    def failing_sink(slot, pcm):
        raise RuntimeError("sink broke")

    hub._sink = failing_sink
    stream.kwargs["callback"](block, 1280, None, None)
    assert hub.dropped_blocks == 1
    hub.stop()


def test_chunk_rms_is_linear_full_scale():
    loud = (np.full(1280, 16384, dtype="<i2")).tobytes()  # half of full scale, constant
    assert abs(chunk_rms(loud) - 0.5) < 1e-6
    assert chunk_rms(SILENCE) == 0.0
    assert chunk_rms(b"") == 0.0
    full = (np.full(1280, -32768, dtype="<i2")).tobytes()
    assert abs(chunk_rms(full) - 1.0) < 1e-6


def test_levels_follow_each_slots_chunks_and_reset_on_stop():
    levels = [0.0, 0.0]
    loud = (np.full(1280, 8192, dtype="<i2")).tobytes()  # 0.25 of full scale
    seen = {}

    async def main():
        r = Run(cfg=fast_cfg(silence_after_s=LONG))
        task = asyncio.create_task(
            serve(
                r.cfg,
                r.publish,
                r.drain,
                lambda: r.stopped,
                env=r.env,
                stream_factory=r.factory,
                mic_factory=r.mic,
                sleep=r.sleep,
                clock=r.clock,
                mic_levels=levels,
            )
        )
        try:
            await until(lambda: r.sessions(0) == r.sessions(1) == 1)
            r.mic.feed([(0, loud), (1, SILENCE)])
            seen["loud"], seen["quiet"] = levels[0], levels[1]
            r.mic.feed([(0, SILENCE)])
            seen["after_silence"] = levels[0]
            r.mic.feed([(1, loud)])
            seen["other_slot"] = levels[1]
        finally:
            r.stopped = True
            await task

    run_async(main)
    assert abs(seen["loud"] - 0.25) < 1e-6 and seen["quiet"] == 0.0
    assert seen["after_silence"] == 0.0, "a quiet chunk lowers the level"
    assert abs(seen["other_slot"] - 0.25) < 1e-6
    assert levels == [0.0, 0.0], "stopping zeroes the levels"


def test_levels_are_zero_without_a_mic():
    levels = [0.9, 0.9]

    async def main():
        r = Run(mic=FakeMic(fail=True))
        task = asyncio.create_task(
            serve(
                r.cfg,
                r.publish,
                r.drain,
                lambda: r.stopped,
                env=r.env,
                stream_factory=r.factory,
                mic_factory=r.mic,
                sleep=r.sleep,
                clock=r.clock,
                mic_levels=levels,
            )
        )
        await asyncio.sleep(0.2)
        assert levels == [0.0, 0.0]
        r.stopped = True
        await task

    run_async(main)


def test_run_accepts_levels_and_still_works_without_them(monkeypatch):
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    for kwargs in ({}, {"levels": [0.5, 0.5]}):
        q, stop = ListQueue(), threading.Event()
        runner = threading.Thread(
            target=run, args=(CFG, q, ListQueue(), stop), kwargs=kwargs, daemon=True
        )
        runner.start()
        time.sleep(0.2)
        stop.set()
        runner.join(timeout=3.0)
        assert not runner.is_alive()
        assert [e.text for e in q.items] == ["no api key", "no api key"]
