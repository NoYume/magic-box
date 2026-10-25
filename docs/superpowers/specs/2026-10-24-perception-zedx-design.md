# Perception on the Jetson and ZED X: design

**Date:** 2026-10-24
**Status:** approved design, pending written-spec review
**Parent spec:** `docs/superpowers/specs/2026-10-24-magic-box-design.md` (this document narrows its §8 `perception/` row, adds the Jetson tools, and replaces its §4 camera row)

## 1. Summary

Fill in the layer that talks to the Jetson and the ZED X camera: open the camera, run body tracking, turn two tracked people into two `PlayerState` streams plus the left camera image, and make that visible and testable. A thin wrapper is the only code that touches `pyzed`; everything after it is plain Python that runs in CI on simulated bodies. The same code runs live, from an SVO recording, inside the tracking benchmark, and in tests.

Casting stays voice first: a player speaks the incantation, then fires the charged spell with one simple gesture, a push toward the camera. Nothing is held or charged with the hands.

## 2. Goals and success criteria

1. On the Jetson, `uv run python scripts/check_env.py` reports the connected ZED X (model, serial) and the `zed_x_daemon` state.
2. `uv run python scripts/bench_tracking.py` with two people in frame prints camera fps, per-stage timings, the share of frames with two people, and GO or NO-GO.
3. `uv run --env-file .env python -m magic_box` on the Jetson shows each opponent's live close-up and each player's mirrored self-view skeleton (milestone M1).
4. `F1` shows the perception overlay: per player tracked or not, distance and zone, pose flags, a live `wrist_vz` graph with the push threshold, a flash on each push, camera fps, and a top-down map in meters.
5. A punch toward the camera produces exactly one `Push`. Walking toward the camera produces none.
6. A camera that fails to open, or a run of failed grabs, is retried inside the perception process without using up the supervisor's restarts.
7. `uv run pytest`, `uv run ruff check` and `uv run ruff format --check` are clean, and every perception module except `zed_source.py` is covered by tests that need no `pyzed`.

## 3. Non-goals

- Game rules, HUD, scenes, intent, voice, AI. They consume `PlayerState` unchanged.
- Finger gestures. `perception/hands.py` stays a stub and the "MediaPipe finger gestures" open decision is closed as **out**.
- Code from the `feature/pipeline-v0` and `feature/handsigns-v1` branches. They are reference only (Appendix A).
- Laptop playback of SVO files. The ZED SDK needs an NVIDIA GPU; laptops keep using `--fake` and, once Nikhil builds it, `--replay`.

## 4. Decisions

| Decision | Choice |
|---|---|
| Camera | **ZED X** over GMSL2 (ZED Link capture card), replacing the ZED 2. GMSL2 is not hot-pluggable: after unplugging, run `sudo systemctl restart zed_x_daemon` or reboot. |
| Play space | Standing, 1–3 m from the camera (unchanged from the parent spec). |
| Structure | **Approach A:** thin SDK wrapper + plain-Python processing. Rejected: passing SDK objects through the logic (untestable off the device, how the beta grew its bugs). |
| Camera mode | `SVGA` 960×600 at 30 fps by default. The benchmark may move it to `HD1200` or `HD1080`. |
| Body format | `BODY_34` with body fitting by default. `BODY_18` and `BODY_38` also work through a name-based keypoint table. |
| Release gesture | A push: the wrist moving toward the camera **relative to the torso**, measured over a short window. |
| Velocities | Computed from positions over a time window (`cam_t`), for both pushes and `root_vx`. ZED's own body velocity is not used, so tests only need positions. |
| Debug overlay | In scope (`render/debug_overlay.py`). |

## 5. Module layout (`src/magic_box/perception/`)

