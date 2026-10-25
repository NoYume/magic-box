# magic-box

Read this first. Each package folder under `src/magic_box/` has its own short `CLAUDE.md`; Claude Code loads it when you work there. Spec: `docs/superpowers/specs/2026-10-24-magic-box-design.md`.

## What this is

A game console built from a ZED 2 stereo camera, a Jetson Orin Nano and an external monitor. It runs a 1v1 magic duel for HackTX 2026 (Hardware, Meta and Best Overall tracks). Two players stand side by side. Each watches their own half of a split screen showing a live close-up of the *opponent*. Players speak a Muse Spark-written incantation into their own clip-on mic to charge a spell, then release it with a body gesture (usually a fast push toward the camera). The defender dodges by stepping aside or ducking. Real distance to the camera scales damage.

## Why ZED + Jetson

1. Depth is load-bearing: push speed (m/s along Z), distance zones and dodges are measured in meters. If a feature works as well on a webcam, it is not a headline feature.
2. Body tracking gives two skeletons with IDs, so no hand-rolled pose model.
3. Everything runs on one small box, with no laptop in the loop at the demo.
4. The ZED 2 has an IMU and works with the Jetson's CUDA stack.
5. The debug overlay (top-down meters view, `wrist_vz` graph) proves the depth story to judges.

Speech-to-text (Muse Voice Transcribe) and Muse Spark run in Meta's cloud. Video never leaves the box.

## Hardware

| Part | Notes |
|---|---|
| ZED 2 | USB 3, has an IMU, so body tracking works. |
| Jetson Orin Nano | RAM and JetPack unconfirmed; `scripts/check_env.py` is step 1. Video out is DisplayPort, so use a DP-to-HDMI adapter if the monitor needs HDMI. |
| Monitor | External, 1920x1080 assumed. |
| Mics | One clip-on lav mic per player: two USB lav mics, or a dual-transmitter wireless kit whose USB receiver puts P1 on L and P2 on R. A USB mic is the spare. |
| Network | Wi-Fi on the Jetson, for the Muse APIs. |

More in `docs/hardware.md`.

## Architecture

```
                ┌──────────── Jetson Orin Nano ─────────────────────────────┐
 ZED 2 ──USB──▶ │ [perception proc]  only module that imports pyzed         │
                │   grab → depth + body tracking (2 people, IDs)            │
                │   → slot assign → push/pose/motion → PlayerState ×2/frame │
                │   → left frame into shared memory (double buffer)         │
                │            │ state stream (drained)    │ shm (latest)      │
                │            ▼                           ▼                   │
 mic P1 ──┐     │ [game proc] pygame-ce @ 60 fps, never blocks              │──DP/HDMI──▶ monitor
 mic P2 ──┴───▶ │   intent → game rules → GameView → renderer (layout C)    │
                │   AI worker thread: Muse Spark (incantations, chronicle)  │
                │            ▲ VoiceEvent stream (drained)                  │
                │ [voice proc] asyncio, one Muse WebSocket per player mic   │
                └──────────────────┬────────────────────────────────────────┘
                                   └──Wi-Fi──▶ api.meta.ai (Voice Transcribe, Spark)
```

**Processes.** `multiprocessing` with the `spawn` start method on every platform (fork after CUDA init is unsafe). Get contexts only from `magic_box.pipeline.streams.spawn_context()`. `pipeline/processes.py` starts and supervises the children and restarts perception or voice if they die.

**Transport rules.**
- **Camera frames are latest-value.** The left image (BGRA uint8) goes into a shared-memory double buffer with `frame_idx` and `cam_t` in the header. The game reads the newest complete buffer and never waits. If `frame_idx` is unchanged, it reuses the last texture.
- **`PlayerState` and `VoiceEvent` are streams.** Bounded `multiprocessing.Queue`s; the game drains every queued item each tick, because a push lives on a single frame's state and dropping states loses inputs. On overflow the producer drops the *oldest* item and counts it. Render uses the newest drained state per slot.
- **Control channel (game → voice).** The game sends a `VoiceConfig` on its own queue when the scene changes: transcript mode in the lobby, each player's incantation set at match start.

**Game loop** (`pipeline/loop.py`, one tick): `render.window.pump()` returns the keys pressed this tick; sources are polled for `PlayerState`, `VoiceEvent` and the latest frame; `intent` makes `Action`s; `game.engine.step()` returns a `GameView` plus `GameEvent`s; `render.window.draw()` draws it. Sources (`pipeline/sources.py`) are live, `--replay` or `--fake`. A keyboard voice source is always merged in. Only `render/` touches `pygame`; key presses reach everyone else as plain data.

**Spark jobs.** On entering `loading` or `victory`, the loop submits a job to the `ai/` worker thread and hands the result back via `engine.provide_incantations()` / `engine.provide_chronicle()`. The engine never waits for it.

**Clock.** Every contract has `t = time.monotonic()` at publish; it is shared by all processes on the machine, and fusion compares voice and push times with it. `PlayerState.cam_t` (ZED image timestamp, seconds) is used only to compute velocities.

