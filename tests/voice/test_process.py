"""Tests for the voice process session logic with fake streams and a fake mic.

No network and no real mic: `serve` gets in-module doubles for the Muse stream and the mic.

Owner: Nikhil
"""

import asyncio
import copy
import threading
import time
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import VoiceConfig
from magic_box.voice.matcher import match_incantation
from magic_box.voice.mic import MicError
from magic_box.voice.muse_stream import MuseError
from magic_box.voice.process import BACKOFF_RESET_S, _Sessions, run, serve

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")

INC = {0: {"fireball": "embers of the forty acres burn"}, 1: {"bolt": "storm of speedway strike"}}
OTHER = {0: {"heal": "gentle light of morning mends"}, 1: {"shield": "iron wall of thunder"}}
ENV = {"META_MODEL_API_KEY": "k"}
KW0 = ["embers", "forty", "acres", "burn"]
KW1 = ["storm", "speedway", "strike"]
SILENCE = b"\x00" * 2560  # 80 ms of PCM16 zeros at 16 kHz


def fast_cfg(**voice):
    cfg = copy.deepcopy(CFG)
    cfg["voice"].update(
        silence_after_s=0.05, reconnect_backoff_s=0.01, reconnect_max_s=0.04, session_max_s=60
    )
    cfg["voice"].update(voice)
    return cfg


def speech_start(turn=1):
    return {"type": "speechStart", "turnId": turn}


def transcript(text):
    return {"type": "transcript", "transcript": text, "final": False}


def speech_complete(text, turn=1):
    return {"type": "speechComplete", "turnId": turn, "transcript": text}


class FakeStream:
    """MuseStream double. Events come from `inbox`; pushing None ends `events()` with `end_code`."""

    def __init__(self, events=(), close_code=1000, fail=False):
        self.fail = fail
        self.end_code = close_code
        self.inbox: asyncio.Queue = asyncio.Queue()
        for event in events:
            self.inbox.put_nowait(event)
        self.keywords = None
        self.connected = False
        self.audio: list[bytes] = []
        self.closed = False
        self.close_code = None

    async def connect(self, keywords):
        self.keywords = list(keywords)
        if self.fail:
            raise MuseError("handshake failed")
        self.connected = True

    async def send_audio(self, pcm):
        self.audio.append(pcm)

    async def events(self):
        while True:
            event = await self.inbox.get()
            if event is None:
                self.close_code = self.end_code
                return
            yield event

    async def close(self):
        self.closed = True

    def drained(self):
        """Connected and every scripted event consumed by the receiver."""
        return self.connected and self.inbox.empty()


class StreamFactory:
    """stream_factory double: hands out each slot's scripted streams in order, then idle ones."""

    def __init__(self, scripts=None):
        self.scripts = {slot: list(streams) for slot, streams in (scripts or {}).items()}
        self.by_slot: dict[int, list[FakeStream]] = {0: [], 1: []}
        self.streams: list[FakeStream] = []
        self.keys: list[str] = []

    def __call__(self, slot, api_key):
        script = self.scripts.get(slot)
        stream = script.pop(0) if script else FakeStream()
        self.by_slot[slot].append(stream)
        self.streams.append(stream)
        self.keys.append(api_key)
        return stream

    def streams_for_slot(self, slot):
        return self.by_slot[slot]

    def keywords_for_slot(self, slot):
        return [s.keywords for s in self.by_slot[slot]]

    def connected(self, slot):
        return [s for s in self.by_slot[slot] if s.connected]


class FakeMic:
    """mic_factory double: calling it stores the sink; start() can raise MicError."""

    def __init__(self, fail=False):
        self.fail = fail
        self.sink = None
        self.started = False
        self.stopped = False
        self.errors: list[BaseException] = []

    def __call__(self, sink):
        self.sink = sink
        return self

    def feed(self, chunks):
        """Call the sink from another thread, like the audio callback, and wait for it."""

        def deliver():
            for slot, pcm in chunks:
                try:
                    self.sink(slot, pcm)
                except BaseException as exc:  # the sink must never raise into the audio thread
                    self.errors.append(exc)

        feeder = threading.Thread(target=deliver)
        feeder.start()
        feeder.join()

    def start(self):
        if self.fail:
            raise MicError("no input device")
        self.started = True

    def stop(self):
        self.stopped = True


