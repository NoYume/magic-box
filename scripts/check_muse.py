"""Live check of Muse Voice Transcribe: partial-transcript latency and incantation matching.

Synthesizes each test phrase with macOS `say` (or reads a WAV with `--wav`, for the Jetson),
converts it to the PCM16 mono `voice.sample_rate` audio `voice/mic.py` sends, and streams it
through `voice/muse_stream.py` in `voice.chunk_ms` frames at real time, the way a live mic
does (a chunk is sent once it has been "recorded"), with the game's handshake (ENDPOINTING,
CUMULATIVE partials). Every partial and final is matched with `voice/matcher.py` against the
phrase's whole incantation set, and fed to the voice process's own `IncantationTurn`. Times
are seconds from the end of the speech (negative = while still speaking):

    first partial    the first `transcript` event
    first match      the first event that matches the right spell at `voice.match_threshold`
    perfect          the first one at `voice.perfect_threshold`
    charge           when the voice process publishes the incantation (`voice.perfect_hold_s`)
    final            `speechComplete`

Each phrase runs once per keyword format: `words` (what the game sends: the distinct words of
the set, `voice.min_keyword_chars` letters or more), `phrases` (whole incantations; Muse
rejects a keyword over 30 characters, so `muse_stream` drops those) and `none`. The last line
suggests `game.charge_window_s` = worst charge latency + 2.0 s of reaction time, rounded to
0.5 s, at least 2.5 s.

    uv run --env-file .env python scripts/check_muse.py
    uv run --env-file .env python scripts/check_muse.py --phrase "lightning answer my call"
    uv run --env-file .env python scripts/check_muse.py --wav p1.wav --phrase "..."
    uv run --env-file .env python scripts/check_muse.py --record 4 --slot 1 --keywords words \
        --phrase "lightning answer my call"      # Jetson: speak into P2's real mic

`--record` captures from `voice.mics` through `voice/mic.py` (as the game does), saves the
WAV under `.superpowers/muse/` and then streams it like any other.

Exit codes: 0 every run charged the right spell; 1 a run failed, did not charge or the
audio had no speech or the mic would not open; 2 no API key or bad arguments.

Owner: Nikhil
"""

import argparse
import asyncio
import math
import os
import shutil
import statistics
import subprocess
import sys
import time
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRATCH = REPO_ROOT / ".superpowers" / "muse"  # gitignored
KEYWORD_MODES = ("words", "phrases", "none")
DEFAULT_PHRASES = ("embers of the forty acres burn", "lightning answer my call")
VOICED_RMS = 300  # 20 ms frame RMS (int16) that counts as speech when finding the speech end
REACTION_S = 2.0  # time a player needs to push after the charge lands (Task 5 brief)
MIN_WINDOW_S = 2.5


@dataclass
class Trial:
    phrase: str
    keyword_mode: str
    keywords: list[str]
    expected: str
    speech_s: float = 0.0
    handshake_s: float | None = None
    session_id: str | None = None
    first_partial: tuple[float, str] | None = None
    match: tuple[float, str, float, str] | None = None  # (dt, spell_id, score, text)
    perfect: tuple[float, str, float, str] | None = None
    charge: tuple[float, str, float, str] | None = None  # what the voice process publishes
    wrong_match: tuple[float, str, float, str] | None = None
    final: tuple[float, str] | None = None
    events: list[tuple[float, dict]] = field(default_factory=list)
    error: str | None = None


def charge_window(latency_s: float) -> float:
    """latency + REACTION_S, rounded to the nearest 0.5 s, at least MIN_WINDOW_S."""
    return max(MIN_WINDOW_S, round((latency_s + REACTION_S) * 2) / 2)


def load_wav(path: Path, rate: int) -> np.ndarray:
    """PCM16 mono at `rate` from a 16-bit WAV (channels averaged, linear resample)."""
    from magic_box.voice.mic import resample

    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: need 16-bit PCM, got {8 * w.getsampwidth()}-bit")
        channels, src_rate = w.getnchannels(), w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if channels > 1:
        pcm = pcm.reshape(-1, channels).mean(axis=1).round().astype(np.int16)
    return resample(pcm, src_rate, rate)


def synthesize(text: str, rate: int, out_dir: Path = SCRATCH) -> Path:
    """macOS `say` to a 16-bit mono WAV at `rate`."""
    if shutil.which("say") is None:
        raise RuntimeError("macOS `say` not found: pass --wav (with --phrase) on the Jetson")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("_".join(text.lower().split())[:60] + ".wav")
    cmd = ["say", "-o", str(path), "--file-format=WAVE", f"--data-format=LEI16@{rate}", text]
    subprocess.run(cmd, check=True)
    return path


