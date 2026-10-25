"""Tests for scripts/check_muse.py with a scripted in-memory Muse stream (no network, no say).

Owner: Nikhil
"""

import asyncio
import importlib.util
import wave
from pathlib import Path

import numpy as np
import pytest

from magic_box.core.config import load_config

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_muse.py"
CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
PHRASE = "embers of the forty acres burn"
PREFIX = "embers of the forty acres"


def _load():
    spec = importlib.util.spec_from_file_location("check_muse", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ScriptedStream:
    """MuseStream double: yields each event once `after` audio chunks have arrived."""

    def __init__(self, script, fail=None):
        self.script = script
        self.fail = fail
        self.keywords = None
        self.session_id = None
        self.sent = 0
        self.closed = False
        self.close_code = None

    async def connect(self, keywords):
        if self.fail is not None:
            raise self.fail
        self.keywords = list(keywords)
        self.session_id = "s-1"

    async def send_audio(self, pcm):
        assert len(pcm) == 2560  # 80 ms of PCM16 at 16 kHz, like voice/mic.py
        self.sent += 1

    async def events(self):
        for after, event in self.script:
            while self.sent < after:
                await asyncio.sleep(0.005)
            yield event
        await asyncio.Event().wait()  # stays open, like a live session

    async def close(self):
        self.closed = True


# 0.5 s lead silence (6.25 chunks) + 0.32 s of "speech": the last voiced chunk is index 10.
SPEECH = np.full(5120, 3000, np.int16)
SCRIPT_EVENTS = [
    (6, {"type": "speechStart", "turnId": 0}),
    (8, {"type": "transcript", "transcript": "embers of", "final": False}),
    (10, {"type": "transcript", "transcript": PREFIX, "final": False}),
    (12, {"type": "transcript", "transcript": PHRASE, "final": False}),
    (13, {"type": "speechComplete", "turnId": 0, "transcript": PHRASE}),
]


def test_charge_window_rounding_and_minimum():
    mod = _load()
    assert mod.charge_window(0.0) == 2.5
    assert mod.charge_window(0.53) == 2.5
    assert mod.charge_window(0.8) == 3.0
    assert mod.charge_window(1.3) == 3.5


def test_incantation_set_and_keyword_modes():
    mod = _load()
    incantations, spell_id = mod.incantation_set("Embers of the Forty Acres burn!", CFG)
    assert spell_id == "fireball" and set(incantations) == {"fireball", "flame_wall", "inferno"}
    assert mod.incantation_set("hello there friend", CFG) == (
        {"phrase": "hello there friend"},
        "phrase",
    )
    words = mod.keywords_for_mode("words", incantations, 4)
    assert words[:4] == ["embers", "forty", "acres", "burn"]
    assert mod.keywords_for_mode("phrases", incantations, 4)[0] == PHRASE
    assert mod.keywords_for_mode("none", incantations, 4) == []


def test_measure_reports_prefix_match_perfect_and_held_charge():
    mod = _load()
    incantations, spell_id = mod.incantation_set(PHRASE, CFG)
    trial = mod.Trial(PHRASE, "words", [], spell_id)
    stream = ScriptedStream(SCRIPT_EVENTS)
    kw = dict(rate=16000, chunk_ms=80, threshold=80, perfect=95, wait_s=2.0)
    asyncio.run(mod.measure(stream, SPEECH, trial, incantations, hold_s=1.0, **kw))
    assert trial.error is None and stream.closed and trial.session_id == "s-1"
    assert trial.speech_s == pytest.approx(0.32)
    assert trial.first_partial[1] == "embers of" and trial.first_partial[0] < 0
    assert trial.match[1] == "fireball" and 80 <= trial.match[2] < 95  # the prefix
    assert trial.perfect[1:3] == ("fireball", 100.0)
    assert trial.charge[1:3] == ("fireball", 100.0)  # held for the whole phrase
    assert trial.charge[0] == pytest.approx(trial.perfect[0], abs=0.02) and trial.charge[0] > 0
    assert trial.final[1] == PHRASE


def test_measure_without_hold_charges_on_the_prefix():
    mod = _load()
    incantations, spell_id = mod.incantation_set(PHRASE, CFG)
    trial = mod.Trial(PHRASE, "words", [], spell_id)
    kw = dict(rate=16000, chunk_ms=80, threshold=80, perfect=95, wait_s=2.0)
    asyncio.run(mod.measure(ScriptedStream(SCRIPT_EVENTS), SPEECH, trial, incantations, **kw))
    assert trial.charge[2] == trial.match[2] < 95


def test_main_end_to_end_and_exit_codes(capsys):
    mod = _load()
    streams = []

    def factory(cfg, key):
        streams.append(ScriptedStream(SCRIPT_EVENTS))
        return streams[-1]

    argv = ["--keywords", "words", "phrases", "--phrase", PHRASE, "--wait", "2"]
    env = {"META_MODEL_API_KEY": "sk-secret"}
    assert mod.main(argv, env=env, stream_factory=factory, audio=lambda p, r: SPEECH) == 0
    out = capsys.readouterr().out
    assert "suggested game.charge_window_s = 2.5" in out and "sk-secret" not in out
    assert streams[0].keywords[:2] == ["embers", "forty"] and streams[1].keywords[0] == PHRASE
    assert mod.main(argv, env={}, stream_factory=factory, audio=lambda p, r: SPEECH) == 2


def test_main_failed_handshake_exits_1_without_the_key(capsys):
    mod = _load()

    def factory(cfg, key):
        return ScriptedStream([], fail=OSError(f"boom {key}"))

    argv = ["--keywords", "words", "--phrase", PHRASE]
    env = {"META_MODEL_API_KEY": "sk-secret"}
    assert mod.main(argv, env=env, stream_factory=factory, audio=lambda p, r: SPEECH) == 1
    out = capsys.readouterr().out
    assert "error: OSError" in out and "sk-secret" not in out


def test_load_wav_downmixes_and_resamples(tmp_path):
    path = tmp_path / "stereo8k.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(np.array([[1000, 3000]] * 800, dtype="<i2").tobytes())
    pcm = _load().load_wav(path, 16000)
    assert pcm.dtype == np.int16 and len(pcm) == 1600 and int(pcm[100]) == 2000
