# magic-box

**Arena: a hand-sign spellcasting duel in a box (HackTX 26).**

A Jetson Orin Nano + ZED X stereo camera sits in a box facing two players side by side at a
desk. Plug it into any screen. You fight with **finger hand signs** (MediaPipe in the browser)
and **body moves** (ZED body tracking): signs cast, the body focuses, braces and dodges.
No controllers.

## How to play
Raise an open palm to join; hold it for a second while the game reads your hand and posture.
Best of three rounds.

| Hand sign | How | Effect |
|---|---|---|
| Ward | Open palm to the screen | Hand-sized ward at your palm, blocks while held, drains mana |
| Gather | Fist, hold | Charges your next spell (rising tone) |
| Bolt | Index + middle together, then **thrust toward the screen** | Fires a bolt; gather charge and thrust speed empower it |
| Ultimate | Two-hand diamond, held 1 s at full charge | Heavy violet blast, long cooldown |

| Body move | How | Effect |
|---|---|---|
| Focus | Lean in toward the screen | Gather charges twice as fast |
| Brace | Lean back and hold | 40% less damage from hits |
| Dodge | Quick sideways sway | Bolts landing in the next 450 ms miss (not the ultimate); 2.5 s cooldown |

Body moves never deal damage on their own. Every sign is held through a short confirm fill
before it counts, and posture moves are measured against your calibrated neutral, so casual
sway does nothing.

Keys: `D` debug overlay (landmarks, skeletons, FPS, thresholds), `M` mute, `R` reset (dev).
Voice hook: `window.arena.castIncantation(slot, 'bolt' | 'ward' | 'gather' | 'ultimate', intensity)`.

## Layout
| Path | What |
|---|---|
| `jetson/tracker.py` | ZED X: body skeletons (JSON) + JPEG frames + mm depth map over WebSocket. Runs on the Jetson |
| `jetson/fake_tracker.py` | Same wire format with synthetic bodies, frames and depth, no hardware |
| `game/src/vision/` | Camera-to-screen transform, hand-sign classifier, depth sampling, hand and body rosters, posture |
| `game/src/game/` | Cast state machine, combat rules, round flow, match orchestrator (all pure, unit tested) |
| `game/src/sources/` | ZED, webcam (MediaPipe hands + pose) and scripted demo sources |
| `game/src/render/`, `ui/`, `audio/` | PixiJS effects, HUD and screens, WebAudio SFX |
| `docs/protocol.md` | Tracker → game message format |

## Run
```bash
cd game && npm run dev                 # http://localhost:5173

# Scripted demo: two bots play the whole loop, no camera needed
open http://localhost:5173/?src=demo

# Laptop webcam (hands + MediaPipe Pose, depth estimated)
open http://localhost:5173/?src=webcam

# Fake tracker (transport, bodies, depth; no hand signs in the drawn frames)
cd jetson && py fake_tracker.py        # python3 on Mac/Linux
open "http://localhost:5173/?src=zed&ws=ws://localhost:8765"

# Real ZED X on the Jetson
python3 /usr/local/zed/get_python_api.py && pip install -r jetson/requirements.txt
python3 jetson/tracker.py --max-range 1.6 --record session.svo2
open "http://<jetson-ip>:5173/?src=zed&ws=ws://<jetson-ip>:8765"
```
For a kiosk, start Chrome with `--autoplay-policy=no-user-gesture-required` so sound plays
without a click.

## Tuning on the real rig
| What | Where |
|---|---|
| Sign thresholds (finger bend, palm facing, sword gap, min score) | `game/src/vision/tuning.js` `SIGN` |
| Play depth, palm size, webcam focal | `game/src/vision/tuning.js` `DEPTH` |
| Thrust speed / travel / window | `game/src/vision/tuning.js` `THRUST` |
| Lean in / back distance, hold, dodge shift, play depth for bodies | `game/src/vision/tuning.js` `BODY` |
| Confirm times, damage, cooldowns, round length | `game/src/game/balance.js` |
| Body move effects (focus, brace, evade window) | `game/src/game/balance.js` `BODY_MOVES` |
| Bystander cut-off | `jetson/tracker.py --max-range` |

## Test
```bash
cd game && npm test                    # node --test, no dependencies
py -m py_compile jetson/*.py
```
