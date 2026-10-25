# Magic Box

A 1v1 magic duel on a ZED 2 camera, a Jetson Orin Nano and a monitor. Two players cast spells by speaking an AI-written incantation, then push toward the camera to release them. The defender dodges by stepping aside or ducking, and real distance scales damage. Built at HackTX 2026.

The production runtime is the Python application under `src/magic_box/`: three spawned processes, shared-memory camera frames, streamed perception and voice events, pure-Python rules, and a pygame-ce renderer. The browser prototype under `game/` is not part of the console runtime.

New here? Read `CLAUDE.md` (architecture, contracts, rules) and the `CLAUDE.md` in the package you work in.

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

Both players raise their hands to leave the lobby. `F1` toggles the debug overlay and `Esc` quits.

Other commands:

```bash
uv run pytest
uv run ruff check
uv run ruff format --check
uv run python scripts/check_env.py --laptop
```

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

## Architecture

```text
ZED 2 -> perception process -> PlayerState stream + shared-memory frames
mics  -> voice process      -> VoiceEvent stream
                                |
                                v
game process: intent -> pure rules -> GameView -> pygame-ce renderer
                    \-> Spark worker (incantations and chronicle)
```

Only `perception/` imports `pyzed`; only `render/` imports `pygame`. The game loop never waits for camera, voice, disk, or network I/O. See `docs/superpowers/specs/2026-10-24-magic-box-design.md` for the complete design.

## Team

| Person | Role | Owns |
|---|---|---|
| Daniel, Enoch | Planning, repo, Jetson | Repo setup, `scripts/`, `docs/hardware.md` |
| Enoch | Camera and tracking | `perception/`, `render/debug_overlay.py` |
| Nikhil | Data pipeline | `core/`, `pipeline/`, `intent/`, `voice/`, `ai/`, `replay/` |
| Adetola | Game UI and design | `game/`, `render/hud.py`, `render/scenes/`, `docs/game-design.md` |

`render/window.py` and `render/layout.py` are shared by Adetola and Nikhil; `render/camera_view.py` and `render/projectiles.py` are Nikhil's.
