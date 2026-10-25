# render

**Owner:** split. `hud.py`, `scenes/`, `fx.py`, `audio.py`, `style.py` = Adetola; `camera_view.py` + `projectiles.py` = Nikhil (projectile sprites: Adetola); `debug_overlay.py` = Enoch; `window.py` + `layout.py` = Adetola + Nikhil.

Draws the `GameView` and the latest camera frame as layout C (two 960x1080 halves, gold divider), and plays event sounds.

## Inputs → Outputs
- In: `GameView` (draw only this, never game state), the latest `Frame`, the newest `PlayerState` per slot, fps and dropped-item count.
- Out: pixels, sounds on `GameView.events`, and from `Window.pump()` the pressed key names (`frozenset[str]`) plus a quit flag.

## Hard rules
- **The only package that may import `pygame`** (pygame-ce). Everything else gets keys as plain data.
- Never import `game/` internals; use the `GameView` contract only. Read `GameEvent.data` with `.get()`: older recordings and the thin engine carry less.
- Never block: 60 fps. If `frame_idx` is unchanged, reuse the last texture. Pre-render static surfaces and go through `Theme.text` (cached) for text; pulsing colors are quantized (`style.pulse`) so they stay cached.
- Pixel coordinates are the unmirrored left image; mirror only the self-view, at draw time.
- Sizes, margins, colors, fonts, FX and audio settings come from `cfg.render` (`theme`, `hud`, `fx`, `audio`, `scenes`, `projectiles`). Validation lives in `core/config.py` `_check_render`: every key read at runtime must be present with the right type (bools are not numbers), so a bad config fails at load.
- Each half shows the *opponent*; the self-view shows the viewer. P1 is the left half.
- Draw with every new `GameView` field empty too (old recordings replay with defaults).

