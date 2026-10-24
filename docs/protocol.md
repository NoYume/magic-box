# Tracker → Game protocol

The tracker (`jetson/tracker.py`, or `jetson/fake_tracker.py` for development) runs a WebSocket
server, default `ws://<jetson>:8765`. The ZED does body tracking (posture moves, stable player
slots) and depth; finger-level hand signs run in the browser (MediaPipe) on the streamed frames,
and the depth map gives each hand a distance. Per camera frame the tracker sends a depth map, the
JPEG frame and a `bodies` message, in that order.

## Binary messages
Every binary message starts with a 1-byte type, a reserved byte (0) and the **capture sequence
number** `seq` (u32): one per camera grab, wrapping at 2^32. All integers are little endian.

| Type | Layout | Meaning |
|---|---|---|
| `0x01` | `type`, `reserved`, `seq` (u32), then JPEG bytes | Left ZED view, downscaled to 960 px wide, camera aspect kept (960×600 on a ZED X in SVGA), **not mirrored** |
| `0x02` | `type`, `reserved`, `seq` (u32), `width` (u16), `height` (u16), then `width*height` × u16 | Depth map in **millimeters**, row-major, aligned to the left view. `0` = unknown (occluded, NaN, too close, or beyond `--max-range`) |

### Keeping a capture together
The frame, depth map and `bodies` message of one grab share a `seq`. JPEG decoding in the browser
is async, so the next capture's depth can arrive before a frame is decoded. The game
(`game/src/sources/capture-sync.js`) holds depth and bodies by `seq`, and when frame N finishes
decoding it takes depth N and bodies N and drops everything older. If the browser skips frame N
because it is still decoding, depth N and bodies N are dropped with it.

- The depth map is small (160 px wide, same aspect as the frame: 160×100) so it costs ~32 KB per frame.
- Each depth map is sent just before the frame it belongs to (same `seq`).
- Beyond `--max-range` (default 1.6 m) the ZED reports `+inf`, sent as `0`, so people standing
  behind the players never get a depth and are ignored.

The browser samples depth at hand landmarks: for each palm landmark (wrist and the four knuckles)
it takes the median of the valid pixels in a 3×3 patch, then the median across those landmarks.
If no pixel is valid the hand's depth is **unknown** for that frame: the hand keeps its track and
sign, but it cannot fire a thrust. The game never substitutes a palm-size estimate on the ZED
path, and a hand that has never had a valid depth is ignored, since it may be a bystander beyond range.

## Text messages (JSON)
```json
{ "type": "hello", "frame": [960, 600], "depth": [160, 100] }
```
Sent once when a client connects.

```json
{ "type": "stats", "fps": 29.8 }
```
Camera loop rate, every 5 s.

```json
{ "type": "bodies", "seq": 4182, "t": 1729790000000, "bodies": [
  { "id": 7, "kp": {
    "head": { "x": 0.30, "y": 0.25, "z": 0.88 }, "neck": { "x": 0.30, "y": 0.42, "z": 0.88 },
    "l_shoulder": { "x": 0.39, "y": 0.45, "z": 0.88 }, "r_shoulder": { "x": 0.21, "y": 0.45, "z": 0.88 },
    "l_wrist": { "x": 0.38, "y": 0.70, "z": 0.70 }, "r_wrist": null, "pelvis": null } } ] }
```
ZED `BODY_34` skeletons, one per tracked person (tracking state `OK` only, within `--max-range`).
- `seq` is the capture this skeleton came from (same as its frame and depth map).
- `id` is the ZED tracking id, stable while the person stays tracked.
- `x`, `y` are normalized to the camera image (0..1, **not mirrored**, same space as the frame).
- `z` is the keypoint's distance from the camera in meters.
- A keypoint the ZED could not place is `null` (at a desk the pelvis usually is).
- `l_`/`r_` are the person's own left/right, so a player facing the camera has `l_shoulder` on the
  image's right.

The game seats the nearest valid torso (both shoulders in frame, torso 0.3-1.6 m) in each half of
the mirrored view, and attaches each MediaPipe hand to the body whose wrist is closest.

## Webcam fallback
`?src=webcam` uses the laptop camera with no depth stream. Hand depth is estimated from the
apparent palm size (wrist → middle knuckle), scaled by a per-player factor captured while the
player holds an open palm during calibration. Bodies come from MediaPipe Pose in the browser and
are converted to the same `bodies` schema; torso `z` is estimated from shoulder width. Posture
moves are measured relative to each player's calibrated neutral, so the absolute error does not
matter.
