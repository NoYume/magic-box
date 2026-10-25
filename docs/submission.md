# Submission

**Owner:** Daniel

Devpost draft and the 2-minute demo video shot list. Deadline: **Sunday 2026-10-25, 11:30 CDT**.

Tracks: **Hardware**, **Meta** (Muse Voice Transcribe + Muse Spark), **Best Overall**.

Every number here was measured. Laptop numbers are labeled as laptop numbers. Lines marked `[TODO 08:00]` need a number from the Jetson session (`docs/runbook.md`) before submitting. If the number isn't measured by then, delete the line rather than guess.

---

## Devpost draft

### Magic Box

A two-player magic duel you play with your voice and your body. Say the spell, then throw it at the camera.

### Inspiration

We wanted a game where you cast a spell the way it happens in stories: you say the words, then you throw it. That needs two things a normal webcam game doesn't have. It needs real depth, so a punch toward the screen can be measured in meters per second and a dodge in meters. And it needs speech recognition fast enough to keep up with a fight. A ZED X stereo camera on a Jetson Orin Nano gives us the first. Meta's Muse Voice Transcribe and Muse Spark give us the second.

### What it does

Two players stand side by side in front of one monitor. The screen is split down the middle. Each player watches their own half, which shows a live close-up of the opponent.

- **Boot:** a self-check of the camera, both mics, the network and the API key.
- **Lobby:** each player says their name and a class (Fire Mage, Lightning Mage or Holy Knight), then both raise their hands to start.
- **Loading:** Muse Spark writes three incantations for each player, themed to their class and name. Each half shows them as a tutorial card.
- **Fight:** 90 seconds. A player reads an incantation into their own clip-on mic to charge a spell, then releases it with a gesture: a fast push toward the camera, a two-hand push, one arm overhead, or hands together at the chest. The defender sees the projectile coming and dodges by stepping aside or ducking.
- **Victory:** the winner, each player's stats, and a Duel Chronicle that Muse Spark writes from the match log.

Depth decides the fight:
- **Push speed** is the wrist's peak speed toward the camera in m/s, measured relative to the neck so walking forward doesn't count. Harder punches do more damage.
- **Distance** scales damage from ×1.4 at 1.2 m to ×0.7 at 2.8 m, for both the attacker and the defender. Stepping in is risky and rewarding.
- **Dodges** are a 0.3 m sidestep or a 0.25 m duck inside the last 0.6 s of a projectile's flight.

There are nine spells, three per class. Six do more than damage: a shield that blocks the next hit, a three-bolt Chain where each bolt needs its own dodge, slower mana regen for the target, a shorter charge window for the target, a heal and a damage buff. Press `F1` and a debug overlay shows a top-down map of both players in meters and each wrist's speed graph against the push threshold.

### How we built it

- **Hardware:** a Stereolabs ZED X on GMSL2 through a ZED Link capture card, a Jetson Orin Nano, an external monitor and one clip-on mic per player. Everything runs on the Jetson. No laptop is in the loop.
- **Three processes**, started with `spawn` and supervised (a crashed child restarts):
  - **Perception** is the only code that touches the ZED SDK. It runs depth and body tracking for two people, assigns them to player slots, detects pushes, poses and zones, and writes the camera image into a shared-memory double buffer.
  - **Voice** runs one Muse Voice Transcribe WebSocket per player mic, with that player's incantation words sent as keywords. It matches partial transcripts against only that player's spells with fuzzy matching.
  - **Game** is a pygame-ce loop that never blocks [TODO 08:00: add the measured fps on the Jetson]: fusion of body and voice into actions, the game rules, and the renderer. Muse Spark calls run on background threads with an 8 s deadline and a fallback.
