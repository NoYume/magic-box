# pipeline

**Owner:** Nikhil

Process plumbing and the game-process loop: supervisor, shared-memory frame bus, stream queues, input sources.

## Inputs → Outputs
- Moves `PlayerState` and `VoiceEvent` (streams, drained every tick) and `Frame` (latest value) between processes.
- Carries `VoiceConfig` from game to voice on a small control queue. The loop sends transcript mode on entering `lobby` (including the first tick) and each player's incantation set on entering `fight`.
- On entering `loading` / `victory` the loop submits a Spark job to the `ai/` `AiWorker` and hands results to `engine.provide_incantations()` / `provide_chronicle()`. `status` `VoiceEvent`s go to `engine.provide_mic_status()`.
- With `--record`, the loop passes states, voice events and game events to `SessionRecorder`.
- `loop.GameLoop.run()` ticks: `window.pump()` → `Sources.poll()` (+ keyboard voice) → `intent` → `engine.step()` → scene-change hooks and `AiWorker.poll()` → `window.draw()`.

## Hard rules
- Never block the game loop. The frame bus read and `DropOldestQueue.drain()` return immediately.
- Streams drop the *oldest* item on overflow and count drops (`dropped`). Do not drop newest.
- Create processes and queues only from `streams.spawn_context()` (spawn start method everywhere).
- No `pygame` here: keys arrive as a `frozenset` of key names; the loop talks to the window through the `Display` protocol.
- No `pyzed`, and `cv2`/`sounddevice` only inside functions.
- Sources share one interface (`Sources.poll(keys, now, dt)`); the keyboard voice source is always merged in.

## Files
- `frame_bus.py`: `FrameBus` shared-memory double buffer with a per-slot seqlock (`write`, `read_latest`).
- `streams.py`: `spawn_context()` and `DropOldestQueue` (`put`, `drain`, `dropped`).
- `processes.py`: `Supervisor` (start, poll, restart with backoff, stop) and `start_live(cfg)`.
- `sources.py`: `FakeSources`, `LiveSources`, `ReplaySources` (wraps `replay/play.py`), `KeyboardVoiceSource`, `Inputs` (incl. `dropped`, the summed queue drop count shown in the debug overlay).
- `loop.py`: `GameLoop` (scene-change hooks, mic status, recording, AI polling), `Display` protocol, `latest_states`.

## Test without the Jetson
```
uv run pytest tests/pipeline
uv run python -m magic_box --fake
uv run python -m magic_box --fake --headless --max-ticks 120
```

## Open TODOs
- `TODO(Nikhil)`: verify the live path on the Jetson (perception + voice + Spark together), then size `game.charge_window_s` from the measured partial latency.
- The frame-bus seqlock has no explicit memory fences. Re-run `MAGIC_BOX_STRESS=1 uv run pytest tests/pipeline/test_frame_bus.py` on the Jetson (aarch64; the stress test free-runs 1280x720 writes for ~3 s) before relying on it.
- On a laptop without pyzed the perception process fails (the supervisor retries a few times) and the window shows "STEP INTO VIEW". Voice runs, but reports `"no api key"` or `"no mic"` when it cannot start.
