# magic-box

A 1v1 magic duel on a ZED X camera, a Jetson Orin Nano and a monitor. Two players cast spells by speaking an AI-written incantation, then push toward the camera to release them. The defender dodges by stepping aside or ducking, and real distance scales damage. Built at HackTX 2026.

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
| Two-hand push | `v` | `m` |
| Spells (voice fallback, always on) | `1` `2` `3` | `8` `9` `0` |

`F1` toggles the debug overlay. `Esc` quits.

A match starts when both players raise their hands in the lobby (`r` + `y` in fake mode).

Other commands: `uv run pytest`, `uv run ruff check`, `uv run python scripts/check_env.py --laptop`.

## Jetson quickstart

0. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
1. Install the ZED SDK, the ZED X driver (for the ZED Link capture card) and the Python API (`pyzed`) into the system Python. Check that the camera daemon runs: `systemctl is-active zed_x_daemon`.
2. `sudo apt install libportaudio2`
3. `uv venv --system-site-packages --python /usr/bin/python3`
4. `uv sync` (no `--extra laptop`: the Jetson uses JetPack's OpenCV)
5. `uv run python scripts/check_env.py`, then `uv run python scripts/bench_tracking.py` with two people standing 1 to 3 m away. It prints GO or NO-GO.
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