**Units and frames.**
- Meters and seconds everywhere.
- ZED `UNIT.METER` and `COORDINATE_SYSTEM.IMAGE`: +X image-right, +Y down, +Z away from the camera. Motion toward the camera has negative `vz`.
- Pixel coordinates refer to the unmirrored left image. Only the self-view is mirrored, at render time.
- **Slot 0 = P1**, who stands on the left from the players' view. P1 appears on the image's *right*, so their root x is greater than 0.

## Contracts

All cross-owner types live in `src/magic_box/core/contracts.py`: `Push`, `PlayerState`, `VoiceEvent`, `Action`, `GameEvent`, `GameView`, `PlayerView`, `SpellView`, `ProjectileView`, `VoiceConfig`, `Frame`. They round-trip to JSON lines via `core/serde.py`.

`PlayerView` carries the knight's parry state (`can_parry`, `guard_s`, `guard_cooldown_s`, `riposte_s`, `parry_flash_s`); a parry is logged as a `block` event with `data["parry"]`, and the riposte is a projectile with `spell_id="riposte"`. Pose flags are `hands_up`, `hands_together` and `guard`.

**Change rule:** changing a contract needs a heads-up to every owner who produces or consumes it, and an update to this file in the same change.

| Boundary | Contract | From → To |
|---|---|---|
| Perception → intent | `PlayerState` | Enoch → Nikhil |
| Voice → intent | `VoiceEvent` | Nikhil |
| Intent → game rules | `Action` | Nikhil → Adetola |
| Game → render | `GameView` | Adetola → Adetola + Nikhil |

## Team and ownership

```
CLAUDE.md, README.md, pyproject.toml, uv.lock, .env.example, .github/, .claude/   Daniel
config.yaml               shared; each section is commented with its owner
docs/game-design.md       Adetola          docs/hardware.md   Daniel + Enoch
src/magic_box/
  main.py, __main__.py    Nikhil           CLI entry
  core/        Nikhil     contracts.py, serde.py, config.py, geometry.py
  perception/  Enoch      process.py, zed_source.py, bodies.py, push.py, poses.py, motion.py, hands.py
  pipeline/    Nikhil     processes.py, frame_bus.py, streams.py, sources.py, loop.py
  intent/      Nikhil     fusion.py, dodge.py
  voice/       Nikhil     process.py, mic.py, muse_stream.py, matcher.py   (mic devices: Daniel)
  ai/          Nikhil     spark_client.py, incantations.py, chronicle.py
  game/        Adetola    classes.py, spells.py, state.py, combat.py, scenes.py, engine.py
  render/      split      hud.py + scenes/ = Adetola; camera_view.py + projectiles.py = Nikhil;
                          debug_overlay.py = Enoch; window.py + layout.py = Adetola + Nikhil
  replay/      Nikhil     record.py, play.py, fake_input.py
assets/        Adetola    sprites/, fonts/, sounds/
scripts/       Daniel + Enoch   check_env.py, bench_tracking.py, record_session.py, sync_to_jetson.sh
recordings/    contents gitignored
tests/         mirrors src/, plus test_boundaries.py and test_blueprint.py
```

| Person | Role |
|---|---|
| Daniel | Planning, repo, Jetson |
| Enoch | Camera and tracking |
| Nikhil | Data pipeline |
| Adetola | Game UI and design |

Work in your own folders. If you need a change in someone else's, ask them or open a small PR.

## Conventions

These are team rules. `tests/test_boundaries.py` enforces the import ones.

**Python and dependencies**
- Python `==3.10.*` (`.python-version` is `3.10`). Use uv only: `uv sync`, `uv run`, `uv add`. No pip, conda or poetry.
- Add no dependency beyond the spec §13.2 list without asking Daniel. Confirm it installs on aarch64/JetPack first. `numpy` is pinned `>=1.24,<2` to match the system `pyzed` build.

**Import boundaries**
- `pyzed` is imported only under `perception/`.
- `pygame` is imported only under `render/`.
- `game/` never imports `pygame`, `pyzed` or `cv2`.
- `core/` imports nothing from `magic_box` outside `core/`.
- `pyzed`, `cv2` and `sounddevice` are never imported at module top level; import them inside functions, so laptops and CI import every module.
- Absolute imports only (`from magic_box.x import y`). Ruff `TID252` bans relative imports.

**Code**
- Every module docstring has a line `Owner: <Name>`.
- A stub raises `NotImplementedError("TODO(<Owner>): <what>")` unless it returns a documented placeholder.
- Every tunable lives in `config.yaml`. Code reads `cfg`; it never hard-codes thresholds, keys, sizes or colors. Numbers marked "(guess)" are untuned.
- Use `multiprocessing` only through `magic_box.pipeline.streams.spawn_context()`.
- Never block the game loop: no network, disk waits or `queue.get()` without a timeout on the 60 fps path.

