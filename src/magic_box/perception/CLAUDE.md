# perception

**Owner:** Enoch

Turns the ZED 2 stream into `PlayerState`s and camera frames. Runs in its own process.

## Inputs → Outputs
- In: ZED 2 (live or an SVO file), settings from `camera` and `perception` in `config.yaml`.
- Out: two `PlayerState`s per camera frame (one per slot) on the state stream; the left image as a `Frame` on the shared-memory frame bus.
- `push` is set only on the frame a push is detected. `pose_flags` are continuous. `zone` uses `perception.zones`.

## Hard rules
- **The only package that may import `pyzed`**, and only inside functions (never at module top level). Same for `cv2`.
- Never import `pygame`. Never touch `game/` or `render/`.
- ZED settings: `UNIT.METER`, `COORDINATE_SYSTEM.IMAGE`. Motion toward the camera has negative `vz`; `Push.speed` is a positive number.
- Slots: bind bodies by x position; slot 0 (P1) is image-right, so root x > 0. Keep the 2 closest bodies within `camera.max_range_m`. Re-bind by side after a loss.
- Stamp `t = time.monotonic()` at publish and `cam_t` from the ZED image timestamp.
- Every threshold comes from `cfg`. Numbers marked "(guess)" need tuning on recordings.
- Publish through the stream/frame bus APIs in `pipeline/`. Never block on a full queue.

## Files
- `process.py`: the perception process loop (entry point the supervisor spawns).
- `zed_source.py`: opens the camera (live or SVO), grabs frames and bodies.
- `bodies.py`: assigns tracked bodies to slots 0 and 1.
- `push.py`: smoothed wrist-Z velocity push detector with cooldown.
- `poses.py`: pose flags (`hands_up`, `hands_together`) from keypoints.
- `motion.py`: `root_vx` and head tracking.
- `hands.py`: optional finger gestures (MediaPipe; cut first if time is short).

## Test without the Jetson
`pyzed` is not available on a laptop, so test the pure logic with synthetic keypoints and states (put tests in `tests/perception/`, which does not exist yet). To see the rest of the app, run the fake source:
```
uv run python -m magic_box --fake
```
On the Jetson: `uv run python scripts/check_env.py` confirms `pyzed.sl` imports inside the venv.

## Open TODOs
- Validate the ZED adapter, body-part mappings and thresholds against the installed SDK and recordings.
- Run `scripts/bench_tracking.py` for the two-person fps go/no-go.
- Decide the body model and camera resolution after that benchmark.
- `hands.py` remains the optional, cut-first finger-gesture stub.
