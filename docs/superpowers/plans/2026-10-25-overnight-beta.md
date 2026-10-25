# Overnight beta plan (2026-10-25)

**Goal:** by 07:30 CDT, `dev` holds a playable, demo-shaped beta that the team runs on the Jetson and ZED X from 08:00, then iterates on until the 11:30 deadline. Spec: `docs/superpowers/specs/2026-10-24-magic-box-design.md`. Game design draft: `docs/game-design.md`.

**Base:** `dev` = `main` at `6c475ca` plus the contract commit below. Each task runs in its own worktree on its own branch and is landed on `dev` by the controller.

## Global constraints (every task)

- Read the root `CLAUDE.md`, the `CLAUDE.md` of every package you touch, and `CLAUDE.local.md` (git workflow). The conventions there are binding: import boundaries, `Owner:` docstring lines, every tunable in `config.yaml` with validation in `core/config.py`, never block the 60 fps loop, `spawn_context()` only, absolute imports.
- Python 3.10, uv only. **No new dependencies.** pygame-ce, numpy (<2), websockets, sounddevice, PyYAML and the stdlib are what you have. On a laptop also opencv-python.
- Done means `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` are all clean in your worktree, plus `uv run python -m magic_box --fake --headless --max-ticks 600` exits 0.
- Commits: `<type>(<scope>): <lowercase summary>`, one line, types `feat`/`fix`/`doc`/`chore`, scope = package or area (`game`, `render`, `pipeline`, `voice`, `ai`, `perception`, `scripts`, `repo`, `plan`). No body, no trailer, no co-author line. Several small commits per task, each one green.
- Stay inside your task's files. If you need a change elsewhere, make the smallest one, say so in your report, and never edit another task's owned files listed below.
- Don't edit the root `CLAUDE.md` or `docs/game-design.md` (Task 6 owns them tonight). Update your own package `CLAUDE.md` so it matches what you built.
- Every design call you make goes in your report under "Decisions", one line each: what you chose, why, and what it costs if wrong.
- Never push to `main`. Don't push `dev` either; commit on your branch and the controller lands it.

## Contract (already on dev, commit "feat(core): add effects, classes, boot checks and tick events to the game view")

