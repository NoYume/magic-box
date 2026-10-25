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
- `hud.py`: placeholder HUD (viewer panel with name, MIC OK / MIC OFF, distance and zone, HP and mana bars, spell lines with the incantation or the release cue; enemy HP bar). `release_cue` turns `SpellView.release` into text.
- `projectiles.py`: spell projectiles from `GameView` flying from the attacker's wrist toward the viewer, scaled by progress.
- `debug_overlay.py`: perception overlay (toggle `F1`). A header with render fps, camera fps and the dropped count. A panel per half for the player shown there: tracked or lost, distance and zone, pose flags, a `wrist_vz` graph with the push threshold line, and a flash on a push. A top-down map in meters below the panels, mirrored like the players' view.
- `scenes/`: `__init__.py` (`draw_scene` dispatches on `GameView.scene`; text lines, `wrap_text`, fonts and colors from `render.scenes` config), `lobby.py` (title and each player's TRACKED / STEP INTO VIEW), `loading.py` (a card per player with incantations and release cues, plus the countdown), `victory.py` (the chronicle under the center banner). All plain-text placeholders.

## Test without the Jetson
```
uv run pytest tests/render
uv run python -m magic_box --fake
uv run python -m magic_box --fake --headless --max-ticks 60
```
Tests use the SDL dummy drivers set in `tests/conftest.py`.

## Open TODOs
- `TODO(Adetola)`: real `hud.py`; real lobby, loading and victory scenes (the current ones are plain text), a boot scene, and the class-pick screen.
- `hud.py` still hard-codes colors; they move to `cfg.render` with the real HUD.
