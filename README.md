# magic-box

**Arena: a pocket AR battle console (HackTX 26).**

A game console in a box: a Jetson Orin Nano + ZED X tracks your body in 3D. Plug it into any screen and fight your friends with your body and voice. No controllers.

- Step **toward** the camera to charge a heavy attack. Step **back** to raise a shield.
- **Thrust a hand** at the screen to fire a bolt (faster push = faster, harder bolt).
- **Both hands up** to heal.
- Voice spells (Muse Voice Transcribe) are next. For now, keys `1 2 3` (P1) and `8 9 0` (P2) cast fireball / lightning / frost. Press `R` to reset.

## Layout
| Path | What |
|---|---|
| `jetson/tracker.py` | ZED X body tracking → WebSocket (skeleton JSON + JPEG frames). Runs on the Jetson. |
| `jetson/fake_tracker.py` | Synthetic 2-player tracker so the game can be built without hardware |
| `game/` | Browser game (PixiJS, no build step): gestures, rules, renderer |
| `docs/protocol.md` | Tracker → game message format |
| `HACKTX_2026.md` | Event research, Meta rules, idea board, plan |

## Run
```bash
# Game (any laptop)
cd game && npm run dev               # http://localhost:5173

# A) laptop webcam fallback
open http://localhost:5173/?src=webcam

# B) fake tracker (no hardware)
cd jetson && py fake_tracker.py      # (python3 on Mac/Linux)
open http://localhost:5173/?src=zed&ws=ws://localhost:8765

# C) real ZED X on the Jetson
python3 /usr/local/zed/get_python_api.py && pip install -r jetson/requirements.txt
python3 jetson/tracker.py --record session.svo2
open http://<jetson-ip>:5173/?src=zed&ws=ws://<jetson-ip>:8765
```

## Test
```bash
cd game && npm test
```
