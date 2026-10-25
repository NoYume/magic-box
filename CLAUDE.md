# magic-box

Read this first. Each package folder under `src/magic_box/` has its own short `CLAUDE.md`; Claude Code loads it when you work there. Spec: `docs/superpowers/specs/2026-10-24-magic-box-design.md`.

**Deadline: Sunday 2026-10-25, 11:30 CDT.** Everything has to be demo-ready and submitted by then. Check the time left before starting multi-step work, and favor what makes the live demo on the Jetson work over polish.

## What this is

A game console built from a ZED X stereo camera, a Jetson Orin Nano and an external monitor. It runs a 1v1 magic duel for HackTX 2026 (Hardware, Meta and Best Overall tracks). Two players stand side by side. Each watches their own half of a split screen showing a live close-up of the *opponent*. Players speak a Muse Spark-written incantation into their own clip-on mic to charge a spell, then release it with a body gesture (usually a fast push toward the camera). The defender dodges by stepping aside or ducking. Real distance to the camera scales damage.

## Why ZED + Jetson

1. Depth is load-bearing: push speed (m/s along Z), distance zones and dodges are measured in meters. If a feature works as well on a webcam, it is not a headline feature.
2. Body tracking gives two skeletons with IDs, so no hand-rolled pose model.
3. Everything runs on one small box, with no laptop in the loop at the demo.
4. The ZED X has an IMU, connects over GMSL2 through a ZED Link capture card, and works with the Jetson's CUDA stack.
5. The debug overlay (top-down meters view, `wrist_vz` graph) proves the depth story to judges.

Speech-to-text (Muse Voice Transcribe) and Muse Spark run in Meta's cloud. Video never leaves the box.

## Hardware

| Part | Notes |
|---|---|
| ZED X | GMSL2 via a ZED Link capture card, has an IMU, so body tracking works. Not hot-pluggable: after re-plugging, run `sudo systemctl restart zed_x_daemon` or reboot. |
| Jetson Orin Nano | RAM and JetPack unconfirmed; `scripts/check_env.py` is step 1. Video out is DisplayPort, so use a DP-to-HDMI adapter if the monitor needs HDMI. |
| Monitor | External, 1920x1080 assumed. |
| Mics | One clip-on lav mic per player: two USB lav mics, or a dual-transmitter wireless kit whose USB receiver puts P1 on L and P2 on R. A USB mic is the spare. |
| Network | Wi-Fi on the Jetson, for the Muse APIs. |

More in `docs/hardware.md`.

## Architecture

