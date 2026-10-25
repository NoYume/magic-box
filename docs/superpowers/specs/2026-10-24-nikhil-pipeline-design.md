# Intent, voice, Spark, replay and a thin engine: design

**Date:** 2026-10-24
**Status:** approved design, pending written-spec review
**Parent spec:** `docs/superpowers/specs/2026-10-24-magic-box-design.md` (this document narrows its §8 rows for `intent/`, `voice/`, `ai/`, `replay/` and the `pipeline/` loop, and adds a placeholder `game/` engine that Adetola replaces)
**Sibling spec:** `docs/superpowers/specs/2026-10-24-perception-zedx-design.md` (produces the `PlayerState` stream this design consumes)

## 1. Summary

Fill in Nikhil's side of the console so a full match plays end to end: players say their names in the lobby, Muse Spark writes each player's incantations during loading, a player speaks an incantation into their own mic to charge a spell and releases it with the spell's gesture, the spell flies on the defender's half, a step or duck in the last moment dodges it, and Spark writes a Duel Chronicle at the end. Every cloud piece has a local fallback, so the game also plays with no Wi-Fi, no key and no mics, using the spell keys.

Adetola's engine is a placeholder that ignores every `Action`, so this phase also fills Adetola's `game/` stub files with a thin, config-driven engine (Appendix A of the parent spec, minus the effects of spells that do no damage). Adetola extends or replaces it in place.

## 2. Goals and success criteria

1. `uv run python -m magic_box --fake` plays a full match: both raise hands (`r` + `y`) → loading countdown with incantations on screen → fight: charge with `1`, push with `f`, a projectile flies on P2's half and P2's HP drops; duck (`n`) during the red window avoids it → KO or time-out → victory with a chronicle → both raise hands → lobby.
2. `uv run python -m magic_box --fake --headless --max-ticks 600` runs clean.
3. In live mode with `META_MODEL_API_KEY` set and mics configured, each player's spoken incantation (and nothing from the other player's set) charges their spell; lobby speech sets names; the HUD shows MIC OK / MIC OFF per player.
4. With no key, no network or no mics, the game still plays: config incantations, template chronicle, spell keys, MIC OFF.
5. `--record DIR` writes a session; `--replay DIR` plays it back on a laptop with silhouettes drawn from the recorded states.
6. `uv run pytest`, `uv run ruff check` and `uv run ruff format --check` are clean. No test touches the network, a mic or `pyzed`.

## 3. Non-goals

- Effects of spells that do no damage (Flame Wall block, Static Field slow, Holy Light buff, Heal). They spend mana, log a `cast` event and show a banner, nothing more. Chain hits once.
- Class selection. Classes stay fixed from `game.default_classes`.
- The `boot` scene and its self-check screen (spec §10). The engine starts in `lobby`.
- Final HUD and scene art. The render changes here are plain-text placeholders for Adetola.
- `frames.mp4` in recordings (decision below).
- Finger gestures (closed as out in the perception spec).

## 4. Decisions