def voiced_samples(pcm: np.ndarray, rate: int = 16000) -> int:
    """Index just past the last voiced 20 ms frame (0 for silence).

    A frame is voiced when its RMS passes VOICED_RMS and 4x the noise floor (the quietest
    tenth of the frames), so a real mic's hiss does not count as speech. The floor term is
    capped at a quarter of the loudest frame, for a clip with no pause in it.
    """
    n = max(1, rate // 50)
    frames = len(pcm) // n
    if frames == 0:
        return 0
    x = pcm[: frames * n].astype(np.float64).reshape(frames, n)
    rms = np.sqrt((x * x).mean(axis=1))
    floor = min(4.0 * float(np.percentile(rms, 10)), 0.25 * float(rms.max()))
    level = max(VOICED_RMS, floor)
    loud = np.flatnonzero(rms > level)
    return 0 if len(loud) == 0 else (int(loud[-1]) + 1) * n


def record(cfg: Mapping, slot: int, seconds: float, sd=None, sleep=time.sleep) -> np.ndarray:
    """Capture `seconds` from that slot's `voice.mics` entry through MicHub, as the game does."""
    from magic_box.voice.mic import MicHub

    v = cfg["voice"]
    mics = [m for m in v["mics"] if int(m["slot"]) == slot]
    chunks: list[bytes] = []
    hub = MicHub(mics, v["sample_rate"], v["chunk_ms"], lambda s, pcm: chunks.append(pcm), sd=sd)
    hub.start()  # MicError if the device cannot open
    try:
        sleep(seconds)
    finally:
        hub.stop()
    return np.frombuffer(b"".join(chunks), dtype="<i2").copy()


def save_wav(pcm: np.ndarray, rate: int, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype("<i2").tobytes())
    return path


def incantation_set(phrase: str, cfg: Mapping) -> tuple[dict[str, str], str]:
    """The slot's whole set that holds `phrase` among the config fallbacks, and its spell id.

    A phrase that is no fallback is its own one-spell set.
    """
    from magic_box.voice.matcher import normalize

    target = normalize(phrase)
    for cls in cfg["game"]["classes"].values():
        for slot in (0, 1):
            spells = {s["id"]: s["fallback"][slot] for s in cls["spells"]}
            for spell_id, text in spells.items():
                if normalize(text) == target:
                    return spells, spell_id
    return {"phrase": phrase}, "phrase"


def keywords_for_mode(mode: str, incantations: Mapping[str, str], min_chars: int) -> list[str]:
    from magic_box.voice.matcher import keywords_for, normalize

    if mode == "words":
        return keywords_for(incantations, min_chars)
    if mode == "phrases":
        return [normalize(t) for t in incantations.values()]
    return []


async def measure(
    stream,
    pcm: np.ndarray,
    trial: Trial,
    incantations: Mapping[str, str],
    *,
    rate: int,
    chunk_ms: int,
    threshold: float,
    perfect: float = 95.0,
    hold_s: float = 0.0,
    lead_s: float = 0.5,
    wait_s: float = 6.0,
    clock: Callable[[], float] = time.monotonic,
) -> Trial:
    """Connect, stream `pcm` at real time, record events until the final or `wait_s`.

    `trial.charge` is what the voice process's IncantationTurn publishes (with `hold_s`).
    """
    from magic_box.voice.matcher import match_incantation
    from magic_box.voice.process import IncantationTurn

    def on_charge(text: str, spell_id: str, score: float) -> None:
        if trial.charge is None:
            trial.charge = (clock(), spell_id, score, text)

    turn = IncantationTurn(incantations, threshold, perfect, hold_s, on_charge)

    n = rate * chunk_ms // 1000
    chunk_s = n / rate
    lead = np.zeros(round(lead_s * rate), np.int16)
    audio = np.concatenate((lead, pcm))
    speech_end = len(lead) + voiced_samples(pcm, rate)
    trial.speech_s = (speech_end - len(lead)) / rate
    end_chunk = max(0, math.ceil(speech_end / n) - 1)  # the chunk holding the last voiced sample
    silence = bytes(n * 2)
    audio_end: list[float] = []
    done = asyncio.Event()

    started = clock()
    await stream.connect(trial.keywords)
    trial.handshake_s = clock() - started
    trial.session_id = getattr(stream, "session_id", None)

    def rel(t: float) -> float:
        return t - audio_end[0] if audio_end else float("nan")

    async def send() -> None:
        t0 = clock()
        i = 0
        while not done.is_set():
            chunk = audio[i * n : (i + 1) * n]
            data = chunk.tobytes() + silence[len(chunk) * 2 :] if len(chunk) else silence
            # A live mic delivers a chunk once it has been recorded: at the end of its window.
            await asyncio.sleep(max(0.0, t0 + (i + 1) * chunk_s - clock()))
            await stream.send_audio(data)
            if i == end_chunk:
                audio_end.append(clock())
            elif audio_end and clock() - audio_end[0] > wait_s:
                return
            i += 1

    async def receive() -> None:
        async for event in stream.events():
            now = clock()
            trial.events.append((now, event))
            kind = event.get("type")
            text = str(event.get("transcript") or "")
            if kind == "transcript" and trial.first_partial is None:
                trial.first_partial = (now, text)
            hit = None
            if kind in ("transcript", "speechComplete"):
                hit = match_incantation(text, incantations, threshold)
            if hit is not None and hit[0] == trial.expected:
                if trial.match is None:
                    trial.match = (now, hit[0], hit[1], text)
                if trial.perfect is None and hit[1] >= perfect:
                    trial.perfect = (now, hit[0], hit[1], text)
            elif hit is not None and trial.wrong_match is None:
                trial.wrong_match = (now, hit[0], hit[1], text)
            turn.handle(event)
            if kind == "speechComplete" and audio_end:
                trial.final = (now, text)
                done.set()
                return
            if kind == "error":
                trial.error = f"Muse error: {event.get('message', '')}"

    sender = asyncio.ensure_future(send())
    receiver = asyncio.ensure_future(receive())
    try:
        await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        done.set()
        for task in (sender, receiver):
            task.cancel()
        await asyncio.gather(sender, receiver, return_exceptions=True)
        turn.cancel()
        await stream.close()
    for name in ("first_partial", "match", "perfect", "charge", "wrong_match", "final"):
        value = getattr(trial, name)
        if value is not None:
            setattr(trial, name, (rel(value[0]), *value[1:]))
    trial.events = [(rel(t), e) for t, e in trial.events]
    if trial.final is None and trial.error is None:
        code = getattr(stream, "close_code", None)
        trial.error = f"no speechComplete within {wait_s:g} s (close code {code})"
    return trial


def _fmt(value: tuple | None) -> str:
    if value is None:
        return "-"
    return f"{value[0]:+.2f} s  {value[-1]!r}"


def report(trial: Trial) -> None:
    print(f'"{trial.phrase}"  keywords={trial.keyword_mode} {trial.keywords}')
    hs = "-" if trial.handshake_s is None else f"{trial.handshake_s:.2f} s"
    print(f"  handshake {hs}  session {trial.session_id}  speech {trial.speech_s:.2f} s")
    print(f"  first partial {_fmt(trial.first_partial)}")
    for label, value in (
        ("first match", trial.match),
        ("perfect", trial.perfect),
        ("charge", trial.charge),
        ("WRONG SPELL", trial.wrong_match),
    ):
        if value is not None:
            dt, spell, score, text = value
            print(f"  {label:<13} {dt:+.2f} s  {spell} score {score:.0f}  {text!r}")
        elif label != "WRONG SPELL":
            print(f"  {label:<13} NONE")
    print(f"  final         {_fmt(trial.final)}")
    if trial.error:
        print(f"  error: {trial.error}")


def _stats(values: Sequence[float]) -> str:
    return f"median {statistics.median(values):+.2f} s max {max(values):+.2f} s"


def summarize(trials: Sequence[Trial]) -> float | None:
    """Print per-mode stats and the charge window; returns the worst charge latency."""
    worst = None
    for mode in dict.fromkeys(t.keyword_mode for t in trials):
        group = [t for t in trials if t.keyword_mode == mode]
        line = f"keywords={mode}: charged {sum(t.charge is not None for t in group)}/{len(group)}"
        for name in ("match", "perfect", "charge", "final"):
            values = [getattr(t, name)[0] for t in group if getattr(t, name) is not None]
            if values:
                line += f"; {name} {_stats(values)}"
        print(line)
        charges = [t.charge[0] for t in group if t.charge is not None]
        if charges:
            worst = max(charges) if worst is None else max(worst, max(charges))
    if worst is not None:
        latency = max(0.0, worst)
        print(
            f"suggested game.charge_window_s = {charge_window(latency):g} "
            f"(worst charge latency {latency:.2f} s + {REACTION_S:g} s reaction, 0.5 s steps, "
            f"min {MIN_WINDOW_S:g})"
        )
    return worst


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=REPO_ROOT / "config.yaml")
    p.add_argument("--phrase", action="append", help="test phrase (repeatable)")
    p.add_argument("--wav", action="append", type=Path, help="16-bit WAV per --phrase, in order")
    p.add_argument(
        "--record",
        type=float,
        metavar="S",
        help="record each --phrase from the --slot mic for S seconds (Jetson, real mics)",
    )
    p.add_argument("--slot", type=int, choices=(0, 1), default=0, help="mic for --record")
    p.add_argument("--keywords", nargs="+", choices=KEYWORD_MODES, default=list(KEYWORD_MODES))
    p.add_argument("--wait", type=float, default=6.0, help="max seconds after speech end")
    p.add_argument("--hold", type=float, help="override voice.perfect_hold_s")
    p.add_argument("--events", action="store_true", help="print every Muse event")
    return p.parse_args(argv)


