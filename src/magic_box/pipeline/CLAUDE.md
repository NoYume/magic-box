# pipeline

**Owner:** Nikhil

Process plumbing and the game-process loop: supervisor, shared-memory frame bus, stream queues, input sources.

## Inputs → Outputs
- Moves `PlayerState` and `VoiceEvent` (streams, drained every tick) and `Frame` (latest value) between processes.
- Carries `VoiceConfig` from game to voice on a small control queue (the queue exists; sending on scene changes is a TODO, below).
- `loop.GameLoop.run()` ticks: `window.pump()` → `Sources.poll()` → `intent` → `engine.step()` → `window.draw()`.

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
- `sources.py`: `FakeSources`, `LiveSources`, `ReplaySources`, `KeyboardVoiceSource`, `Inputs` (incl. `dropped`, the summed queue drop count shown in the debug overlay).
- `loop.py`: `GameLoop`, `Display` protocol, `latest_states`.

## Test without the Jetson
```
uv run pytest tests/pipeline
uv run python -m magic_box --fake
uv run python -m magic_box --fake --headless --max-ticks 120
```

## Open TODOs
- `TODO(Nikhil)` in `loop.py`: submit Spark jobs on `loading` / `victory` (spec §6).
- `TODO(Nikhil)` in `loop.py` and `main.py`: send `VoiceConfig` on scene changes via `runtime.control_q` (spec §6). Nothing sends it today.
- `TODO(Nikhil)` in `main.py`: `--record` builds a `SessionRecorder` but nothing feeds it; hook it into `GameLoop` (states, voice, events, frames).
- `ReplaySources` waits on `replay/` (`--replay` exits 2 today).
- The frame-bus seqlock has no explicit memory fences. Re-run `MAGIC_BOX_STRESS=1 uv run pytest tests/pipeline/test_frame_bus.py` on the Jetson (aarch64; the stress test free-runs 1280x720 writes for ~3 s) before relying on it.
- Live mode starts perception and voice, both stubs today; on a laptop the window shows "STEP INTO VIEW".