class ListQueue:
    def __init__(self):
        self.items = []

    def put(self, item):
        self.items.append(item)

    def drain(self):
        items, self.items = self.items, []
        return items


class Run:
    """One serve() run: published events, pending control items, recorded backoff delays."""

    def __init__(
        self,
        cfg=None,
        env=ENV,
        factory=None,
        mic=None,
        configs=(),
        clock=time.monotonic,
        on_event=None,
    ):
        self.cfg = cfg or fast_cfg()
        self.env = env
        self.factory = factory or StreamFactory()
        self.mic = mic or FakeMic()
        self.controls = list(configs)
        self.clock = clock
        self.events = []
        self.sleeps: list[float] = []
        self.stopped = False
        self.loop_errors: list[dict] = []  # anything the loop's exception handler would log
        self.on_event = on_event  # called inside publish, in the same step as the event
        self.stop_s: float | None = None  # how long serve took to return after stop

    def publish(self, event):
        self.events.append(event)
        if self.on_event is not None:
            self.on_event(event)

    def drain(self):
        items, self.controls = self.controls, []
        return items

    async def sleep(self, delay):
        self.sleeps.append(delay)
        await asyncio.sleep(delay)

    def statuses(self, slot):
        return [e.text for e in self.events if e.kind == "status" and e.slot == slot]

    def sessions(self, slot):
        """Sessions serve has announced as connected (the fake's own flag is set earlier)."""
        return self.statuses(slot).count("connected")

    def of_kind(self, kind):
        return [e for e in self.events if e.kind == kind]


def run_async(main, timeout=5.0):
    """asyncio.run(wait_for(main(), timeout)) in a daemon thread, joined with a deadline.

    wait_for alone can't bound a hang: it waits for the cancelled task to finish, which never
    happens if the code under test swallows the cancel. Then this fails instead of hanging.
    """
    outcome: dict = {}

    def target():
        try:
            outcome["result"] = asyncio.run(asyncio.wait_for(main(), timeout))
        except BaseException as exc:
            outcome["error"] = exc

    runner = threading.Thread(target=target, daemon=True)
    runner.start()
    runner.join(timeout + 3.0)
    assert not runner.is_alive(), "the event loop hung: a cancel was ignored"
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")


