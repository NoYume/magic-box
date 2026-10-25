# voice

**Owner:** Nikhil (mic devices: Daniel)

Per-player speech recognition. Runs in its own process, one Muse WebSocket per player mic.

## Inputs → Outputs
- In: two mics (`voice.mics`: slot, device, channel), `VoiceConfig` from the game (transcript mode in the lobby; each player's incantation set at match start, used as `keywords`).
- Out: `VoiceEvent` on the voice stream. `kind="incantation"` carries `spell_id` and `match_score`; `kind="transcript"` is for lobby names and class picks.

## Hard rules
- `sounddevice` is imported only inside functions (laptops and CI have no PortAudio).
- Capture PCM16 mono at `voice.sample_rate` (16 kHz); resample in-process if the device cannot.
- Match with `rapidfuzz` against **only that player's** incantations. At most one incantation event per speech turn.
- Use `ENDPOINTING` mode with `CUMULATIVE` partials. Match partials as they arrive. Keep sending silence during pauses.
- Reconnect with backoff, including at the 60-minute session limit. A dropped stream must not crash the process.
- The API key is read from `META_MODEL_API_KEY` (`uv run --env-file .env`). Never commit it or hard-code it.
- Never block the game loop: all of this runs in the voice process; the game only drains the queue.

## Files
- `process.py`: voice process entry point and loop.
- `mic.py`: per-player mic capture (device, channel).
- `muse_stream.py`: Muse WebSocket client (open, send audio, events, close).
- `matcher.py`: rapidfuzz incantation match using `match_threshold` / `perfect_threshold`.

## Test without the Jetson
Tests live in `tests/voice/` (`test_mic.py` uses `fake_sd.py`, no real mic). In the app, the spell keys are the fallback and always work:
```
uv run python -m magic_box --fake     # P1: 1 2 3, P2: 8 9 0
```
Real mics: set `voice.mics` in `config.local.yaml` (see `docs/hardware.md`).

## Open TODOs
- `TODO(Nikhil)` in `matcher.py`, `process.py`.
- Open decision (Daniel): mic hardware model and channel routing.
- Verify the Muse endpoint `voice.url` and model against the dev.meta.ai docs before first use.
- Measure partial-transcript latency at M4.