| Decision | Choice |
|---|---|
| Scope | Nikhil's stubs **plus a thin engine** in Adetola's existing `game/` files (approach A). Rejected: a throwaway single-file engine; implementing every spell effect (that decides Adetola's balance). |
| Build order | Vertical slices: intent + engine + projectiles (M2) → voice (M4) → Spark + names + chronicle (M5/M6) → replay. |
| Two-hand push | Recognised by intent within `intent.two_hand_window_s` (0.1 s) on either side of the push; every push is held up to 0.1 s to wait for the other hand. Carried as `Action.two_hand`. |
| Lobby names | Transcript `VoiceEvent`s become `Action(kind="speech", text=...)`; the engine decides what speech means per scene. |
| Mic status | New `VoiceEvent` kind `"status"`; the loop passes it to `engine.provide_mic_status()`. |
| Release cues | `SpellView.release` lets the HUD and loading card say exactly how to cast. |
| Muse mode | `ENDPOINTING` with `CUMULATIVE` partials in both lobby and fight; keywords fixed at the handshake, so a mode change restarts the sessions. |
| Matcher | Sliding word window + `rapidfuzz.fuzz.ratio`. Rejected: `partial_ratio` (scores a half-said partial at 100). |
| Mic devices | One input stream per distinct device, channels split to slots (a stereo wireless receiver is one device). |
| Spark model | `muse-spark-1.3` (current per dev.meta.ai), in config. |
| Replay frames | Not recorded. The Jetson already records SVO; laptop replay draws fake-mode silhouettes from the recorded states. Avoids `cv2` video codecs. |
| Fake mode | New two-hand push key: P1 `v`, P2 `m`. |

## 5. Module layout

| File | Owner | Change |
|---|---|---|
| `core/contracts.py` | Nikhil | `Action.two_hand`, `Action.text`, action kind `"speech"`, voice kind `"status"`, `SpellView.release` (§6) |
| `core/config.py` | Nikhil | Validate the new `game`, `voice`, `ai` keys (§14) |
| `intent/fusion.py`, `intent/dodge.py` | Nikhil | Implement (§7) |
| `game/classes.py`, `spells.py`, `combat.py`, `state.py`, `scenes.py`, `engine.py` | Adetola | Thin engine (§8). Module docstrings note "thin placeholder rules; replace freely". |
| `voice/matcher.py`, `mic.py`, `muse_stream.py`, `process.py` | Nikhil | Implement (§9) |
| `ai/spark_client.py`, `incantations.py`, `chronicle.py` | Nikhil | Implement (§10) |
| `ai/worker.py` | Nikhil | New: `AiWorker` (§10) |
| `pipeline/loop.py`, `main.py` | Nikhil | Spark jobs, `VoiceConfig`, mic status, recorder (§11) |
| `render/projectiles.py` | Nikhil | Implement (§12) |
| `render/hud.py`, `render/scenes/{lobby,loading,victory}.py` | Adetola | Plain-text placeholders (§12) |
| `replay/record.py`, `replay/play.py`, `replay/fake_input.py` | Nikhil | Implement; extract silhouette drawing; two-hand key (§13) |

Import boundaries are unchanged: `game/` stays pure Python; `sounddevice` only inside functions; `websockets` and `openai` are already dependencies. No new dependencies.

## 6. Contract changes (heads-up to Adetola and Enoch; root `CLAUDE.md` updated in the same change)

```python
ACTION_KINDS = ("charge", "push", "pose", "dodge", "speech")
VOICE_KINDS = ("incantation", "transcript", "status")

@dataclass(frozen=True)
class Action:
    ...existing fields...
    two_hand: bool = False   # push: the other hand crossed the push threshold within two_hand_window_s
    text: str = ""           # speech: final transcript of one speech turn

@dataclass(frozen=True)
class SpellView:
    id: str
    name: str
    incantation: str         # "" while loading and not yet written
    cost: float
    charged: bool
    release: str = "push"    # push | two_hand_push | arm_overhead | hands_together
```

- `VoiceEvent(kind="status")` carries `text` = `"connected"` | `"reconnecting"` | `"no mic"` | `"no api key"`, `spell_id=None`, `match_score=0`.
- All new fields have defaults, so `core/serde.py` round-trips them with no change.
- `Engine` gains `provide_mic_status(slot: int, ok: bool) -> None`; `step`, `provide_incantations`, `provide_chronicle` keep their signatures.

## 7. Intent (`intent/`)

`Intent.update(states, voice, now) -> list[Action]` runs every tick on **all** drained states (not just the newest per slot) and skips states with `tracking_ok=False`. No I/O, no wall clock; time is `t` on the contracts and `now` (both `time.monotonic()`).

- **Push.** A tracked state with `push` set opens a pending push for its slot (one at a time; a second push while one is pending is dropped). Let `thr = cfg.perception.push_speed_mps` and `w = cfg.intent.two_hand_window_s`. The other hand is "in" when its `wrist_vz <= -thr` in any tracked state of that slot with `t` in `[push.t - w, push.t + w]`. Intent keeps the last `w` seconds of `wrist_vz` per hand to check the past side.
  - Other hand already in → emit `Action("push", two_hand=True)` at once.
  - Else hold. Emit `two_hand=True` as soon as the other hand comes in, or `two_hand=False` once `now >= push.t + w`.
  - The action carries the original `push`, `t = push state's t`, `dist = root[2]` at the push.
- **Pose.** A flag present in a tracked state's `pose_flags` but not in that slot's previous tracked state emits `Action("pose", pose=flag, dist=...)`.
- **Charge.** `VoiceEvent(kind="incantation")` with a `spell_id` → `Action("charge", spell_id, match_score, dist=<slot's latest tracked root Z, else 0.0>)`.
- **Speech.** `VoiceEvent(kind="transcript")` → `Action("speech", text=event.text)`.
- **Status.** Ignored by intent (the loop routes it, §11).
- **Dodge** (`DodgeDetector.update(state) -> "step" | "duck" | None`, one window per slot of `(t, root.x, head.y)` over `dodge_lookback_s`, oldest samples dropped by `t`).
  - `"step"` when `|root.x_now - x_i| >= dodge_step_m` for some sample in the window.
  - `"duck"` when `head.y_now - min(head.y in window) >= dodge_duck_m` (+Y is down, so ducking increases `y`).
  - Step wins if both fire on the same state. After reporting, the slot's window is cleared, so one movement gives one action.
  - Each report emits `Action("dodge", dodge=..., dist=...)`.
- Output order within a tick: charges and speech first, then per-state push/pose/dodge in state order, then pushes released by timeout.

## 8. Thin engine (`game/`)

Pure Python, every number from `cfg.game` (plus `cfg.voice.perfect_threshold`). `Engine.step(actions, states, now)` applies actions in order, then advances time, then builds the `GameView`. `states` is the loop's newest state per slot (stale states already marked untracked).

- **`classes.py`:** `class_ids(cfg)`, `class_name(cfg, class_id)`.
- **`spells.py`:** `SpellDef(id, name, cost, damage, travel_s, release, fallback: dict[int, str])`; `load_spells(cfg, class_id) -> list[SpellDef]`.
- **`combat.py`:** `speed_mult(speed, cfg)`, `dist_mult(dist, cfg)`, `damage(base, push_speed, atk_dist, def_dist, buff_mult, cfg)` with `push_speed=None` meaning a speed multiplier of 1.0.
  - `speed_mult = clamp(speed / speed_ref_mps, speed_mult_min, speed_mult_max)`.
  - `dist_mult` is linear from `near_mult` at `near_m` to `far_mult` at `far_m`, clamped outside.
  - `damage = base × speed_mult × dist_mult(atk_dist) × dist_mult(def_dist) × buff_mult`. A distance of 0 or less (unknown) uses a multiplier of 1.0.
- **`state.py` (`MatchState`):** per slot `PlayerMatch(name, class_id, spells, incantations, hp, mana, charge, basic_ready_at, mic_ok, last_dist)`; projectiles in flight; round timer; banner text and its expiry; event log for the current match.
  - **Charge** (`Action("charge")`): ignored outside `fight`, for a spell not in the player's class, or when `mana < cost`. Otherwise refund any current charge, subtract the cost, and store `Charge(spell, deadline = now + charge_window_s, score)`. An expired charge is dropped and refunded.
  - **Release:**
    - push, `two_hand=False`: releases a charged `push` spell;
    - push, `two_hand=True`: releases a charged `two_hand_push` or `push` spell;
    - pose `hands_up`: releases `arm_overhead`; pose `hands_together`: releases `hands_together`.
    - A push that releases nothing is a **basic attack** if `now >= basic_ready_at` (`basic_attack_damage`, `basic_attack_travel_s`, spell id `"basic"`, sets `basic_ready_at = now + basic_attack_cooldown_s`). A charge whose release doesn't match stays charged.
  - **Cast:** a spell with `damage > 0` launches a projectile toward the other slot: `origin_px` is the push's `origin_px`; for a pose release, the caster's wrist keypoint (`r_wrist`, else `l_wrist`) or the center of `bbox_px`. `buff_mult = perfect_mult` when the charge score `>= voice.perfect_threshold`, else 1.0. A spell with `damage == 0` sets the banner to its name in capitals with "!" for `banner_s`. Both log `cast`.
  - **Projectiles:** `progress = (now - launched) / travel_s` (`travel_s == 0` hits at once); `in_dodge_window = travel_s - (now - launched) <= dodge_window_s`. A `dodge` action from the target removes every projectile aimed at them that is in its window and logs one `dodge` per projectile. At `progress >= 1`: damage with the attacker's `dist` at release and the defender's `last_dist` at impact; HP drops (floored at 0); `hit` logged. HP reaching 0 logs `ko`.
  - **Regen:** `mana_regen_per_s × dt`, capped at `mana_max`.
- **`scenes.py` (`SceneMachine`):** scenes `lobby → loading → fight → victory → lobby`. "Both ready" means both slots tracked with `hands_up` in `pose_flags` on the same tick.
  - **lobby:** banner `"SAY YOUR NAME · BOTH RAISE YOUR HANDS"`. `speech` actions set the speaker's name: lowercase-strip leading "my name is", "i'm", "i am", "this is", "call me", "it's"; drop punctuation; title-case; cap at `name_max_chars`. Empty results are ignored. Names default to `P1`, `P2` and persist across matches until changed. Both ready → loading.
  - **loading:** incantations start empty. `provide_incantations()` is accepted only in this scene (validated to contain every spell id per slot; missing ids take the config fallback). Leaves when `elapsed >= loading_min_s` and incantations are set; at `loading_max_s` the engine sets the config fallback itself. `timer_s` = `max(0, loading_min_s - elapsed)`.
  - **fight:** on entry, reset HP, mana, charges, projectiles, timer `round_s`, banner `"FIGHT!"` for `banner_s`, log `match_start` (`names`, `classes`). Ends on `ko`, or at time-out with the higher HP winning (equal HP is a draw); logs `match_end` (`winner` slot or None, `reason` `"ko"` or `"time"`, `hp`). Pause: if either slot is untracked for more than `pause_after_s`, the timer, regen, charge deadlines and projectiles freeze and the banner is `"STEP INTO VIEW"` until both are tracked again.
  - **victory:** banner `"<NAME> WINS"` or `"DRAW"`; `chronicle` is `None` until `provide_chronicle()` (accepted only in this scene). Returns to lobby when both ready after `victory_min_s`, or at `victory_max_s`.
- **`engine.py`:** facade that owns `MatchState` and `SceneMachine`, routes actions, and builds `GameView` / `PlayerView` / `SpellView` (with `release` and `charged`) / `ProjectileView`. `step` returns the `GameEvent`s logged that tick. `provide_mic_status(slot, ok)` sets `mic_ok`.
- **`GameEvent` data:** `match_start {names, classes}`, `cast {spell_id, release, two_hand}`, `hit {spell_id, damage, target, hp_left}` (slot = attacker), `dodge {spell_id, dodge}` (slot = defender), `ko {winner}`, `match_end {winner, reason, hp}`. Damage is rounded to 1 decimal in the log.

## 9. Voice (`voice/`)

Facts from Meta's realtime docs are in Appendix A.

- **Matcher** (`match_incantation(text, incantations, threshold) -> tuple[str, float] | None`):
  - Normalize both sides: lowercase, punctuation removed, whitespace collapsed.
  - Per spell with `n` words: for every window of `n-1`, `n` and `n+1` consecutive transcript words (sizes ≥ 1), `score = fuzz.ratio(window, incantation)`; the spell's score is the best window. A transcript shorter than the window sizes is scored as a whole.
  - Return the best spell if its score `>= threshold`, else `None`. Ties go to the first spell in the mapping.
- **Mic capture** (`MicHub(mics, sample_rate, chunk_ms)`):
  - Groups `voice.mics` entries by `device`; opens one `sounddevice.InputStream` per device with `channels = max(channel) + 1`, dtype int16.
  - Requests `sample_rate`; if the device rejects it, opens at the device's default rate and resamples each chunk to `sample_rate` with numpy linear interpolation.
  - The callback thread splits channels and delivers `chunk_ms` chunks of PCM16 little-endian bytes per slot to a sink (in the process: `loop.call_soon_threadsafe(queue.put_nowait, ...)`; a full queue drops the chunk).
  - `start()` raises `MicError` when PortAudio is missing or a device fails to open; `stop()` closes all streams. `sounddevice` is imported inside methods only.
- **Muse client** (`MuseStream(url, api_key, model, handshake_timeout_s)`):
  - `connect(keywords)`: opens the socket with `websockets`, sends as the first text frame
    ```json
    {"authorization": {"accessToken": "Bearer <key>"}, "audioEncoding": "PCM_16KHZ",
     "model": "<voice.model>", "mode": "ENDPOINTING", "partialMode": "CUMULATIVE",
     "emitAudioProgress": false, "keywords": ["..."]}
    ```
    (`keywords` omitted when empty), then waits up to `handshake_timeout_s` for the reply frame and stores its `sessionId`. An `error` frame or timeout raises `MuseError`.
  - `send_audio(pcm)`: one binary frame. `events()`: async iterator of parsed JSON dicts; ends when the socket closes. `close_code` property after close.
  - `close()`: sends `{"type": "endStream"}` if open, then closes the socket.
- **Voice process** (`run(cfg, voice_q, control_q, stop)` → `asyncio.run(...)`):
  - **Startup:** key from the env var named by `voice.api_key_env`. No key → publish `status "no api key"` for both slots and idle until `stop`. `MicError` → `status "no mic"` for both slots and idle. The process never exits on these, so the supervisor never restart-loops.
  - **Mode:** starts in transcript mode and waits for a `VoiceConfig`; incantation mode uses each slot's `incantations[slot]`.
  - **Per slot session task:** connect with keywords (incantation mode: the distinct words of that slot's incantations with at least `min_keyword_chars` letters; transcript mode: none) → `status "connected"` → run a sender and a receiver until the socket closes, `session_max_s` elapses, the config changes, or `stop` is set.
  - **Sender:** forwards that slot's mic chunks; if none arrives within `silence_after_s`, sends `chunk_ms` of zeros (Muse closes sessions that stop receiving audio).
  - **Receiver, incantation mode:** `speechStart` starts a turn and re-arms; each `transcript` (cumulative partial) is matched against **only that slot's** incantations with `match_threshold`; the first match publishes `VoiceEvent(slot, now, "incantation", text, spell_id, score)` and disarms until the next `speechStart`; `speechComplete` matches its final text once more if still armed. **Transcript mode:** each `speechComplete` with non-empty text publishes `VoiceEvent(slot, now, "transcript", text, None, 0)`. `error` events are logged. Unknown types are ignored.
  - **Reconnect:** on any close other than a config change or stop, publish `status "reconnecting"` and retry with exponential backoff from `reconnect_backoff_s` doubling to `reconnect_max_s`; the backoff resets after a session lasts 30 s. Close code 1008 logs the error loudly (bad request or pacing) and uses `reconnect_max_s`.
  - **Control:** a task drains `control_q` every 100 ms; the newest `VoiceConfig` wins. If the mode or a slot's incantations changed, both sessions close immediately (no drain) and reconnect with the new keywords.
  - **Stop:** a task watches the `stop` event, closes sessions (`endStream`) and stops the mics.

## 10. Spark (`ai/`)

- **`SparkClient(cfg)`:** `openai.OpenAI(base_url=ai.base_url, api_key=<env ai.api_key_env>, timeout=ai.timeout_s, max_retries=0)`, created lazily. `complete(system, user) -> str` returns the first choice's message content from `chat.completions.create(model=ai.model, temperature=ai.temperature, messages=[system, user])`. Raises `SparkUnavailable` when `ai.enabled` is false or the key is missing. Never logs the key.
- **Incantations:**
  - `fallback_incantations(classes, cfg) -> {slot: {spell_id: text}}` from each spell's `fallback[slot]`.
  - `generate_incantations(client, classes, names, cfg)`: prompt with both players' names, classes and spell names (with what each spell does); ask for only JSON `{"0": {spell_id: text, ...}, "1": {...}}`, `min_words`–`max_words` words each, Texas / Austin / HackTX flavor, easy to say aloud, the two players' sets clearly different. Strip a code fence if present, parse, validate per spell:
    - word count in `[min_words, max_words]`;
    - only letters, spaces and apostrophes;
    - unique within the player's own set;
    - `fuzz.ratio` against every incantation in the other player's set `< max_cross_similarity`.
  - An invalid or missing entry takes that spell's fallback. Validation runs slot 0 first, so slot 1 is checked against slot 0's final set. Any exception or unparseable reply → full fallback.
- **Chronicle:**
  - `template_chronicle(events, names) -> str`: 2–4 sentences from the log: who fought (names and class names), casts and hits per player, the biggest hit (spell, damage), dodges, and the ending (KO winner, time-out winner, or draw). Always returns text, including for an empty log.
  - `write_chronicle(client, events, names, cfg)`: sends a compact summary (the same counts and the ordered list of hits, dodges and the ending), asks for at most `chronicle_max_words` words of story using both names. Empty reply or exception → template.
- **`AiWorker(cfg, client_factory=SparkClient)`** (new `ai/worker.py`): a single-thread `ThreadPoolExecutor`.
  - `start_incantations(classes, names, now)` and `start_chronicle(events, names, now)` submit a job with deadline `now + ai.timeout_s`, replacing (and ignoring) any pending job of the same kind.
  - `poll(now) -> list[tuple[str, object]]` returns `("incantations", dict)` / `("chronicle", str)` for finished jobs; a job past its deadline returns its fallback instead and its late result is discarded. Never waits.
  - With `ai.enabled` false or no key, jobs resolve to the fallback immediately.
  - `close()`: `shutdown(wait=False, cancel_futures=True)`.

## 11. Game loop and `main.py`

`GameLoop` gains optional `ai: AiWorker`, `voice_control: DropOldestQueue` (the live `control_q`; `None` in fake and replay) and `recorder: SessionRecorder`.

- **First tick:** send `VoiceConfig(mode="transcript", incantations={})`.
- **Scene change** (compared with the previous tick's `view.scene`):
  - → `lobby`: send the transcript `VoiceConfig`.
  - → `loading`: `ai.start_incantations({slot: class_id}, {slot: name}, now)` from the view.
  - → `fight`: send `VoiceConfig(mode="incantation", incantations={p.slot: {s.id: s.incantation for s in p.spells}})`, so voice matches exactly what the HUD shows.
  - → `victory`: `ai.start_chronicle(events since the last match_start, names, now)`.
- **Every tick:** `ai.poll(now)` results go to `engine.provide_incantations()` / `provide_chronicle()`; status voice events go to `engine.provide_mic_status(slot, text == "connected")`; all voice events still go to intent. The loop keeps the current match's `GameEvent`s (reset at `match_start`).
- **Recorder:** each tick, `recorder.write_state` for every drained state, `write_voice` for every voice event (keyboard and status included), `write_event` for every `GameEvent`.
- `main.py` builds the `AiWorker` and, with `--record`, the `SessionRecorder` (live and fake); passes `runtime.control_q` in live mode; closes worker and recorder on exit. `--replay DIR` uses `ReplaySources(session_dir, cfg)` (it now passes `cfg` through to `SessionPlayer`). The two "exit 2" paths go away.
- Sending on `control_q` uses `DropOldestQueue.put` (never blocks).

## 12. Screen output (`render/`)

- **Projectiles** (`draw_projectiles(surface, half, crop, projectiles, target_slot, cfg_render, font)`; window passes the extra args): for each projectile aimed at the viewer:
  - start = `origin_px` mapped from camera pixels into the half through `crop` (`half.x + (px - crop.x) × half.w / crop.w`, same for y), clamped to the half;
  - target = `(half center x, half.y + end_y_frac × half.h)`;
  - position = lerp(start, target, progress); radius = lerp(`start_radius_px`, `end_radius_px`, progress);
  - color = `rgb[spell_id]` or `default_rgb`; `dodge_rgb` while `in_dodge_window`, with `"DODGE!"` drawn above the target.
- **HUD** (placeholder): a charged spell's line reads `CHARGED: PUSH!` / `TWO-HAND PUSH!` / `RAISE ARM!` / `HANDS TOGETHER!` from `release`; the name line ends with `MIC OK` or `MIC OFF`.
- **Lobby** (placeholder): title, both names, each player's TRACKED / STEP INTO VIEW, the banner instruction.
- **Loading** (placeholder): one card per player: name, class, each spell's name, incantation (`…` while empty) and release cue; the countdown from `timer_s`.
- **Victory** (placeholder): the banner, then the chronicle wrapped to the screen width (`writing the chronicle…` while `None`).
- Colors and sizes for the new placeholder text live in `render.scenes` and `render.projectiles` config.

## 13. Replay (`replay/`)

- **`SessionRecorder(out_dir, cfg, mode)`:** creates the directory; writes `meta.json` (`version: 1`, `mode`, `started_t` monotonic, `started_wall` ISO time, `config` snapshot); appends `serde.to_json` lines to `states.jsonl`, `voice.jsonl`, `events.jsonl` from a background writer thread fed by a `queue.SimpleQueue`, so the game loop never touches the disk. `write_frame` is removed. `close()` flushes, closes and joins.
- **`SessionPlayer(session_dir, cfg)`:** loads the three files (events are not replayed; the engine regenerates them). On the first `poll(now)`, offset = `now - earliest t`; every state's and voice event's `t` is shifted by the offset (`cam_t` unchanged). `poll(now)` returns the items now due, in order, plus a `Frame` drawn from the newest due states. After the last item it returns nothing more (states go stale, halves show STEP INTO VIEW).
- **Silhouettes:** the drawing in `FakePlayers` moves to `draw_silhouettes(image, states, focal_px)`, which fills each tracked state's `bbox_px` and a head box around `keypoints_px["head"]` (radius `_HEAD_RADIUS_M × focal_px / root z`) in that slot's color. `FakePlayers` and `SessionPlayer` both use it.
- **Fake two-hand key** (`keys.fake.<slot>.two_hand_push`): on press, the state gets `push` on the right hand and both `wrist_vz` at `-fake.push_speed_mps`.

## 14. Config changes (`config.yaml`)

```yaml
intent:
  dodge_step_m: 0.3           # (guess)
  dodge_duck_m: 0.25          # (guess)
  dodge_lookback_s: 0.4       # (guess)
  two_hand_window_s: 0.1      # (guess) other hand within this of the push; every push waits this long

voice:
  enabled: true
  url: wss://api.meta.ai/v1/asr/realtime
  model: muse-voice-transcribe-1.0
  api_key_env: META_MODEL_API_KEY
  sample_rate: 16000
  chunk_ms: 80
  match_threshold: 80
  perfect_threshold: 95
  handshake_timeout_s: 5
  reconnect_backoff_s: 1.0
  reconnect_max_s: 10.0
  session_max_s: 3300         # reopen before Muse's 60-minute limit
  silence_after_s: 0.2        # send zeros if the mic is quiet this long
  min_keyword_chars: 4
  mics: ...unchanged...

ai:
  enabled: true
  base_url: https://api.meta.ai/v1
  model: muse-spark-1.3
  timeout_s: 8
  api_key_env: META_MODEL_API_KEY
  temperature: 0.9            # (guess)
  min_words: 3
  max_words: 7
  max_cross_similarity: 60    # (guess) rapidfuzz ratio between the two players' incantations
  chronicle_max_words: 120

game:
  ...existing keys...
  basic_attack_damage: 8      # (guess)
  basic_attack_travel_s: 0.7  # (guess)
  perfect_mult: 1.15
  banner_s: 1.2
  loading_min_s: 3.0
  loading_max_s: 10.0
  victory_min_s: 5.0
  victory_max_s: 30.0
  pause_after_s: 2.0
  name_max_chars: 12
  combat:
    speed_ref_mps: 2.0
    speed_mult_min: 0.6
    speed_mult_max: 1.8
    near_m: 1.2
    near_mult: 1.4
    far_m: 2.8
    far_mult: 0.7

render:
  projectiles:                # owner: Nikhil
    start_radius_px: 18
    end_radius_px: 140
    end_y_frac: 0.85
    font_px: 64
    default_rgb: [255, 220, 120]
    dodge_rgb: [230, 50, 50]
    rgb: {basic: [240, 240, 240], fireball: [255, 120, 30], inferno: [255, 60, 0],
          bolt: [120, 180, 255], chain: [160, 140, 255], judgment: [255, 230, 120]}
  scenes:                     # owner: Adetola (placeholder text scenes)
    title_px: 96
    text_px: 36
    text_rgb: [240, 240, 240]
    dim_rgb: [150, 150, 160]

keys:
  fake:
    0: {..., two_hand_push: v}
    1: {..., two_hand_push: m}
```

`core/config.py` validation adds: `game.combat` present with all seven keys; `voice.api_key_env`, `voice.chunk_ms`, `ai.api_key_env`, `ai.min_words <= ai.max_words`; every class spell's `release` in the four release kinds.

## 15. Testing

All on laptops and CI, no network, mics or `pyzed`:

- **Contracts:** new kinds and fields validate and round-trip through serde.
- **Intent:** single push after the window; two-hand when the other hand leads, lags, or never comes; pose rising edges only, including after a tracking gap; charge and speech mapping; step and duck with re-arm; untracked states ignored.
- **Combat:** speed and distance multipliers at, between and beyond the anchors; unknown distance.
- **Engine:** charge reserves and refunds (replacement, expiry), insufficient mana, wrong class; each release kind; basic attack and its cooldown; mismatched release keeps the charge; projectile progress and dodge window; dodge inside vs outside the window; hit damage uses release and impact distances; KO; time-out winner and draw; pause freezes everything; scene flow lobby → loading (min time, provided vs fallback at max time, late `provide_incantations` ignored) → fight → victory → lobby; name parsing.
- **Voice:** matcher on exact, filler-prefixed, partial, misheard and other-player transcripts; keyword extraction; `MuseStream` against a local `websockets` server that asserts the handshake fields and plays scripted events and close codes; session logic (one incantation per turn, transcript mode, reconnect backoff, config change restarts, no key / no mic status and idle) with fake mic and fake streams; `MicHub` channel split and resampling with a fake `sounddevice` module.
- **Spark:** client with a fake OpenAI-style client; incantation validation (good, too long, too short, symbols, duplicate, cross-similar, missing spell, code fence, garbage, exception); template chronicle on KO, time-out, draw and empty logs; `write_chronicle` fallback; `AiWorker` finished, timed-out and late results, replacement, disabled.
- **Loop:** a fake engine that changes scenes: the `VoiceConfig`s sent, the jobs started, results and mic status delivered, events collected per match, recorder calls.
- **Replay:** record → play round trip with rebased `t`; due-item timing; end of session; recorder never blocks the caller.
- **Render:** headless draws of projectiles (in and out of the dodge window, off-crop origins), HUD charged lines, and the three placeholder scenes.
- **End to end:** `python -m magic_box --fake --headless --max-ticks 600`; a scripted `GameLoop` test with fake key presses that goes lobby → fight → one hit → victory.

On the Jetson (needs a key and mics): live Muse in both modes, live Spark, the two-hand window with real arms, partial-transcript latency against `charge_window_s`.

## 16. Docs to update

- Root `CLAUDE.md`: contract changes and field notes (`two_hand`, `speech`, `status`, `release`, `provide_mic_status`); "Working without the Jetson" (`--record` / `--replay` work; voice and Spark status; fake two-hand key); fake-mode key table; commands; open decisions (Muse keyword format, charge window after latency measurement).
- `README.md`: fake-mode key table (two-hand push).
- Package `CLAUDE.md` files for `intent/`, `voice/`, `ai/`, `replay/`, `pipeline/`, `game/`, `render/`: files, rules, what is done and what is left.
- `docs/game-design.md`: a short note that the thin engine implements Appendix A without the effects of spells that do no damage, and lists the new `game` numbers.
- Parent spec §8: append "Details: `2026-10-24-nikhil-pipeline-design.md`." to the `intent/`, `voice/`, `ai/`, `replay/` rows.

## 17. Risks

- **Every push waits `two_hand_window_s`** (0.1 s) before it reaches the engine. Tune on the Jetson; 0 removes the wait (then only hands that cross on the same frame count as two-handed).
- **`Push.speed` is flat** (≈1.5–1.7 m/s, perception spec), so `speed_mult` sits near 0.75–0.85 for everyone until Adetola and Enoch decide on peak speed.
- **Muse keyword format** (words vs phrases) and **partial latency** are unmeasured. Measure at M4 and size `charge_window_s` from it.
- **Mic hardware is undecided.** The per-device stream covers both two USB mics and one stereo receiver; device names come from `check_env.py`.
- **Spark latency** on `muse-spark-1.3` is unknown; the 8 s worker deadline and per-spell fallback cap the cost.
- **Ownership:** the thin engine and placeholder scenes live in Adetola's folders. Adetola owns them from here; nothing in Nikhil's code depends on engine internals beyond `Engine`'s facade.
- **The beta is still moving:** `feature/arena-docker` (JS game in Docker) gained commits on 2026-10-24. This design does not use it.

## Appendix A: Meta API facts used (checked 2026-10-24)

- **Realtime ASR** ([speech to text](https://dev.meta.ai/docs/speech-to-text), [schemas](https://dev.meta.ai/docs/api-reference/voice/schemas), [realtime reference](https://dev.meta.ai/docs/api-reference/voice/realtime)): `wss://api.meta.ai/v1/asr/realtime`; first JSON text frame within 10 s carries `authorization.accessToken = "Bearer <key>"` (no HTTP auth header), `audioEncoding` `PCM_24KHZ` | `PCM_16KHZ` (required), `model` (required), `mode` `PUSH_TO_TALK` | `ENDPOINTING` | `DIARIZATION`, `partialMode` `CUMULATIVE` | `DELTA`, `emitAudioProgress`, `keywords`, `languageBias`; reply `{"sessionId": ...}` with no `type`; then binary PCM16 LE mono at about real time, never more than 5 s ahead; events `speechStart {turnId}`, `transcript {transcript, final}` (cumulative partials replace the previous one), `speechEnd {turnId}`, `speechComplete {turnId, transcript}`, `audioProgress`, `error {message, sessionId}`; end with `{"type": "endStream"}`; keep sending silence on a live source; 60-minute sessions, no resume; close codes 1000 normal, 1008 bad request or pacing (don't retry unchanged), 1011 internal (retry with backoff; new session at max duration), 1013 rate limited (retry after backoff). Meta's example sends 80 ms frames.
- **Spark** ([models](https://dev.meta.ai/docs/models), [quickstart](https://dev.meta.ai/docs/quickstart)): OpenAI-compatible chat completions at `https://api.meta.ai/v1`, `Authorization: Bearer <key>`; current model `muse-spark-1.3` (`muse-spark-1.1` still supported). Meta's docs name the env var `MODEL_API_KEY`; this repo keeps `META_MODEL_API_KEY`.
