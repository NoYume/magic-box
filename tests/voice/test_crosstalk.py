"""Tests for dropping lav-mic crosstalk transcripts by comparing the two mics' levels.

No network and no real mic: `serve` gets the fake streams and fake mic from test_process.

Owner: Nikhil
"""

import asyncio
import copy

import numpy as np
import pytest

from magic_box.core.config import validate
from magic_box.core.contracts import VoiceConfig
from magic_box.voice.crosstalk import LevelHistory, chunk_dbfs
from tests.voice.test_process import (
    CFG,
    INC,
    FakeMic,
    FakeStream,
    StreamFactory,
    fast_cfg,
    run_serve,
    speech_complete,
    speech_start,
    transcript,
    until,
)

LOUD, QUIET = 3000, 949  # PCM16 amplitudes about 10 dB apart
CHUNK_S = CFG["voice"]["chunk_ms"] / 1000


def tone(amp):
    """One 80 ms chunk at a constant amplitude (its RMS is `amp`)."""
    return np.full(1280, amp, dtype="<i2").tobytes()


def both(amp0, amp1, n=10):
    """n time-aligned chunk pairs, as the Hollyland receiver's one callback delivers them."""
    return [(0, tone(amp0)), (1, tone(amp1))] * n


def lobby_turn(chunks, *, start=True, cfg=None, text="my name is bob"):
    """P1's Muse session hears one lobby utterance while the mics deliver `chunks`."""
    stream = FakeStream()
    mic = FakeMic()

    async def driver(r):
        await until(lambda: r.sessions(0) == 1 and r.sessions(1) == 1)
        if start:
            stream.inbox.put_nowait(speech_start())
            await until(stream.drained)
        mic.feed(chunks)
        await asyncio.sleep(0.05)  # the sink hands the chunks to the loop
        stream.inbox.put_nowait(speech_complete(text))
        await until(stream.drained)
        await asyncio.sleep(0.05)

    r = run_serve(driver, factory=StreamFactory({0: [stream]}), mic=mic, cfg=cfg)
    return [(e.slot, e.text) for e in r.of_kind("transcript")]


def test_chunk_level_in_dbfs():
    assert chunk_dbfs(tone(32767)) == pytest.approx(0.0, abs=0.01)
    assert chunk_dbfs(tone(LOUD)) - chunk_dbfs(tone(QUIET)) == pytest.approx(10.0, abs=0.05)
    assert chunk_dbfs(tone(0)) < -90
    assert chunk_dbfs(b"") < -90


def test_transcript_dropped_when_the_other_mic_was_10_db_louder(capsys):
    assert lobby_turn(both(QUIET, LOUD)) == []
    assert 'P1 transcript dropped as crosstalk (P2 +10.0 dB): "my name is bob"' in (
        capsys.readouterr().err
    )


def test_transcript_kept_when_own_mic_was_louder():
    assert lobby_turn(both(LOUD, QUIET)) == [(0, "my name is bob")]


def test_transcript_kept_when_both_mics_were_equally_loud():
    assert lobby_turn(both(LOUD, LOUD)) == [(0, "my name is bob")]


def test_transcript_kept_without_level_data_for_the_other_slot():
    only_p1 = [(0, tone(QUIET))] * 10
    assert lobby_turn(only_p1) == [(0, "my name is bob")]


def test_transcript_kept_without_any_level_data():
    assert lobby_turn([]) == [(0, "my name is bob")]


@pytest.mark.parametrize("margin", [0, -3.0])
def test_zero_or_negative_margin_disables_the_check(margin):
    cfg = fast_cfg(crosstalk_margin_db=margin)
    assert lobby_turn(both(QUIET, LOUD), cfg=cfg) == [(0, "my name is bob")]


def test_lookback_window_used_without_a_speech_start(capsys):
    assert lobby_turn(both(QUIET, LOUD), start=False) == []
    assert "dropped as crosstalk" in capsys.readouterr().err


def test_margin_is_the_threshold():
    assert lobby_turn(both(QUIET, LOUD), cfg=fast_cfg(crosstalk_margin_db=12.0)) == [
        (0, "my name is bob")
    ]


def test_incantation_matching_is_unaffected():
    second = FakeStream()
    mic = FakeMic()
    factory = StreamFactory({0: [FakeStream(), second]})

    async def driver(r):
        await until(lambda: second.connected)
        mic.feed(both(QUIET, LOUD))  # P2's mic far louder: crosstalk if this were the lobby
        await asyncio.sleep(0.05)
        for event in (
            speech_start(),
            transcript(INC[0]["fireball"]),
            speech_complete(INC[0]["fireball"]),
        ):
            second.inbox.put_nowait(event)
        await until(second.drained)
        await asyncio.sleep(0.05)

    r = run_serve(driver, factory=factory, mic=mic, configs=[VoiceConfig("incantation", INC)])
    assert [(e.slot, e.spell_id) for e in r.of_kind("incantation")] == [(0, "fireball")]


def test_other_player_talking_at_another_time_does_not_drop():
    """P1 talks, then P2 talks while P1's final is still pending: compare at P1's speech."""
    levels = LevelHistory((0, 1), CFG["voice"]["chunk_ms"])
    t = 0.0
    for _ in range(10):  # P1 talks: P2's mic hears it 10 dB quieter
        levels.add(0, t, tone(LOUD))
        levels.add(1, t, tone(QUIET))
        t += CHUNK_S
    for _ in range(20):  # then P2 talks louder than P1 did: P1's mic hears it quietly
        levels.add(0, t, tone(QUIET // 3))
        levels.add(1, t, tone(LOUD * 3))
        t += CHUNK_S
    excess = levels.excess_db(0, 1, 0.0, t)
    assert excess == pytest.approx(-10.0, abs=0.1)


def test_level_history_needs_aligned_chunks():
    levels = LevelHistory((0, 1), CFG["voice"]["chunk_ms"])
    levels.add(0, 0.0, tone(QUIET))
    levels.add(1, 5.0, tone(LOUD))  # far outside the pairing tolerance
    assert levels.excess_db(0, 1, 0.0, 10.0) is None
    assert levels.excess_db(0, 1, 6.0, 10.0) is None  # no data in the window


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("crosstalk_margin_db", "6"),
        ("crosstalk_margin_db", None),
        ("crosstalk_window_s", 0),
        ("crosstalk_window_s", 11),
        ("crosstalk_window_s", True),
    ],
)
def test_config_rejects_bad_crosstalk_values(key, value):
    cfg = copy.deepcopy(CFG)
    cfg["voice"][key] = value
    assert any(p.startswith(f"voice.{key}:") for p in validate(cfg))


def test_config_accepts_the_defaults():
    assert CFG["voice"]["crosstalk_margin_db"] == 6.0
    assert not [p for p in validate(CFG) if "crosstalk" in p]