def main(
    argv: Sequence[str] | None = None, env=None, stream_factory=None, audio=None, sd=None
) -> int:
    """`stream_factory(cfg, key)`, `audio(phrase, rate)` and `sd` (sounddevice) are test seams."""
    args = parse_args(argv)
    from magic_box.core.config import load_config
    from magic_box.voice.mic import MicError
    from magic_box.voice.muse_stream import MuseError, MuseStream

    cfg = load_config(args.config)
    v = cfg["voice"]
    env = os.environ if env is None else env
    key = (env.get(v["api_key_env"]) or "").strip()
    if not key:
        print(f"FAIL: ${v['api_key_env']} is not set")
        return 2
    phrases = args.phrase or list(DEFAULT_PHRASES)
    if args.wav and len(args.wav) != len(phrases):
        print("FAIL: give one --phrase per --wav")
        return 2
    if args.wav and args.record is not None:
        print("FAIL: --wav and --record are exclusive")
        return 2
    factory = stream_factory or (
        lambda c, k: MuseStream(v["url"], k, v["model"], v["handshake_timeout_s"])
    )
    rate = v["sample_rate"]
    hold_s = v["perfect_hold_s"] if args.hold is None else args.hold
    print(f"url {v['url']}  model {v['model']}  PCM16 mono {rate} Hz, {v['chunk_ms']} ms frames")
    print(f"threshold {v['match_threshold']}  perfect {v['perfect_threshold']}  hold {hold_s} s")

    trials: list[Trial] = []
    for i, phrase in enumerate(phrases):
        if audio is not None:
            pcm = audio(phrase, rate)
        elif args.record is not None:
            print(f'P{args.slot + 1}: say "{phrase}" now ({args.record:g} s)...', flush=True)
            try:
                pcm = record(cfg, args.slot, args.record, sd=sd)
            except MicError as exc:
                print(f"FAIL: {exc}")
                return 1
            name = "_".join(phrase.lower().split())[:50]
            print(f"  saved {save_wav(pcm, rate, SCRATCH / f'rec-p{args.slot + 1}-{name}.wav')}")
        else:
            pcm = load_wav(args.wav[i] if args.wav else synthesize(phrase, rate), rate)
        if voiced_samples(pcm, rate) == 0:
            print(f'FAIL: no speech in the audio for "{phrase}"')
            return 1
        incantations, expected = incantation_set(phrase, cfg)
        for mode in args.keywords:
            words = keywords_for_mode(mode, incantations, v["min_keyword_chars"])
            trial = Trial(phrase, mode, words, expected)
            try:
                asyncio.run(
                    measure(
                        factory(cfg, key),
                        pcm,
                        trial,
                        incantations,
                        rate=rate,
                        chunk_ms=v["chunk_ms"],
                        threshold=v["match_threshold"],
                        perfect=v["perfect_threshold"],
                        hold_s=hold_s,
                        wait_s=args.wait,
                    )
                )
            except MuseError as exc:
                trial.error = f"MuseError: {exc}"
            except Exception as exc:  # never print the key: type only
                trial.error = type(exc).__name__
            report(trial)
            if args.events:
                for dt, event in trial.events:
                    print(f"    {dt:+.2f} s {event}")
            trials.append(trial)
    print()
    summarize(trials)
    ok = all(t.charge is not None and t.charge[1] == t.expected and not t.error for t in trials)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