## Files
- `window.py`: `Window` (`pump`, `tick`, `draw`, `close`, and `render(view, frame, states, now)` which draws without flipping, for tests and previews). Picks the scene, draws the banner (per half with a pop in the fight, a bottom ribbon elsewhere, the victory scene uses it as its headline), the round timer, FX and the KO overlay, and plays sounds. Audio is off when headless.
- `layout.py`: layout C geometry (halves, crop and self-view rects).
- `style.py`: `Theme` (fonts and colors from `render.theme`, the optional display font, a bounded text cache with drop shadows, cached panels and additive glow sprites) plus widgets: bars, rings, chips, check marks, effect icons, `edge_glow`, the scene background.
- `hud.py`: `Hud` (stateful). Viewer panel: name, MIC and TRACKED chips, distance with a three-zone meter, basic-attack cooldown bar, eased HP bar with a damage ghost (low HP pulses), mana bar, three spell rows (cost badge, name, release cue, incantation that shrinks, then wraps to two lines, before an ellipsis; greyed when unaffordable; the charged one glows with a charge ring, seconds rounded up, and the big cue), effect icons with countdowns above the panel. Opponent bar at the top with their effects and a pulsing "CHARGING <SPELL>!" warning. Round timer at the top center (red under `hud.timer_low_s`). `release_cue` turns `SpellView.release` into text.
- `projectiles.py`: projectiles flying from the attacker's wrist toward the viewer. Per spell family (`render.projectiles.family`): fire tongues, lightning arcs, holy rays or a basic orb, with an additive glow and a stateless trail. Red pulsing ring and "DODGE!" in the dodge window.
- `fx.py`: `Fx` driven by `GameView.events`: hit = red flash + shake on the target's half, "-N" by their HP bar and "N" over the opponent on the attacker's half; dodge "DODGE!" / "MISS"; block flash "BLOCKED!"; heal sparkles "+N" and buff edge glow (with "SHIELD UP!", "MANA SLOWED!", ...) on the affected player (`data["target"]`, else the caster); a 0-damage hit only bursts; cast edge pulse; KO banner with slow-motion FX for `fx.ko_s` (2.5 s, equal to `game.ko_hold_s`: the engine freezes the fight that long after a KO, and a shorter banner leaves a bare frozen frame). FX exist only in the fight scene and are cleared when it leaves. Particles and texts are capped (`fx.max_particles`, `fx.max_texts`).
- `audio.py`: `Audio` synthesizes the sounds with numpy at startup (cast, hit, dodge, block, heal, buff, KO, tick, match start) and plays them on events; ticks each second of the loading countdown and the last `audio.tick_last_s` of the fight. Silently off if the mixer cannot open, under the SDL dummy audio driver, headless, or with `audio.enabled: false`.
- `camera_view.py`: opponent crop (8:9, padded, EMA-smoothed), mirrored self-view with skeleton, crop math.
- `debug_overlay.py`: perception overlay (toggle `F1`). A header with render fps, camera fps and the dropped count. A panel per half for the player shown there: tracked or lost, distance and zone, pose flags, a `wrist_vz` graph with the push threshold line, and a flash on a push. A top-down map in meters below the panels, mirrored like the players' view.
- `scenes/`: `__init__.py` (`draw_scene` dispatch, `SceneStyle`, `wrap_text`, `headline`, `stat_lines`), `boot.py` (self-check list with marks and an "ALL SYSTEMS GO" / missing note), `lobby.py` (a card per player: name, TRACKED, MIC, the heard transcript, class options from `GameView.classes` with the pick highlighted and the keyword to say, hands-up ready), `loading.py` (a tutorial card per half: each spell's incantation, shrunk to fit up to three lines, and release, tips, the countdown ring), `victory.py` (winner headline, a stats card per player with the keys present, the wrapped chronicle).

## Test without the Jetson
```
uv run pytest tests/render
uv run python -m magic_box --fake
uv run python -m magic_box --fake --headless --max-ticks 60
```
Tests use the SDL dummy drivers set in `tests/conftest.py`. `tests/factories.py` has `make_full_view(scene)` with every optional field populated. To eyeball a scene, render it with `Window.render(make_full_view("lobby"), None, {}, now)` and `pygame.image.save(window.screen, ...)`.

Measured on the dev laptop (Apple M5, SDL dummy video): a populated fight frame renders in about 1.9-2.6 ms (2.8-3.4 ms with heavy FX, worst about 4 ms). Budget 6 ms. On the Orin Nano expect several times that; see the fallbacks below.

## Open TODOs
- Measure the fight frame on the Jetson with the live camera. If it is slow: lower `fx.max_particles`, `projectiles.trail_steps` and `projectiles.glow_max_px`.
- Titles, the victory headline and the KO banner use Cinzel Decorative Bold (`assets/fonts/`, SIL OFL, license beside it; `render.theme.display_font`). Everything players must read fast (HUD, fight banners) stays in the bold default font.
- Sound is synthesized, not designed; real samples could go in `assets/sounds/`.

## Jetson fps fallbacks
All config, defaults unchanged. Try them in this order if the Orin Nano drops below 60 fps (the F1 overlay header shows stage times; `--debug` prints them every `pipeline.perf_window_s`):
1. `render.crop_cache: true` (default): one scaled crop is kept per placement (dest rect and mirroring) and reused while the frame surface is the same and the smoothed crop rect moved less than `render.crop_cache_px` (default 2) in every coordinate, so a repeated `frame_idx` costs almost nothing. The image can lag the true crop by under that many pixels.
2. `render.self_view: false`: skips the mirrored self-view and its skeleton (two scaled crops per frame).
3. `render.camera_scale_quality: fast` (default, `pygame.transform.scale`) or `smooth` (`smoothscale`, nicer, slower). Keep `fast` on the Jetson.
4. `display.vsync: true`: uses `SCALED` + vsync. Can fix tearing but caps fps at the monitor rate. Leave off unless tearing shows. (Fullscreen always uses `SCALED`, so a monitor that isn't 1080p keeps its mode and the 1920x1080 frame is scaled to fit.)
5. FX: lower `render.fx.max_particles` (160), `render.projectiles.trail_steps` (6) and `render.projectiles.glow_max_px` (224). The glow cache (all tints prebuilt at startup) is about 21 MB in 177 surfaces with the defaults; raising `glow_max_px` or lowering the step sizes grows it.
6. Lower `display.fps`, or switch the camera to `BODY_18` with `camera.body_fitting: false` (see the root `CLAUDE.md` risks). SVGA is already the smallest ZED X `camera.resolution`.

`camera_view.configure(cfg["render"])` applies items 1-3 (called from `main.py`).