| File | Status | Responsibility |
|---|---|---|
| `raw.py` | new | Plain dataclasses: `RawBody`, `Capture`, `CameraInfo`. No SDK types. |
| `keypoints.py` | new | Documented SDK part-name order per body format, and the map from SDK parts to our `KEYPOINT_NAMES`. Converts SDK keypoint arrays to name → point dicts, dropping invalid points. |
| `kinematics.py` | new | `WindowedVelocity`: velocity and travel of one scalar over the last N seconds of `cam_t`. |
| `zed_source.py` | fill | `ZedSource`: open (live or SVO, optional recording), `grab() -> Capture | None`, `info`, `close`. The only file that imports `pyzed`, inside methods. |
| `bodies.py` | fill | `SlotAssigner`: which tracked body is P1 and which is P2. |
| `motion.py` | fill | `MotionTracker`: `root_vx`. |
| `push.py` | fill | `PushDetector`: the release gesture. |
| `poses.py` | fill | `detect_poses`: `hands_up`, `hands_together`. |
| `tracker.py` | new | `PlayerTracker.step(capture, now) -> list[PlayerState]`: composes the four above plus zones. |
| `process.py` | fill | `run(...)` (supervisor entry, signature unchanged) and a testable `run_loop(...)`. |
| `hands.py` | unchanged | Stub; finger gestures are out. |

`perception/` still never imports `pygame`, `game/` or `render/`.

## 6. Plain data (`raw.py`)

These types stay inside `perception/` (and the scripts); they are not cross-owner contracts.

- `RawBody`: `id: int` (ZED tracking id), `tracking_ok: bool` (tracking state is `OK`), `confidence: float`, `position: Vec3` (ZED body position, meters), `kp3d: dict[str, Vec3]`, `kp2d: dict[str, Px]`, `bbox_px: tuple[int, int, int, int]` (x, y, w, h from the 2D box corners). Keypoint dicts use `KEYPOINT_NAMES` and contain only valid points.
- `Capture`: `frame: Frame`, `bodies: list[RawBody]`. `frame.image` may be a view of SDK memory, valid only until the next `grab()`; the loop writes it to the frame bus right away (the bus copies).
- `CameraInfo`: `model: str`, `serial: int`, `width: int`, `height: int`, `fps: float`, `sdk_version: str`, `source: str` (`"live"` or the SVO path).

## 7. Per-frame processing

`PlayerTracker.step(capture, now)` runs these in order. Every threshold comes from `cfg`.

**7.1 Filter.** Keep bodies with `tracking_ok` and `position` z ≤ `camera.max_range_m`. If more than two remain, keep the two with the smallest z.

**7.2 Assign slots (`SlotAssigner`).**
1. A slot bound to a ZED id keeps it while that id is present.
2. A bound id that disappears keeps its slot for `perception.slot_hold_s`; if it comes back in time it rebinds silently. After that the slot is free.
3. Unbound bodies fill free slots. If both slots are free and two bodies are unbound, the larger image x (`position[0]`) is slot 0 (P1 stands on the players' left, so appears on the image's right). If one body is unbound and both slots are free, x ≥ 0 goes to slot 0, otherwise slot 1. If only one slot is free, the body takes it.
4. A slot that gets a new id starts fresh: its motion, push and pose history is cleared.

