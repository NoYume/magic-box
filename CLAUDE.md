# magic-box

Read this first. Each package folder under `src/magic_box/` has its own short `CLAUDE.md`; Claude Code loads it when you work there. Spec: `docs/superpowers/specs/2026-10-24-magic-box-design.md`.

**Deadline: Sunday 2026-10-25, 11:30 CDT.** Everything has to be demo-ready and submitted by then. Check the time left before starting multi-step work, and favor what makes the live demo on the Jetson work over polish.

## What this is

A game console built from a ZED X stereo camera, a Jetson Orin Nano and an external monitor. It runs a 1v1 magic duel for HackTX 2026 (Hardware, Meta and Best Overall tracks). Two players stand side by side. Each watches their own half of a split screen showing a live close-up of the *opponent*. Players speak a Muse Spark-written incantation into their own clip-on mic to charge a spell, then release it with a body gesture (usually a fast push toward the camera). The defender dodges by stepping aside or ducking. Real distance to the camera scales damage.

## Why ZED + Jetson

1. Depth is load-bearing: push speed (m/s along Z), distance zones and dodges are measured in meters. If a feature works as well on a webcam, it is not a headline feature.
2. Body tracking gives two skeletons with IDs, so no hand-rolled pose model.
3. Everything runs on one small box, with no laptop in the loop at the demo.
4. The ZED X has an IMU, connects over GMSL2 through a ZED Link capture card, and works with the Jetson's CUDA stack.
5. The debug overlay (top-down meters view, `wrist_vz` graph) proves the depth story to judges.

Speech-to-text (Muse Voice Transcribe) and Muse Spark run in Meta's cloud. Video never leaves the box.

## Hardware

| Part | Notes |
|---|---|
| ZED X | GMSL2 via a ZED Link capture card, has an IMU, so body tracking works. Not hot-pluggable: after re-plugging, run `sudo systemctl restart zed_x_daemon` or reboot. |
| Jetson Orin Nano | RAM and JetPack unconfirmed; `scripts/check_env.py` is step 1. Video out is DisplayPort, so use a DP-to-HDMI adapter if the monitor needs HDMI. |
| Monitor | External, 1920x1080 assumed. |
| Mics | One clip-on lav mic per player: two USB lav mics, or a dual-transmitter wireless kit whose USB receiver puts P1 on L and P2 on R. A USB mic is the spare. |
| Network | Wi-Fi on the Jetson, for the Muse APIs. |

More in `docs/hardware.md`.

## Architecture

```
                ┌──────────── Jetson Orin Nano ─────────────────────────────┐
 ZED X ─GMSL2─▶ │ [perception proc]  only module that imports pyzed         │
                │   grab → depth + body tracking (2 people, IDs)            │
                │   → slot assign → push/pose/motion → PlayerState ×2/frame │
                │   → left frame into shared memory (double buffer)         │
                │            │ state stream (drained)    │ shm (latest)      │
                │            ▼                           ▼                   │
 mic P1 ──┐     │ [game proc] pygame-ce @ 60 fps, never blocks              │──DP/HDMI──▶ monitor
 mic P2 ──┴───▶ │   intent → game rules → GameView → renderer (layout C)    │
                │   AI worker threads: Muse Spark (incantations, chronicle) │
                │            ▲ VoiceEvent stream (drained)                  │
                │ [voice proc] asyncio, one Muse WebSocket per player mic   │
                └──────────────────┬────────────────────────────────────────┘
                                   └──Wi-Fi──▶ api.meta.ai (Voice Transcribe, Spark)
```

**Processes.** `multiprocessing` with the `spawn` start method on every platform (fork after CUDA init is unsafe). Get contexts only from `magic_box.pipeline.streams.spawn_context()`. `pipeline/processes.py` starts and supervises the children and restarts perception or voice if they die (at most `pipeline.max_restarts`; a child that stays up `pipeline.restart_reset_s`, 60 s, gets its count back). Children exit on their own when the game process is gone.