- **Contracts:** every message between processes is a typed dataclass that round-trips to JSON lines. That gave us `--fake` mode (keyboard players and a synthetic camera) to build the game on laptops, and `--record` / `--replay` to replay real sessions.
- **Visuals and sound:** a HUD per player, five scenes, hit and K.O. effects, per-element projectiles with glows and trails, and sounds synthesized with numpy at startup. Titles use Cinzel Decorative (SIL Open Font License).
- **Tests:** 960 automated tests, run headless in GitHub Actions with Ruff lint and format checks. They include 30 end-to-end tests that drive the real game loop through whole fake matches on a fake clock. A soak script plays random fake matches for as long as you ask and watches fps and memory.

### Challenges we ran into

- **Spark was too slow at first.** With the model's default reasoning, generating six incantations ran past our 8 s deadline every time, so every match would have used the fixed fallback text. Setting `reasoning_effort: minimal` brought it to 3.1-3.8 s with all six incantations passing validation (laptop Wi-Fi, three runs).
- **Partial transcripts match early.** Muse's cumulative partials reach our match threshold on the first few words of a phrase, so the "perfect incantation" bonus almost never fired. We now hold a sub-perfect match for up to 0.5 s in case the full phrase lands.
- **A 30-character keyword limit.** Muse rejects the whole session handshake if any keyword is longer than 30 characters. We found this live and now send single words.
- **Voice is slower than a punch.** The charge lands about 0.4 s after the player stops talking. A player who punches on the last word would throw a basic attack instead of the spell, so the game holds an uncharged push for up to 0.6 s while that player's mic is on.
- **Peak speed, not threshold speed.** At first the push speed was read at the moment it crossed the threshold, which is almost the same for every punch. We now wait up to 0.1 s for the peak, so damage tracks how hard you punch.
- **GMSL2 is not hot-pluggable.** Re-plugging the camera while the Jetson runs needs a daemon restart, so the camera cable is taped down and nobody touches it.

### Accomplishments that we're proud of

- The full loop works end to end: boot, lobby by voice, Spark-written incantations, a fight driven by voice and body, and a Spark-written chronicle.
- Both Meta APIs were verified live. In 17 test sessions on a laptop with synthesized speech, Muse matched the right spell every time and never a wrong one.
- The game is built to keep running on bad venue Wi-Fi: spell keys always work, and incantations and the chronicle fall back to built-in text.
- Quitting takes 0.27 s even with a Spark call in flight (laptop test).
- `[TODO 08:00]` Jetson numbers: tracking fps and the share of frames with two people tracked (`bench_tracking.py`), and render fps with both players in the fight (F1 overlay).

### What we learned

- Depth makes body input honest. Speeds and distances in meters let us write rules a player can feel.
- Real-time speech has latency you have to design around, not just measure.
- Typed contracts between processes let four people build in parallel and test without the hardware.

### What's next

- Tune the numbers with more players: push threshold, dodge distances, charge window.
- More classes and spells, and gestures beyond pushes.
- An enclosure so the console is one box with a camera and a screen.
- Spectator view on a second display.

### Built with