**7.3 Root, head, wrists.** `root` = `pelvis` keypoint if valid, else `position`. `head` = `head` keypoint if valid, else `neck`, else `root`. `wrists` holds `"L"` / `"R"` only for valid `l_wrist` / `r_wrist` (the person's own left and right, ZED convention).

**7.4 Motion (`MotionTracker`).** `root_vx` = windowed velocity of root x over `perception.motion_window_s`; 0.0 with fewer than two samples.

**7.5 Push (`PushDetector`), per hand.**
- Signal: `d = wrist_z − neck_z` (falls back to `root` z when `neck` is invalid). A frame with no valid wrist adds no sample for that hand.
- Over the last `perception.push_window_s` of `cam_t`: `v = (d_last − d_first) / (t_last − t_first)` and `travel = d_first − d_last`. With fewer than two samples, `v = 0` and nothing fires.
- **Fires** when the hand is armed, `−v ≥ push_speed_mps`, `travel ≥ push_min_travel_m`, and at least `push_cooldown_s` has passed since this player's last push (either hand).
- After firing, that hand is disarmed until `−v < push_speed_mps × push_rearm_ratio` (the hand slowed or came back). One push gives one event.
- If both hands fire on the same frame, `Push.hand` is the faster one and both are disarmed. A two-hand push is therefore one `Push`; intent recognises it when the other hand's `wrist_vz` crosses `−push_speed_mps` within ~100 ms of the push (`wrist_vz` is published every frame).
- `Push(hand, speed=−v, origin_px=kp2d wrist)`. `wrist_vz[hand] = v` (0.0 without enough samples). Both keys are always present.

**7.6 Poses (`detect_poses(kp3d, perception_cfg)`).** IMAGE coordinates, so +y is down.
- `hands_up`: at least one wrist with `y < head_y − hands_up_margin_m` (one arm overhead counts; Holy Light's "arm overhead").
- `hands_together`: both wrists valid, `|L − R| < hands_together_max_m`, both below the head (`y > head_y`) and above the pelvis when the pelvis is valid.

**7.7 Zone.** `zone_for_distance(root z, perception.zones)` (existing helper in `core/geometry.py`).

**7.8 Publish.** For each bound slot with a body this frame: a full `PlayerState` with `tracking_ok=True`, `player_id` = ZED id, `t = now` (`time.monotonic()`), `cam_t` and `frame_idx` from the capture, `bbox_px` and `keypoints_px` from the body, `finger_gesture = {"L": None, "R": None}`. For a slot with no body this frame that has published before: its last state again with `tracking_ok=False`, `push=None`, `root_vx=0`, `wrist_vz` zeros and fresh `t`, `cam_t`, `frame_idx`, so the screen says STEP INTO VIEW at once instead of after the 200 ms staleness timeout. A slot that has never had a body publishes nothing.

## 8. Camera setup (`ZedSource`)

**Open** (live, or SVO when `camera.svo_path` is set):
- `InitParameters`: `camera_resolution` and `camera_fps` from `camera`; `depth_mode` from `camera.depth_mode`; `coordinate_units = METER`; `coordinate_system = IMAGE`; `depth_maximum_distance = camera.max_range_m` (farther pixels read as unknown, so bystanders drop out); for SVO, `set_from_svo_file(path)` with `svo_real_time_mode = True`.
- Open failure raises `CameraError` with the SDK status and the hint "ZED X not detected? `sudo systemctl restart zed_x_daemon`, or reboot with the camera plugged in."
- The opened resolution must equal `camera.image_width` × `camera.image_height` (the frame bus was sized from them). A mismatch raises `RuntimeError` (fatal, not retried).
- `camera.record_svo` set: `enable_recording(path, H264)`; failure is fatal.
- Positional tracking with `set_as_static = True` (the box doesn't move). Enabled explicitly: SDK 5.3+ otherwise turns on a hidden fallback.
- Body tracking: `enable_tracking = True`, `enable_body_fitting = camera.body_fitting`, `detection_model = camera.body_model`, `body_format = camera.body_format`, `max_range = camera.max_range_m`. Runtime: `detection_confidence_threshold = camera.detection_confidence`.
- `RuntimeParameters.measure3D_reference_frame = CAMERA`, so body positions are in the camera frame.
- The keypoint table in `keypoints.py` is checked against the SDK's `BODY_xx_PARTS` enum values; a mismatch is fatal (the SDK changed its order).
- Logs one line: model, serial, resolution, fps, SDK version, source.

**Grab:** `grab()` returns a `Capture`, or `None` on failure.
- Success test: `status <= SUCCESS` (SDK 5 reports warnings below `SUCCESS`), falling back to `status == SUCCESS` where the enum has no ordering (SDK 4).
- `END_OF_SVOFILE_REACHED`: rewind to frame 0 and return `None` (SVO always loops).
- On success: `retrieve_bodies`, `retrieve_image(LEFT)` (BGRA, native resolution), `cam_t` from the image timestamp in seconds, and a `frame_idx` counter that keeps counting across reopen.

**Keypoint table** (`KEYPOINT_NAMES` ← SDK parts):

| Ours | `BODY_18` | `BODY_34` | `BODY_38` |
|---|---|---|---|
| `head` | `NOSE` | `HEAD` | `NOSE` |
| `neck` | `NECK` | `NECK` | `NECK` |
| `pelvis` | mean of `LEFT_HIP`, `RIGHT_HIP` | `PELVIS` | `PELVIS` |
| `l_/r_shoulder` | `LEFT_/RIGHT_SHOULDER` | same | same |
| `l_/r_wrist` | `LEFT_/RIGHT_WRIST` | same | same |
| `l_/r_ankle` | `LEFT_/RIGHT_ANKLE` | same | same |

A point is invalid if any coordinate is NaN or infinite, or its 2D position is negative. A mean is valid only if all its parts are.

## 9. Perception loop and failures (`process.py`)

`run(cfg, state_q, frame_bus_name, stop)` attaches the frame bus, builds `ZedSource` and `PlayerTracker`, calls `run_loop`, and closes the camera and bus in `finally`.

`run_loop(source, tracker, write_frame, put_state, stop, cfg, clock, log)`:

| Situation | Behavior |
|---|---|
| Camera not open | Try `open()`. `CameraError` → log, `stop.wait(perception.open_retry_s)`, try again. |
| `grab()` returns `None` | Count it. After `perception.max_grab_failures` in a row, close and reopen. |
| `grab()` returns a capture | Reset the count, `write_frame(capture.frame)`, then `put_state` for each `PlayerState` from `tracker.step(capture, clock())`. |
| Any other exception | Propagates; the process exits and the supervisor restarts it. |
| `stop` set | Leave the loop within one grab. |

Every `perception.stats_every_s` it logs camera fps, bodies seen and the ids bound to P1 and P2. Logs go to stderr prefixed `perception:`.

## 10. Debug overlay (`render/debug_overlay.py`)

`draw_debug_overlay(...)` becomes `DebugOverlay(cfg)` with `draw(surface, states, fps, dropped)`. `render/window.py` builds it once and calls it while `F1` is on.

- **Header:** render fps, camera fps (from `frame_idx` and `cam_t` of the states it has seen), dropped-item count.
- **One panel per half**, for the player shown there: P1/P2, ZED id, TRACKED or LOST, distance (root z) and zone, pose flags, and a graph of `wrist_vz` L and R over the last `graph_s` seconds with a line at `−push_speed_mps`. A push flashes "PUSH R 2.3 m/s" for `push_flash_s`.
- **Top-down map:** x from −`topdown_x_m` to +`topdown_x_m`, z from 0 to `topdown_z_m`, camera at the bottom, zone bands from `perception.zones`, a dot per tracked player.
- History is recorded once per new `frame_idx`. The game loop keeps only the newest state per slot per tick; at a 30 fps camera and a 60 fps render that is almost always every state.
- Sizes, ranges and colors live in `render.debug_overlay` in `config.yaml`. The history and fps math are plain functions, tested without drawing; one headless test draws the overlay.

## 11. Jetson tools (`scripts/`)

- **`check_env.py`** gains Jetson-only checks: `zed_camera` (required: `sl.Camera.get_device_list()` finds a camera; fails if none, or if its model is not `camera.model`), and `zed_x_daemon` (`systemctl is-active zed_x_daemon`, not required).
- **`bench_tracking.py`** runs `ZedSource` + `PlayerTracker` for `--seconds` (flags `--body-format`, `--resolution`, `--svo` override config). Per frame it records grab-and-retrieve ms, tracker ms, bodies after filtering, and slots bound. It prints frames, fps, p50/p95 per stage, the share of frames with two bodies, and **GO** when fps ≥ `--min-fps` (default 25) and the two-body share ≥ `--min-two` (default 0.9), else **NO-GO** with the failing number. The summary is a plain function with tests.
- **`record_session.py`** records an SVO2 from the ZED X for `--seconds` to `--out` (default `recordings/session-YYYYmmdd-HHMMSS.svo2`). Replaying it through perception on the Jetson is `camera.svo_path` in `config.local.yaml`. The JSON-lines `--record` stays Nikhil's.

## 12. Config changes (`config.yaml`)

```yaml
camera:             # owner: Enoch
  model: ZED_X                # check_env compares the connected camera's model
  resolution: SVGA            # ZED X: SVGA (960x600) | HD1080 | HD1200
  image_width: 960
  image_height: 600
  fps: 30
  depth_mode: PERFORMANCE
  body_format: BODY_34        # BODY_18 | BODY_34 | BODY_38
  body_model: HUMAN_BODY_FAST
  body_fitting: true
  detection_confidence: 40
  max_range_m: 3.5            # (guess) depth and bodies beyond this are ignored
  svo_path: null              # play this .svo2 instead of the live camera (Jetson only)
  record_svo: null            # record the live camera to this .svo2 path

perception:         # owner: Enoch
  push_speed_mps: 1.5         # (guess) wrist speed toward the camera, relative to the neck
  push_min_travel_m: 0.12     # (guess) wrist travel toward the camera within the window
  push_window_s: 0.15         # (guess)
  push_rearm_ratio: 0.35      # (guess) re-arm once speed drops below this share of push_speed_mps
  push_cooldown_s: 0.4        # (guess)
  motion_window_s: 0.2        # (guess)
  slot_hold_s: 1.0            # (guess) a lost body keeps its slot this long
  hands_up_margin_m: 0.10     # (guess) wrist above the head by this much
  hands_together_max_m: 0.25  # (guess) wrists closer than this
  open_retry_s: 2.0
  max_grab_failures: 30
  stats_every_s: 5.0
  zones: {danger_max_m: 1.6, far_min_m: 2.4}   # unchanged

render:
  debug_overlay:    # owner: Enoch
    graph_s: 3.0
    vz_range_mps: 4.0
    push_flash_s: 0.3
    topdown_x_m: 2.0
    topdown_z_m: 4.0
    # plus panel, text, P1, P2 and threshold colors as RGB lists
```

`perception.wrist_vz_smoothing` is removed (the window replaces it). `fake.focal_px` goes from 700 to 525 so fake mode looks the same at 960×600.

`core/config.py` validation gains: `camera.resolution` must be a known mode and `image_width` × `image_height` must match it (`HD2K` 2208×1242, `HD1200` 1920×1200, `HD1080` 1920×1080, `HD720` 1280×720, `SVGA` 960×600, `VGA` 672×376), and `camera.body_format` must be one of the three formats.

## 13. Contract notes (types unchanged; heads-up to Nikhil and Adetola)

- `PlayerState.wrist_vz` is the wrist's velocity **relative to the neck** (m/s, negative toward the camera), the same signal pushes fire on. `Push.speed` is that speed as a positive number.
- `wrists` and `keypoints_px` contain only valid points; read them with `.get()`. `wrist_vz` always has both `"L"` and `"R"`.
- A two-hand push arrives as one `Push` (the faster hand). Intent recognises it when the other hand's `wrist_vz` crosses `−push_speed_mps` within ~100 ms of the push (`wrist_vz` is published every frame).
- `player_id` is the ZED tracking id.
- A player who leaves is republished at once with `tracking_ok=False` (§7.8).

These go into the root `CLAUDE.md` contracts section and the `contracts.py` field comments in the same change.

## 14. Testing

All of the following run on a laptop and in CI, with no `pyzed`:

- `tests/perception/fakes.py`: builds `RawBody`s from a simple standing-body model (position, duck, arm poses, wrist offsets) and a `FakeSource` that replays a scripted list of captures, `None`s and `CameraError`s.
- `keypoints`: every format maps every `KEYPOINT_NAMES` entry; NaN, infinite and negative-2D points are dropped; the `BODY_18` pelvis is the hip mean and invalid if a hip is.
- `kinematics`: velocity and travel over the window; fewer than two samples gives zero.
- `bodies`: two new bodies bind by x; ids stick when players cross the middle; a lost id rebinds within `slot_hold_s` and frees after it; a third, farther body is ignored; one free slot takes the newcomer.
- `push`: a fast relative push fires once; a slow one does not; a whole-body walk toward the camera does not; no re-fire until re-armed; cooldown across hands; both hands on one frame gives the faster hand; a missing neck falls back to root.
- `poses`, `zone`, and `PlayerTracker`: field values, history cleared on rebinding, the republish-on-loss rule.
- `run_loop`: retries open after `CameraError`, reopens after `max_grab_failures`, writes the frame before the states, stops when `stop` is set.
- Config validation for resolution/size and body format; existing tests that hard-code 1280×720 read the config instead.
- `debug_overlay`: history and camera-fps helpers; a headless draw with tracked and lost players.
- `bench_tracking` summary and verdict; `record_session` and `check_env` argument handling.
- `test_boundaries.py` keeps `pyzed` inside `perception/` and module-level imports banned.

On the Jetson, in order: `check_env.py` → `bench_tracking.py` with two people → `MAGIC_BOX_STRESS=1 uv run pytest tests/pipeline/test_frame_bus.py` → `python -m magic_box` with `F1`.

## 15. Docs to update

- Root `CLAUDE.md`: ZED X in "What this is", "Why ZED + Jetson", the hardware table and the diagram (`ZED X ──GMSL2──▶`); `wrist_vz` and the other contract notes; risks (GMSL not hot-pluggable, SVGA crop upscaling); open decisions (body format defaults to `BODY_34`; finger gestures closed as out); commands (`bench_tracking.py`, `record_session.py`, `camera.svo_path`).
- Parent spec §4: the camera row becomes ZED X, pointing here.
- `README.md`: ZED X in the intro; Jetson quickstart adds the ZED X driver and `zed_x_daemon`.
- `docs/hardware.md`: ZED X row and mounting; troubleshooting (`systemctl restart zed_x_daemon`, `sudo dmesg | grep zedx`, `ZED_Diagnostic`, never re-plug GMSL while running).
- `src/magic_box/perception/CLAUDE.md`: rewritten for the new files and rules. `render/CLAUDE.md`: the overlay line.
- `docs/game-design.md`: the `BODY_18` question points to the `BODY_34` default.

## 16. Risks

- **Push thresholds are guesses.** Tune with the overlay's `wrist_vz` graph and SVO replays on the Jetson.
- **A lunge moves the torso with the hand,** so a relative push reads slower than the absolute one. Players punch, they rarely lunge; revisit if testing says otherwise.
- **Orin Nano fps** at SVGA with `BODY_34` and two people: the beta ran this mode, but no fps was recorded. The benchmark is the go/no-go; fallbacks are `BODY_18` and fitting off.
- **GMSL2 is not hot-pluggable.** Reopening covers transient grab errors only; a physical re-plug needs the daemon restart, which the open-failure log tells you.
- **SDK 4 vs 5 differences** (warning codes, enum ordering) are handled by the grab success test and the keypoint table check.
- **`zed_source.py` is untested in CI.** It is kept thin, and the benchmark exercises it on the device.

## Appendix A: what the beta branches taught us

Taken (as ideas, rewritten to this design):
- ZED setup that worked on the Orin Nano: `HUMAN_BODY_FAST`, static positional tracking, `depth_maximum_distance` and body `max_range` as the bystander cut, grab warnings counted as success, SVO record and replay.
- Push detection needs both speed and travel over a ~150–200 ms window, plus a re-arm ratio so one motion cannot fire twice.
- Sticky slots: a body keeps its player while tracked, instead of re-sorting by side every frame.
- Time-based math on `cam_t`, so behavior does not depend on frame rate.

Rejected:
- The WebSocket/JPEG transport and the browser game (the repo is all Python, pygame, shared memory).
- MediaPipe finger signs and held-sign "confirm" and "gather" charging (buggy and unintuitive; casting is voice first).
- Seated desk scale (0.5–1.2 m, 1.6 m range) and lean stances.
- Its UI.
