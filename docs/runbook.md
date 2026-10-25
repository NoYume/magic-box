# Jetson runbook

**Owner:** Daniel

The 08:00 hardware session on Sunday 2026-10-25, in order. Submission deadline: **11:30 CDT**.

Every command runs from the repo root on the Jetson (`~/magic-box`) unless it says "laptop". Without the ZED SDK on the host, prefix it with `docker compose run --rm magic-box` (README: "Jetson with Docker"). Commands that need the Meta key use `--env-file .env`. Never type or paste the key into a command line.

> **GMSL2 is not hot-pluggable.** Never unplug or re-plug the ZED X cable while the Jetson is on. If it was re-plugged, run `sudo systemctl restart zed_x_daemon` (or reboot with the camera plugged in), then rerun `check_env.py`.

## First 30 minutes

The short path. Each step links to its full section below.

| Min | Step | Command | Pass |
|---|---|---|---|
| 0 | Camera plugged in, then power on | (none) | Jetson boots to the desktop on the monitor |
| 2 | Max power and clocks | `sudo nvpmodel -q` then `sudo jetson_clocks` | mode printed, no error |
| 3 | Get `dev` onto the Jetson | [Sync](#2-sync) | `git log -1` (or the laptop's) shows the latest `dev` commit |
| 5 | Install | `uv sync` | no errors |
| 6 | Environment check | `uv run --env-file .env python scripts/check_env.py --network` | exit 0, `zed_camera OK`, `zed_x_daemon OK`, `meta_api OK` |
| 8 | Tracking go/no-go, two people 1-3 m away | `uv run python scripts/bench_tracking.py --seconds 30` | prints `GO` |
| 12 | Mics in `config.local.yaml` | [Mics](#4-mics) | `check_env.py` lists both devices |
| 15 | Spark over the venue Wi-Fi | `uv run --env-file .env python scripts/check_spark.py --chronicle` | exit 0, lines marked `[spark]` |
| 17 | Muse with the real mics | [Voice checks](#5-voice-and-spark-checks) | exit 0 for each player |
| 22 | Full game | `DISPLAY=:0 scripts/run_demo.sh -- --debug` | boot shows 5 green checks, lobby, a match plays |
| 30 | Start the bug bash and tuning | [Tune](#7-tune) and [Bug bash](#9-bug-bash) | |

If `bench_tracking.py` says NO-GO, fix that before anything else. It decides the camera settings for the rest of the day.

## 1. Boot and environment

1. Plug the ZED X into the ZED Link card **before** power-on. Strain-relieve the cable.
2. The dev kit's video out is DisplayPort. Use a DP-to-HDMI adapter if the monitor needs HDMI.
3. Power mode and clocks:
   ```bash
   sudo nvpmodel -q
   sudo nvpmodel -q --verbose     # lists the mode ids for this JetPack
   sudo jetson_clocks
   ```
   Set the highest mode with `sudo nvpmodel -m <id>` if it is not already set. Mode ids differ between JetPack versions, so read them from the verbose output.
4. Camera daemon:
   ```bash
   systemctl is-active zed_x_daemon
   sudo systemctl restart zed_x_daemon     # only if it is not active, or after a re-plug
   sudo dmesg | grep -i zedx               # both sensors should say "bound"
   ```
5. Environment check:
   ```bash
   uv run --env-file .env python scripts/check_env.py --network
   ```
   If `.env` does not exist yet, do the first-time step in section 2 first, or run `uv run python scripts/check_env.py`. One line per check: `OK`, `FAIL` (required) or `WARN` (optional). Exit 1 means a required check failed. `--network` adds a `meta_api` probe (`GET https://api.meta.ai/v1/models`). The `sounddevice` line lists the audio input devices; you need those names in section 4.

   If `pyzed` fails with a numpy ABI error, see the Jetson quickstart in `README.md`.

From SSH, every command that opens a window needs `DISPLAY=:0` in front of it (or `export DISPLAY=:0` once per shell).

## 2. Sync

Pick the one that matches how the Jetson got the repo.

**A. The Jetson has a git clone.**
```bash
cd ~/magic-box
git fetch origin
git switch dev
git pull --ff-only
uv sync
```

**B. Copy from a laptop** (the Jetson has no `.git`). On the laptop, in a checkout of the latest `dev`:
```bash
JETSON_HOST=<user>@<jetson-ip> scripts/sync_to_jetson.sh
```
`JETSON_DIR` overrides the target folder (default `~/magic-box`). The script never copies or deletes `.env`, `config.local.yaml`, `recordings/` or `.venv`, so the Jetson keeps its own. Then on the Jetson:
```bash
cd ~/magic-box
uv sync
```

On the Jetson, always plain `uv sync`. Never `--extra laptop`: `opencv-python` shadows JetPack's `cv2`.

First time only: `cp .env.example .env`, then open `.env` in an editor (`nano .env`) and set `META_MODEL_API_KEY`. Never commit `.env`.

## 3. Tracking go/no-go

Two people stand 1 to 3 m from the camera, about a shoulder-width apart, and move around for 30 s.

```bash
uv run python scripts/bench_tracking.py --seconds 30
```

It prints the fps, the grab and tracker times, the share of frames with two people, then `GO` or `NO-GO: <reason>`. Exit codes: 0 GO, 1 NO-GO, 2 camera error (also when `pyzed` is missing). GO needs at least 25 fps (`--min-fps`) and two people in 90% of frames (`--min-two`). Ctrl-C prints the summary so far.

The game must not be running: only one process can open the camera.

**On NO-GO, try these in order** and rerun the benchmark after each:

1. Lighter body format:
   ```bash
   uv run python scripts/bench_tracking.py --seconds 30 --body-format BODY_18
   ```
2. BODY_18 with body fitting off. The script has no flag for fitting, so put it in `config.local.yaml` (the scripts read it too):
   ```yaml
   camera:
     body_format: BODY_18
     body_fitting: false
   ```
   Then rerun the plain benchmark command. BODY_34 and BODY_38 need fitting on.
3. If only "two people" fails: check the play area (both inside `camera.max_range_m`, 3.5 m), the lighting, and that nobody else stands closer than the players.

SVGA (960x600) is already the smallest ZED X mode, so a lower camera resolution is not an option. When a setting works, keep it in `config.local.yaml` and tell Enoch, who owns the `camera:` defaults.

## 4. Mics

Find the device names and channel counts:
```bash
uv run python scripts/check_env.py
uv run python -c "import sounddevice as sd; print(sd.query_devices())"
```

Write `config.local.yaml` beside `config.yaml` (gitignored). List **both** slots: a list in `config.local.yaml` replaces the one in `config.yaml`. `device` is a name (a unique part of it is enough) or an index from the list above; `null` is the system default.

Two USB lav mics:
```yaml
voice:
  mics:
    - {slot: 0, device: "USB Lav Mic 1", channel: 0}
    - {slot: 1, device: "USB Lav Mic 2", channel: 0}
```

One wireless receiver with P1 on the left channel and P2 on the right:
```yaml
voice:
  mics:
    - {slot: 0, device: "Wireless Receiver", channel: 0}
    - {slot: 1, device: "Wireless Receiver", channel: 1}
```

Slot 0 is P1, who stands on the left from the players' view. Replace the device names with the real ones. The voice process opens each device at 16 kHz, or at the device's own rate and resamples. A mic that will not open gives status `"no mic"` (HUD: MIC OFF); the spell keys still work.

No need for `display.fullscreen` here: `run_demo.sh` passes `--fullscreen` on the Jetson, and leaving it out keeps `--windowed` working.

## 5. Voice and Spark checks

**Spark** (incantations, then a Duel Chronicle):
```bash
uv run --env-file .env python scripts/check_spark.py --chronicle
```
It prints the latency, the model id the reply reports, and each incantation marked `[spark]` or `[fallback]`. Exit 0: Spark answered. Exit 1: a call failed (error type and HTTP status only). Exit 2: Spark disabled or no key. On the laptop it took 3.1-3.8 s with `ai.reasoning_effort: minimal`. Anything near 8 s (`ai.timeout_s`) means the game will fall back on this Wi-Fi.

**Muse with the real mics.** Each `--phrase` is recorded for 4 s from that player's mic, one after another; speak at each `say "..." now` prompt. A phrase recorded in silence makes the script exit 1 at once (`FAIL: no speech in the audio`), so be ready before you press Enter. On the Jetson always use `--record`, because the default audio comes from macOS `say`.

P1 (slot 0, Fire Mage phrases):
```bash
uv run --env-file .env python scripts/check_muse.py --record 4 --slot 0 --keywords words --phrase "embers of the forty acres burn" --phrase "rise crimson rampart"
```

P2 (slot 1, Lightning Mage phrases):
```bash
uv run --env-file .env python scripts/check_muse.py --record 4 --slot 1 --keywords words --phrase "lightning answer my call" --phrase "hum of the restless grid"
```

For each phrase it prints the first partial, first match, perfect and charge times (seconds after the end of speech) and a final line `suggested game.charge_window_s = ...`. Exit 0: every run charged the right spell. Do a few clean readings and a few sloppy ones, so the held sub-perfect path gets measured. The WAVs are saved under `.superpowers/muse/`.

Crosstalk check: run the P2 command with P2 silent while P1 reads P2's phrase out loud from P1's spot. A good result is `FAIL: no speech in the audio` or no charge. If P2's mic charges the spell, move the players apart or turn the receiver gain down.

## 6. Run the game

```bash
DISPLAY=:0 scripts/run_demo.sh
```

On the Jetson it runs fullscreen, passes `--env-file .env` if `.env` exists, and records every run to `recordings/<timestamp>/` (session files plus `game.log`). A crash restarts the game (at most 5 times in 60 s). `Esc` quits the game and ends the launcher. Ctrl-C in the terminal stops both.

Useful forms:
```bash
DISPLAY=:0 scripts/run_demo.sh -- --debug        # start with the F1 overlay on and print perf to stderr
DISPLAY=:0 scripts/run_demo.sh --windowed        # not fullscreen
DISPLAY=:0 scripts/run_demo.sh --no-record       # no session recording
scripts/run_demo.sh --dry-run                    # print the command it would run
DISPLAY=:0 scripts/run_demo.sh --fake            # keyboard players, no camera or mics
```

Without the launcher: `DISPLAY=:0 uv run --env-file .env python -m magic_box --fullscreen`.

What a good start looks like:
1. **Boot** lists `camera`, `mic P1`, `mic P2`, `network` and `api key`, each with a check or a cross. It goes to the lobby once the camera has sent a frame (2 s at the earliest), or at 8 s whatever the checks say.
2. **Lobby** banner: `SAY NAME · SAY FIRE, LIGHTNING OR HOLY · HANDS UP`. Each player's card shows TRACKED and MIC OK. Say your name and class, then **wait until your card shows your name and class before raising your hands**: the final transcript arrives about 3 s after you stop talking.

**If something is wrong at the venue**
- **CAMERA RECONNECTING for more than 30 s:** press `Esc` and rerun the launcher. Do not unplug the camera. If perception dies six times (the first run plus five restarts; the count resets after `pipeline.restart_reset_s`, 60 s, of healthy running) after it had delivered frames, the game exits with code 3 and prints `perception gave up`; `run_demo.sh` then starts the game again by itself, with fresh camera and voice processes. A laptop without `pyzed` never delivered a frame, so it does not exit (it stays on CAMERA RECONNECTING).
- **`check_env.py` doesn't list both mics:** swap in the spare mic before starting. If one mic fails to open at start, only that player gets `no mic` (MIC OFF) and the other keeps working; spell keys still work for the dead one.
- **Wi-Fi is down:** the boot `network` check fails and the game uses the config incantations and the template chronicle at once, with no 8 s wait. **Restarting the game re-probes the network**, so after Wi-Fi comes back, restart it (`Esc`, then the launcher).
- **The ZED takes a long time to open:** time from launch to the first frame in the boot log, then set `pipeline.camera_boot_timeout_s` (5.0) above it in `config.local.yaml`. Until then a slow open shows a failed `camera` check.
- If the voice process dies, both mics show MIC OFF until it restarts and connects again.

## 7. Tune

Change values in `config.local.yaml` on the Jetson, then quit (`Esc`) and start again. Note what worked and move it into `config.yaml` with its owner afterwards.

**Debug overlay** (`F1`, or start with `-- --debug`):
- Header: render fps, camera fps, dropped queue items, and stage times `poll / intent / engine / draw` in ms plus `lat` (PlayerState to draw). `--debug` also prints a `perf:` line with the worst tick every 10 s.
- A panel per half: tracked or lost, distance and zone, pose flags, and a `wrist_vz` graph with the red push threshold line. The panel flashes on a push.
- A top-down map in meters below the panels, mirrored like the players' view.
- Render fps: a macOS laptop shows about 48 fps because its sleep oversleeps (frame work is only 2-5 ms). On the Jetson the header should read about 60. If it also reads about 48 there, the fix is in `Window.tick` (`render/window.py`): tell Nikhil.

**What to change**

| Symptom | Key (default) | Direction |
|---|---|---|
| Basic attacks feel laggy with the mics on | `game.release_grace_s` (0.6) | Lower to 0.3, or 0 to turn the hold off. It holds an uncharged push this long in case a voice charge is about to land, but only while the player can afford, by the end of the hold, a spell that push could release (mana regen during the hold counts; out of mana, the basic fires at once). First knob to try. |
| A spoken spell fizzles before the player can push | `game.charge_window_s` (3.0) | Raise to 3.5. Lower toward 2.5 only if `check_muse.py` suggests it with real voices. |
| The charge lands too long after speaking | `voice.perfect_hold_s` (0.5) | Lower to 0.25, or 0 (publish the first match). Costs ×1.15 perfect bonuses. |
| The ×1.15 perfect bonus almost never fires | `voice.perfect_hold_s` (0.5) | Raise to 0.8. Charges land later. |
| Correct incantations don't charge | `voice.match_threshold` (80) | Lower to 70. Watch for wrong-spell charges. |
| Two-hand pushes come out as one-hand pushes | `intent.two_hand_window_s` (0.1) | Raise to 0.15-0.2. Every one-hand push waits this long. |
| Two-hand pushes are still missed after raising `two_hand_window_s` | `perception.push_peak_wait_s` (0.1) | Lower to 0.05. Change it only for missed two-hand pushes: the push is emitted sooner after the crossing, so `Push.speed` is less of a peak. Validation caps it at 0.1. |
| Punches don't fire (`wrist_vz` never crosses the red line) | `perception.push_speed_mps` (1.5) | Lower to 1.2. Also `perception.push_min_travel_m` (0.12) down to 0.08. |
| Pushes fire on their own (gesturing, talking with hands) | `perception.push_speed_mps` (1.5) | Raise to 1.8, or raise `push_min_travel_m`. |
| One punch fires twice | `perception.push_cooldown_s` (0.4) | Raise to 0.6. |
| Dodges are missed | `intent.dodge_step_m` (0.3) / `intent.dodge_duck_m` (0.25) | Lower to 0.2 / 0.15. |
| Dodges fire by accident | same keys | Raise. |
| Hands up flickers, the lobby won't start | `perception.hands_up_margin_m` (0.10), `game.hands_up_hold_s` (0.3) | Lower the margin to 0.05. Keep the hold at 0.3 or raise it. |
| Heal (hands together) won't trigger | `perception.hands_together_max_m` (0.25) | Raise to 0.35. |
| The fight pauses (STEP INTO VIEW) too often | `game.pause_after_s` (2.0), `perception.slot_hold_s` (1.0) | Raise either. |
| Bystanders get tracked | `camera.max_range_m` (3.5) | Lower to the back of the play area. |
| Zone readout disagrees with the floor tape | `perception.zones.danger_max_m` (1.6), `far_min_m` (2.4) | Match the tape, or move the tape. |
| Every hit lands at the same multiplier | `game.combat.speed_ref_mps` (2.0) | `Push.speed` is now the punch's peak. Check `best_push_mps` on the victory screen and set the reference near a typical punch. |
| Loading card shows the config incantations (Spark fell back) | `ai.timeout_s` (8), `game.loading_max_s` (10) | Check Wi-Fi first (phone hotspot). If Spark times out often, raise `ai.timeout_s` and keep `game.loading_max_s` above it. |
| Players can't finish reading their incantations before the fight | `game.loading_read_s` (4.0) | Raise to 6. The loading card stays up at least this long after the incantations arrive, with no countdown until they do. Lower it if loading drags. The Muse sessions open as soon as the incantations are known (handshake 0.4-1.1 s), so keep it above about 1.5 s. |
| Holy Light or Heal doesn't fire when the pose is made on the last word | `game.pose_grace_s` (1.0) | Raise to 1.5. A charge releases a pose that is already held only if the pose rose within this time before the charge. |
| A buff fires from a pose held since before the incantation | `game.pose_grace_s` (1.0) | Lower to 0.6. Hands up held since the lobby never releases; a new pose edge does. |
| A child process keeps dying and the box restarts too often | `pipeline.restart_reset_s` (60), `pipeline.max_restarts` (5) | A child that runs `restart_reset_s` without dying gets its restart count back. |
| Players leave victory before reading the chronicle, or it keeps them waiting | `game.victory_read_s` (4.0) | Raise to 6 to give the chronicle more time; lower it if players stand with hands up and nothing happens. `victory_max_s` (30) still ends victory. |
| Sound too loud or too quiet | `render.audio.volume` (0.6) | Adjust. `render.audio.enabled: false` mutes. |
| K.O. effect gets cut off, or the frozen fight outlasts it | `game.ko_hold_s` (2.5), `render.fx.ko_s` (2.5) | Change both together and keep them equal. Validation rejects `fx.ko_s` above `ko_hold_s`. |

**Jetson fps fallbacks.** If render fps drops below 60, try these in order (details in `src/magic_box/render/CLAUDE.md`):
1. `render.crop_cache: true` (the default): reuses the scaled crop while it barely moves.
2. `render.self_view: false`: skips the mirrored self-view and its skeleton.
3. `render.camera_scale_quality: fast` (the default). Keep it on the Jetson.
4. `display.vsync: true` only if the picture tears. It caps fps at the monitor rate.
5. FX: lower `render.fx.max_particles` (160), `render.projectiles.trail_steps` (6) and `render.projectiles.glow_max_px` (224).
6. Lower `display.fps`, or use `camera.body_format: BODY_18` with `camera.body_fitting: false`.

If camera fps (header) is the low one, it is perception, not render: see step 3.

## 8. Recordings and backup

**Session recordings.** `run_demo.sh` records every run to `recordings/<timestamp>/`. Copy a good match to a laptop as a backup (on the laptop):
```bash
rsync -az <user>@<jetson-ip>:magic-box/recordings/<timestamp> recordings/
uv run python -m magic_box --replay recordings/<timestamp>
```
A replay has no video. It redraws the players as silhouettes from the recorded states.

**SVO recordings** (real video and depth, for offline tuning on the Jetson). Quit the game first: only one process can open the camera.
```bash
uv run python scripts/record_session.py --seconds 120
```
It writes `recordings/session-<timestamp>.svo2` (or `--out PATH`). Ctrl-C closes the file cleanly. To tune against it, add this to `config.local.yaml` and run the game as usual (the SVO loops):
```yaml
camera:
  svo_path: recordings/session-<timestamp>.svo2
```
**Remove `svo_path` before the demo**, or the game plays the recording instead of the camera.

Record SVOs of: two-person punches at each distance, one- and two-hand pushes, sidesteps and ducks, arm overhead and hands together.

**Demo video backup.** Film the screen and players on a phone during a good match, as well as recording. Video is the deliverable that can't be redone after 11:30.

## 9. Bug bash

Run with `-- --debug` so the overlay is one key away. Tick each line, and write down anything that fails with the time and the session folder name.

**Boot**
- [ ] All five lines show; camera goes green once frames arrive; boot leaves then (2 s at the earliest).
- [ ] Without `.env` (`mv .env .env.off`, run, then `mv .env.off .env`): `api key` is a cross, boot still reaches the lobby by 8 s, spell keys work.
- [ ] Wi-Fi off: `network` is a cross; boot still reaches the lobby.

**Lobby**
- [ ] "My name is Ada" sets the name. It shows after about 3 s (Muse waits for silence before the final transcript).
- [ ] "Fire", "lightning", "holy" and "knight" each pick a class; the last keyword said wins. If Muse writes "lightening", that works too.
- [ ] "My name is Ada, fire" sets both.
- [ ] Chatter ("I'm ready", "so what do I do now", "this is cool") does not rename anyone. A one- or two-word reply ("Bob") does.
- [ ] Both raise hands and hold about 0.3 s: loading starts. A one-frame flicker does not start it.

**Loading**
- [ ] Each half shows its player's class, incantations and release cue. Long incantations shrink and wrap instead of being cut off.
- [ ] No countdown until the incantations arrive (about 3-4 s with Spark), then at least 4 s (`loading_read_s`) to read them before the fight.
- [ ] The incantations are Spark-written, not the config ones (for example, not "embers of the forty acres burn").

**Fight: each spell** (say it, then release). Damage and effects show on the target's half.
- [ ] Fireball: push. Hit flash and damage number.
- [ ] Flame Wall: two-hand push. SHIELD UP; the next incoming hit shows BLOCKED and does no damage.
- [ ] Inferno: push. Target shows SLOWED; their next charge window is shorter.
- [ ] Bolt: push. Fast (0.9 s travel).
- [ ] Chain: push. Three bolts 0.25 s apart; each needs its own dodge.
- [ ] Static Field: two-hand push. Target shows MANA SLOWED; their mana refills slowly for 5 s.
- [ ] Holy Light: one arm overhead. EMPOWERED; hits for 6 s do ×1.5. Also raise the arm on the last word of the incantation: the spell fires when the charge lands (`pose_grace_s`).
- [ ] An arm already up since before the incantation does not fire Holy Light; lower it and raise it again.
- [ ] Heal: hands together at the chest. +25 HP, not above 100.
- [ ] Judgment: push.
- [ ] Spell keys (P1 `1 2 3`, P2 `8 9 0`) charge the same spells with no voice.
- [ ] A clean reading gets the ×1.15 perfect bonus sometimes (watch the damage number).

**Fight: everything else**
- [ ] Basic attack: a push with nothing charged. With mics on it lands about 0.6 s late (`release_grace_s`). Out of mana for every spell that push could release, it fires at once.
- [ ] Say a spell and push on the last word: the spell fires, not a basic attack. This works even right after a basic attack, during its cooldown.
- [ ] With mics on, spam basic attacks (push, push, push): they keep firing every 0.8 s (the cooldown), each up to 0.6 s after the push, and never stall.
- [ ] Dodge by a 0.3 m sidestep and by a 0.25 m duck during the red ring: DODGE! and no damage.
- [ ] Damage rises when the players stand closer: the distance multiplier runs from ×1.4 at 1.2 m to ×0.7 at 2.8 m, for the attacker at release and the defender at impact.
- [ ] One player steps out for more than 2 s: the fight freezes and the banner counts down (`STEP INTO VIEW · 20`, `· 19`, ...); stepping back resumes it.
- [ ] One player stays out about 22 s (2 s to pause, then `abandon_after_s` 20 s): the match ends and the tracked player wins.
- [ ] KO: the fight freezes for `game.ko_hold_s` (2.5 s) while the K.O. overlay and slow-motion effects play (`render.fx.ko_s`, 2.5 s), then victory.
- [ ] Time-out at 90 s: higher HP wins.

**Sound** (synthesized at startup with numpy; nobody has heard it on real speakers yet)
- [ ] Listen on the venue speakers or monitor audio: cast whoosh, hit thump, dodge swish, block clang, heal chime, buff shimmer, K.O. boom, the loading countdown tick, the fight's last-5-seconds tick and the match-start fanfare.
- [ ] Set `render.audio.volume` (0.6) so it is clear but not harsh. If any sound is bad, `render.audio.enabled: false` mutes them all.

**Victory and rematch**
- [ ] Winner headline, a stats card per player, the chronicle (Spark-written with Wi-Fi, a template without).
- [ ] Hands up does nothing until 5 s have passed and the chronicle has been on screen for 4 s (`victory_read_s`; Spark, or the template within 8 s). Then both raise their hands: back to the lobby with names and classes kept. After 30 s it goes back on its own. Hands still up from victory don't start a match: lower them, then raise them again.

**Failures**
- [ ] Network off mid-match: MIC OFF; spell keys still work; the next loading card uses config incantations; the chronicle uses the template. Network back on: mics reconnect within about 10 s.
- [ ] Camera: **do not unplug it** to test this (GMSL2). Cover the lens instead to test the tracking pause. The CAMERA RECONNECTING path is covered by unit tests only.
- [ ] `Esc` quits within about a second, and the next start opens the camera without a daemon restart.
- [ ] Ten minutes of play without a frame-rate drop or a restart in `game.log`.
- [ ] Optional, while nobody plays: `uv run python scripts/soak.py --seconds 600` (fake mode, headless, random inputs). It prints fps and RSS samples and exits 1 on a crash or memory growth.

## 10. Before judging

- [ ] `config.local.yaml` has the real mics and no `svo_path`.
- [ ] `.env` is present; `check_spark.py` passes on the venue Wi-Fi, or the phone hotspot is connected.
- [ ] Camera level and centered; floor tape at 1.6 m and 2.4 m (`perception.zones`), far edge at 3.5 m.
- [ ] Game started with `DISPLAY=:0 scripts/run_demo.sh`. `F1` ready to show the depth overlay.
- [ ] Spare USB mic and the phone hotspot within reach.
