# Submission

**Owner:** Daniel

Devpost draft and the 2-minute demo video shot list. Deadline: **Sunday 2026-10-25, 11:30 CDT**.

Tracks: **Hardware**, **Meta** (Muse Voice Transcribe + Muse Spark), **Best Overall**.

Every number here was measured. Laptop numbers are labeled as laptop numbers. Lines marked `[TODO 08:00]` need a number from the Jetson session (`docs/runbook.md`) before submitting. If the number isn't measured by then, delete the line rather than guess.

---

## Elevator pitch

Magic Box is a two-player duel controlled by voice and motion. Say a Muse-written spell, then punch to cast it. A ZED X measures speed, distance and dodges in 3D while a Jetson runs the game.

## Devpost draft

### Magic Box

Say an incantation into your mic, then throw the spell at your opponent with a push toward the camera. Magic Box is a two-player duel played with voice and body movement.

### Inspiration

In stories, casting a spell takes words and a gesture. We wanted that moment to feel physical: if you punch harder or step closer, the hit should change. A webcam can't measure how fast a wrist moves toward it or how far someone steps to dodge. We used a ZED X stereo camera and a Jetson Orin Nano for depth and body tracking, with Meta's Muse Voice Transcribe for the spoken part. Muse Spark writes the words players cast.

### What it does

Two players stand side by side at one monitor. Each half of the screen shows a live close-up of the opponent. At startup, the game checks the camera, both mics, network and API key. In the lobby, players say their names and choose Fire Mage, Lightning Mage or Holy Knight by voice, then raise their hands to begin. Muse Spark writes three incantations per player, themed to their name and class, and the loading screen shows how to cast each one.

The fight lasts 90 seconds. Saying an incantation into a clip-on mic charges a spell; releasing it takes a fast push, a two-hand push, an arm overhead or hands together at the chest. The defender can see the projectile coming and step aside or duck. After the fight, the screen shows the winner, both players' stats and a Duel Chronicle written by Muse Spark from the match log.

The camera measures the wrist's peak speed toward it relative to the neck, so walking forward alone doesn't count as a punch. A harder punch does more damage. Distance matters for attacker and defender alike: the multiplier runs from ×1.4 at 1.2 m to ×0.7 at 2.8 m. A dodge takes a 0.3 m sidestep or a 0.25 m duck in the last 0.6 s of a projectile's flight.

Each class has three spells. Six have effects beyond damage: a shield against the next hit, a three-bolt Chain that requires three dodges, slower mana regeneration or a shorter charge window for the target, a heal, and a damage buff. `F1` opens a debug overlay with both players on a top-down map in meters and a graph of each wrist's speed against the push threshold.

### How we built it

A Stereolabs ZED X connects over GMSL2 through a ZED Link capture card to a Jetson Orin Nano. The Jetson drives the monitor and runs the game; each player has a clip-on mic. There is no laptop in the demo loop.

Three supervised processes start with `spawn`, and a crashed child restarts. Perception alone accesses the ZED SDK. It tracks two bodies, assigns player slots, detects pushes and poses, and puts camera frames in a shared-memory double buffer. Voice keeps a Muse Voice Transcribe WebSocket open for each mic; it sends that player's incantation words as keywords and fuzzy-matches partial transcripts against their spells. The pygame-ce game loop fuses voice and body input, runs the rules and draws the screen without blocking [TODO 08:00: add the measured fps on the Jetson]. Muse Spark runs in background threads with an 8 s deadline and fallback text.

Typed dataclasses carry messages between processes and round-trip to JSON lines. We could build on laptops using `--fake`, with keyboard players and a synthetic camera, then use `--record` and `--replay` for real sessions. The game has a HUD for each player, five scenes, hit and K.O. effects, projectiles with glows and trails, and sounds synthesized with NumPy at startup. Titles use Cinzel Decorative (SIL Open Font License).

We run 960 automated tests headless in GitHub Actions alongside Ruff lint and format checks. Thirty end-to-end tests play whole fake matches on a fake clock. A soak script plays random matches and watches frame rate and memory use.

### Challenges we ran into

Muse Spark initially missed our 8 s deadline when generating six incantations with its default reasoning setting. With `reasoning_effort: minimal`, it took 3.1-3.8 s and all six incantations passed validation in three runs on laptop Wi-Fi.

Muse's cumulative partial transcripts can match a spell after only the first few words. That meant the full-phrase "perfect incantation" bonus rarely fired. We now wait up to 0.5 s on a sub-perfect match to give the rest of the phrase time to arrive. We also found that one keyword longer than 30 characters makes Muse reject the entire session handshake, so we send single words.

Speech and gestures arrive on different clocks. In our laptop tests, the charge arrived about 0.4 s after speech ended. If someone punched on the last word, they got a basic attack instead of their spell. While that player's mic is on, we now hold an uncharged push for up to 0.6 s. For punches, reading speed as soon as it crossed the threshold made nearly every hit look alike. We wait up to 0.1 s for the wrist's peak speed instead.

The GMSL2 camera connection isn't hot-pluggable. Re-plugging it while the Jetson runs requires a daemon restart, so we taped down the cable.

### Accomplishments that we're proud of

We have the full sequence from boot and voice-controlled lobby through Spark-written incantations, a voice-and-body fight and the match chronicle. Both Meta APIs were verified live on a laptop. Using synthesized speech, Muse matched the correct spell in all 17 test sessions and made no wrong matches. Spell keys and built-in text for incantations and the chronicle let the game run when venue Wi-Fi fails. A laptop test also measured 0.27 s to quit with a Spark request still in flight.

`[TODO 08:00]` Add Jetson tracking fps and the share of frames with two people tracked (`bench_tracking.py`), plus render fps during a fight with both players (F1 overlay).

### What we learned

Measuring depth in meters let us tie damage and dodges to movements players can feel. We also had to make room for speech latency in the rules: a correct transcript that arrives after the punch is too late without a grace period. Typed contracts let four of us build and test separate processes before we had the hardware together.

### What's next

We want to test with more players and tune the push threshold, dodge distances and charge window. We'd also like more classes, spells and gestures beyond pushes, a single enclosure for the camera and screen, and a spectator view on a second display.

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