**Transport rules.**
- **Camera frames are latest-value.** The left image (BGRA uint8) goes into a shared-memory double buffer with `frame_idx` and `cam_t` in the header. The game reads the newest complete buffer and never waits. If `frame_idx` is unchanged, it reuses the last texture.
- **`PlayerState` and `VoiceEvent` are streams.** Bounded `multiprocessing.Queue`s; the game drains every queued item each tick, because a push lives on a single frame's state and dropping states loses inputs. On overflow the producer drops the *oldest* item and counts it. Render uses the newest drained state per slot.
- **Control channel (game → voice).** The game sends a `VoiceConfig` on its own queue when the scene changes: transcript mode in the lobby, and each player's incantation set in loading, as soon as the engine has the incantations, so the Muse sessions are open before the fight.

**Game loop** (`pipeline/loop.py`, one tick): `render.window.pump()` returns the keys pressed this tick; sources are polled for `PlayerState`, `VoiceEvent` and the latest frame; `intent` makes `Action`s; `game.engine.step()` returns a `GameView` plus `GameEvent`s; `render.window.draw()` draws it. Sources (`pipeline/sources.py`) are live, `--replay` or `--fake`. A keyboard voice source is always merged in. Only `render/` touches `pygame`; key presses reach everyone else as plain data.

**Spark jobs.** On entering `loading` or `victory`, the loop submits a job to the `ai/` worker (one daemon thread per job, so a call in flight never holds the quit) and hands the result back via `engine.provide_incantations()` / `engine.provide_chronicle()`. The engine never waits for it.

**Clock.** Every contract has `t = time.monotonic()` at publish; it is shared by all processes on the machine, and fusion compares voice and push times with it. `PlayerState.cam_t` (ZED image timestamp, seconds) is used only to compute velocities.

**Units and frames.**
- Meters and seconds everywhere.
- ZED `UNIT.METER` and `COORDINATE_SYSTEM.IMAGE`: +X image-right, +Y down, +Z away from the camera. Motion toward the camera has negative `vz`.
- Pixel coordinates refer to the unmirrored left image. Only the self-view is mirrored, at render time.
- **Slot 0 = P1**, who stands on the left from the players' view. P1 appears on the image's *right*, so their root x is greater than 0.

## Contracts

All cross-owner types live in `src/magic_box/core/contracts.py`: `Push`, `PlayerState`, `VoiceEvent`, `Action`, `GameEvent`, `GameView`, `PlayerView`, `SpellView`, `EffectView`, `ClassView`, `CheckView`, `ProjectileView`, `VoiceConfig`, `Frame`. They round-trip to JSON lines via `core/serde.py`.

**Change rule:** changing a contract needs a heads-up to every owner who produces or consumes it, and an update to this file in the same change.

| Boundary | Contract | From → To |
|---|---|---|
| Perception → intent | `PlayerState` | Enoch → Nikhil |
| Voice → intent | `VoiceEvent` | Nikhil |
| Intent → game rules | `Action` | Nikhil → Adetola |
| Game → render | `GameView` | Adetola → Adetola + Nikhil |

**`PlayerState` field notes** (Enoch produces, Nikhil consumes):
1. `wrist_vz` is the wrist's velocity relative to the neck (the root when there is no neck), in m/s, negative toward the camera. `Push.speed` is positive and is the peak wrist speed of the thrust: the push is detected when the window speed crosses `push_speed_mps`, then emitted on the first frame the speed falls or after `perception.push_peak_wait_s` (0.1 s), whichever is first. So a push arrives up to 0.1 s after the crossing, before intent's own 0.1 s two-hand hold, and `speed_mult` varies with punch speed. Walking toward the camera does not fire a push.
2. `wrists` and `keypoints_px` hold only valid points, so read them with `.get()`. `wrist_vz` always has `"L"` and `"R"`.
3. A two-hand push arrives as one `Push` (the faster hand). Intent recognises it when the other hand's `wrist_vz` crosses `-push_speed_mps` within ~100 ms of the push (`wrist_vz` is published every frame). A push gives one event: a cooldown and a re-arm stop repeats.
4. `player_id` is the ZED tracking id.
5. A player who leaves is republished at once with `tracking_ok=False`, carrying the last pose flags and zone, with `push=None`. Consumers (intent) must gate on `tracking_ok`.

