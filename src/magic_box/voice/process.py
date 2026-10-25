"""Voice process: one Muse realtime speech-to-text session per player mic.

Spec: docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md section 9 (Voice process).

Starts in transcript mode and connects both slots at once; the game's `VoiceConfig`s switch
to incantation mode (each slot's own set, used as Muse keywords) and back. Sessions reconnect
with backoff and reopen before Muse's 60-minute limit. The process only returns on stop.

Owner: Nikhil
"""

import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from multiprocessing.synchronize import Event
from typing import Any

import numpy as np

from magic_box.core.config import Config
from magic_box.core.contracts import VoiceConfig, VoiceEvent
from magic_box.pipeline.streams import DropOldestQueue, ParentAwareStop
from magic_box.voice.crosstalk import LevelHistory
from magic_box.voice.matcher import keywords_for, match_incantation
from magic_box.voice.mic import MicError, MicHub
from magic_box.voice.muse_stream import MuseStream

SLOTS = (0, 1)
POLL_S = 0.1  # stop and control polling period (spec section 9: control drains every 100 ms)
BACKOFF_RESET_S = 30.0  # a session at least this long resets the reconnect backoff (spec 9)
STOP_GRACE_S = 1.5  # on stop, sessions get this long to close, then are cancelled and get
#                     one POLL_S more: under the supervisor's 2 s join before it terminates us
CLOSE_BAD_REQUEST = 1008  # Muse: bad request or pacing; don't retry unchanged
SPEECH_START_LEAD_S = 1.0  # Muse's speechStart lands after the speech began (queue, network
#                            and endpointer latency): the crosstalk window starts this much earlier

PACE_SLACK_S = 0.25  # voice.pace_slack_s: how far the audio sent may trail the wall clock
PACE_MAX_PAD_S = 2.0  # most silence one catch-up adds, so a long stall never bursts more
HEALTH_LOG_S = 10.0  # the audio-path health line is logged at most this often per slot

_CONNECTED, _FAILED, _WOKEN = "connected", "failed", "woken"


def log_line(msg: str) -> None:
    print(f"voice: {msg}", file=sys.stderr, flush=True)


def chunk_rms(pcm: bytes) -> float:
    """Linear RMS of PCM16 LE mono samples, 0.0 (silence) to 1.0 (full scale)."""
    samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2")
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))) / 32768.0


def zero_levels(levels: Any, slot: int | None = None) -> None:
    """Zero the mic-level array (one slot, or both); a no-op without one."""
    if levels is None:
        return
    for s in SLOTS if slot is None else (slot,):
        try:
            levels[s] = 0.0
        except Exception:
            pass  # cosmetic; a bad array must never stop the voice process


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


