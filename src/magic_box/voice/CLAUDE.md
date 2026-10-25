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
- **Perfect hold** (`IncantationTurn`): live partials reach `match_threshold` on a prefix (scores 80-91), and the whole phrase lands 0.1-0.9 s later. A match under `perfect_threshold` is held up to `voice.perfect_hold_s` (1.0 s) for a better partial; a perfect match, `speechEnd`, `speechComplete` or the next `speechStart` publishes the best one at once. Without it the ×1.15 perfect bonus almost never fires. `perfect_hold_s: 0` publishes the first match (about 0.4 s sooner).
- `ENDPOINTING` mode with `CUMULATIVE` partials, in the lobby and in the fight. Keywords are fixed at the handshake, so a mode change restarts the sessions. Match partials as they arrive.
- **Keywords are single words** (`keywords_for`: distinct words of the set, at least `min_keyword_chars` letters). Muse accepts phrases, but rejects the whole handshake for one keyword over 30 characters, so `muse_stream.handshake` drops those (`MAX_KEYWORD_CHARS`). 120 keywords were accepted.
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
| **Charge** (published, with the 1.0 s hold) | **+0.4 s** | **+0.3 to +0.6 s** |
| `speechComplete` (final) | +3.4 s | +0.4 to +3.8 s (bimodal: about 0.5 s or about 3.3 s) |

- 17/17 matched the right spell, never a wrong one. A 0.8 s hold charged 4/5 at score 100 (one whole phrase came 0.88 s after the prefix), so the hold is 1.0 s; that charged 3/3 at 100. The charge row is from the 1.0 s hold.
- `game.charge_window_s` = 0.6 s worst charge latency + 2.0 s reaction, rounded to 0.5 s, minimum 2.5 → **2.5 s**.
- `keywords=words` was the best format: earliest matches, and it spells "forty" (with no keywords Muse wrote "40", scoring 88). `phrases` gave nothing extra and one handshake failed on the 30-character limit.
- Lobby names and class picks come from `speechComplete`, so they arrive about 3.3 s after the player stops talking when the endpointer waits for silence.
- `turnId` starts at 0. A bad key gets an error frame at the handshake ("Unauthorized: ...") in 0.2 s, which becomes `MuseError`, then reconnect with backoff (HUD: MIC OFF).

## Files
- `process.py`: voice process entry point (`run`), the asyncio `serve` loop, per-slot session handling and `IncantationTurn` (match, hold, one event per turn).
- `mic.py`: `MicHub` per-device capture, channel split, `resample`.
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
- `TODO(Nikhil)`: re-measure on the Jetson with the real lav mics and real voices, then check `game.charge_window_s` (2.5) and `perfect_hold_s` (1.0) against venue noise and crosstalk. Set `voice.mics` in `config.local.yaml` first; each run records 4 s, so start speaking at the prompt:
  ```
  uv run --env-file .env python scripts/check_muse.py --record 4 --slot 0 --keywords words \
      --phrase "embers of the forty acres burn" --phrase "rise crimson rampart"
  uv run --env-file .env python scripts/check_muse.py --record 4 --slot 1 --keywords words \
      --phrase "lightning answer my call" --phrase "hum of the restless grid"
  ```
- Open decision (Daniel): mic hardware model and channel routing.