**Intent, voice and game field notes** (Nikhil produces unless noted; Adetola's engine consumes):
6. `Action.two_hand` is set on a `push` Action when the other hand's `wrist_vz` is at or below `-push_speed_mps` within `intent.two_hand_window_s` (0.1 s, a guess) of the push. So a push is held up to 0.1 s before it reaches the engine, unless the other hand already crossed (then it fires at once as two-hand); if the other hand crosses during the hold, it fires then as two-hand. Charge, push, pose and dodge Actions carry `dist` (root Z; a charge uses the player's last tracked root Z).
7. `Action(kind="speech", text=...)` is one final transcript of a speech turn, from a `transcript` `VoiceEvent`. The engine decides what speech means per scene: the lobby picks a class from a keyword (`game.classes.<id>.keywords`) and takes a name after a prefix such as "my name is" (see `game/CLAUDE.md`). Finals come from Muse's `speechComplete`, often about 3.3 s after the player stops talking.
8. `VoiceEvent(kind="status")` has `text` of `"no api key"`, `"no mic"`, `"connected"` or `"reconnecting"`. The loop passes each one to `Engine.provide_mic_status(slot, ok)`, with `ok` true only for `"connected"` (HUD: MIC OK, else MIC OFF).
9. `SpellView.release` is `push`, `two_hand_push`, `arm_overhead` or `hands_together`, so the HUD and loading card can say how to cast.

