# magic-box: Design Spec

- **Date:** 2026-10-24
- **Event:** HackTX 2026. Tracks: Hardware, Meta ("Bringing people closer together with AI"), Best Overall
- **Team:** Daniel (planning, repo, Jetson), Enoch (camera and tracking), Nikhil (data pipeline), Adetola (game UI and design)
- **Status:** Approved in brainstorming. This spec covers the system architecture and the repo blueprint. Game mechanics are a proposed draft owned by Adetola and remain open (Appendix A).

## 1. Summary

magic-box is a game console built from a ZED 2 stereo camera, a Jetson Orin Nano, and an external monitor. It runs a 1v1 magic duel. Two players stand side by side facing the monitor. Each player watches their own half of the split screen, which shows a live close-up of the *opponent*. Players cast spells by speaking a Muse Spark-generated incantation into their own clip-on mic and then releasing the spell with a body gesture, usually a fast push toward the camera. Spells fly out of the opponent's hand on the defender's half and grow as they approach. The defender dodges by physically stepping aside or ducking. Real distance to the camera scales damage dealt and taken.

All vision, depth, game logic and rendering run on the Jetson. Speech-to-text (Muse Voice Transcribe) and text generation (Muse Spark) are cloud APIs called from the Jetson.

## 2. Goals and success criteria

- **Live demo:** two players fight a full match on the Jetson, with no laptop in the loop.
- **Depth is load-bearing (Hardware track):** push speed (m/s along camera Z), distance zones, and step or duck dodges are all measured by the ZED in meters. A debug overlay shows this to judges. If a feature works equally well on a flat webcam, it is not a headline feature.
- **AI is essential (Meta track):**
  - Muse Voice Transcribe recognizes spells per player.
  - Muse Spark writes fresh incantations every match.
  - Muse Spark writes a Duel Chronicle of the match using both players' names.
