# magic-box

## Arena (hand-sign game)

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

### Docker on the Jetson
The image (`jetson/Dockerfile`) carries the ZED SDK, pyzed and the tracker's packages, so the host
needs only JetPack, the ZED Link driver and Docker. The tracker serves the game page and the camera
stream on one port, so nothing else needs to run:
```bash
docker compose up --build -d arena                       # live ZED X
docker compose --profile fake up --build -d arena-fake   # no camera: synthetic bodies and depth
docker compose logs -f arena
open http://<jetson-ip>:8765/                            # redirects to ?src=zed
docker compose down
```
Only one process can open the ZED X, so stop anything else using it first. The first live run
downloads and optimizes the body-tracking model, which takes a few minutes; the result is kept in
the `zed-resources` volume.

### Debug log (why was that detection iffy?)
Open `http://<jetson-ip>:8765/?src=zed&debug=1&log=1`, or press `L` in the game to start logging
and `B` to mark a bad moment. The tracker writes what the browser saw for each capture (hand
landmarks, sign scores and finger features, depth, rejections, body slots and posture) next to the
ZED skeletons and raw frames, in `logs/<session>/` on the Jetson; a mark also keeps every frame of
the last 10 s. Live views: `/debug/annotated.jpg` (the newest record drawn on its frame),
`/debug/frame.jpg`, `/debug/state.json`. Summarize and render a session:
```bash
python3 jetson/debug_report.py logs/<session> --render --marks   # writes logs/<session>/annotated/
```

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
## Magic Box (voice-driven game)

A 1v1 magic duel on a ZED 2 camera, a Jetson Orin Nano and a monitor. Two players cast spells by speaking an AI-written incantation, then push toward the camera to release them. The defender dodges by stepping aside or ducking, and real distance scales damage. Built at HackTX 2026.

New here? Read `CLAUDE.md` (architecture, contracts, rules) and the `CLAUDE.md` in the folder you work in.

## Laptop quickstart

No camera needed. Python 3.10 and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --extra laptop
uv run python -m magic_box --fake
```

Fake-mode keys (from `config.yaml`):

| Action | P1 | P2 |
|---|---|---|
| Left / right | `a` / `d` | `j` / `l` |
| Closer / farther | `w` / `s` | `i` / `k` |
| Push | `f` | `h` |
| Duck | `c` | `n` |
| Hands up | `r` | `y` |
| Hands together | `t` | `u` |
| Spells (voice fallback, always on) | `1` `2` `3` | `8` `9` `0` |

`F1` toggles the debug overlay. `Esc` quits.

Other commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/check_env.py --laptop`.

## Jetson quickstart

0. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
1. Install the ZED SDK and its Python API (`pyzed`) into the system Python.
2. `sudo apt install libportaudio2`
3. `uv venv --system-site-packages --python /usr/bin/python3`
4. `uv sync` (no `--extra laptop`: the Jetson uses JetPack's OpenCV)
5. `uv run python scripts/check_env.py`
6. `cp .env.example .env` and set `META_MODEL_API_KEY`
7. `uv run --env-file .env python -m magic_box`

From SSH, run `export DISPLAY=:0` first, otherwise pygame finds no video device.

If `import pyzed.sl` fails with a numpy ABI error, change the numpy pin in `pyproject.toml`, run `uv lock`, and commit the lock file (CI uses `--locked`).

Per-machine settings (real mic devices, fullscreen) go in `config.local.yaml`, which is gitignored. See `docs/hardware.md`. From a laptop, `scripts/sync_to_jetson.sh` copies the repo to the Jetson.

## Team

| Person | Role | Owns |
|---|---|---|
| Daniel, Enoch | Planning, repo, Jetson | Repo setup, `scripts/`, `docs/hardware.md` |
| Enoch | Camera and tracking | `perception/`, `render/debug_overlay.py` |
| Nikhil | Data pipeline | `core/`, `pipeline/`, `intent/`, `voice/`, `ai/`, `replay/` |
| Adetola | Game UI and design | `game/`, `render/hud.py`, `render/scenes/`, `docs/game-design.md` |

`render/window.py` and `render/layout.py` are shared by Adetola and Nikhil; `render/camera_view.py` and `render/projectiles.py` are Nikhil's.