async def _cancel(*tasks: asyncio.Future) -> None:
    """Cancel the tasks and wait for them, retrieving whatever they ended with."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _idle(should_stop: Callable[[], bool]) -> None:
    while not should_stop():
        await asyncio.sleep(POLL_S)


class IncantationTurn:
    """One session's incantation matching: at most one published match per speech turn.

    Muse's cumulative partials reach the match threshold on a prefix ("lightning answer"
    scores 80 against "lightning answer my call"), and the whole phrase lands 0-0.9 s later,
    median 0.4 s (measured live 2026-10-25). So a match under `perfect` is held for up to
    `hold_s` while a better partial may arrive; a perfect match, `speechEnd`, `speechComplete`
    or the next `speechStart` publishes the best one at once. `hold_s` 0 publishes the first
    match.
    `publish(text, spell_id, score)` may run from a loop timer. Needs a running event loop.
    `scripts/check_muse.py` drives this same class against the live API.
    """

    def __init__(
        self,
        incantations: Mapping[str, str],
        threshold: float,
        perfect: float,
        hold_s: float,
        publish: Callable[[str, str, float], None],
    ) -> None:
        self._incantations = incantations
        self._threshold = threshold
        self._publish = publish
        self._perfect = perfect
        self._hold_s = hold_s
        self._held: tuple[str, str, float] | None = None  # (text, spell_id, score)
        self._timer: asyncio.TimerHandle | None = None
        self.armed = True  # a session can open mid-utterance, before its first speechStart

    def handle(self, event: Mapping[str, Any]) -> None:
        """Feed one Muse event (any type; unknown ones are ignored)."""
        kind = event.get("type")
        if kind == "speechStart":
            self.start()
        elif kind == "speechEnd":
            self.flush()
        elif self.armed and kind in ("transcript", "speechComplete"):
            text = str(event.get("transcript") or "")
            match = match_incantation(text, self._incantations, self._threshold)
            if match is not None:
                self.offer(text, *match)
            if kind == "speechComplete":
                self.flush()

    def start(self) -> None:
        """speechStart: publish what the last turn held, then re-arm."""
        self.flush()
        self.armed = True

    def offer(self, text: str, spell_id: str, score: float) -> None:
        if not self.armed:
            return
        if self._held is None or score > self._held[2]:
            self._held = (text, spell_id, score)
        if score >= self._perfect or self._hold_s <= 0:
            self.flush()
        elif self._timer is None:
            self._timer = asyncio.get_running_loop().call_later(self._hold_s, self.flush)

    def flush(self) -> None:
        """Publish the held match now, if any, and disarm until the next speechStart."""
        self._stop_timer()
        if self._held is not None:
            held, self._held = self._held, None
            self.armed = False
            try:
                self._publish(*held)
            except Exception as exc:  # may run as a loop callback: never raise into the loop
                log_line(f"cannot publish an incantation: {_describe(exc)}")

    def cancel(self) -> None:
        """Drop the held match unpublished and stop its timer (the session is restarting)."""
        self._held = None
        self._stop_timer()

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


class _Health:
    """What the audio path lost or had to make up, logged at most every HEALTH_LOG_S per slot.

    Muse closes a session with 1008 when its audio arrives slower than real time. This shows
    where it went: chunks dropped from a full queue, silence the pacer added to keep up, and
    PortAudio input overflows (`mic.overflows`, set by `serve` once the mic exists).
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self.mic: Any = None
        self.dropped = dict.fromkeys(SLOTS, 0)
        self.padded_s = dict.fromkeys(SLOTS, 0.0)
        self._mark: dict[int, tuple[float, int, float, int]] = {}

    def _overflows(self) -> int:
        return int(getattr(self.mic, "overflows", 0) or 0)

    def maybe_log(self, slot: int) -> None:
        now = self._clock()
        current = (now, self.dropped[slot], self.padded_s[slot], self._overflows())
        mark = self._mark.setdefault(slot, current)
        if now - mark[0] < HEALTH_LOG_S:
            return
        self._mark[slot] = current
        dropped, padded, overflows = (current[i] - mark[i] for i in (1, 2, 3))
        if dropped or padded > 0 or overflows:
            log_line(
                f"slot {slot}: audio path, last {now - mark[0]:.0f} s: {dropped} chunk(s) dropped "
                f"(queue full), {padded:.2f} s of silence added to keep real-time pace, "
                f"{overflows} mic input overflow(s)"
            )


