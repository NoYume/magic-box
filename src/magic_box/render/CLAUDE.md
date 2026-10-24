# render

**Owner:** split. `hud.py` + `scenes/` = Adetola; `camera_view.py` + `projectiles.py` = Nikhil; `debug_overlay.py` = Enoch; `window.py` + `layout.py` = Adetola + Nikhil.

Draws the `GameView` and the latest camera frame as layout C (two 960x1080 halves, gold divider).

## Inputs → Outputs
- In: `GameView` (draw only this, never game state), the latest `Frame`, the newest `PlayerState` per slot, fps and dropped-item count.
- Out: pixels, and from `Window.pump()` the pressed key names (`frozenset[str]`) plus a quit flag.

## Hard rules
- **The only package that may import `pygame`** (pygame-ce). Everything else gets keys as plain data.
- Never import `game/` internals; use the `GameView` contract only.
- Never block: 60 fps. If `frame_idx` is unchanged, reuse the last texture.
- Pixel coordinates are the unmirrored left image; mirror only the self-view, at draw time.
- Sizes, margins and colors come from `cfg.render`. Placeholders that still hard-code colors (`hud.py`) must move them to config.
- Each half shows the *opponent*; the self-view shows the viewer. P1 is the left half.

## Files
- `window.py`: `Window` (`pump`, `tick`, `draw`, `close`); picks the scene.
- `layout.py`: layout C geometry (halves, crop and self-view rects).
- `camera_view.py`: opponent crop (8:9, padded, EMA-smoothed), mirrored self-view with skeleton, crop math.
- `hud.py`: placeholder HUD (viewer panel, enemy HP bar).
- `projectiles.py`: spell projectiles flying wrist → viewer, scaled by progress.
- `debug_overlay.py`: debug overlay (toggle `F1`); fps only today.
- `scenes/lobby.py`, `scenes/loading.py`, `scenes/victory.py`: scene placeholders (draw the scene name).

## Test without the Jetson
```
uv run pytest tests/render
uv run python -m magic_box --fake
uv run python -m magic_box --fake --headless --max-ticks 60
```
Tests use the SDL dummy drivers set in `tests/conftest.py`.

## Open TODOs
- `TODO(Nikhil)` `projectiles.py`: `draw_projectiles` raises `NotImplementedError` when a projectile targets a viewer. The placeholder engine never emits projectiles, so `--fake` works today.
- `TODO(Adetola)`: real `hud.py`; real lobby, loading and victory scenes.
- `TODO(Enoch)` `debug_overlay.py`: top-down meters view and `wrist_vz` graph (M3, the depth proof for judges).