**Git**
- Commit format: `<type>(<scope>): <lowercase summary>`. Types `feat`, `fix`, `doc`, `chore`. One line, no body, no trailer.
- A change is done when `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` are all clean. Tests run headless (`tests/conftest.py` sets the SDL dummy drivers).

## Working without the Jetson

- **`--fake`:** keyboard-driven players and a synthetic camera frame (two silhouettes that follow fake root x and z). Runs on any laptop. This is how you develop render, game and intent work.
- **`--replay DIR`:** feeds a recorded session back with original timing.
- **`--record DIR`:** writes a session directory (`states.jsonl`, `voice.jsonl`, `events.jsonl`, `frames.mp4`, `meta.json`).
- **Live mode** (no `--fake`/`--replay`) starts the ZED perception and per-player Muse voice processes. Hardware and API behavior must still be validated on the Jetson.
- Spell keys always work as a voice fallback, so you can test casting with no mic and no Wi-Fi.

**Fake-mode keys** (from `config.yaml` `keys:`)

| Action | P1 | P2 |
|---|---|---|
| Left / right | `a` / `d` | `j` / `l` |
| Closer / farther | `w` / `s` | `i` / `k` |
| Push | `f` | `h` |
| Duck | `c` | `n` |
| Hands up / together | `r` / `t` | `y` / `u` |
| Guard (knight parry) | `g` | `o` |
| Spells | `1` `2` `3` | `8` `9` `0` |

`F1` toggles the debug overlay. `Esc` quits.

Per-machine overrides go in `config.local.yaml` (gitignored, deep-merged over `config.yaml`): real mic devices under `voice.mics`, `display.fullscreen: true`.

## Commands

| Command | What it does |
|---|---|
| `uv sync --extra laptop` | Install on a laptop (adds `opencv-python`). On the Jetson use plain `uv sync`. |
| `uv run python -m magic_box --fake` | Run with keyboard players. |
| `uv run --env-file .env python -m magic_box` | Live mode; `.env` holds `META_MODEL_API_KEY`. |
| `uv run python -m magic_box --help` | Flags: `--fake`, `--replay DIR`, `--record DIR`, `--debug`, `--headless`, `--config PATH`, `--max-ticks N`. |
| `uv run pytest` | Run all tests. |
| `uv run ruff check` / `uv run ruff format --check` | Lint and format check. |
| `uv run python scripts/check_env.py [--laptop]` | Environment check (Python, JetPack, RAM, pyzed, CUDA, cv2, audio, API key). |
| `scripts/sync_to_jetson.sh` | rsync the repo from a laptop to the Jetson (`JETSON_HOST`, `JETSON_DIR` override the defaults). |

`scripts/bench_tracking.py` is the hour-1 go/no-go for two-person tracking; `scripts/record_session.py` records a timed live session through the production runtime.

## Milestones

- **Hour 0–1:** Daniel: Jetson env and `check_env.py`. Enoch: `bench_tracking.py` go/no-go with two people. Nikhil: `--fake` running on the Jetson's monitor. Adetola: `docs/game-design.md` pass.
- **M1:** live ZED → `PlayerState` → layout C crops and self-view skeletons on the monitor.
- **M2:** push → basic attack projectile → HP drops (first playable).
- **M3:** debug overlay with a top-down meters view and the `wrist_vz` graph (the depth proof for judges).
- **M4:** voice charge + push release with fixed incantations; poses (Holy Light, Heal); dodges.
- **M5:** Spark incantations, full scene flow, lobby name capture.
- **M6:** Duel Chronicle, polish, demo video.
- **Cut first:** MediaPipe finger gestures.

## Risks

- **Orin Nano fps** with two bodies, depth, 60 fps render and crops. Benchmark first. Fallbacks: `BODY_18`, lower camera resolution, GPU crops via pygame-ce's SDL2 `Texture` API.
- **numpy ABI mismatch** between the venv and the system `pyzed` build. Pin to whatever works on the device.
- **Venue Wi-Fi.** Keyboard spell keys, config incantations and a template chronicle keep the demo alive. A phone hotspot is the backup.
- **Lav-mic crosstalk** at 1–2 m. Each mic matches only its own player's incantations, and the two sets are kept clearly different.
- **Muse partial-transcript latency** is unmeasured. Measure it at M4 and size the charge window from it.
- **Crop upscaling blur:** HD720 scaled about 2.4x to fill a half. Resolution is a config tunable.
- **Lighting, crowds and thermals** if the hardware goes in an enclosure.

## Open decisions

| Decision | Owner |
|---|---|
| Final classes, spells, costs, gestures, numbers (draft in `docs/game-design.md`) | Adetola |
| Scene flow details and lobby interactions | Adetola |
| Mic hardware model and channel routing | Daniel |
| JetPack, Python, RAM, ZED SDK version (confirm, then pin) | Daniel |
| Body model (`BODY_18`/`34`/`38`) and camera resolution after the benchmark | Enoch |
| Muse Spark `base_url` and model id (verify against dev.meta.ai docs) | Nikhil |
| Enclosure (Hardware track) | Daniel |
| MediaPipe finger gestures in or out | Enoch |