**`GameView` additions, 2026-10-25** (Adetola's engine produces; Adetola's HUD and scenes consume). Every new field has a default, so older recordings still load.
10. `PlayerView.effects` (fight only) holds `EffectView(kind, remaining_s)` for `shield` (Flame Wall), `empowered` (Holy Light), `mana_slow` (Static Field) and `slow` (Inferno). `charge_s` and `cooldown_s` (fight only) are seconds left on the charge window and the basic-attack cooldown. `ready` is the debounced hands-up flag (`game.hands_up_hold_s`) in the lobby or victory. `heard` is the last final transcript from that player's mic. `stats` (fight and victory, `{}` elsewhere) holds match totals keyed `damage`, `hits`, `casts`, `dodges`, `blocks`, `heals` and `best_push_mps`; render shows the keys that are present.
11. `GameView.events` repeats the `GameEvent`s `step` returned this tick, so render can flash hits and play sounds without reading the match log. Event slots: `buff` carries the caster with `data["target"]` and `data["effect"]`, `heal` the caster (who is also the healed player) with `data["amount"]`, `block` the defender with `data["attacker"]`. `classes` lists `ClassView(id, name, spells)` and `checks` lists `CheckView(name, ok, detail)` (`camera`, `mic P1`, `mic P2`, `network`, `api key`); both are filled in every scene. `winner_slot` is set in victory and during the KO hold, `None` for a draw.
12. The loop reports camera health with `Engine.provide_camera_status(ok)` (False while perception restarts or frames stop: banner "CAMERA RECONNECTING", the fight freezes) and boot checks with `Engine.provide_check(name, ok, detail)`. Only `provide_check("camera", True)`, sent once a frame is seen, passes boot; a camera status never makes the camera line ok.
13. **Parry (Adetola's PR #2, ported onto dev 2026-10-25).** `PlayerState.pose_flags` can hold `guard` (perception: a wrist `perception.guard_forward_m` in front of the neck, between head and shoulder height). `PlayerView.can_parry` is true for classes in `game.parry_classes` (the Holy Knight); `guard_s`, `guard_cooldown_s` and `riposte_s` (fight only) are seconds left on the raised guard's parry window, until a new guard counts, and to push the riposte. A parry is a `block` event with `data["parry"] = True`; the riposte projectile has `spell_id="riposte"`.
14. `GameView.howto_s` (loading only, else None): seconds left on the how-to-play screen that opens loading (`game.howto_s`, 7 s; Spark writes the incantations meanwhile). `timer_s` is None while it shows; the spell cards' `loading_read_s` starts after it. The lobby also shows a how-to-play strip.

Heads-up for Adetola (engine, HUD and scenes were filled in overnight on 2026-10-25; they are yours to change) and Enoch (the two-hand push rule lives in `intent/`, not in perception; `Push.speed` is now the peak).

## Team and ownership

```
CLAUDE.md, README.md, pyproject.toml, uv.lock, .env.example, .github/, .claude/   Daniel
docker/, compose.yaml, .dockerignore   Daniel + Enoch (Jetson in Docker: README "Jetson with Docker")
config.yaml               shared; each section is commented with its owner
docs/game-design.md       Adetola          docs/hardware.md   Daniel + Enoch
docs/runbook.md, docs/submission.md   Daniel
src/magic_box/
  main.py, __main__.py    Nikhil           CLI entry
  core/        Nikhil     contracts.py, serde.py, config.py, geometry.py
  perception/  Enoch      process.py, zed_source.py, raw.py, keypoints.py, kinematics.py, bodies.py, tracker.py, push.py, poses.py, motion.py, hands.py
  pipeline/    Nikhil     processes.py, frame_bus.py, streams.py, sources.py, loop.py, health.py, perf.py
  intent/      Nikhil     fusion.py, dodge.py
  voice/       Nikhil     process.py, mic.py, muse_stream.py, matcher.py   (mic devices: Daniel)
  ai/          Nikhil     spark_client.py, incantations.py, chronicle.py, worker.py
  game/        Adetola    classes.py, spells.py, state.py, effects.py, combat.py, scenes.py, engine.py
  render/      split      hud.py, scenes/, fx.py, audio.py, style.py = Adetola; camera_view.py + projectiles.py = Nikhil;
                          debug_overlay.py = Enoch; window.py + layout.py = Adetola + Nikhil
  replay/      Nikhil     record.py, play.py, fake_input.py
assets/        Adetola    sprites/, fonts/, sounds/
scripts/       Daniel + Enoch   check_env.py, bench_tracking.py, record_session.py, sync_to_jetson.sh, run_demo.sh, soak.py
               Nikhil           check_spark.py, check_muse.py
recordings/    contents gitignored
tests/         mirrors src/, plus test_boundaries.py, test_blueprint.py and test_e2e.py
```

| Person | Role |
|---|---|
| Daniel | Planning, repo, Jetson |
| Enoch | Camera and tracking |
| Nikhil | Data pipeline |
| Adetola | Game UI and design |

Work in your own folders. If you need a change in someone else's, ask them or open a small PR.

## Conventions

These are team rules. `tests/test_boundaries.py` enforces the import ones.

**Python and dependencies**
- Python `==3.10.*` (`.python-version` is `3.10`). Use uv only: `uv sync`, `uv run`, `uv add`. No pip, conda or poetry.
- Add no dependency beyond the spec §13.2 list without asking Daniel. Confirm it installs on aarch64/JetPack first. `numpy` is pinned `>=1.24,<2` to match the system `pyzed` build.

**Import boundaries**
- `pyzed` is imported only under `perception/`.
- `pygame` is imported only under `render/`.
- `game/` never imports `pygame`, `pyzed` or `cv2`.
- `core/` imports nothing from `magic_box` outside `core/`.
- `pyzed`, `cv2` and `sounddevice` are never imported at module top level; import them inside functions, so laptops and CI import every module.
- Absolute imports only (`from magic_box.x import y`). Ruff `TID252` bans relative imports.

**Code**
- Every module docstring has a line `Owner: <Name>`.
- A stub raises `NotImplementedError("TODO(<Owner>): <what>")` unless it returns a documented placeholder.
- Every tunable lives in `config.yaml`. Code reads `cfg`; it never hard-codes thresholds, keys, sizes or colors. Numbers marked "(guess)" are untuned.
- Use `multiprocessing` only through `magic_box.pipeline.streams.spawn_context()`.
- Never block the game loop: no network, disk waits or `queue.get()` without a timeout on the 60 fps path.

**Git**
- Commit format: `<type>(<scope>): <lowercase summary>`. Types `feat`, `fix`, `doc`, `chore`. One line, no body, no trailer.
- A change is done when `uv run ruff check`, `uv run ruff format --check` and `uv run pytest` are all clean. Tests run headless (`tests/conftest.py` sets the SDL dummy drivers).

## Working without the Jetson

- **`--fake`:** keyboard-driven players and a synthetic camera frame (two silhouettes that follow fake root x and z). Runs on any laptop. This is how you develop render, game and intent work.
- **`--replay DIR`:** feeds a recorded session back with rebased timing. There is no video: the camera frame is redrawn as silhouettes from the recorded states. A missing session exits 2 with "replay: no session at DIR".
- **`--record DIR`:** writes a session directory (`states.jsonl`, `voice.jsonl`, `events.jsonl`, `meta.json`). No `frames.mp4`: the Jetson already records SVO (`scripts/record_session.py`). A writer thread does the disk work, so the game loop never waits.
- **Live mode** (no `--fake`/`--replay`) starts the perception and voice processes. On a laptop the perception process exits with "pyzed is not installed ... use --fake on a laptop", and the supervisor retries it 5 times before giving up. The window shows boot with the camera line at "no frames" for 8 s (`boot_max_s`), then the lobby with "CAMERA RECONNECTING".
- **Voice and Spark need `META_MODEL_API_KEY`** (in `.env`, run with `--env-file`). Without it the voice process reports `"no api key"` (HUD: MIC OFF), and Spark falls back at once to the config incantations and a template chronicle. With `ai.enabled: false`, or when the boot `network` check failed, Spark falls back the same way; voice is unaffected. Restarting the game re-probes the network. A mic device that won't open gives only its own slot `"no mic"`; the other player's mic keeps working. If the voice process dies, both slots show MIC OFF until it is back.
- **Muse and Spark were verified live on 2026-10-25, from a laptop** (`scripts/check_muse.py`, `scripts/check_spark.py`). Muse: 17/17 test sessions matched the right spell, using macOS `say` audio; with `voice.perfect_hold_s` 0.5 the charge lands a median 0.4 s after the end of speech (replayed from 13 sessions' event times). Spark: incantations in 3.1-3.8 s with `ai.reasoning_effort: minimal` (the default effort timed out at 8 s). Muse rejects a keyword over 30 characters, so longer ones are dropped. Not yet run on the Jetson with the lav mics and venue Wi-Fi; `docs/runbook.md` has the commands.
- Spell keys always work as a voice fallback, so you can test casting with no mic and no Wi-Fi.
- The engine in `game/` (filled in overnight on 2026-10-25, Adetola to confirm the numbers) plays `boot → lobby → loading → fight → victory → lobby` with Appendix A damage and every spell effect: Flame Wall shield, Static Field mana slow, Inferno slow, Holy Light ×1.5, Heal +25, Chain as 3 bolts that each need their own dodge. Boot shows the self-checks and leaves once the camera sends a frame (`boot_min_s` 2 s at the earliest, `boot_max_s` 8 s at the latest). In the lobby a class keyword picks the class and a name prefix sets the name. Hands up must hold `hands_up_hold_s` (0.3 s). Loading lasts at least `loading_read_s` (4 s) after the incantations arrive, with no countdown until then. With a live mic, an uncharged push waits `release_grace_s` (0.6 s) for a late voice charge, but only if the player can afford a spell that push could release by the end of the hold (mana regen over `release_grace_s` counts, slowed while mana-slowed); otherwise the basic attack fires at once. A push held during the basic-attack cooldown can only release a spell and is dropped if no charge lands; a push after the cooldown ends replaces that hold, so spammed basic attacks keep firing (with the mic on they keep the cooldown cadence, each up to `release_grace_s` late, because a held push's cooldown counts from the push). A charge for a pose spell releases at once if that pose is held and rose within `pose_grace_s` (1.0 s). A KO holds the frozen fight `ko_hold_s` (2.5 s) for the finishing effects. During a tracking pause the banner counts down to the abandon (`STEP INTO VIEW · 12`); a player gone `abandon_after_s` (20 s) after the pause starts loses the match. Victory leaves on hands up only after `victory_min_s` and at least `victory_read_s` (4 s) after the chronicle arrives, or at `victory_max_s`. Details in `game/CLAUDE.md`.
- The visuals in `render/` (HUD, the five scenes, hit and K.O. effects, per-family projectiles, numpy-synthesized sounds, the Cinzel Decorative OFL display font) are described in `render/CLAUDE.md`. Sounds are off when headless or under the SDL dummy audio driver. Fullscreen always uses `SCALED`, so a monitor that isn't 1920x1080 keeps its mode and the frame is scaled. Validation rejects `render.fx.ko_s` above `game.ko_hold_s`; both are 2.5.

**Fake-mode keys** (from `config.yaml` `keys:`)

| Action | P1 | P2 |
|---|---|---|
| Left / right | `a` / `d` | `j` / `l` |
| Closer / farther | `w` / `s` | `i` / `k` |
| Push | `f` | `h` |
| Duck | `c` | `n` |
| Hands up / together | `r` / `t` | `y` / `u` |
| Two-hand push | `v` | `m` |
| Guard (Holy Knight parry) | `g` | `o` |
| Spells | `1` `2` `3` | `8` `9` `0` |

`F1` toggles the debug overlay. `Backspace` goes back to the lobby from any scene (names and classes kept). `Esc` quits.

**Fake match walkthrough** (`uv run python -m magic_box --fake`):
1. Boot: the self-check list (camera, both mics, network, API key). Fake mode reports the camera at once, so it moves on after 2 s. The mics stay "checking": fake mode starts no voice process.
2. Lobby: the banner reads `SAY NAME · SAY FIRE, LIGHTNING OR HOLY · HANDS UP`. Live, a player picks a class by saying a keyword (`fire`, `lightning`, `holy` or `knight`, and the ASR spelling `lightening`; the last one said wins) and sets a name with "my name is Ada", "call me Ada", "I'm Ada", or a one- or two-word reply ("Ada"). One sentence can do both: "my name is Ada, fire". Chatter such as "I'm ready" changes nothing. The keyboard can't speak, so in fake mode the classes stay `game.default_classes` (P1 Fire Mage, P2 Holy Knight) and the names stay P1 and P2.
3. Both players hold their hands up (`r` + `y`) for 0.3 s (`hands_up_hold_s`) to start.
4. Loading: each player's incantations and release cues on their half. The countdown starts once the incantations arrive and runs at least `loading_read_s` (4 s). With no key, the config incantations arrive at once, so fake-mode loading takes about 4 s.
5. Fight: charge with `1`, push with `f`. A projectile flies on P2's half and P2's HP drops. Ducking (`n`) during the red window avoids it. Two-hand spells need `v` / `m`. P2 is the Holy Knight: Holy Light is hands up (`y`), Heal is hands together (`u`), and guarding (`o`) in the 0.4 s before a projectile lands parries it ("PARRIED!"), after which P2's next push (`h`) within 1.5 s is a 20-damage riposte. For the Lightning Mage, set `game.default_classes` in `config.local.yaml`. With no mic the push is not held, so basic attacks fire at once.
6. KO or time-out: after a KO the fight freezes 2.5 s for the K.O. effect, then the victory scene shows the winner, stats and a chronicle. Live, a player who leaves the view for 2 s pauses the fight with a countdown banner (`STEP INTO VIEW · 20`); at 0 the match ends and the other player wins.
7. Both raise hands again (after `victory_min_s`, and at least 4 s after the chronicle shows, `victory_read_s`): back to the lobby. Names and classes persist across matches, and new ones can be said here. Release the keys and raise hands again to start the next match: hands held up from victory don't start it.

Per-machine overrides go in `config.local.yaml` (gitignored, deep-merged over `config.yaml`; a list such as `voice.mics` replaces the whole list): real mic devices under `voice.mics`, `display.fullscreen: true` (or the `--fullscreen` flag), camera fallbacks.

## Commands

| Command | What it does |
|---|---|
| `uv sync --extra laptop` | Install on a laptop (adds `opencv-python`). On the Jetson use plain `uv sync`. |
| `uv run python -m magic_box --fake` | Run with keyboard players. |
| `uv run --env-file .env python -m magic_box` | Live mode; `.env` holds `META_MODEL_API_KEY`. |
| `uv run python -m magic_box --web` | Browser output instead of a window (no monitor at the venue): the game draws off-screen and streams MJPEG on `display.web.port` (8000); keys typed in the page reach the game. `docker compose up` runs the demo this way. |
| `uv run python -m magic_box --help` | Flags: `--fake`, `--replay DIR`, `--record DIR`, `--debug` (overlay on, perf printed to stderr), `--fullscreen`, `--headless`, `--config PATH`, `--max-ticks N`. |
| `scripts/run_demo.sh [--fake] [--windowed] [--no-record] [--dry-run] [-- GAME_ARGS...]` | Demo launcher. On the Jetson: fullscreen and `--env-file .env`. Records each run to `recordings/<timestamp>/` with `game.log`, restarts on a crash (at most 5 in 60 s). Exit code 3 means perception gave up (six deaths: the first run plus five restarts, after it had delivered frames): the launcher then starts the game again, with fresh camera and voice processes. A laptop with no `pyzed` never delivers a frame, so it keeps running with CAMERA RECONNECTING instead. `Esc` or Ctrl-C ends it. |
| `docker compose build` / `docker compose run --rm magic-box <command>` / `DISPLAY=:0 docker compose up` | Jetson without a host ZED SDK: the image has the SDK, the repo is mounted at `/app`. Leave `DISPLAY` unset for headless runs (a refused display breaks the ZED X capture). README "Jetson with Docker". |
| `uv run pytest` | Run all tests. |
| `uv run ruff check` / `uv run ruff format --check` | Lint and format check. |
| `uv run python scripts/check_env.py [--laptop] [--network]` | Environment check (Python, JetPack, RAM, pyzed, ZED camera and `zed_x_daemon`, CUDA, cv2, audio devices, API key; `--network` probes the Meta API). |
| `uv run python scripts/bench_tracking.py [--seconds N] [--body-format F] [--resolution R] [--svo PATH] [--min-fps X] [--min-two S]` | Two-person tracking benchmark on the Jetson. Prints GO or NO-GO. Exit 0 GO, 1 NO-GO, 2 camera error or no `pyzed`. |
| `uv run python scripts/record_session.py [--seconds N] [--out PATH]` | Record the live ZED X to an SVO2 file in `recordings/`. Exit 2 on a camera error or no `pyzed`. |
| `uv run --env-file .env python scripts/check_spark.py [--classes P1 P2] [--names P1 P2] [--chronicle] [--reasoning-effort E]` | Live Spark check: latency, reply model, each incantation marked `[spark]` or `[fallback]`. |
| `uv run --env-file .env python scripts/check_muse.py [--phrase TEXT ...] [--wav F ...] [--record S --slot 0\|1] [--keywords words\|phrases\|none ...] [--hold S] [--events]` | Live Muse check: partial and charge latency, spell matching, a suggested `game.charge_window_s`. Default audio is macOS `say`; on the Jetson use `--record` with the real mics. |
| `uv run pytest tests/test_e2e.py` | End-to-end tests that drive the real game loop through a whole match (part of `uv run pytest`). |
| `uv run python scripts/soak.py [--seconds N] [--sample-s S] [--seed N] [--fast] [--debug] [--config PATH]` | Soak test: fake mode, headless, random inputs, for `--seconds` of wall time (`--fast`: no frame cap, fake clock; `--debug`: also draws the F1 overlay). Reports fps, RSS and growth; exits 1 on a crash or unbounded growth. |
| `scripts/sync_to_jetson.sh` | rsync the repo from a laptop to the Jetson (`JETSON_HOST`, `JETSON_DIR` override the defaults). |

The Jetson session, in order, is `docs/runbook.md`. `bench_tracking.py` is the hour-1 go/no-go for two-person tracking. It prints GO or NO-GO from the measured fps and the share of frames with two people. On NO-GO, retry with `--body-format BODY_18`. To tune offline, record an SVO with `record_session.py`, then set `camera.svo_path` in `config.local.yaml` and run the game as usual (playback loops; perception handles the `cam_t` rewind).

## Milestones

All milestones land before the deadline: **Sunday 2026-10-25, 11:30 CDT**.

- **Hour 0–1:** Daniel: Jetson env and `check_env.py`. Enoch: `bench_tracking.py` go/no-go with two people. Nikhil: `--fake` running on the Jetson's monitor. Adetola: `docs/game-design.md` pass.
- **M1:** live ZED → `PlayerState` → layout C crops and self-view skeletons on the monitor.
- **M2:** push → basic attack projectile → HP drops (first playable).
- **M3:** debug overlay with a top-down meters view and the `wrist_vz` graph (the depth proof for judges).
- **M4:** voice charge + push release with fixed incantations; poses (Holy Light, Heal); dodges.
- **M5:** Spark incantations, full scene flow, lobby name capture.
- **M6:** Duel Chronicle, polish, demo video.
- Finger gestures are out. `perception/hands.py` stays a stub.

## Risks

- **Orin Nano fps** with two bodies, depth, 60 fps render and crops. Benchmark first. Fallbacks: `BODY_18` with body fitting off (`camera.body_fitting: false`; BODY_34/38 need fitting), the render fallbacks in `render/CLAUDE.md` ("Jetson fps fallbacks", all config), GPU crops via pygame-ce's SDL2 `Texture` API. SVGA is already the smallest ZED X mode, so a lower camera resolution is not available.
- **numpy ABI mismatch** between the venv and the system `pyzed` build. Pin to whatever works on the device.
- **Venue Wi-Fi.** Keyboard spell keys, config incantations and a template chronicle keep the demo alive. A phone hotspot is the backup.
- **Lav-mic crosstalk** at 1–2 m. Each mic matches only its own player's incantations, and the two sets are kept clearly different.
- **Muse partial-transcript latency** was measured on a laptop with TTS audio only (charge about 0.4 s after speech). Re-measure with the lav mics and real voices (`check_muse.py --record`) and size `game.charge_window_s` (3.0) and `game.release_grace_s` (0.6) from it.
- **Crop upscaling blur:** SVGA (960x600) is scaled about 1.8x to fill a half. HD1200 is the fallback if it looks too soft, at a cost in fps. Resolution is a config tunable.
- **GMSL2 is not hot-pluggable.** Never re-plug the camera while the system runs. See the ZED X troubleshooting section in `docs/hardware.md`.
- **Lighting, crowds and thermals** if the hardware goes in an enclosure.

## Open decisions

| Decision | Owner | Status |
|---|---|---|
| Final classes, spells, costs, gestures, numbers (draft in `docs/game-design.md`) | Adetola | Open for tuning. Decided overnight, Adetola to confirm: single 90 s round (no best of three), the ×1.15 perfect bonus stays, one dodge per Chain bolt, every spell effect as in `game/CLAUDE.md`. |
| Scene flow details and lobby interactions | Adetola | Decided overnight, Adetola to confirm: boot self-check scene, class pick by voice keyword, name only after a prefix or as a 1-2 word reply, hands up held 0.3 s, a paused match ends after 20 s (tracked player wins), 2.5 s KO hold. |
| Mic hardware model and channel routing | Daniel | Open. |
| JetPack, Python, RAM, ZED SDK version (confirm, then pin) | Daniel | Open: `check_env.py` at 08:00. |
| Body format (defaults to `BODY_34`) and camera resolution (defaults to SVGA), confirmed by `bench_tracking.py` | Enoch | Open: `bench_tracking.py` at 08:00. |
| Muse Spark `base_url` and model id | Nikhil | Confirmed live 2026-10-25: `https://api.meta.ai/v1`, `muse-spark-1.3`, with `ai.reasoning_effort: minimal`. |
| Muse keyword format (words vs phrases) and `game.charge_window_s`, after measuring partial latency | Nikhil | Words, measured live. `charge_window_s` stays 3.0 and `voice.perfect_hold_s` is 0.5 until the Jetson lav-mic run. |
| Replace the thin engine in `game/` (spell effects, class pick, boot scene, real HUD and scenes) | Adetola | Done overnight (engine and visuals), Adetola to confirm. |
| `Push.speed`: threshold speed or peak speed, for damage scaling | Adetola + Enoch | Decided overnight, Adetola/Enoch to confirm: peak speed (`perception.push_peak_wait_s`). |
| `game.release_grace_s` (an uncharged push waits 0.6 s for a voice charge when the mic is on), `game.pose_grace_s` (1.0 s) and `game.loading_read_s` (4.0 s) | Adetola + Nikhil | Decided overnight, Adetola to confirm. `release_grace_s` is the first knob to tune on the Jetson if basic attacks feel laggy. |
| Enclosure (Hardware track) | Daniel | Open. |
