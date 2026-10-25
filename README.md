# magic-box

A 1v1 magic duel console built from a ZED X stereo camera, a Jetson Orin Nano and a monitor. Two players stand side by side. Each one speaks an incantation into their own clip-on mic to charge a spell, then pushes toward the camera to throw it. The defender dodges by stepping aside or ducking. Real distance to the camera scales damage. Built at HackTX 2026.

New here? Read `CLAUDE.md` (architecture, contracts, rules) and the `CLAUDE.md` in the folder you work in. The Jetson session is `docs/runbook.md`.

## How a match goes

1. **Boot:** a self-check of the camera, both mics, the network and the API key.
2. **Lobby:** each player says their name ("my name is Ada") and a class: `fire`, `lightning` or `holy` (`knight` works too). Both hold their hands up to start.
3. **Loading:** Muse Spark writes each player's incantations. Each half shows them as a tutorial card.
4. **Fight:** 90 s. Say an incantation, then release it: a push for attacks, a two-hand push for some spells, one arm overhead or hands together for the Holy Knight's buffs. A push with nothing charged is a basic attack.
5. **Victory:** the winner, match stats and a Duel Chronicle written by Muse Spark.

Each player watches their own half of a split screen, which shows a live close-up of the opponent.

| Class | Spells |
|---|---|
| Fire Mage | Fireball, Flame Wall (blocks the next hit), Inferno (slows the next charge) |
| Lightning Mage | Bolt, Chain (3 bolts, each needs its own dodge), Static Field (slows mana regen) |
| Holy Knight | Holy Light (×1.5 damage for 6 s), Heal (+25 HP), Judgment |

## Why a ZED X and a Jetson

- **Depth is the game.** Push speed is measured in m/s toward the camera, dodges in meters of sidestep or duck, and damage scales with each player's real distance. A webcam can't measure any of that.
- **Two skeletons with IDs** come from the ZED SDK's body tracking, so there is no hand-rolled pose model.
- **One box.** The camera, tracking, game and rendering all run on the Jetson, with no laptop in the loop. Only speech-to-text (Muse Voice Transcribe) and text generation (Muse Spark) go to Meta's cloud. Video never leaves the box.
- **The proof is on screen.** `F1` shows a top-down map in meters and each player's wrist speed graph against the push threshold.

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
| Two-hand push | `v` | `m` |
| Guard (Holy Knight parry) | `g` | `o` |
| Spells (voice fallback, always on) | `1` `2` `3` | `8` `9` `0` |

`F1` toggles the debug overlay. `Esc` quits.

Boot moves on after 2 s. In the lobby both players hold their hands up (`r` + `y`) for 0.3 s to start. The keyboard can't speak, so fake mode keeps the default classes (P1 Fire Mage, P2 Holy Knight). With a `.env` holding `META_MODEL_API_KEY`, `uv run --env-file .env python -m magic_box --fake` also calls Muse Spark for the incantations and the chronicle.

Other commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/check_env.py --laptop`, and `uv run --env-file .env python scripts/check_spark.py` (live Spark check).

## Jetson quickstart

0. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
1. Install the ZED SDK, the ZED X driver (for the ZED Link capture card) and the Python API (`pyzed`) into the system Python. Check that the camera daemon runs: `systemctl is-active zed_x_daemon`.
2. `sudo apt install libportaudio2`
3. `uv venv --system-site-packages --python /usr/bin/python3`
4. `uv sync` (no `--extra laptop`: the Jetson uses JetPack's OpenCV)
5. `cp .env.example .env` and set `META_MODEL_API_KEY` in it with an editor
6. `uv run --env-file .env python scripts/check_env.py --network`, then `uv run python scripts/bench_tracking.py` with two people standing 1 to 3 m away. It prints GO or NO-GO.
7. `scripts/run_demo.sh`: fullscreen, live camera and mics, records each run to `recordings/`, restarts on a crash. Or run the game directly: `uv run --env-file .env python -m magic_box --fullscreen`.

From SSH, run `export DISPLAY=:0` first, otherwise pygame finds no video device.

Never re-plug the ZED X while the Jetson is on (GMSL2 is not hot-pluggable). After a re-plug, run `sudo systemctl restart zed_x_daemon` or reboot.

If `import pyzed.sl` fails with a numpy ABI error, change the numpy pin in `pyproject.toml`, run `uv lock`, and commit the lock file (CI uses `--locked`).

Per-machine settings (real mic devices, camera fallbacks) go in `config.local.yaml`, which is gitignored. See `docs/hardware.md` and `docs/runbook.md`. From a laptop, `scripts/sync_to_jetson.sh` copies the repo to the Jetson.

## Docs

| File | What |
|---|---|
| `CLAUDE.md` | Architecture, contracts, conventions, commands |
| `docs/runbook.md` | The Jetson hardware session: checks, tuning, bug bash |
| `docs/hardware.md` | Parts, mic routing, camera placement, ZED X troubleshooting |
| `docs/game-design.md` | Classes, spells, numbers and scene flow |
| `docs/submission.md` | Devpost draft and demo video shot list |

## Team

| Person | Role | Owns |
|---|---|---|
| Daniel | Planning, repo, Jetson | Repo setup, `scripts/` (with Enoch), `docs/hardware.md` (with Enoch), `docs/runbook.md` |
| Enoch | Camera and tracking | `perception/`, `render/debug_overlay.py` |
| Nikhil | Data pipeline | `core/`, `pipeline/`, `intent/`, `voice/`, `ai/`, `replay/` |
| Adetola | Game UI and design | `game/`, `render/hud.py`, `render/scenes/`, `docs/game-design.md` |

`render/window.py` and `render/layout.py` are shared by Adetola and Nikhil; `render/camera_view.py` and `render/projectiles.py` are Nikhil's.
