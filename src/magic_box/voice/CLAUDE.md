# voice

**Owner:** Nikhil (mic devices: Daniel)

Per-player speech recognition. Runs in its own process, one Muse WebSocket per player mic. Spec: `docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md` section 9 and Appendix A.

**Status:** implemented against Meta's documented realtime ASR API and tested only with fakes. Not verified live, and partial-transcript latency is unmeasured.

## Inputs → Outputs
- In: two mics (`voice.mics`: slot, device, channel), `VoiceConfig` from the game (transcript mode in the lobby; each player's incantation set at match start, used as `keywords`).
- Out: `VoiceEvent` on the voice stream. `kind="incantation"` carries `spell_id` and `match_score`; `kind="transcript"` is a final transcript for lobby names; `kind="status"` carries `"no api key"`, `"no mic"`, `"connected"` or `"reconnecting"`. The game shows MIC OK only for `"connected"`.

## Hard rules
- `sounddevice` is imported only inside functions (laptops and CI have no PortAudio).
- One `sounddevice` stream per distinct device; channels are split per slot (a stereo wireless receiver is one device). Capture PCM16 mono at `voice.sample_rate` (16 kHz). If the device rejects that, fall back to its default rate and resample. A failed open or start gives status `"no mic"`; the process idles and never restart-loops.
- Match with `rapidfuzz` (`fuzz.ratio` over a sliding word window, not `partial_ratio`) against **only that player's** incantations. At most one incantation event per speech turn.
- `ENDPOINTING` mode with `CUMULATIVE` partials, in the lobby and in the fight. Keywords are fixed at the handshake, so a mode change restarts the sessions. Match partials as they arrive.
- Starts in transcript mode and connects at once. A session starts armed before its first `speechStart`. The slot's audio queue is cleared on connect. Silence frames are sent after `silence_after_s` of a quiet mic.
- Reopen before `session_max_s` (3300 s) without a "reconnecting" status. Reconnect backoff doubles from `reconnect_backoff_s` to `reconnect_max_s` and resets after a 30 s session; close code 1008 uses the max. A dropped stream must not crash the process.
- Stop is bounded (about 1.5 s grace) and always stops the mics.
- The API key is read from `META_MODEL_API_KEY` (`uv run --env-file .env`). Never commit, hard-code or log it.
- Never block the game loop: all of this runs in the voice process; the game only drains the queue.

## Files
- `process.py`: voice process entry point (`run`), the asyncio `serve` loop and per-slot session handling.
- `mic.py`: `MicHub` per-device capture, channel split, `resample`.
- `muse_stream.py`: Muse WebSocket client (`handshake`, send audio, events, close).
- `matcher.py`: rapidfuzz incantation match using `match_threshold` / `perfect_threshold`; `keywords_for`.

## Test without the Jetson
Tests live in `tests/voice/` (`test_mic.py` uses `fake_sd.py`; no real mic, no network). In the app, the spell keys are the fallback and always work:
```
uv run pytest tests/voice
uv run python -m magic_box --fake     # P1: 1 2 3, P2: 8 9 0
```
Real mics: set `voice.mics` in `config.local.yaml` (see `docs/hardware.md`).

## Open TODOs
- `TODO(Nikhil)`: verify live on the Jetson with a real `META_MODEL_API_KEY`; confirm the keyword format (words vs phrases).
- `TODO(Nikhil)`: measure partial-transcript latency (end of incantation to charge) and set `game.charge_window_s`.
- Open decision (Daniel): mic hardware model and channel routing.