```
                ┌──────────── Jetson Orin Nano ─────────────────────────────┐
 ZED X ─GMSL2─▶ │ [perception proc]  only module that imports pyzed         │
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

**Change rule:** changing a contract needs a heads-up to every owner who produces or consumes it, and an update to this file in the same change.

| Boundary | Contract | From → To |
|---|---|---|
| Perception → intent | `PlayerState` | Enoch → Nikhil |
| Voice → intent | `VoiceEvent` | Nikhil |
| Intent → game rules | `Action` | Nikhil → Adetola |
| Game → render | `GameView` | Adetola → Adetola + Nikhil |

**`PlayerState` field notes** (Enoch produces, Nikhil consumes):
1. `wrist_vz` is the wrist's velocity relative to the neck (the root when there is no neck), in m/s, negative toward the camera. `Push.speed` is a positive number. `Push.speed` is the window-average speed at the moment the push threshold is crossed. For most punches that is just above `push_speed_mps` (about 1.5-1.7 m/s), not the punch's peak speed. Whether to report peak speed instead is an open decision for Adetola (game balance) and Enoch. Walking toward the camera does not fire a push.
2. `wrists` and `keypoints_px` hold only valid points, so read them with `.get()`. `wrist_vz` always has `"L"` and `"R"`.
3. A two-hand push arrives as one `Push` (the faster hand). Intent recognises it when the other hand's `wrist_vz` crosses `-push_speed_mps` within ~100 ms of the push (`wrist_vz` is published every frame). A push gives one event: a cooldown and a re-arm stop repeats.
4. `player_id` is the ZED tracking id.
5. A player who leaves is republished at once with `tracking_ok=False`, carrying the last pose flags and zone, with `push=None`. Consumers (intent) must gate on `tracking_ok`.

**Intent, voice and game field notes** (Nikhil produces unless noted; Adetola's engine consumes):
6. `Action.two_hand` is set on a `push` Action when the other hand's `wrist_vz` is at or below `-push_speed_mps` within `intent.two_hand_window_s` (0.1 s, a guess) of the push. So every push is held up to 0.1 s before it reaches the engine. Pose and dodge Actions carry `dist` (root Z).
7. `Action(kind="speech", text=...)` is one final transcript of a speech turn, from a `transcript` `VoiceEvent`. The engine decides what speech means per scene (the lobby takes it as the player's name).
8. `VoiceEvent(kind="status")` has `text` of `"no api key"`, `"no mic"`, `"connected"` or `"reconnecting"`. The loop passes each one to `Engine.provide_mic_status(slot, ok)`, with `ok` true only for `"connected"` (HUD: MIC OK, else MIC OFF).
9. `SpellView.release` is `push`, `two_hand_push`, `arm_overhead` or `hands_together`, so the HUD and loading card can say how to cast.

Heads-up for Adetola (engine, HUD, scenes: the thin engine in `game/` is yours to replace) and Enoch (the two-hand push rule now lives in `intent/`, not in perception).

## Team and ownership

```
CLAUDE.md, README.md, pyproject.toml, uv.lock, .env.example, .github/, .claude/   Daniel
config.yaml               shared; each section is commented with its owner
docs/game-design.md       Adetola          docs/hardware.md   Daniel + Enoch
src/magic_box/
  main.py, __main__.py    Nikhil           CLI entry
  core/        Nikhil     contracts.py, serde.py, config.py, geometry.py
  perception/  Enoch      process.py, zed_source.py, raw.py, keypoints.py, kinematics.py, bodies.py, tracker.py, push.py, poses.py, motion.py, hands.py
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
- **`--replay DIR`:** feeds a recorded session back with rebased timing. There is no video: the camera frame is redrawn as silhouettes from the recorded states. A missing session exits 2 with "replay: no session at DIR".
- **`--record DIR`:** writes a session directory (`states.jsonl`, `voice.jsonl`, `events.jsonl`, `meta.json`). No `frames.mp4`: the Jetson already records SVO (`scripts/record_session.py`). A writer thread does the disk work, so the game loop never waits.
- **Live mode** (no `--fake`/`--replay`) starts the perception and voice processes. On a laptop the perception process exits with "pyzed is not installed ... use --fake on a laptop" and the window shows "STEP INTO VIEW". The supervisor retries the perception process a few times before giving up.
- **Voice and Spark need `META_MODEL_API_KEY`** (in `.env`, run with `--env-file`). Without it (or with `ai.enabled: false`) Spark falls back at once to the config incantations and a template chronicle, and the voice process reports `"no api key"` (HUD: MIC OFF). Without a usable mic it reports `"no mic"` and idles.
- **Muse and Spark are not verified live.** They are implemented against Meta's documented API (checked 2026-10-24) and tested only with fakes; partial-transcript latency is unmeasured. Verify on the Jetson with a real key.
- Spell keys always work as a voice fallback, so you can test casting with no mic and no Wi-Fi.
- The engine in `game/` is thin: it plays the whole match flow with Appendix A damage, but spells that do 0 damage (Flame Wall, Static Field, Holy Light, Heal) only spend mana, log a `cast` event and show a banner. Classes are fixed from `game.default_classes`, and there is no boot scene. Adetola replaces it.

**Fake-mode keys** (from `config.yaml` `keys:`)

| Action | P1 | P2 |
|---|---|---|
| Left / right | `a` / `d` | `j` / `l` |
| Closer / farther | `w` / `s` | `i` / `k` |
| Push | `f` | `h` |
| Duck | `c` | `n` |
| Hands up / together | `r` / `t` | `y` / `u` |
| Two-hand push | `v` | `m` |
| Spells | `1` `2` `3` | `8` `9` `0` |

`F1` toggles the debug overlay. `Esc` quits.

