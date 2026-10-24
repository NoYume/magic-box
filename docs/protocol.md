# Tracker → Game protocol

The tracker (`jetson/tracker.py`, or `jetson/fake_tracker.py` for development) runs a WebSocket
server, default `ws://<jetson>:8765`. It streams what the camera sees; hand tracking and sign
recognition run in the browser on those frames, and the depth map gives each hand a distance.

## Binary messages
Every binary message starts with a 1-byte type.

| Type | Layout | Meaning |
|---|---|---|
| `0x01` | `type` + JPEG bytes | Left ZED view, downscaled to 960 px wide, camera aspect kept (960×600 on a ZED X in SVGA), **not mirrored** |
| `0x02` | `type`, `reserved` (u8, 0), `width` (u16 LE), `height` (u16 LE), then `width*height` × u16 LE | Depth map in **millimeters**, row-major, aligned to the left view. `0` = unknown (occluded, NaN, too close, or beyond `--max-range`) |

- The depth map is small (160 px wide, same aspect as the frame: 160×100) so it costs ~32 KB per frame.
- Each depth map is sent just before the frame it belongs to.
- Beyond `--max-range` (default 1.6 m) the ZED reports `+inf`, sent as `0`, so people standing
  behind the players never get a depth and are ignored.

The browser samples depth at hand landmarks: for each palm landmark (wrist and the four knuckles)
it takes the median of the valid pixels in a 3×3 patch, then the median across those landmarks.

## Text messages (JSON)
```json
{ "type": "hello", "frame": [960, 600], "depth": [160, 100] }
```
Sent once when a client connects.

```json
{ "type": "stats", "fps": 29.8 }
```
Camera loop rate, every 5 s.

## Webcam fallback
`?src=webcam` uses the laptop camera with no depth stream. Hand depth is estimated from the
apparent palm size (wrist → middle knuckle), scaled by a per-player factor captured while the
player holds an open palm during calibration.
