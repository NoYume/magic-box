# perception

**Owner:** Enoch

Turns the ZED X stream into `PlayerState`s and camera frames. Runs in its own process.

## Inputs → Outputs
- In: the ZED X (live over GMSL2, or an SVO2 file via `camera.svo_path`), settings from `camera` and `perception` in `config.yaml`.
- Out: up to two `PlayerState`s per camera frame (one per slot) on the state stream; the left image as a `Frame` on the shared-memory frame bus. A slot that has never been seen publishes nothing.
- `push` is set only on the frame a push is detected. One push gives one event: a cooldown and a re-arm (`push_rearm_ratio`) stop repeats.
- `pose_flags` are continuous. `zone` uses `perception.zones`.
- The push is measured on the wrist relative to the neck (the root when there is no neck), so walking toward the camera does not fire it. A two-hand push arrives as one `Push` (the faster hand). Intent recognises it when the other hand's `wrist_vz` crosses `-push_speed_mps` within ~100 ms of the push (`wrist_vz` is published every frame).
- `Push.speed` is the window-average speed at the moment the push threshold is crossed. For most punches that is just above `push_speed_mps` (about 1.5-1.7 m/s), not the punch's peak speed. Whether to report peak speed instead is an open decision for Adetola (game balance) and Enoch.
- A player who leaves is republished at once with `tracking_ok=False`, the last pose flags and zone, `push=None`, `root_vx=0` and zero `wrist_vz`. Intent must gate on `tracking_ok`.
- `wrists` and `keypoints_px` hold only valid points. `wrist_vz` always has `"L"` and `"R"`.

## Hard rules
- **`zed_source.py` is the only file that imports `pyzed`**, and only inside functions (never at module top level). Same for `cv2`. All SDK calls stay in that file, so tests swap in `tests/perception/fake_sl.py`.
- Never import `pygame`. Never touch `game/` or `render/`.
- ZED settings: `UNIT.METER`, `COORDINATE_SYSTEM.IMAGE`. Motion toward the camera has negative velocity; `Push.speed` is a positive number.
- **`wrist_vz` is the wrist's velocity relative to the neck**, in m/s, negative toward the camera. It is not the wrist's velocity in the camera frame.
- **Velocities, windows and the slot hold use `cam_t`** (the ZED image timestamp), never `time.monotonic()`. `PlayerState.t` is `time.monotonic()` at publish. A `cam_t` that goes backwards (a looping SVO) clears the windows.
- A neck that flickers in and out only clears the speed windows (the reference changed). It does not re-arm a push or reset the cooldown.
- Slots: slot 0 (P1) is image-right, so root x > 0. Keep tracked bodies within `camera.max_range_m`, and the 2 closest if there are more. A slot keeps its ZED id for `perception.slot_hold_s` after it disappears.
- The camera opens with retries every `perception.open_retry_s`. After `perception.max_grab_failures` failed grabs in a row it is closed and reopened. SDK 5 warning codes count as a successful grab. Each open reuses one image buffer.
- Every threshold comes from `cfg`. Numbers marked "(guess)" need tuning on recordings.
- Publish through the stream/frame bus APIs in `pipeline/`. Never block on a full queue.

## Files
- `raw.py`: `RawBody`, `Capture`, `CameraInfo`, the plain types between the camera layer and the logic.
- `keypoints.py`: maps `BODY_18`, `BODY_34` and `BODY_38` keypoints to our names; drops NaN, infinite and negative-2D points.
- `kinematics.py`: `WindowedVelocity`, velocity and travel over a time window.
- `bodies.py`: `filter_bodies` (range and the 2 closest) and `SlotAssigner` (bodies to slots 0 and 1).
- `motion.py`: `MotionTracker`, `root_vx`.
- `push.py`: `PushDetector`, wrist speed relative to the neck with cooldown and re-arm. `clear_windows()` drops the speed history only; `reset()` also re-arms and clears the cooldown (a new body in the slot).
- `poses.py`: pose flags (`hands_up`, `hands_together`, and the forward-wrist `guard`) from keypoints.
- `tracker.py`: `PlayerTracker.step(capture, now)` makes the `PlayerState`s (slots, root, head, wrists, push, poses, zone).
- `zed_source.py`: `ZedSource` opens the camera (live or SVO), grabs frames and bodies. `CameraError` marks a failed open worth retrying.
- `process.py`: `run` (the entry point the supervisor spawns) and `run_loop` (open, grab, write the frame, publish the states, log stats).
- `hands.py`: finger gestures. Out; it stays a stub.

## Test without the Jetson
`pyzed` is not available on a laptop. The tests use `tests/perception/fakes.py` (simulated bodies and a `FakeSource`) and `tests/perception/fake_sl.py` (a fake `pyzed.sl` module for `ZedSource`).
```
uv run pytest tests/perception
uv run python -m magic_box --fake
```
`--fake` shows the rest of the app with keyboard players. Live mode on a laptop exits the perception process with "pyzed is not installed ... use --fake on a laptop", and the window shows STEP INTO VIEW.

On the Jetson:
- `uv run python scripts/check_env.py` checks `pyzed.sl`, the `zed_camera` and the `zed_x_daemon`.
- `uv run python scripts/bench_tracking.py` prints GO or NO-GO for two-person tracking.
- `uv run python scripts/record_session.py --seconds 60` keeps an SVO2 in `recordings/`. Replay it with `camera.svo_path` in `config.local.yaml`.
- `F1` shows the debug overlay (`render/debug_overlay.py`) with the `wrist_vz` graph and the top-down map.

## Open TODOs
- Tune the "(guess)" values in `perception:` on the device with the overlay and SVO replays.
- Confirm the body format (default `BODY_34`) and the camera resolution (default SVGA) with `bench_tracking.py`.
- `hands.py` stays a stub: finger gestures are out.