async def until(cond, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "condition not met in time"
        await asyncio.sleep(0.01)


def run_serve(driver=None, *, stop_after=0.0, **kwargs):
    """Run serve() until `driver(run)` returns (plus stop_after), then stop it and wait."""
    r = Run(**kwargs)

    async def main():
        asyncio.get_running_loop().set_exception_handler(lambda _, ctx: r.loop_errors.append(ctx))
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
            if driver is not None:
                await driver(r)
            await asyncio.sleep(stop_after)
            assert not task.done(), "serve returned before stop"
        finally:
            stopped_at = time.monotonic()
            r.stopped = True
            await task
            r.stop_s = time.monotonic() - stopped_at

    run_async(main)
    assert r.loop_errors == []
    return r


def test_no_api_key_publishes_status_and_idles():
    r = run_serve(env={}, stop_after=0.3)
    assert [(e.slot, e.kind, e.text) for e in r.events] == [
        (0, "status", "no api key"),
        (1, "status", "no api key"),
    ]
    assert not r.mic.started and r.factory.streams == []


def test_one_dead_mic_reports_no_mic_for_its_slot_only():
    mic = FakeMic()
    mic.failed_slots = {1}
    r = run_serve(mic=mic, stop_after=0.5)
    assert [(e.slot, e.text) for e in r.events if e.text == "no mic"] == [(1, "no mic")]
    assert r.factory.by_slot[0] and not r.factory.by_slot[1]  # no session for slot 1


def test_no_mic_publishes_status_and_idles():
    r = run_serve(mic=FakeMic(fail=True), stop_after=0.3)
    assert len(r.events) == 2
    assert {(e.slot, e.text) for e in r.events} == {(0, "no mic"), (1, "no mic")}
    assert r.factory.streams == []


def test_incantation_mode_one_event_per_turn():
    second = FakeStream(
        [
            speech_start(1),
            transcript("embers of the"),
            transcript("embers of the forty acres burn"),
            transcript("embers of the forty acres burn now"),
            speech_complete("embers of the forty acres burn now", 1),
            speech_start(2),
            transcript("embers of the forty acres burn"),
        ]
    )
    factory = StreamFactory({0: [FakeStream(), second]})

    async def driver(r):
        await until(second.drained)

    r = run_serve(driver, factory=factory, configs=[VoiceConfig("incantation", INC)])
    inc = r.of_kind("incantation")
    assert [(e.slot, e.spell_id, e.match_score) for e in inc] == [
        (0, "fireball", 100.0),
        (0, "fireball", 100.0),
    ]
    assert [e.text for e in inc] == ["embers of the forty acres burn"] * 2


def test_final_text_matched_when_no_partial_matched():
    second = FakeStream([speech_start(), speech_complete("embers of the forty acres burn")])
    factory = StreamFactory({0: [FakeStream(), second]})

    async def driver(r):
        await until(second.drained)

    r = run_serve(driver, factory=factory, configs=[VoiceConfig("incantation", INC)])
    assert [e.spell_id for e in r.of_kind("incantation")] == ["fireball"]


# Live Muse partials reach the threshold on a prefix: this one scored 91 on 2026-10-25.
PREFIX = "embers of the forty acres"
PREFIX_SCORE = match_incantation(PREFIX, INC[0], 80)[1]


def incantations_after(events, cfg, wait=None):
    """Run one incantation-mode session on slot 0 with `events`; optionally keep it open."""
    second = FakeStream(events)
    factory = StreamFactory({0: [FakeStream(), second]})

    async def driver(r):
        await until(second.drained)
        if wait is not None:
            await wait(r)

    r = run_serve(driver, cfg=cfg, factory=factory, configs=[VoiceConfig("incantation", INC)])
    return [(e.spell_id, e.match_score, e.text) for e in r.of_kind("incantation")]


def test_prefix_match_waits_for_the_whole_phrase():
    assert 80 <= PREFIX_SCORE < 95
    events = [speech_start(), transcript(PREFIX), transcript(PREFIX + " burn")]
    cfg = fast_cfg(perfect_hold_s=5.0)
    assert incantations_after(events, cfg) == [("fireball", 100.0, PREFIX + " burn")]


def test_held_prefix_match_publishes_when_the_hold_ends():
    async def wait(r):
        assert r.of_kind("incantation") == []  # still held
        await until(lambda: r.of_kind("incantation"))

    events = [speech_start(), transcript(PREFIX), transcript("embers of the forty")]
    out = incantations_after(events, fast_cfg(perfect_hold_s=0.3), wait)
    assert out == [("fireball", PREFIX_SCORE, PREFIX)]  # the best partial, not the last


def test_speech_end_publishes_a_held_match_at_once():
    events = [speech_start(), transcript(PREFIX), {"type": "speechEnd", "turnId": 1}]
    started = time.monotonic()
    assert incantations_after(events, fast_cfg(perfect_hold_s=30.0)) == [
        ("fireball", PREFIX_SCORE, PREFIX)
    ]
    assert time.monotonic() - started < 5.0


def test_next_speech_start_publishes_the_held_match_and_rearms():
    events = [speech_start(1), transcript(PREFIX), speech_start(2), transcript(PREFIX + " burn")]
    assert incantations_after(events, fast_cfg(perfect_hold_s=30.0)) == [
        ("fireball", PREFIX_SCORE, PREFIX),
        ("fireball", 100.0, PREFIX + " burn"),
    ]


def test_zero_hold_publishes_the_first_match():
    events = [speech_start(), transcript(PREFIX), transcript(PREFIX + " burn")]
    assert incantations_after(events, fast_cfg(perfect_hold_s=0)) == [
        ("fireball", PREFIX_SCORE, PREFIX)
    ]


def test_speech_complete_publishes_a_held_match_at_once():
    events = [speech_start(), transcript(PREFIX), speech_complete("embers of the forty")]
    started = time.monotonic()
    assert incantations_after(events, fast_cfg(perfect_hold_s=30.0)) == [
        ("fireball", PREFIX_SCORE, PREFIX)  # the final scores lower: the held best wins
    ]
    assert time.monotonic() - started < 5.0


@pytest.mark.parametrize(
    "change", [VoiceConfig("transcript", {}), VoiceConfig("incantation", OTHER)]
)
def test_held_match_is_dropped_on_a_mode_or_incantation_change(change):
    second = FakeStream([speech_start(), transcript(PREFIX)])
    factory = StreamFactory({0: [FakeStream(), second]})

    async def driver(r):
        await until(second.drained)
        r.controls.append(change)  # the scene changes while the match is held (0.1 s polls)
        await until(lambda: len(factory.connected(0)) == 3)
        await asyncio.sleep(0.8)  # past the 0.6 s hold: a leaked timer would have fired

    r = run_serve(
        driver,
        cfg=fast_cfg(perfect_hold_s=0.6),
        factory=factory,
        configs=[VoiceConfig("incantation", INC)],
    )
    assert second.closed and r.of_kind("incantation") == []


def test_held_match_is_published_when_the_stream_drops():
    events = [speech_start(), transcript(PREFIX), None]  # None: the server closes the socket
    second = FakeStream(events, close_code=1011)
    factory = StreamFactory({0: [FakeStream(), second]})

    async def driver(r):
        await until(lambda: "reconnecting" in r.statuses(0))

    r = run_serve(
        driver,
        cfg=fast_cfg(perfect_hold_s=30.0),
        factory=factory,
        configs=[VoiceConfig("incantation", INC)],
    )
    inc = r.of_kind("incantation")
    assert [(e.spell_id, e.match_score, e.text) for e in inc] == [
        ("fireball", PREFIX_SCORE, PREFIX)
    ]


class SendFailsWhenDrained(FakeStream):
    """A dropped socket seen by the sender first: sending fails once the events are read."""

    async def send_audio(self, pcm):
        if self.drained():
            raise ConnectionError("socket gone")
        await super().send_audio(pcm)


def test_held_match_is_published_when_the_sender_sees_the_drop_first():
    second = SendFailsWhenDrained([speech_start(), transcript(PREFIX)])
    factory = StreamFactory({0: [FakeStream(), second]})

    async def driver(r):
        await until(lambda: "reconnecting" in r.statuses(0))

    r = run_serve(
        driver,
        cfg=fast_cfg(perfect_hold_s=30.0),
        factory=factory,
        configs=[VoiceConfig("incantation", INC)],
    )
    assert [e.spell_id for e in r.of_kind("incantation")] == ["fireball"]


def test_only_own_players_set_matches():
    second = FakeStream(
        [
            speech_start(),
            transcript("storm of speedway strike"),
            speech_complete("storm of speedway strike"),
        ]
    )
    factory = StreamFactory({0: [FakeStream(), second]})

    async def driver(r):
        await until(second.drained)

    r = run_serve(driver, factory=factory, configs=[VoiceConfig("incantation", INC)])
    assert r.of_kind("incantation") == []


def test_transcript_mode_emits_final_text_only():
    first = FakeStream(
        [
            speech_start(1),
            transcript("my name"),
            speech_complete("my name is ada", 1),
            speech_start(2),
            speech_complete("   ", 2),
        ]
    )
    factory = StreamFactory({1: [first]})

    async def driver(r):
        await until(first.drained)

    r = run_serve(driver, factory=factory)
    assert [(e.slot, e.kind, e.text) for e in r.of_kind("transcript")] == [
        (1, "transcript", "my name is ada")
    ]
    assert r.of_kind("incantation") == []


def test_config_change_restarts_with_new_keywords():
    factory = StreamFactory()

    async def driver(r):
        await until(lambda: r.sessions(0) == r.sessions(1) == 1)
        r.controls.append(VoiceConfig("transcript", {}))  # same as the start mode: no restart
        await asyncio.sleep(0.25)
        assert len(factory.streams) == 2
        r.controls.append(VoiceConfig("incantation", INC))
        await until(lambda: r.sessions(0) == r.sessions(1) == 2)

    r = run_serve(driver, factory=factory)
    assert factory.keywords_for_slot(0) == [[], KW0]
    assert factory.keywords_for_slot(1) == [[], KW1]
    assert factory.streams_for_slot(0)[0].closed and factory.streams_for_slot(1)[0].closed
    assert r.statuses(0) == r.statuses(1) == ["connected", "connected"]
    assert r.sleeps == []


def test_burst_of_configs_restarts_once_with_newest():
    factory = StreamFactory()
    burst = [
        VoiceConfig("incantation", OTHER),
        VoiceConfig("transcript", {}),
        VoiceConfig("incantation", INC),
        "not a VoiceConfig",  # ignored
    ]

    async def driver(r):
        await until(lambda: r.sessions(0) == r.sessions(1) == 2)
        await asyncio.sleep(0.25)  # more control polls: no further restart

    run_serve(driver, factory=factory, configs=burst)
    assert factory.keywords_for_slot(0) == [[], KW0]
    assert factory.keywords_for_slot(1) == [[], KW1]


def test_drop_reconnects_with_backoff_and_status():
    first = FakeStream([None], close_code=1011)
    factory = StreamFactory({0: [first]})

    async def driver(r):
        await until(lambda: len(r.statuses(0)) >= 3)

    r = run_serve(driver, factory=factory)
    statuses = [e.text for e in r.events if e.kind == "status" and e.slot == 0]
    assert statuses[:3] == ["connected", "reconnecting", "connected"]
    assert r.sleeps[0] == pytest.approx(0.01)
    assert first.closed
    assert r.statuses(1) == ["connected"]


def test_close_1008_uses_max_backoff(capsys):
    factory = StreamFactory({0: [FakeStream([None], close_code=1008)]})

    async def driver(r):
        await until(lambda: len(r.statuses(0)) >= 3)

    r = run_serve(driver, factory=factory)
    assert r.statuses(0)[:3] == ["connected", "reconnecting", "connected"]
    assert r.sleeps[0] == pytest.approx(0.04)
    assert "1008" in capsys.readouterr().err


def test_handshake_failure_retries_and_never_exits(capsys):
    factory = StreamFactory({0: [FakeStream(fail=True), FakeStream(fail=True)]})

    async def driver(r):
        await until(lambda: len(r.statuses(0)) >= 3)

    r = run_serve(driver, factory=factory, env={"META_MODEL_API_KEY": "sk-secret-123"})
    statuses = [e.text for e in r.events if e.kind == "status" and e.slot == 0]
    assert statuses[:3] == ["reconnecting", "reconnecting", "connected"]
    assert r.sleeps[:2] == pytest.approx([0.01, 0.02])
    assert set(factory.keys) == {"sk-secret-123"}
    assert "sk-secret-123" not in capsys.readouterr().err


def test_backoff_doubles_to_cap_and_resets_after_long_session():
    now = [100.0]
    long_lived = FakeStream(close_code=1011)
    failing = [FakeStream(fail=True) for _ in range(4)]
    factory = StreamFactory({0: [*failing, long_lived]})

    async def driver(r):
        await until(lambda: r.sessions(0) == 1)  # serve noted the session start
        now[0] += BACKOFF_RESET_S + 1.0
        long_lived.inbox.put_nowait(None)
        await until(lambda: len(r.sleeps) == 5)

    r = run_serve(driver, factory=factory, clock=lambda: now[0])
    assert r.sleeps == pytest.approx([0.01, 0.02, 0.04, 0.04, 0.01])


def test_backoff_wait_ends_on_config_change_and_stop():
    factory = StreamFactory({0: [FakeStream(fail=True), FakeStream(fail=True)]})

    async def driver(r):
        await until(lambda: r.sleeps == [30.0])
        r.controls.append(VoiceConfig("incantation", INC))
        await until(lambda: len(r.sleeps) == 2)  # the change cut the wait; the retry failed too

    start = time.monotonic()
    r = run_serve(
        driver, factory=factory, cfg=fast_cfg(reconnect_backoff_s=30.0, reconnect_max_s=30.0)
    )
    assert time.monotonic() - start < 1.0  # stop cut the second 30 s wait too
    assert factory.keywords_for_slot(0) == [[], KW0]
    assert r.statuses(0) == ["reconnecting", "reconnecting"]
    assert all(s.closed for s in factory.streams)


def test_mic_chunks_forwarded_and_silence_when_quiet():
    chunk = b"\x01\x00" * 1280
    mic, factory, marks = FakeMic(), StreamFactory(), {}

    def on_event(e):
        if e.slot == 0 and e.text == "connected":
            marks["connected"] = time.monotonic()
            mic.feed([(0, chunk)])  # one chunk right after the connect, then a quiet mic

    async def driver(r):
        await until(lambda: r.sessions(0) == 1)
        await asyncio.sleep(0.25)
        marks["frames"] = list(factory.connected(0)[0].audio)
        marks["snapshot"] = time.monotonic()

    run_serve(driver, factory=factory, mic=mic, on_event=on_event)
    frames = marks["frames"]
    assert frames[0] == chunk
    assert SILENCE in frames[1:]
    assert set(frames[1:]) == {SILENCE}
    quiet_s = marks["snapshot"] - marks["connected"]
    assert len(frames) - 1 <= quiet_s / 0.05 + 2  # paced by silence_after_s, not a tight loop
    assert set(factory.streams_for_slot(1)[0].audio) <= {SILENCE}


def test_full_mic_queue_drops_chunks_and_sink_never_raises():
    chunks = [(0, bytes([i + 1]) * 2560) for i in range(30)] + [(7, b"\x05" * 2560)]
    mic, factory = FakeMic(), StreamFactory()

    def on_event(e):
        if e.slot == 0 and e.text == "connected":
            mic.feed(chunks)  # all land before the sender's first read

    async def driver(r):
        await until(lambda: factory.connected(0) and len(factory.connected(0)[0].audio) >= 26)

    run_serve(driver, factory=factory, mic=mic, on_event=on_event)
    frames = factory.streams_for_slot(0)[0].audio
    assert CFG["voice"]["audio_queue_chunks"] == 25
    assert frames[:25] == [bytes([i + 1]) * 2560 for i in range(25)]  # the 5 newest dropped
    assert frames[25] == SILENCE
    assert mic.errors == []
    mic.sink(0, b"\x00\x00")  # the loop is closed now: swallowed, never raised


def test_session_reopened_at_max_age():
    factory = StreamFactory()

    async def driver(r):
        await until(lambda: r.sessions(0) >= 2)

    r = run_serve(driver, factory=factory, cfg=fast_cfg(session_max_s=0.1))
    assert len(factory.streams_for_slot(0)) >= 2
    assert "reconnecting" not in [e.text for e in r.events if e.slot == 0]
    assert r.statuses(0)[:2] == ["connected", "connected"]
    assert factory.streams_for_slot(0)[0].closed
    assert r.sleeps == []


def test_stop_closes_streams():
    factory = StreamFactory()

    async def driver(r):
        await until(lambda: r.sessions(0) == r.sessions(1) == 1)

    r = run_serve(driver, factory=factory)
    assert len(factory.streams) == 2
    assert all(s.closed for s in factory.streams)
    assert r.mic.stopped
    assert [e.text for e in r.events] == ["connected", "connected"]


def test_run_without_key_returns_on_stop(monkeypatch):
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    q, stop = ListQueue(), threading.Event()
    runner = threading.Thread(target=run, args=(CFG, q, ListQueue(), stop), daemon=True)
    runner.start()
    time.sleep(0.3)
    assert runner.is_alive(), "run() returned before stop"
    stop.set()
    runner.join(timeout=3.0)
    assert not runner.is_alive(), "run() did not return after stop"
    assert [e.text for e in q.items] == ["no api key", "no api key"]


class _AudioSink:
    def __init__(self):
        self.audio = []

    async def send_audio(self, pcm):
        self.audio.append(pcm)


def test_sender_honours_cancel_when_a_chunk_lands_in_the_same_iteration():
    # Python 3.10's asyncio.wait_for returns the inner result and drops a cancel that arrives
    # once the inner future is done; a sender built on it ignored this cancel forever.
    async def go():
        queues = {0: asyncio.Queue(25), 1: asyncio.Queue(25)}
        sessions = _Sessions(
            fast_cfg(), "k", lambda e: None, None, queues, asyncio.sleep, time.monotonic
        )
        sender = asyncio.ensure_future(sessions._send(0, _AudioSink()))
        try:
            await asyncio.sleep(0.01)  # the sender is parked waiting for a chunk
            queues[0].put_nowait(b"\x01\x00")  # a chunk lands ...
            sender.cancel()  # ... in the same loop iteration as the cancel
            await asyncio.wait({sender}, timeout=0.5)
            assert sender.cancelled()
        finally:
            sender.cancel()
            await asyncio.wait({sender}, timeout=0.5)

    run_async(go)


def test_fast_mic_through_restarts_and_reopens_never_wedges():
    mic, factory = FakeMic(), StreamFactory()
    quit_feeding = threading.Event()

    def feed():  # a chunk per slot every ~1 ms, from another thread, through stop and after
        chunk = b"\x01\x00" * 16
        while not quit_feeding.is_set():
            mic.sink(0, chunk)
            mic.sink(1, chunk)
            time.sleep(0.001)

    feeder = threading.Thread(target=feed, daemon=True)

    async def driver(r):
        await until(lambda: mic.started)  # the sink exists from here on
        feeder.start()
        counts = [(r.sessions(0), r.sessions(1))]
        for i in range(4):
            mode = VoiceConfig("transcript", {}) if i % 2 else VoiceConfig("incantation", OTHER)
            r.controls.append(mode)
            await asyncio.sleep(0.1)
            counts.append((r.sessions(0), r.sessions(1)))
        r.controls.append(VoiceConfig("incantation", INC))
        await until(
            lambda: (
                factory.connected(0)[-1].keywords == KW0
                and factory.connected(1)[-1].keywords == KW1
            )
        )
        counts.append((r.sessions(0), r.sessions(1)))
        for before, after in zip(counts, counts[1:], strict=False):
            assert after[0] > before[0] and after[1] > before[1], counts  # no slot wedged

    try:
        r = run_serve(driver, factory=factory, mic=mic, cfg=fast_cfg(session_max_s=0.02))
    finally:
        quit_feeding.set()
        if feeder.is_alive():
            feeder.join()
    assert factory.connected(0)[-1].keywords == KW0  # the newest config's keywords
    assert factory.connected(1)[-1].keywords == KW1
    assert r.stop_s < 0.5
    assert all(s.closed for s in factory.streams)


class SwallowingConnect(FakeStream):
    """connect() blocks, then completes despite being cancelled (as 3.10's wait_for can)."""

    def __init__(self):
        super().__init__()
        self.entered = False

    async def connect(self, keywords):
        self.keywords = list(keywords)
        self.entered = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        self.connected = True


def test_stream_closed_when_its_connect_swallows_the_cancel():
    stuck = SwallowingConnect()
    factory = StreamFactory({0: [stuck]})

    async def driver(r):
        await until(lambda: stuck.entered and r.sessions(1) == 1)
        r.controls.append(VoiceConfig("incantation", INC))
        await until(lambda: r.sessions(0) == 1 and r.sessions(1) == 2)

    r = run_serve(driver, factory=factory)
    assert stuck.connected and stuck.closed
    assert factory.keywords_for_slot(0) == [[], KW0]
    assert r.statuses(0) == ["connected"]  # only the new session was announced


def test_audio_queued_while_reconnecting_is_not_sent():
    stale = b"\x07\x00" * 1280
    mic = FakeMic()
    factory = StreamFactory({0: [FakeStream(fail=True)]})

    def on_event(e):
        if e.slot == 0 and e.text == "reconnecting":
            mic.feed([(0, stale)])  # queued during the backoff

    async def driver(r):
        await until(lambda: factory.connected(0) and len(factory.connected(0)[0].audio) >= 2)

    run_serve(driver, factory=factory, mic=mic, on_event=on_event)
    assert stale not in factory.connected(0)[0].audio


class HangingClose(FakeStream):
    async def close(self):
        self.closed = True
        await asyncio.Event().wait()


def test_stop_is_bounded_when_a_stream_close_hangs(monkeypatch):
    monkeypatch.setattr("magic_box.voice.process.STOP_GRACE_S", 0.1)
    factory = StreamFactory({0: [HangingClose()]})

    async def driver(r):
        await until(lambda: r.sessions(0) == r.sessions(1) == 1)

    r = run_serve(driver, factory=factory)
    assert r.stop_s < 1.0
    assert r.mic.stopped
    assert all(s.closed for s in factory.streams)