- **Human connection (Meta track, 30%):** two people in the same room, looking at each other instead of at their own screens, plus a shared post-match story.
- **Meta submission:** a 2–3 minute demo video covering the problem, the demo, the AI's role, and the tools used.
- **Blueprint (this spec's deliverable):** four people can work in parallel from hour 1, each in a folder they own, against stable contracts, with Claude context in every folder.

## 3. Non-goals for this spec

- Final game balance, the final spell list, and the final gestures. Adetola owns these and they are open (Appendix A).
- Real tracking, voice or rules implementations. The blueprint ships stubs for these (§13).
- Online multiplayer, more than two players, controllers.

## 4. Hardware

| Part | Notes |
|---|---|
| ZED 2 | USB 3. Has an IMU, so body tracking is supported. |
| Jetson Orin Nano | RAM and JetPack version unconfirmed. Checking them is step 1 on the device (`scripts/check_env.py`). The dev kit's video output is DisplayPort, so use a DP-to-HDMI adapter if the monitor needs HDMI. |
| Monitor | External, 1920×1080 assumed. This is the console's main display. |
| Mics | One clip-on lav mic per player, which works better in a noisy room than one big mic. Either two USB lav mics or a dual-transmitter wireless kit whose USB receiver puts P1 on the L channel and P2 on R. An external USB mic is a spare. |
| Network | Wi-Fi on the Jetson, for the Muse APIs. |

## 5. Decisions made

| Decision | Choice |
|---|---|
| Voice attribution | **One mic per player plus push to release (option C).** Each mic feeds its own Muse stream, so the mic decides who spoke. Attack spells still need a depth-measured push to release. |
| Incantations | **Muse Spark writes them per match (option B)**, during the loading screen. The HUD shows them. They're fuzzy-matched against Muse partial transcripts. A fixed set in config is the fallback. |
| Screen layout | **Layout C:** each half shows a tracked close-up of the opponent, plus a small mirrored self-view with skeleton, the "CHARGED, PUSH!" cue, and distance zone. |
| Meta extra | **Duel Chronicle (option B):** players say their names in the lobby, and after the match Spark writes a short story from the event log. Stretch goal after the core game works. |
| Stack | **All Python, three processes, pygame-ce renderer (approach A).** Godot and raw OpenGL were rejected for hackathon speed. |
| Environment | **uv**: `uv venv --system-site-packages`, pinned to the Jetson's system Python, so `pyzed` and JetPack's OpenCV are visible. |
| Mechanics | Open. Appendix A is a draft for Adetola. |

## 6. Architecture

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

**Processes.**
- **Start method:** `multiprocessing` with the `spawn` start method on every platform, because forking after CUDA init is unsafe.
- **Supervision:** a launcher (`pipeline/processes.py`) starts the three processes, watches them, and restarts perception or voice if either dies.

**Transport rules.** There are two kinds of data and they travel differently.
- **Camera frames are latest-value.**
  - **Format:** the left image goes into a shared-memory double buffer. The header holds `frame_idx` and `cam_t`, and the image is BGRA uint8 at the configured resolution.
  - **Reading:** the game reads the newest complete buffer and never waits. If `frame_idx` hasn't changed, it reuses the last texture.
- **`PlayerState` and `VoiceEvent` are streams.**
  - **Delivery:** they travel on bounded `multiprocessing.Queue`s, and the game drains every queued item each tick. Discrete detections such as a push live on a single frame's state, so dropping states would lose inputs.
  - **Overflow:** if a queue fills because the game stalled, the producer drops the *oldest* item and counts the drop.
  - **Rendering:** uses the newest drained state per slot.

**Control channel (game → voice).** The game process sends a `VoiceConfig` message on its own queue whenever the scene changes:
- **Lobby:** transcript mode, so names and class picks come through as raw text.
- **Match start:** each player's incantation set, which restarts the Muse sessions with those words as `keywords`.

**One game loop, many sources.** `pipeline/loop.py` runs the game process tick:
1. `render.window.pump()` returns the keys pressed this tick.
2. Sources are polled for `PlayerState`s, `VoiceEvent`s and the latest frame.
3. `intent` turns those into `Action`s.
4. `game.engine.step()` returns a `GameView` plus `GameEvent`s.
5. `render.window.draw()` draws the view.

Sources sit behind one interface in `pipeline/sources.py`:
- **live:** process queues and shared memory;
- **`--replay`:** file readers;
- **`--fake`:** `replay/fake_input.py`, which receives the pressed keys from the loop.

A `KeyboardVoiceSource` is always merged in. It turns spell keys into `VoiceEvent(kind="incantation", match_score=100)`. Because the window hands key presses to everything else as plain data, only `render/` touches `pygame`.

**Spark jobs.** When the engine enters `loading` or `victory`, the loop submits a job to the `ai/` worker thread and passes the result back through `engine.provide_incantations()` and `engine.provide_chronicle()`. The engine never blocks waiting for it.

**Clock.**
- **`t` (shared clock):** every contract has a `t` set to `time.monotonic()` when the item is published. That clock is shared by all processes on the same machine, and fusion compares voice and push times with it.
- **`cam_t` (velocities only):** `PlayerState` also carries `cam_t`, the ZED image timestamp in seconds, which is used only to compute velocities.

**Units and frames.**
- **Units:** meters and seconds everywhere.
- **ZED settings:** `UNIT.METER` and `COORDINATE_SYSTEM.IMAGE`, so +Z points away from the camera and motion toward the camera has negative `vz`.
- **Pixel coordinates:** refer to the unmirrored left image. Only the self-view is mirrored, and only at render time.

## 7. Data contracts (`src/magic_box/core/contracts.py`)

These are the only types that cross ownership boundaries. Changing one requires a heads-up to every owner and an update to the root `CLAUDE.md`.

```python
Vec3 = tuple[float, float, float]           # meters, camera frame
Px = tuple[float, float]                    # pixels, unmirrored left image

@dataclass(frozen=True)
class Push:                                 # one detected thrust toward the camera
    hand: str                               # "L" | "R"
    speed: float                            # m/s toward camera (positive number)
    origin_px: Px                           # wrist pixel when detected (projectile spawn point)

@dataclass(frozen=True)
class PlayerState:                          # perception → game, one per slot per camera frame
    slot: int                               # 0 = P1 (stands left), 1 = P2 (stands right)
    player_id: int                          # ZED tracking id currently bound to this slot
    t: float                                # time.monotonic() at publish
    cam_t: float                            # ZED image timestamp, seconds
    frame_idx: int                          # matches the frame bus / recording frame
    tracking_ok: bool
    root: Vec3                              # pelvis; root[2] is distance to camera
    root_vx: float                          # m/s sideways, smoothed (dodge feature)
    head: Vec3                              # head position (duck feature)
    wrists: dict[str, Vec3]                 # "L"/"R"
    wrist_vz: dict[str, float]              # m/s along Z, negative = toward camera
    zone: str                               # "danger" | "neutral" | "far" (thresholds in config)
    push: Push | None                       # set only on the frame a push is detected
    pose_flags: frozenset[str]              # continuous poses, e.g. {"hands_up", "hands_together"}
    bbox_px: tuple[int, int, int, int]      # x, y, w, h (opponent crop)
    keypoints_px: dict[str, Px]             # named joints for the self-view skeleton
    finger_gesture: dict[str, str | None]   # optional MediaPipe result per hand, else None

@dataclass(frozen=True)
class VoiceEvent:                           # voice → game
    slot: int
    t: float
    kind: str                               # "incantation" | "transcript" (lobby: names, class picks)
    text: str                               # cumulative partial or final transcript
    spell_id: str | None                    # set when kind == "incantation"
    match_score: float                      # 0-100, rapidfuzz score vs the matched incantation

@dataclass(frozen=True)
class Action:                               # intent → game rules (signal processing done, no rules yet)
    kind: str                               # "charge" | "push" | "pose" | "dodge"
    slot: int
    t: float
    spell_id: str | None = None             # charge
    match_score: float = 0.0                # charge
    push: Push | None = None                # push
    pose: str | None = None                 # pose (rising edge of a pose flag)
    dodge: str | None = None                # "step" | "duck"
    dist: float = 0.0                       # actor's root Z at this moment

@dataclass(frozen=True)
class GameEvent:                            # append-only match log (chronicle, recordings, debugging)
    t: float
    kind: str                               # "match_start" | "cast" | "hit" | "dodge" | "block" | "heal" | "buff" | "ko" | "match_end"
    slot: int | None
    data: dict[str, Any]

@dataclass(frozen=True)
class GameView:                             # game → render, one snapshot per tick. Render draws only this.
    scene: str                              # "boot" | "lobby" | "loading" | "fight" | "victory"
    players: tuple[PlayerView, PlayerView]
    projectiles: tuple[ProjectileView, ...]
    banner: str | None                      # center text, e.g. "ROUND START", "STEP INTO VIEW"
    timer_s: float | None
    chronicle: str | None                   # victory scene

@dataclass(frozen=True)
class PlayerView:
    slot: int
    name: str
    class_id: str
    hp: float
    hp_max: float
    mana: float
    mana_max: float
    spells: tuple[SpellView, ...]           # id, display name, incantation, cost, charged: bool
    zone: str
    dist: float
    mic_ok: bool
    tracking_ok: bool

@dataclass(frozen=True)
class ProjectileView:
    spell_id: str
    target_slot: int                        # drawn on the target's half
    origin_px: Px                           # attacker wrist in the camera image
    progress: float                         # 0 = just cast, 1 = impact
    in_dodge_window: bool
```

`SpellView(id: str, name: str, incantation: str, cost: float, charged: bool)` is also a frozen dataclass. All contracts round-trip to and from JSON lines (`core/serde.py`) for recording and replay.

**Ownership of the boundaries:**
- **Perception → intent:** `PlayerState` (Enoch → Nikhil).
- **Voice → intent:** `VoiceEvent` (Nikhil).
- **Intent → game rules:** `Action` (Nikhil → Adetola).
- **Game → render:** `GameView` (Adetola → Adetola + Nikhil).

## 8. Subsystems

| Package | Owner | Input → Output | Responsibilities |
|---|---|---|---|
| `perception/` | Enoch | ZED 2 → `PlayerState`, frames | Open the camera (live or SVO); body tracking; keep only bodies within `max_range` and, if there are more than two, the 2 closest; bind bodies to slots by x position at round start and re-bind by side after loss; smooth wrist Z velocity and detect pushes with a cooldown; detect pose flags; compute motion features (`root_vx`, head); compute zone. **Only package that imports `pyzed`.** |
| `pipeline/` | Nikhil | processes ↔ queues and shared memory | Launcher with `spawn` and restart on crash, shared-memory frame bus, bounded drop-oldest stream queues, the source interface (live / replay / fake, plus keyboard voice), the game-process loop, the `VoiceConfig` control queue. |
| `intent/` | Nikhil | `PlayerState` stream + `VoiceEvent` → `Action` | Turn voice matches into `charge`; turn `push` into `push` actions; rising edges of pose flags → `pose`; windowed step and duck detection → `dodge`. Signal processing only, with no rules about HP or mana. |
| `voice/` | Nikhil | mics → `VoiceEvent` | Per-player capture from (device, channel) as PCM16 mono at 16 kHz, resampled in-process if the device can't do it; one Muse WebSocket per player in `ENDPOINTING` mode with `CUMULATIVE` partials; keep sending silence during pauses; per-match `keywords`; reconnect with backoff, including at the 60-minute session limit; `rapidfuzz` match against **only that player's** incantations; at most one incantation event per speech turn. |
| `ai/` | Nikhil | match context → incantations, chronicle | Muse Spark through an OpenAI-compatible client. Generates the incantation set (validated for length and for distance from the other player's set) with an 8 s timeout and the config fallback. Generates the chronicle from the `GameEvent` log, falling back to a template. Runs on a worker thread in the game process. |
| `game/` | Adetola | `Action` → `GameView` + `GameEvent` | Classes, spell table (data in `config.yaml`), HP and mana, charge windows, projectiles in flight, dodge windows, combat formula, scene state machine. **Pure Python: no `pygame`, `pyzed` or `cv2` imports.** |
| `render/` | Adetola + Nikhil | `GameView` + latest frame → pixels | `layout.py` (layout C geometry), `hud.py`, `scenes/` (Adetola); `camera_view.py` (smoothed opponent crop, mirrored self-view with skeleton), `projectiles.py` (spell flight from wrist toward viewer, scale by progress) (Nikhil); `debug_overlay.py`: top-down view in meters, `wrist_vz` graph, fps (Enoch). **The only package that imports `pygame`.** `window.pump()` hands key presses to the rest of the code as plain data. |
| `replay/` | Nikhil | recordings ↔ streams | `record.py` writes a session directory (`states.jsonl`, `voice.jsonl`, `events.jsonl`, `frames.mp4`, `meta.json`); `play.py` feeds it back with original timing; `fake_input.py` turns pressed key names into `PlayerState`s plus a synthetic numpy frame. |

**Voice mode note:** use `mode: ENDPOINTING` with `partialMode: CUMULATIVE`, because it gives a `speechStart` / `speechComplete` turn structure for the one-cast-per-turn rule. Partial `transcript` events within a turn are matched as they arrive, without waiting for the endpoint. `DIARIZATION` is not used; Meta says it isn't tuned for low-latency commands.

**Spark note:** use model `muse-spark-1.1` through the OpenAI SDK, with `base_url` and the model name in `config.yaml`. Confirm both against dev.meta.ai docs before first use. The API key is read from env var `META_MODEL_API_KEY` (loaded with `uv run --env-file .env`).

## 9. Screen layout (layout C)

- **Display:** a 1920×1080 output split into two 960×1080 halves with a gold divider. P1 stands on the left and watches the left half; P2 stands on the right and watches the right half.
- **Each half shows the opponent:** a crop around the opponent's `bbox_px`. The crop has an 8:9 aspect ratio and padding, is EMA-smoothed against jitter, and is scaled to fill the half.
- **Enemy HP:** a slim bar at the top of the half, with the enemy's name and class.
- **Self-view:** a small mirrored crop of the viewer in the top-right corner, with skeleton lines drawn from `keypoints_px`.
- **Your HUD at the bottom:**
  - name and class;
  - distance and zone label, e.g. "1.9 m · NEUTRAL";
  - HP and mana bars;
  - spell cards showing each incantation, with a glowing "CHARGED, PUSH!" state while a spell is charged;
  - mic status icon.
- **Incoming spells:** drawn on the defender's half. Each starts at the attacker's wrist inside the crop and moves toward the bottom center while growing. During the dodge window it turns red and "DODGE!" appears.
- **Debug overlay:** toggled with a key.

The approved mockup is in `.superpowers/brainstorm/` (gitignored).

## 10. Scene flow (proposed; Adetola owns)

`boot → lobby → loading → fight → victory → lobby`

| Scene | What happens |
|---|---|
| boot | Self-check: camera, both mics, network, API key. Shows status. Missing network still boots (voice offline, keyboard fallback). |
| lobby | Players step into the play area. Each says their name, which doubles as a mic check, picks a class by saying its name, and both raise their hands to start. |
| loading | Spark generates incantations, shown on each half as a tutorial card. Voice sessions restart with the match's `keywords`. Countdown. |
| fight | Default 90 s round. KO, or higher HP at time-out, wins. |
| victory | Winner banner, stats, and the Duel Chronicle (stretch). |

## 11. Error handling

| Failure | Behavior |
|---|---|
| A player leaves the frame | `tracking_ok=False`. That half shows "STEP INTO VIEW" and the round pauses after 2 s. Re-bind by side. |
| Old perception data | A `PlayerState` older than 200 ms counts as `tracking_ok=False` for that slot. Render keeps drawing at 60 fps. |
| Perception process dies | "CAMERA RECONNECTING" banner; the launcher restarts the process. |
| Muse stream drops, or no Wi-Fi | Reconnect with backoff; the mic icon shows the status. **Keyboard spell keys always work:** P1 `1` `2` `3`, P2 `8` `9` `0`. |
| Spark fails or takes longer than 8 s | Fall back to fixed incantations from config; the chronicle falls back to a template filled from the event log. |
| Queue overflow | Drop the oldest item, increment a counter, and show the counter in the debug overlay. |

## 12. Testing

- **Laptop and CI (`uv run pytest`):**
  - contract JSON round-trip;
  - config load and validation;
  - frame bus (shared memory) write and read;
  - drop-oldest queue;
  - incantation matcher on sample transcripts;
  - intent timing (charge, then push within the window; pose rising edges; step and duck);
  - combat formula;
  - scene transitions;
  - a render smoke test with `SDL_VIDEODRIVER=dummy`.
- **Architecture boundary test (`tests/test_boundaries.py`):** scans imports and fails if:
  - `pyzed` is imported outside `perception/`;
  - `pygame` is imported outside `render/`;
  - `game/` imports `pygame`, `pyzed` or `cv2`.
- **Replay tests:** once recordings exist, a recorded `.jsonl` file goes in and the expected `Action`s must come out.
- **Jetson:**
  - `scripts/check_env.py` checks the Python version, JetPack and RAM, that `pyzed` imports *inside the venv*, CUDA, how `cv2` was built, the audio devices, and whether the Meta API key works.
  - `scripts/bench_tracking.py` measures fps with two people in frame (go/no-go in hour 1).
- **Lint:** `ruff check` and `ruff format`.
- **CI:** `.github/workflows/ci.yml` runs `uv sync --extra laptop`, `ruff`, and `pytest` on every push. Laptop-side code only.
- **Lazy imports:** `sounddevice`, `cv2` and `pyzed` are imported inside functions, never at module top level, so CI and laptops without PortAudio, OpenCV or the ZED SDK can still import every module.

## 13. Repo blueprint

```
CLAUDE.md                 Daniel   project brief, architecture, contracts, conventions, team map, milestones
README.md                 Daniel   human quickstart: Jetson setup + laptop setup
pyproject.toml, uv.lock   Daniel   uv project; requires-python pinned to the Jetson's system Python
.python-version           Daniel   3.10 (confirm on device; change if JetPack differs)
config.yaml               shared   ALL tunables; each section commented with its owner
.env.example              Daniel   META_MODEL_API_KEY=
.gitignore                Daniel   .venv, .env, recordings/*, .superpowers/, __pycache__, *.svo
.claude/settings.json     Daniel   shared permission allowlist (uv run pytest/ruff/python -m magic_box, uv sync, read-only git)
.github/workflows/ci.yml  Daniel   ruff + pytest
docs/
  game-design.md          Adetola  seeded from Appendix A, marked DRAFT / open
  hardware.md             Daniel+Enoch  wiring, ZED placement and height, play-area markings, mic routing, Jetson setup
  superpowers/specs/      this file
  superpowers/plans/      implementation plans
src/magic_box/
  __init__.py
  __main__.py             Nikhil   `python -m magic_box` → main.run()
  main.py                 Nikhil   modes: live | --replay <dir> | --fake ; --record <dir> ; --debug
  core/        CLAUDE.md  Nikhil   contracts.py, serde.py, config.py
  perception/  CLAUDE.md  Enoch    process.py, zed_source.py, bodies.py, push.py, poses.py, motion.py, hands.py (optional)
  pipeline/    CLAUDE.md  Nikhil   processes.py, frame_bus.py, streams.py, sources.py, loop.py
  intent/      CLAUDE.md  Nikhil   fusion.py, dodge.py
  voice/       CLAUDE.md  Nikhil   process.py, mic.py, muse_stream.py, matcher.py
  ai/          CLAUDE.md  Nikhil   spark_client.py, incantations.py, chronicle.py
  game/        CLAUDE.md  Adetola  classes.py, spells.py, state.py, combat.py, scenes.py, engine.py
  render/      CLAUDE.md  split    window.py, layout.py, hud.py, scenes/, camera_view.py, projectiles.py, debug_overlay.py
  replay/      CLAUDE.md  Nikhil   record.py, play.py, fake_input.py
assets/                   Adetola  sprites/, fonts/, sounds/ (.gitkeep)
scripts/                  Daniel+Enoch  check_env.py, bench_tracking.py, record_session.py, sync_to_jetson.sh
recordings/               .gitkeep (contents gitignored)
tests/                    mirrors src/ + test_boundaries.py
```

### 13.1 Claude files

- **Root `CLAUDE.md`:** the whole-project picture. It's built from the team's mock and updated with every decision in this spec: what the project is and why ZED + Jetson matters, hardware, architecture, contracts, the transport and clock rules, conventions, working without the Jetson, commands, team and ownership map, milestones, risks, and open decisions with owners.
- **One `CLAUDE.md` per package**, which Claude Code loads when working in that folder. Each one is short and states:
  - the owner;
  - its inputs and outputs (which contracts);
  - hard rules (import boundaries, never block, units);
  - how to run and test it without the Jetson;
  - the files and what each does;
  - open `TODO(owner)` items.
- **`.claude/settings.json`:** a shared, non-personal permission allowlist only. No hooks; the boundary test enforces architecture instead.

### 13.2 Dependencies

- **Runtime:**
  - `numpy` — the version must match what `pyzed` was built against on the Jetson; `check_env.py` verifies `import pyzed.sl` inside the venv;
  - `pygame-ce`, `pyyaml`, `rapidfuzz`, `websockets`, `sounddevice`, `openai`.
- **Laptop extra:** `opencv-python`. The Jetson uses the JetPack system `cv2` through system site-packages and must not install this extra.
- **Dev group:** `pytest`, `ruff`.
- **Not in pyproject:**
  - `pyzed`, which comes from the ZED SDK installer into system Python;
  - PortAudio (`apt install libportaudio2` on the Jetson).
- **Before adding any dependency:** confirm it installs on aarch64 and JetPack.

### 13.3 Blueprint depth

- **Real, tested code (the shared foundation):**
  - `core/`: contracts, serde, and config with validation;
  - `pipeline/`: launcher, frame bus, streams, sources, loop;
  - `replay/fake_input.py`: keyboard players, plus synthetic numpy frames that draw two silhouettes whose position and size follow fake root x and z;
  - `main.py` with `--fake`;
  - `render/window.py` + `layout.py` + `camera_view.py`: the placeholder layout C, with opponent crops, mirrored self-views, and static HP and mana bars from a stub `GameView`;
  - `tests/test_boundaries.py`;
  - `scripts/check_env.py`.

  Running `uv run python -m magic_box --fake` on any laptop shows layout C, with the fake players moving in response to the keyboard.
- **Stubs:** every other module has a docstring, typed signatures that raise `NotImplementedError` or return a placeholder, and `TODO(owner)` markers. `game/engine.py` returns a fixed `GameView`.
- **Not written yet:** tracking, voice, Spark, rules, HUD art, scenes.

## 14. Milestones (parallel tracks, integration checkpoints)

- **Hour 0–1:**
  - Daniel: Jetson env and `check_env.py`.
  - Enoch: `bench_tracking.py` go/no-go with two people.
  - Nikhil: blueprint `--fake` running on the Jetson's monitor.
  - Adetola: `docs/game-design.md` pass.
- **M1:** live ZED → `PlayerState` → layout C crops and self-view skeletons on the monitor.
- **M2:** push → basic attack projectile → HP drops (first playable).
- **M3:** debug overlay with a top-down view in meters and the `wrist_vz` graph (the depth proof for judges).
- **M4:** voice charge + push release using fixed incantations; poses (Holy Light, Heal); dodges.
- **M5:** Spark incantations, the full scene flow, and the lobby name capture.
- **M6:** Duel Chronicle, polish, demo video.
- **Optional, cut first:** MediaPipe finger gestures.

## 15. Risks

- **Orin Nano fps** with two bodies, depth, a 60 fps render, and crops. Benchmark first. Fallbacks: `BODY_18`, lower camera resolution, render crops through pygame-ce's SDL2 `Texture` API on the GPU.
- **numpy ABI mismatch** between the venv's `numpy` and the system `pyzed` build. Pin to whatever works on the device.
- **Venue Wi-Fi.** Muse and Spark are cloud APIs. Keyboard fallback, fixed incantations, and a template chronicle keep the demo alive. A phone hotspot is the backup.
- **Crosstalk between lav mics** about 1–2 m apart. The design limits it: each mic matches only its own player's incantations, and the two players' sets are kept clearly different.
- **Muse partial-transcript latency** is unmeasured. Measure it at M4, and size the charge window accordingly.
- **Crop upscaling blur:** a person in an HD720 frame scaled up about 2.4× to fill a half. Camera resolution is a config tunable.
- **Lighting, crowds, and thermals** if the hardware goes in an enclosure.

## 16. Open decisions

| Decision | Owner |
|---|---|
| Final classes, spells, costs, gestures, numbers (Appendix A draft) | Adetola |
| Scene flow details and lobby interactions | Adetola |
| Mic hardware model and channel routing | Daniel |
| JetPack, Python, RAM, ZED SDK version (confirm, then pin) | Daniel |
| Body model (`BODY_18` / `34` / `38`) and camera resolution after benchmark | Enoch |
| Muse Spark `base_url` and model id confirmation | Nikhil |
| Enclosure (Hardware track) | Daniel |
| MediaPipe finger gestures in or out | Enoch |

## Appendix A: Proposed mechanics (DRAFT, Adetola owns, open for discussion)

Every number lives in `config.yaml` and is a guess until tuned on recordings.

**Casting:**
1. **Speak** the incantation into your own mic. A match score of 80 or more charges the spell for 3 s and reserves its mana.
2. **Release.** Attacks release with a push faster than 1.5 m/s toward the camera. Buffs release with a pose: arm overhead for Holy Light, hands together at the chest for Heal. If the window passes with no release, the charge fizzles and the mana is refunded.
3. **Flight.** The projectile flies over the spell's travel time.
4. **Dodge.** In the last 0.6 s the defender can dodge by stepping at least 0.3 m sideways or ducking at least 0.25 m. A successful dodge means no damage.

**Basic attack:** a push with no charged spell. Free, 0.8 s cooldown, fast. The knight's main source of damage.

**Damage:** `base × speed_mult × atk_dist_mult × def_dist_mult × buffs`.
- `speed_mult` = push speed ÷ 2.0 m/s, clamped to 0.6–1.8.
- The distance multiplier runs smoothly from ×1.4 at 1.2 m to ×0.7 at 2.8 m. The attacker's distance is read at release and the defender's at impact.

| Class | Spells (mana) | Release |
|---|---|---|
| Fire Mage | Fireball, 18 damage (25) · Flame Wall, blocks next hit for 4 s (30) · Inferno, 35 damage, slow (60) | push · two-hand push · push |
| Lightning Mage | Bolt, 12 damage, 0.9 s travel (20) · Chain, 3 hits of 7 (35) · Static Field, slows opponent mana regen 5 s (30) | push · push · two-hand push |
| Holy Knight | Holy Light, ×1.5 damage for 6 s (30) · Heal, +25 HP (40) · Judgment, 25-damage sword wave (45) | arm overhead · hands together · push |

**Resources and match:** 100 HP, 100 mana, mana regenerates at 8 per second. One 90 s round.

**Incantations:** Spark writes 3–7 words per spell, themed by class with an Austin or HackTX flavor, and keeps each player's set clearly different from the other's. A match score of 95 or more gives a ×1.15 "perfect incantation" bonus.
