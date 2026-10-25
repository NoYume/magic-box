# voice

**Owner:** Nikhil (mic devices: Daniel)

Per-player speech recognition. Runs in its own process, one Muse WebSocket per player mic. Spec: `docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md` section 9 and Appendix A.

**Status:** verified live against `wss://api.meta.ai/v1/asr/realtime` on 2026-10-25, from a laptop with macOS `say` audio streamed at real time (`scripts/check_muse.py`). The handshake, events and close match Meta's docs. Not yet run with real lav mics on the Jetson.

## Inputs → Outputs
- In: two mics (`voice.mics`: slot, device, channel), `VoiceConfig` from the game (transcript mode in the lobby; each player's incantation set at match start, used as `keywords`).
- Out: `VoiceEvent` on the voice stream. `kind="incantation"` carries `spell_id` and `match_score`; `kind="transcript"` is a final transcript for lobby names; `kind="status"` carries `"no api key"`, `"no mic"`, `"connected"` or `"reconnecting"`. The game shows MIC OK only for `"connected"`.

## Hard rules
- `sounddevice` is imported only inside functions (laptops and CI have no PortAudio).
- One `sounddevice` stream per distinct device; channels are split per slot (a stereo wireless receiver is one device). Capture PCM16 mono at `voice.sample_rate` (16 kHz). If the device rejects that, fall back to its default rate and resample. A failed open or start gives status `"no mic"`; the process idles and never restart-loops.
- Match with `rapidfuzz` (`fuzz.ratio` over a sliding word window, not `partial_ratio`) against **only that player's** incantations. At most one incantation event per speech turn.
- **Perfect hold** (`IncantationTurn`): live partials reach `match_threshold` on a prefix (scores 80-91), and the whole phrase lands 0-0.9 s later (median 0.4 s). A match under `perfect_threshold` is held up to `voice.perfect_hold_s` (0.5 s) for a better partial; a perfect match, `speechEnd`, `speechComplete` or the next `speechStart` publishes the best one at once, and so does the stream ending on its own (a Wi-Fi drop or a server close). A mode change, a new `VoiceConfig` or stop drops a held match: it is never published after the session restarts. Without the hold the ×1.15 perfect bonus almost never fires. `perfect_hold_s: 0` publishes the first match.
- **Charge timing vs the engine:** a held sub-perfect match publishes at first match + `perfect_hold_s`, so up to about +0.8 s after speech with 0.5 s. The engine's `game.release_grace_s` (0.6 s, Task 1) makes an uncharged push with a live mic wait that long for a charge, so a push on the last word still casts when the charge lands within the grace.
- `ENDPOINTING` mode with `CUMULATIVE` partials, in the lobby and in the fight. Keywords are fixed at the handshake, so a mode change restarts the sessions. Match partials as they arrive.
- **Keywords are single words** (`keywords_for`: distinct words of the set, at least `min_keyword_chars` letters). Muse accepts phrases, but rejects the whole handshake for one keyword over 30 characters, so `muse_stream.handshake` drops those (`MAX_KEYWORD_CHARS`). 120 keywords were accepted.
- **Crosstalk drop (transcripts only)** (`crosstalk.py`, `_Sessions._is_crosstalk`): both lav mics hear both players, and every lobby or victory final is a name or class pick. `serve` stamps each mic chunk with `clock()` on the audio thread and records its RMS dBFS on the loop thread (`LevelHistory`, 12 s per slot, no lock). On a transcript-mode `speechComplete` for slot s, the window runs from `SPEECH_START_LEAD_S` (1 s) before the turn's `speechStart` arrival to its `speechEnd` arrival (Muse events carry no audio times); with no `speechStart` it is the last `voice.crosstalk_window_s` (6 s) before `speechEnd` or now. At slot s's loudest chunks in the window (at or above its 90th percentile), each is paired with the other mic's nearest chunk (within 2 chunks); if the median (other - s) is at least `voice.crosstalk_margin_db` (6 dB, guess), the transcript is dropped and logged (`voice: P1 transcript dropped as crosstalk (P2 +9.1 dB): "..."`). Both talking at once, or the other player talking at another moment in the window, keeps it. No level data for the other slot (one mic, a dead mic) never drops. `crosstalk_margin_db <= 0` turns it off. Incantation matching is never checked.
- Starts in transcript mode and connects at once. A session starts armed before its first `speechStart`. The slot's audio queue is cleared on connect. Silence frames are sent after `silence_after_s` of a quiet mic.
- Reopen before `session_max_s` (3300 s) without a "reconnecting" status. Reconnect backoff doubles from `reconnect_backoff_s` to `reconnect_max_s` and resets after a 30 s session; close code 1008 uses the max. A dropped stream must not crash the process.
- Stop is bounded (about 1.5 s grace) and always stops the mics.
- The API key is read from `META_MODEL_API_KEY` (`uv run --env-file .env`). Never commit, hard-code or log it.
- Never block the game loop: all of this runs in the voice process; the game only drains the queue.

## Live measurements (2026-10-25, laptop, `say` voice, `keywords=words`, 17 sessions)
Seconds from the end of the speech; negative means while the player is still speaking.

| Event | Median | Range |
|---|---|---|
| Handshake (connect to `sessionId`) | 0.6 s | 0.4-1.1 s |
| First partial | -0.7 s | -1.1 to -0.1 s |
| First match at `match_threshold` (usually a prefix, score 80-91) | 0.0 s | -0.3 to +0.3 s |
| Whole phrase (score 100) | +0.4 s | +0.2 to +0.7 s |
| Gap from first match to whole phrase (13 sessions with event times) | 0.4 s | 0-0.9 s |
| **Charge with the 0.5 s hold** (replayed from those 13 sessions' event times) | **+0.4 s** | **+0.2 to +0.6 s** |
| `speechComplete` (final) | +3.4 s | +0.4 to +3.8 s (bimodal: about 0.5 s or about 3.3 s) |

- 17/17 matched the right spell, never a wrong one.
- With a 0.5 s hold, 7/13 would charge at score 100 and 6/13 at the held prefix score (84-90). The live runs used 0.8 s and 1.0 s holds, which never expired (every session reached 100), so they say nothing about the sub-perfect path. A real sub-perfect match publishes at first match + hold: up to about +0.8 s with 0.5 s (it was about +1.3 s with 1.0 s).
- **`game.charge_window_s` stays 3.0** (the brief's formula on that +0.8 s worst case: 0.8 + 2.0 s reaction, rounded to 0.5 s, gives 3.0). The TTS runs alone would give 2.5; that waits for the Jetson real-voice run.
- `keywords=words` was the best format: earliest matches, and it spells "forty" (with no keywords Muse wrote "40", scoring 88). `phrases` gave nothing extra and one handshake failed on the 30-character limit.
- Lobby names and class picks come from `speechComplete`, so they arrive about 3.3 s after the player stops talking when the endpointer waits for silence.
- `turnId` starts at 0. A bad key gets an error frame at the handshake ("Unauthorized: ...") in 0.2 s, which becomes `MuseError`, then reconnect with backoff (HUD: MIC OFF).

## Files
- `process.py`: voice process entry point (`run`), the asyncio `serve` loop, per-slot session handling and `IncantationTurn` (match, hold, one event per turn).
- `mic.py`: `MicHub` per-device capture, channel split, `resample`.
- `crosstalk.py`: `chunk_dbfs` and `LevelHistory` (per-slot chunk levels, `excess_db` for the crosstalk drop).
- `muse_stream.py`: Muse WebSocket client (`handshake`, send audio, events, close).
- `matcher.py`: rapidfuzz incantation match using `match_threshold`; `keywords_for`.
- `scripts/check_muse.py`: live latency and matching check. It streams `say` audio, a `--wav` file or a `--record S` capture from a real mic (through `MicHub`, saved under `.superpowers/muse/`) through `MuseStream` and `IncantationTurn` at real time.

## Test without the Jetson
Tests live in `tests/voice/` (`test_mic.py` uses `fake_sd.py`, `test_check_muse.py` a scripted stream; no real mic, no network). In the app, the spell keys are the fallback and always work:
```
uv run pytest tests/voice
uv run python -m magic_box --fake     # P1: 1 2 3, P2: 8 9 0
uv run --env-file .env python scripts/check_muse.py                 # live, macOS say
uv run --env-file .env python scripts/check_muse.py --keywords words --phrase "lightning answer my call"
```
Real mics: set `voice.mics` in `config.local.yaml` (see `docs/hardware.md`).

## Open TODOs
- `TODO(Nikhil)`: re-measure on the Jetson with the real lav mics and real voices, then set `game.charge_window_s` (3.0) from the worst `charge` line and the `suggested game.charge_window_s` output, and check `perfect_hold_s` (0.5) against venue noise and crosstalk. Include some deliberately sloppy readings, so the held sub-perfect path is measured. Set `voice.mics` in `config.local.yaml` first; each run records 4 s, so start speaking at the prompt:
  ```
  uv run --env-file .env python scripts/check_muse.py --record 4 --slot 0 --keywords words \
      --phrase "embers of the forty acres burn" --phrase "rise crimson rampart"
  uv run --env-file .env python scripts/check_muse.py --record 4 --slot 1 --keywords words \
      --phrase "lightning answer my call" --phrase "hum of the restless grid"
  ```
- `TODO(Nikhil)`: on the Jetson with both lav mics, watch the `dropped as crosstalk` log lines in the lobby: tune `voice.crosstalk_margin_db` (6 dB guess) from the real own-vs-other level gap, and check the two receiver channels' gains match (a hot channel biases the comparison).
- Open decision (Daniel): mic hardware model and channel routing.