`core/contracts.py` gained `EFFECT_KINDS = ("shield", "empowered", "mana_slow", "slow")`, `EffectView(kind, remaining_s)`, `ClassView(id, name, spells)`, `CheckView(name, ok, detail="")`.
`PlayerView` gained `effects`, `charge_s`, `cooldown_s`, `ready`, `heard`, `stats` (keys `damage`, `hits`, `casts`, `dodges`, `blocks`, `heals`, `best_push_mps`).
`GameView` gained `events` (this tick's GameEvents), `classes`, `checks`, `winner_slot`.
`Engine` gained `provide_camera_status(ok)` and `provide_check(name, ok, detail="")` (stored only; Task 1 makes them do something).
Root `CLAUDE.md` notes 10-12 describe them. Don't change these signatures; if you must add a field, add it with a default and say so in your report.

## Rulings already made (Daniel delegated Adetola's open decisions; flag in the morning report)

- Main is the source of truth. `feature/*` branches are read-only references for ideas.
- Single 90 s round (no best of three). Perfect-incantation bonus stays (×1.15 at score ≥ 95).
- Class pick happens in the lobby by voice: a final transcript containing a class keyword (`fire`, `lightning`, `holy` or `knight`) picks that class; otherwise the transcript sets the name. "my name is X" / "call me X" / "i am X" take X. Defaults stay `game.default_classes`.
- A paused match (a player untracked) ends after `game.abandon_after_s` (20 s) with the tracked player as winner (draw if both gone) and goes to victory.
- `Push.speed` becomes the peak speed of the thrust (Task 4), so `speed_mult` actually varies with punch speed.

## File ownership tonight

| Task | Owns |
|---|---|
| 1 Engine | `src/magic_box/game/**`, `config.yaml` `game:` section, `tests/game/**` |
| 2 Visuals | `src/magic_box/render/hud.py`, `render/scenes/**`, `render/window.py`, `render/projectiles.py`, new `render/fx.py`, `render/audio.py`, `assets/**`, `config.yaml` `render:` + `display:`, `tests/render/**` (except camera and overlay tests) |
| 3 Pipeline | `src/magic_box/pipeline/**`, `main.py`, `render/camera_view.py`, `render/debug_overlay.py`, `replay/**`, `scripts/run_demo.sh`, `scripts/sync_to_jetson.sh`, `pyproject.toml`, `uv.lock`, `config.yaml` `pipeline:`/`replay:`, `tests/pipeline/**`, `tests/replay/**`, camera and overlay tests |
| 4 Perception | `src/magic_box/perception/**`, `config.yaml` `perception:`/`camera:`, `tests/perception/**`, `scripts/bench_tracking.py`, `scripts/record_session.py` |
| 5 Live voice + Spark | `src/magic_box/voice/**`, `src/magic_box/ai/**`, `src/magic_box/intent/**`, new `scripts/check_spark.py`, `scripts/check_muse.py`, `config.yaml` `voice:`/`ai:`/`intent:` and `game.charge_window_s`, `tests/voice/**`, `tests/ai/**`, `tests/intent/**` |
| Shared | `src/magic_box/core/config.py` validation: add only your own keys, at the end of your section's block. `tests/factories.py`: additive helpers only. |

---

### Task 1: Engine (Adetola's game/)

Replace the thin engine's gaps so every spell does what `docs/game-design.md` says and the scene flow is `boot → lobby → loading → fight → victory → lobby`.

1. **Spell effects** (numbers in `config.yaml` per spell, read via `cfg.game`):
   - Flame Wall: `shield` on the caster for 4 s; the next incoming hit is blocked (no damage, `block` event), then the shield ends.
   - Static Field: projectile; on hit (not dodged/blocked) the target gets `mana_slow` for 5 s (mana regen × `mana_slow_mult`, 0.25).
   - Inferno: 35 damage, and the target gets `slow` for 3 s: their next charge window is shortened by `slow_charge_mult` (0.6). It must be visible and cheap.
   - Holy Light: `empowered` on the caster for 6 s; their damage × 1.5.
   - Heal: +25 HP on the caster, capped at `hp_max`, `heal` event.
   - Chain: 3 projectiles of 7 damage, spaced `chain_gap_s` (0.25 s), each dodgeable on its own.
   - Every effect shows in `PlayerView.effects` with its remaining time; `buff`/`heal`/`block` events fire.
2. **Lobby:** class pick and name by voice per the rulings above; `PlayerView.heard` shows the last transcript; `PlayerView.ready` mirrors hands up; `GameView.classes` lists every class from config; the class picked is used for the match's spells. Banner prompts say what to do ("SAY YOUR NAME · SAY FIRE, LIGHTNING OR HOLY · BOTH RAISE YOUR HANDS"; keep it short enough for one line at 1920 px, or split across the two halves).
3. **Victory debounce:** a hands-up must be held `game.hands_up_hold_s` (0.3 s) before it counts, in lobby and victory (Jetson flicker protection).
4. **Boot scene:** the engine starts in `boot`. `GameView.checks` shows `camera`, `mic P1`, `mic P2`, `network`, `api key` from `provide_check` / `provide_camera_status` / `provide_mic_status` (unknown = not ok, detail "checking"). Go to the lobby after `boot_min_s` (2.0) once the camera is ok, or at `boot_max_s` (8.0) whatever the checks say. `--fake` must still reach the lobby within `boot_max_s` even if nothing reports (the loop in fake mode will report camera ok; Task 3 wires that).
5. **Camera reconnecting:** while `provide_camera_status(False)`, banner "CAMERA RECONNECTING" and the fight clock freezes like a pause.
6. **Abandon:** per the ruling (`abandon_after_s`).
7. **View fields:** fill `charge_s`, `cooldown_s`, `stats`, `events` (the same events `step` returns), `winner_slot`.
8. Remove the "Thin placeholder" docstring line from files you've fully replaced, and the `NotImplementedError` stubs that are now real (classes.py, combat.py, spells.py, state.py if any remain). Update `game/CLAUDE.md`.
9. Tests for every effect, the lobby parsing (name vs class keyword, "my name is"), boot timing, debounce, abandon and camera pause. Keep the existing tests green or update them where the ruling changes behaviour.

### Task 2: Visuals (Adetola's HUD, scenes, FX, sound)

Make it look and sound like a game on a 1920x1080 monitor at arm's length. Draw only from `GameView`; colors, sizes and fonts in `cfg.render`.

1. **HUD** (`render/hud.py`), per half (the viewer's panel and the opponent's bar):
   - Animated HP and mana bars that ease toward the target, with a ghost "damage taken" segment.
   - A charge ring or timer when a spell is charged (`charge_s`).
   - Basic-attack cooldown.
   - Effect icons with countdowns (`effects`).
   - Spell list with cost, the incantation, and the release cue (keep `release_cue`), greyed when the player can't afford it.
   - MIC and TRACKED indicators, distance with a zone meter (danger / neutral / far).
   - Move every hard-coded color to config.
2. **Scenes** (`render/scenes/`):
   - Boot: the checklist with OK and missing marks.
   - Lobby: a card per player with name, class (highlighting the pick from `classes`), the `heard` text as a mic check, TRACKED, and a hands-up ready indicator; the class options with their spells.
   - Loading: a tutorial card per half with each spell's incantation and how to release it, plus a big countdown.
   - Victory: winner banner (`winner_slot`, draw), per-player stats from `stats`, and the chronicle, wrapped.
3. **FX** (`render/fx.py`), driven by `GameView.events`:
   - hit flash and screen shake on the target's half, damage numbers
   - dodge "DODGE!", block shield flash, heal sparkles, buff glow, KO slow-mo banner
   - projectile sprites per spell family (fire, lightning, holy), procedurally drawn with glow and a trail, in `render/projectiles.py`
   - Particles are capped (`render.fx.max_particles`) so the Jetson stays at 60 fps.
4. **Sound** (`render/audio.py`): synthesize short effects with numpy at startup (cast whoosh, hit, block, heal chime, KO, countdown tick, match start), play on events through `pygame.mixer`. If the mixer can't open (no audio device, dummy driver in tests), sound is silently off. Volume and enable flag in `cfg.render.audio`.
5. **Fonts:** pygame's bundled default is fine. A single OFL font file under `assets/fonts/` with its license is allowed if you can get it without new deps; not required.
6. Keep the self-view mirrored and the halves showing the opponent. Don't touch `camera_view.py` or `debug_overlay.py` (Task 3).
7. Tests: headless draw of every scene with fully populated views (effects, events, checks, stats, winner) doesn't crash; FX caps hold; audio off under the dummy driver. Update `render/CLAUDE.md`.
8. Budget: a frame of the fight scene at 1920x1080 should draw in under 6 ms on this laptop (measure and report the number).

### Task 3: Pipeline, perf and launch (Nikhil + Enoch's Jetson readiness)

1. **Camera and boot checks in the loop:**
   - `Engine.provide_camera_status`: ok once frames arrive; not ok when no new `frame_idx` for `pipeline.camera_stale_s` (1.5 s) in live mode or while the supervisor restarts perception. Fake and replay always report ok.
   - `Engine.provide_check`:
     - `camera`: first frame
     - `api key`: `META_MODEL_API_KEY` present (never log it)
     - `network`: a non-blocking reachability probe of the Spark host on a background thread with a 3 s timeout; replace it with the `ai/` worker's own check if one exists
     - mic checks come via `provide_mic_status` already
2. **Perf instrumentation:** per-tick timings (poll, intent, engine, draw) and camera-to-screen latency (`PlayerState.t` → draw), shown in the debug overlay header (F1) and printed once every 10 s with `--debug`. Report the numbers on this laptop in fake mode.
3. **Cheap Jetson fallbacks**, all config, defaults unchanged:
   - `render.camera_scale_quality` (smoothscale vs scale)
   - `render.self_view` on/off
   - a crop texture cache so an unchanged `frame_idx` costs nothing
   - `display.vsync`
   - Document them in `render/CLAUDE.md` under a "Jetson fps fallbacks" list (append only; Task 2 edits the rest of that file).
4. **Quit fast:** Esc or window close returns within 1 s even if a Spark call is in flight. Coordinate through the `ai/` worker's public API only; if the worker needs a change, describe it in your report for Task 5 rather than editing `ai/`.
5. **Demo launcher** `scripts/run_demo.sh`:
   - On the Jetson: fullscreen, `--env-file .env`, records every run to `recordings/<timestamp>`.
   - Restarts the game if it crashes (max 5 restarts per minute) and logs to `recordings/<timestamp>/game.log`.
   - `--fake` passes through for laptop tests.
   - Executable, with a usage header.
6. `pyproject.toml`: raise `websockets>=12` to `>=14` and refresh `uv.lock` with `uv lock` (no other dependency changes).
7. Tests for the stale-camera logic, the checks, and the launcher's argument handling (shellcheck-clean if `shellcheck` exists). Update `pipeline/CLAUDE.md` and `replay/CLAUDE.md` if behaviour changed.

### Task 4: Perception (Enoch's peak push speed)

1. `Push.speed` reports the thrust's peak wrist speed toward the camera instead of the threshold-crossing window average. Detect the threshold as today, then emit the push when the speed stops rising (first frame where it drops) or after `perception.push_peak_wait_s` (0.1 s), whichever comes first, with `speed` = peak. `origin_px` stays the wrist pixel at detection. Cooldown and re-arm logic unchanged.
2. Keep the `PlayerState` contract unchanged. If you change root `CLAUDE.md` note 1's meaning, say so in your report; Task 6 edits the root file.
3. Fake input (`replay/fake_input.py` is Task 3's file; don't edit it) already sends a fixed push speed; leave it.
4. Tests with synthetic wrist tracks: a fast punch reports a higher speed than a slow one; walking toward the camera still doesn't fire; the extra latency is at most `push_peak_wait_s`; two quick punches still respect cooldown.
5. Review `bench_tracking.py` and `record_session.py` for anything that would fail on first run on the Jetson (argument defaults, paths, error messages) and fix what's cheap. Report what you checked.
6. Update `perception/CLAUDE.md`.

### Task 5: Live voice + Spark (Nikhil's verification TODOs)

`META_MODEL_API_KEY` may be in `/Users/daniel/Downloads/magic-box/.env` (the main checkout; never print it, never copy it into a commit, read it with `--env-file`). If it's absent, do everything except the live runs and say so.

1. `scripts/check_spark.py`:
   - Calls Spark through `ai/spark_client.py` the way the game does.
   - Prints latency, the model id used, and the incantations for two classes.
   - Exits nonzero with the error type and HTTP status on failure, never the key.
2. `scripts/check_muse.py`:
   - Synthesizes an incantation with macOS `say` (or reads a WAV on the Jetson).
   - Converts it to the PCM format `voice/mic.py` sends, and streams it through `voice/muse_stream.py` at real time.
   - Reports time from audio end to the first partial and to the final, plus whether the keyword or phrase matched via `voice/matcher.py`.
   - Runs both words and phrase keyword formats if the API distinguishes them.
3. Run both live if the key exists. Fix any mismatch with Meta's real API in `spark_client.py` / `muse_stream.py` (URL, model id, headers, message shapes), with tests against the existing fakes updated to match reality.
4. Set `game.charge_window_s` from the measured partial latency (latency + 2.0 s of reaction time, rounded to 0.5 s, min 2.5) and record the measurement in `voice/CLAUDE.md`.
5. Make sure an in-flight Spark call can't block quitting (daemon thread or a bounded join); expose whatever Task 3 needs as a public method.
6. Intent: re-check `intent.two_hand_window_s` handling and the duck/step thresholds against the rulings; nothing to change unless a test shows a bug.
7. Update `voice/CLAUDE.md`, `ai/CLAUDE.md`, `intent/CLAUDE.md`.

### Task 6: Docs, runbook and submission (Daniel's work) — wave 2

After Tasks 1-5 land.

1. `docs/runbook.md`: the 08:00 hardware session, in order:
   - Jetson boot and env: `check_env.py`, the `zed_x_daemon` restart.
   - Sync: `git pull` of `dev` or `sync_to_jetson.sh`, then `uv sync`.
   - `bench_tracking.py` GO/NO-GO with its fallbacks.
   - Mic routing and `config.local.yaml` (`voice.mics`).
   - `check_spark.py` and `check_muse.py`.
   - `run_demo.sh`.
   - What to tune, which key and what to watch in the debug overlay.
   - Recording an SVO and a session for backup.
   - A bug-bash checklist covering each spell, dodge, class pick, boot checks, camera unplug (don't, see GMSL2), and network off.
   - Every command copy-pasteable.
2. Root `CLAUDE.md` and `docs/game-design.md` updated for tonight's rulings and new behaviour (keep the change rule: contract notes stay accurate).
3. `README.md` refresh (what it is, why ZED and Jetson, how to run fake and live).
4. `docs/submission.md`: Devpost write-up draft (inspiration, what it does, how we built it, challenges, accomplishments, what's next, built with) and a 2-minute demo video shot list. Track angles: Hardware, Meta (Muse Voice + Spark), Best Overall.

### Task 7: QA and bug fix (wave 2)

After Tasks 1-5 land.

1. Scripted headless fake matches: drive `--fake` input programmatically (via `replay/fake_input.py`'s API or a recorded session) through boot → lobby (names, class pick) → loading → fight (every spell of every class, dodges, blocks, heal, KO and time-out) → victory → lobby. Put this in `tests/test_e2e.py` with fast clocks; it must run in under 20 s.
2. Record a fake session with `--record`, replay it with `--replay`, and check it plays to the same result.
3. Fix the bugs you find, in whichever package. Report each one.
4. A 10-minute soak in fake mode with random inputs: no crash, no unbounded memory or particle growth, fps reported.
