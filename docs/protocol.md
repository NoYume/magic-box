# Tracker → Game protocol

The tracker (`jetson/tracker.py`) runs a WebSocket server, default `ws://<jetson>:8765`.

## Binary messages
Each binary message is one JPEG camera frame (left ZED view, downscaled, **not mirrored**).

## Text messages (JSON)
```json
{
  "type": "bodies",
  "t": 1729790000123,
  "bodies": [
    {
      "id": 3,
      "kp": {
        "head":       { "x": 0.51, "y": 0.18, "z": 2.10 },
        "neck":       { "x": 0.50, "y": 0.27, "z": 2.12 },
        "l_shoulder": { "x": 0.45, "y": 0.29, "z": 2.13 },
        "r_shoulder": { "x": 0.56, "y": 0.29, "z": 2.13 },
        "l_wrist":    { "x": 0.40, "y": 0.45, "z": 1.80 },
        "r_wrist":    { "x": 0.61, "y": 0.47, "z": 2.05 },
        "pelvis":     { "x": 0.50, "y": 0.55, "z": 2.15 }
      }
    }
  ]
}
```
- `x`, `y`: normalized image coordinates (0–1, origin top-left, un-mirrored).
- `z`: distance from the camera in **meters** (smaller = closer).
- A keypoint the tracker could not see is `null`.
- `id`: tracker-assigned id, stable while the person stays tracked.

The webcam fallback (`game/src/sources.js`) produces the same shape. Its `z` is *estimated* from shoulder width, so it is rougher.