**Fake match walkthrough** (`uv run python -m magic_box --fake`):
1. Lobby: both players raise their hands (`r` + `y`) to start.
2. Loading: a countdown, with each player's incantations and release cues on their half.
3. Fight: charge with `1`, push with `f`. A projectile flies on P2's half and P2's HP drops. Ducking (`n`) during the red window avoids it. Two-hand spells need `v` / `m`.
4. KO or time-out: the victory scene shows a chronicle.
5. Both raise hands again (after `victory_min_s`): back to the lobby. Names persist across matches.

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
| `uv run python scripts/check_env.py [--laptop]` | Environment check (Python, JetPack, RAM, pyzed, ZED camera and `zed_x_daemon`, CUDA, cv2, audio, API key). |
| `uv run python scripts/bench_tracking.py [--seconds N] [--body-format F] [--resolution R] [--svo PATH] [--min-fps X] [--min-two S]` | Two-person tracking benchmark on the Jetson. Prints GO or NO-GO. |
| `uv run python scripts/record_session.py [--seconds N] [--out PATH]` | Record the live ZED X to an SVO2 file in `recordings/`. |
| `scripts/sync_to_jetson.sh` | rsync the repo from a laptop to the Jetson (`JETSON_HOST`, `JETSON_DIR` override the defaults). |

`bench_tracking.py` is the hour-1 go/no-go for two-person tracking. It prints GO or NO-GO from the measured fps and the share of frames with two people. On NO-GO, retry with `--body-format BODY_18`. To tune offline, record an SVO with `record_session.py`, then set `camera.svo_path` in `config.local.yaml` and run the game as usual (playback loops; perception handles the `cam_t` rewind).

## Milestones

All milestones land before the deadline: **Sunday 2026-10-25, 11:30 CDT**.

- **Hour 0–1:** Daniel: Jetson env and `check_env.py`. Enoch: `bench_tracking.py` go/no-go with two people. Nikhil: `--fake` running on the Jetson's monitor. Adetola: `docs/game-design.md` pass.
- **M1:** live ZED → `PlayerState` → layout C crops and self-view skeletons on the monitor.
- **M2:** push → basic attack projectile → HP drops (first playable).
- **M3:** debug overlay with a top-down meters view and the `wrist_vz` graph (the depth proof for judges).
- **M4:** voice charge + push release with fixed incantations; poses (Holy Light, Heal); dodges.
- **M5:** Spark incantations, full scene flow, lobby name capture.
- **M6:** Duel Chronicle, polish, demo video.
- Finger gestures are out. `perception/hands.py` stays a stub.

## Risks

- **Orin Nano fps** with two bodies, depth, 60 fps render and crops. Benchmark first. Fallbacks: `BODY_18` with body fitting off (`camera.body_fitting: false`; BODY_34/38 need fitting), a lower camera resolution, GPU crops via pygame-ce's SDL2 `Texture` API.
- **numpy ABI mismatch** between the venv and the system `pyzed` build. Pin to whatever works on the device.
- **Venue Wi-Fi.** Keyboard spell keys, config incantations and a template chronicle keep the demo alive. A phone hotspot is the backup.
- **Lav-mic crosstalk** at 1–2 m. Each mic matches only its own player's incantations, and the two sets are kept clearly different.
- **Muse partial-transcript latency** is unmeasured. Measure it at M4 and size the charge window from it.
- **Crop upscaling blur:** SVGA (960x600) is scaled about 1.8x to fill a half. HD1200 is the fallback if it looks too soft, at a cost in fps. Resolution is a config tunable.
- **GMSL2 is not hot-pluggable.** Never re-plug the camera while the system runs. See the ZED X troubleshooting section in `docs/hardware.md`.
- **Lighting, crowds and thermals** if the hardware goes in an enclosure.

## Open decisions

| Decision | Owner |
|---|---|
| Final classes, spells, costs, gestures, numbers (draft in `docs/game-design.md`) | Adetola |
| Scene flow details and lobby interactions | Adetola |
| Mic hardware model and channel routing | Daniel |
| JetPack, Python, RAM, ZED SDK version (confirm, then pin) | Daniel |
| Body format (defaults to `BODY_34`) and camera resolution (defaults to SVGA), confirmed by `bench_tracking.py` | Enoch |
| Muse Spark `base_url` and model id (set to `muse-spark-1.3`; confirm live) | Nikhil |
| Muse keyword format (words vs phrases) and `game.charge_window_s`, after measuring partial latency | Nikhil |
| Replace the thin engine in `game/` (spell effects, class pick, boot scene, real HUD and scenes) | Adetola |
| `Push.speed`: threshold speed (today) or peak speed, for damage scaling | Adetola + Enoch |
| Enclosure (Hardware track) | Daniel |