Python 3.10, uv, pygame-ce, NumPy, Stereolabs ZED SDK (pyzed), ZED X, ZED Link, NVIDIA Jetson Orin Nano, Meta Muse Voice Transcribe, Meta Muse Spark, OpenAI Python SDK (for Spark's OpenAI-compatible API), websockets, sounddevice (PortAudio), RapidFuzz, PyYAML, pytest, Ruff, Claude Code.

---

## Numbers we can cite

| Claim | Number | Where measured |
|---|---|---|
| Muse spell matching | 17/17 sessions matched the right spell, none wrong | laptop, macOS `say` audio, 2026-10-25 |
| Muse charge latency | median +0.4 s after end of speech (range +0.2 to +0.6 s) with the 0.5 s hold | replayed from 13 laptop sessions' event times |
| Muse handshake | median 0.6 s (0.4-1.1 s) | laptop |
| Spark incantations | 3.1-3.8 s, 6/6 valid, `reasoning_effort: minimal` | laptop Wi-Fi, 3 runs |
| Spark with default effort | timed out at 8 s | laptop Wi-Fi |
| Spark chronicle | 1.6-1.7 s, 87-88 words | laptop Wi-Fi |
| Fight frame render time | about 2 ms; about 3 ms with heavy effects (3.9 ms worst) | Apple M5 laptop, SDL dummy video, not the Jetson |
| Quit with a Spark call in flight | 0.27 s | laptop |
| Automated tests | 960 passed, 2 skipped | laptop, 2026-10-25 05:20 |
| End-to-end tests (`tests/test_e2e.py`) | 30 passed in 15.6 s | laptop |
| 10-minute soak (`scripts/soak.py --seconds 600`) | no crash; 13 matches (11 KO, 2 time-outs); RSS 190 MB at the end, max 204 MB; draw 1.8-4.1 ms per frame | macOS laptop, before the last fix wave; 48 fps there is a macOS sleep artifact, not a Jetson number |
| Fast soak (`--fast`, fake clock) | about 34 minutes of game time in 5 min, 55 matches, no crash; RSS flat at 206-217 MB | macOS laptop |
| Tracking fps, two-person share | `[TODO 08:00]` | Jetson, `bench_tracking.py` |
| Render fps in a fight | `[TODO 08:00]` | Jetson, F1 overlay |
| Muse latency with real voices | `[TODO 08:00]` | Jetson, `check_muse.py --record` |

Don't claim a Jetson fps, a real-voice latency or a mic accuracy that isn't in this table.

---

## 2-minute demo video shot list

Film on a phone on a tripod, framing both players and the monitor. Record a few full matches and cut from the best. Keep the lav mics on so the incantations are audible.

| Time | Shot | What is on screen | Voice-over or caption |
|---|---|---|---|
| 0:00-0:08 | Cold open | P1 says an incantation and punches; a fireball flies on P2's half; P2's HP drops | (none, game sound) |
| 0:08-0:15 | Title card | "Magic Box" over the lobby | "A magic duel you play with your voice and your body." |
| 0:15-0:27 | Hardware | Close-ups: ZED X, the GMSL2 cable into the ZED Link card, the Jetson, the monitor | "A ZED X stereo camera and a Jetson Orin Nano. Everything runs on this box." |
| 0:27-0:37 | Boot and lobby | Boot check list going green; a player says "my name is Ada, fire" and the card updates | "Players pick a class and a name by voice." |
| 0:37-0:47 | Loading | The tutorial cards with Spark-written incantations | "Muse Spark writes each player's spells for this match." |
| 0:47-1:10 | Fight | A charge and push; a sidestep dodge (DODGE!); Flame Wall blocking a hit (BLOCKED!); a two-hand push; Holy Light or Heal with a pose | "Say it, then throw it. Step aside or duck to dodge." |
| 1:10-1:27 | Depth proof | Press F1: the top-down map in meters and the wrist speed graph crossing the red threshold line on a punch; a player steps closer and the damage number grows | "Push speed and distance are measured in meters. Harder and closer hits do more." |
| 1:27-1:42 | KO and victory | The K.O. slow motion, the victory screen with stats, a line of the chronicle | "Muse Spark writes the story of the duel." |
| 1:42-1:54 | How it works | A simple diagram: camera, three processes, Muse in the cloud; "video never leaves the box" | "Speech goes to Muse. Video stays on the Jetson." |
| 1:54-2:00 | End card | Team names (Daniel, Enoch, Nikhil, Adetola), "HackTX 2026", tracks | (none) |

Capture checklist:
- [ ] One clean match with a KO, start to finish, in one take.
- [ ] A dodge and a block in close-up on the defender's half.
- [ ] The F1 overlay during a punch, with the graph readable on camera.
- [ ] A player stepping from the far zone into the danger zone.
- [ ] Cutaways of the hardware with the game running.
- [ ] Room tone and game sound at a sensible level (the synthesized sounds have not been checked on real speakers yet).