class _Sessions:
    """Both slots' Muse sessions plus the shared mode, the per-slot wake-ups and the stop flag.

    A slot's wake event is set by a config change or by stop; every wait in a session
    (handshake, streaming, backoff) ends when it is set.
    """

    def __init__(
        self,
        cfg: Config,
        api_key: str,
        publish: Callable[[VoiceEvent], None],
        stream_factory: Callable[[int, str], Any],
        queues: Mapping[int, asyncio.Queue],
        sleep: Callable[[float], Awaitable[Any]],
        clock: Callable[[], float],
        levels: LevelHistory | None = None,
        health: _Health | None = None,
    ) -> None:
        v = cfg["voice"]
        self._key = api_key
        self._publish = publish
        self._factory = stream_factory
        self._queues = queues
        self._sleep = sleep
        self._clock = clock
        self._threshold = v["match_threshold"]
        self._perfect = v["perfect_threshold"]
        self._hold_s = v["perfect_hold_s"]
        self._min_chars = v["min_keyword_chars"]
        self._backoff_s = v["reconnect_backoff_s"]
        self._max_s = v["reconnect_max_s"]
        self._session_max_s = v["session_max_s"]
        self._silence_after_s = v["silence_after_s"]
        self._silence = bytes(v["sample_rate"] * v["chunk_ms"] // 1000 * 2)
        self._chunk_s = v["chunk_ms"] / 1000.0
        self._bytes_per_s = v["sample_rate"] * 2
        self._pace_slack_s = v.get("pace_slack_s", PACE_SLACK_S)
        self._pace_max_chunks = max(1, int(PACE_MAX_PAD_S / self._chunk_s))
        self._health = health or _Health(clock)
        self._levels = levels
        self._crosstalk_margin_db = v["crosstalk_margin_db"]
        self._crosstalk_window_s = v["crosstalk_window_s"]
        self._mode = "transcript"
        self._incantations: dict[int, dict[str, str]] = {}
        self._wake = {slot: asyncio.Event() for slot in SLOTS}
        self._stopping = False

    def status(self, slot: int, text: str) -> None:
        self._publish(VoiceEvent(slot, self._clock(), "status", text, None, 0.0))

    def stop(self) -> None:
        self._stopping = True
        for wake in self._wake.values():
            wake.set()

    def apply(self, config: VoiceConfig) -> None:
        """Restart both sessions if the mode or the incantations changed."""
        if config.mode == self._mode and config.incantations == self._incantations:
            return
        self._mode, self._incantations = config.mode, config.incantations
        for wake in self._wake.values():
            wake.set()

    async def control(self, drain_control: Callable[[], Iterable[Any]]) -> None:
        """Every POLL_S, apply the newest VoiceConfig in the control queue."""
        while True:
            await asyncio.sleep(POLL_S)
            try:
                items = list(drain_control())
            except Exception as exc:
                log_line(f"cannot read the control queue: {_describe(exc)}")
                continue
            configs = [item for item in items if isinstance(item, VoiceConfig)]
            if configs:
                self.apply(configs[-1])

    async def run_slot(self, slot: int) -> None:
        """Connect, stream and reconnect for one slot; returns only after stop()."""
        delay = self._backoff_s
        while not self._stopping:
            # No await between clearing the wake and reading the mode: a change made after
            # this point sets the wake again and restarts the session it would have missed.
            self._wake[slot].clear()
            dropped, lasted, code = await self._attempt(
                slot, self._mode, self._incantations.get(slot, {})
            )
            if lasted >= BACKOFF_RESET_S:
                delay = self._backoff_s
            if not dropped or self._stopping:
                continue  # config change, max age or stop: no status, no backoff
            self.status(slot, "reconnecting")
            if code == CLOSE_BAD_REQUEST:
                wait = self._max_s
                log_line(
                    f"ERROR slot {slot}: Muse closed the session with {code} "
                    f"(bad request or pacing); retrying in {wait:g} s"
                )
            else:
                wait = delay
                closed = "" if code is None else f" (close code {code})"
                log_line(f"slot {slot}: reconnecting in {wait:g} s{closed}")
            delay = min(delay * 2, self._max_s)
            await self._backoff(slot, wait)

    async def _attempt(
        self, slot: int, mode: str, incantations: Mapping[str, str]
    ) -> tuple[bool, float, int | None]:
        """One session: connect, stream until it ends, close the stream.

        Returns (dropped, seconds it stayed connected, close code). `dropped` is False when a
        config change, the session age limit or stop ended it.
        """
        stream = None
        started: float | None = None
        dropped = True
        try:
            keywords = keywords_for(incantations, self._min_chars) if mode == "incantation" else []
            stream = self._factory(slot, self._key)
            outcome = await self._connect(slot, stream, keywords)
            if outcome == _CONNECTED:
                self._drop_queued_audio(slot)
                self.status(slot, "connected")
                started = self._clock()
                dropped = await self._stream(slot, stream, mode, incantations)
            else:
                dropped = outcome == _FAILED
        except Exception as exc:  # any failure counts as a drop; the slot loop never exits
            log_line(f"slot {slot}: session failed: {_describe(exc)}")
        finally:
            if stream is not None:
                await self._close(slot, stream)
        lasted = 0.0 if started is None else self._clock() - started
        code = getattr(stream, "close_code", None) if started is not None else None
        return dropped, lasted, code

    async def _wait_or_wake(
        self, slot: int, tasks: Iterable[asyncio.Future], timeout: float | None = None
    ) -> set:
        """Wait until a task finishes, the timeout passes or the slot is woken; returns done."""
        waker = asyncio.ensure_future(self._wake[slot].wait())
        try:
            done, _ = await asyncio.wait(
                {*tasks, waker}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            await _cancel(waker)
        done.discard(waker)
        return done

    async def _connect(self, slot: int, stream: Any, keywords: list[str]) -> str:
        task = asyncio.ensure_future(stream.connect(keywords))
        try:
            done = await self._wait_or_wake(slot, [task])
        finally:
            await _cancel(task)  # no-op once done
        if task not in done or self._wake[slot].is_set():
            return _WOKEN
        exc = asyncio.CancelledError() if task.cancelled() else task.exception()
        if exc is not None:
            log_line(f"slot {slot}: cannot connect: {_describe(exc)}")
            return _FAILED
        return _CONNECTED

    async def _stream(
        self, slot: int, stream: Any, mode: str, incantations: Mapping[str, str]
    ) -> bool:
        """Run the sender and receiver. True if the stream dropped; False at max age or wake."""
        sender = asyncio.ensure_future(self._send(slot, stream))
        receiver = asyncio.ensure_future(self._receive(slot, stream, mode, incantations))
        try:
            done = await self._wait_or_wake(slot, [sender, receiver], self._session_max_s)
        finally:
            await _cancel(sender, receiver)
        for task in done:
            exc = None if task.cancelled() else task.exception()
            if exc is not None:
                log_line(f"slot {slot}: stream failed: {_describe(exc)}")
        return bool(done) and not self._wake[slot].is_set()

    def _drop_queued_audio(self, slot: int) -> None:
        """Chunks queued before this session (during a backoff or handshake) are stale."""
        queue = self._queues[slot]
        while not queue.empty():
            queue.get_nowait()

    async def _send(self, slot: int, stream: Any) -> None:
        """Forward this slot's mic chunks, keeping the audio sent at real-time pace.

        A chunk of zeros goes out when the mic stays quiet. Muse closes a session whose audio
        arrives slower than real time (close 1008), so the sender also keeps a timeline: the
        audio seconds sent versus the wall-clock seconds since the first send. Real chunks are
        never delayed, dropped or reordered; but when the timeline trails the clock by more than
        `pace_slack_s` (a stalled mic, a blocked socket, chunks lost to a full queue), whole
        chunks of silence are sent first to make it up, at most PACE_MAX_PAD_S per catch-up.
        Padding only happens while behind, so it never pushes the timeline past the clock; it
        runs ahead only by real chunks that queued up (at most `audio_queue_chunks`).

        Never asyncio.wait_for here: on Python 3.10 it drops a cancel that arrives just as a
        chunk does, and the session could then never be stopped or restarted.
        """
        queue = self._queues[slot]
        start: float | None = None
        sent_s = 0.0  # seconds of audio sent in this session
        while True:
            getter = asyncio.ensure_future(queue.get())
            try:
                done, _ = await asyncio.wait({getter}, timeout=self._silence_after_s)
            finally:
                getter.cancel()  # no-op once done; a chunk taken as we are cancelled is dropped
            pcm = getter.result() if done else self._silence
            now = self._clock()
            if start is None:
                start = now
            else:
                behind = (now - start) - sent_s
                if behind > self._pace_slack_s:
                    pad = min(int(behind / self._chunk_s), self._pace_max_chunks)
                    for _ in range(pad):
                        await stream.send_audio(self._silence)
                    sent_s += pad * self._chunk_s
                    self._health.padded_s[slot] += pad * self._chunk_s
            await stream.send_audio(pcm)
            sent_s += len(pcm) / self._bytes_per_s
            self._health.maybe_log(slot)

    async def _receive(
        self, slot: int, stream: Any, mode: str, incantations: Mapping[str, str]
    ) -> None:
        """Turn Muse events into VoiceEvents until the socket closes."""

        def publish(text: str, spell_id: str, score: float) -> None:
            self._publish(VoiceEvent(slot, self._clock(), "incantation", text, spell_id, score))

        turn = IncantationTurn(incantations, self._threshold, self._perfect, self._hold_s, publish)
        speech_start: float | None = None  # transcript mode: this turn's event arrival times
        speech_end: float | None = None
        try:
            async for event in stream.events():
                kind = event.get("type")
                if kind == "error":
                    log_line(f"slot {slot}: Muse error: {event.get('message', '')}")
                elif mode == "incantation":
                    turn.handle(event)
                elif kind == "speechStart":
                    speech_start, speech_end = self._clock(), None
                elif kind == "speechEnd":
                    speech_end = self._clock()
                elif kind == "speechComplete":
                    text = str(event.get("transcript") or "").strip()
                    if text and not self._is_crosstalk(slot, text, speech_start, speech_end):
                        self._publish(
                            VoiceEvent(slot, self._clock(), "transcript", text, None, 0.0)
                        )
                    speech_start = speech_end = None
        finally:
            if self._wake[slot].is_set():
                turn.cancel()  # a mode change, a new VoiceConfig or stop: the match is stale
            else:
                # The stream ended on its own (server close, Wi-Fi drop seen by either task,
                # session age): the player did say it, so publish what the turn held.
                turn.flush()

    def _is_crosstalk(self, slot: int, text: str, start: float | None, end: float | None) -> bool:
        """True if the other mic was louder by crosstalk_margin_db over this utterance.

        The window runs from SPEECH_START_LEAD_S before this turn's speechStart to its
        speechEnd. Muse's events carry no audio times, so their arrival times stand in. With
        no speechStart (the session opened mid-utterance) it is the last crosstalk_window_s
        before the speechEnd, or before now when no speechEnd came either. Never drops
        without level data for both slots in the window.
        """
        if self._levels is None or self._crosstalk_margin_db <= 0:
            return False
        end = self._clock() if end is None else end
        start = end - self._crosstalk_window_s if start is None else start - SPEECH_START_LEAD_S
        other = 1 - slot
        excess = self._levels.excess_db(slot, other, start, end)
        if excess is None or excess < self._crosstalk_margin_db:
            return False
        log_line(
            f'P{slot + 1} transcript dropped as crosstalk (P{other + 1} {excess:+.1f} dB): "{text}"'
        )
        return True

    async def _backoff(self, slot: int, delay: float) -> None:
        """The injected sleep, cut short by stop or a config change."""
        sleeper = asyncio.ensure_future(self._sleep(delay))
        try:
            await self._wait_or_wake(slot, [sleeper])
        finally:
            await _cancel(sleeper)

    async def _close(self, slot: int, stream: Any) -> None:
        try:
            await stream.close()
        except Exception as exc:
            log_line(f"slot {slot}: close failed: {_describe(exc)}")


async def serve(
    cfg: Config,
    publish: Callable[[VoiceEvent], None],
    drain_control: Callable[[], list],
    should_stop: Callable[[], bool],
    *,
    env: Mapping[str, str],
    stream_factory: Callable[[int, str], Any],
    mic_factory: Callable[[Callable[[int, bytes], None]], Any],
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
    mic_levels: Any = None,
) -> None:
    """Run both slots' sessions until `should_stop()`; never returns before that.

    `stream_factory(slot, api_key)` returns a fresh object with MuseStream's async interface;
    `mic_factory(sink)` returns an object with start()/stop() that calls `sink(slot, pcm)`
    from its audio thread. `sleep` is used only for reconnect backoff delays.
    `mic_levels` is an optional length-2 array the process writes (the HUD's mic wave): each
    real chunk sets `mic_levels[slot]` to its linear RMS, 0.0 to 1.0 of full scale; both are
    zeroed when the mic is not running.
    """
    v = cfg["voice"]
    zero_levels(mic_levels)

    def status_all(text: str) -> None:
        for slot in SLOTS:
            publish(VoiceEvent(slot, clock(), "status", text, None, 0.0))

    api_key = (env.get(v["api_key_env"]) or "").strip()
    if not api_key:
        log_line(f"${v['api_key_env']} is not set; speech is off (spell keys still work)")
        status_all("no api key")
        await _idle(should_stop)
        return

    loop = asyncio.get_running_loop()
    queues = {slot: asyncio.Queue(maxsize=v["audio_queue_chunks"]) for slot in SLOTS}
    levels = LevelHistory(SLOTS, v["chunk_ms"])
    health = _Health(clock)

    def put(slot: int, pcm: bytes, t: float) -> None:
        try:
            levels.add(slot, t, pcm)  # on the loop thread, so the audio callback never waits
        except Exception as exc:
            log_line(f"cannot record a mic level: {_describe(exc)}")
        try:
            queues[slot].put_nowait(pcm)
        except asyncio.QueueFull:
            health.dropped[slot] += 1  # the sender is behind; drop this chunk

    def sink(slot: int, pcm: bytes) -> None:
        """Runs on the audio thread: hand the chunk to the loop, never raise."""
        if slot not in queues:
            return
        if mic_levels is not None:
            try:
                mic_levels[slot] = chunk_rms(pcm)
            except Exception:
                pass  # a level is cosmetic; never raise into the audio thread
        try:
            loop.call_soon_threadsafe(put, slot, pcm, clock())  # level stamped at capture
        except RuntimeError:
            pass  # the loop is closed after stop

    mic = mic_factory(sink)
    health.mic = mic
    try:
        mic.start()
    except MicError as exc:
        log_line(f"no mic: {exc}")
        zero_levels(mic_levels)
        status_all("no mic")
        await _idle(should_stop)
        return

    dead = set(getattr(mic, "failed_slots", ()))
    for slot in sorted(dead):
        log_line(f"no mic for slot {slot}; the other player's mic keeps working")
        zero_levels(mic_levels, slot)
        publish(VoiceEvent(slot, clock(), "status", "no mic", None, 0.0))
    sessions = _Sessions(
        cfg, api_key, publish, stream_factory, queues, sleep, clock, levels, health
    )
    slot_tasks = [asyncio.ensure_future(sessions.run_slot(s)) for s in SLOTS if s not in dead]
    control = asyncio.ensure_future(sessions.control(drain_control))
    try:
        await _idle(should_stop)
    finally:
        sessions.stop()
        try:
            control.cancel()
            _, pending = await asyncio.wait([control, *slot_tasks], timeout=STOP_GRACE_S)
            if pending:
                log_line(f"sessions still closing after {STOP_GRACE_S:g} s; cancelling them")
                for task in pending:
                    task.cancel()
                await asyncio.wait(pending, timeout=POLL_S)
            for task in slot_tasks:
                if task.done() and not task.cancelled() and task.exception() is not None:
                    log_line(f"session task failed: {_describe(task.exception())}")
        finally:
            mic.stop()
            zero_levels(mic_levels)


def run(
    cfg: Config,
    voice_q: DropOldestQueue,
    control_q: DropOldestQueue,
    stop: Event,
    levels: Any = None,
) -> None:
    """Capture mics, stream to Muse, publish VoiceEvents; read VoiceConfig from control_q.

    `levels`: optional length-2 array (a multiprocessing RawArray('d', 2) from the game) that
    this process fills with each slot's mic level; see `serve(mic_levels=...)`.
    """
    v = cfg["voice"]
    parent_aware = ParentAwareStop(stop)
    try:
        asyncio.run(
            serve(
                cfg,
                voice_q.put,
                control_q.drain,
                parent_aware.is_set,
                env=os.environ,
                stream_factory=lambda slot, key: MuseStream(
                    v["url"], key, v["model"], v["handshake_timeout_s"]
                ),
                mic_factory=lambda sink: MicHub(v["mics"], v["sample_rate"], v["chunk_ms"], sink),
                mic_levels=levels,
            )
        )
    finally:
        voice_q.cancel_join()  # the game may be gone; never hang at exit on unread events
