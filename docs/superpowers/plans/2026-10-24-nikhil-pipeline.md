# Intent, Voice, Spark, Replay and a Thin Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a full match playable end to end: intent turns states and voice into `Action`s, a thin config-driven engine in `game/` runs lobby → loading → fight → victory, projectiles fly on screen, per-player Muse voice charges spells, Muse Spark writes incantations and the Duel Chronicle (with local fallbacks), and sessions can be recorded and replayed.

**Architecture:**
- `intent/` and `game/` are pure Python on the contracts. `MatchState` runs on its own match clock, so pausing is "don't advance".
- `voice/` is an asyncio program in the voice process: `MicHub` (sounddevice) feeds per-slot queues, one `MuseStream` (websockets) session per slot; all I/O is injected so tests use fakes.
- `ai/` runs Spark calls on an `AiWorker` thread with deadlines and fallbacks; `pipeline/loop.py` reacts to scene changes (Spark jobs, `VoiceConfig`) and never blocks.

**Tech Stack:** Python 3.10 (uv), numpy<2, pygame-ce, rapidfuzz, websockets 16 (`websockets.asyncio`), openai SDK, sounddevice (lazy), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md`. Read all of it; §7 (intent), §8 (engine), §9 (voice) are the core. Parent spec: `docs/superpowers/specs/2026-10-24-magic-box-design.md` §6–§11 and Appendix A.

## Global Constraints

**Python and dependencies**
- Python `==3.10.*`. Use uv only (`uv run`, `uv sync`). Add no dependencies. There is no pytest-asyncio: async tests call `asyncio.run(...)` inside plain test functions, always wrapped in `asyncio.wait_for(..., timeout)` so a bug fails instead of hanging.

**Git**
- **Never run git commands that change the repo** (`add`, `commit`, `push`, `checkout`, `stash`, `restore`, `rm`, …). Delete files with plain `rm`. At the end of each task, print the commit commands for Daniel to run. Format: `<type>(<scope>): <lowercase summary>`, one line, no body, no trailer.

**Import boundaries** (`tests/test_boundaries.py` enforces these for `src/`)
- `pygame` only under `src/magic_box/render/`. `game/` never imports `pygame`, `pyzed` or `cv2`. `core/` imports only `magic_box.core`.
- `sounddevice`, `cv2`, `pyzed` are never imported at module top level; import them inside functions.
- Absolute imports only (`from magic_box.x import y`).

**Conventions**
- Every module docstring has a line `Owner: <Name>`: Nikhil for `core/`, `intent/`, `voice/`, `ai/`, `replay/`, `pipeline/`, `main.py`, `render/projectiles.py`; Adetola for `game/`, `render/hud.py`, `render/scenes/`; Adetola + Nikhil for `render/window.py`. New `game/` and placeholder render modules add a docstring line: `Thin placeholder rules (2026-10-24 phase); replace freely.`
- Every tunable lives in `config.yaml`; code reads it from `cfg`. Numbers marked "(guess)" are untuned.
- Time is `time.monotonic()` seconds (`t` on contracts, `now` in the loop). `MatchState` uses its own match clock. Meters for distances. +Y is down in camera coordinates.
- Slot 0 = P1, slot 1 = P2. Default classes: slot 0 `fire_mage`, slot 1 `lightning_mage`.
- Never block the game loop: no network, disk writes or blocking `queue.get` on the 60 fps path.
- Never log or print the API key.

**Done criteria for each task**
- `uv run ruff check` and `uv run ruff format --check` are clean.
- `uv run pytest` is green. Tests never touch the network, a real mic or `pyzed`.
- `uv run python -m magic_box --fake --headless --max-ticks 60` exits 0.

## Review Focus

1. **Venue network: the Muse handshake never answers, or the socket drops mid-turn.** The slot reconnects with backoff, publishes `reconnecting` then `connected`, and the voice process never exits. Tested in Task 9 (`test_handshake_failure_retries_and_never_exits`, `test_drop_reconnects_with_backoff_and_status`).
2. **A mic goes silent or is unplugged mid-match.** The sender keeps the Muse session alive with zero-filled chunks instead of letting the server close it. Tested in Task 9 (`test_silence_sent_when_mic_quiet`).
3. **A player steps out of view while a spell is in flight.** The fight pauses; the projectile neither advances nor lands while paused and resumes from the same progress. Tested in Task 4 (`test_pause_freezes_projectile_and_resumes`).
4. **Spark returns the same (or nearly the same) incantations for both players.** Crosstalk would let one player cast the other's spell, so slot 1's offending entries fall back to config. Tested in Task 10 (`test_identical_sets_force_fallback_for_slot_1`).
5. **Scene changes arrive in a burst** (lobby → loading → fight within one control poll). The voice process applies only the newest `VoiceConfig` and restarts each session once. Tested in Task 9 (`test_burst_of_configs_restarts_once_with_newest`).

---

## File Map

| Task | Creates | Modifies |
|---|---|---|
| 1 | | `core/contracts.py`, `core/config.py`, `config.yaml`, `tests/core/test_contracts.py`, `tests/core/test_config.py` |
| 2 | `tests/intent/__init__.py`, `tests/intent/test_fusion.py`, `tests/intent/test_dodge.py` | `intent/fusion.py`, `intent/dodge.py` |
| 3 | `tests/game/test_combat.py`, `tests/game/test_state.py` | `game/classes.py`, `game/spells.py`, `game/combat.py`, `game/state.py` |
| 4 | `tests/game/test_scenes.py`, `tests/game/test_engine.py` | `game/scenes.py`, `game/engine.py`; deletes `tests/game/test_engine_stub.py` |
| 5 | `tests/render/test_projectiles.py`, `tests/render/test_scenes.py`, `tests/render/test_hud.py` | `render/projectiles.py`, `render/hud.py`, `render/scenes/{__init__,lobby,loading,victory}.py`, `render/window.py`, `replay/fake_input.py`, `tests/render/test_window.py`, `tests/replay/test_fake_input.py` |
| 6 | `tests/voice/__init__.py`, `tests/voice/test_matcher.py` | `voice/matcher.py` |
| 7 | `tests/voice/fake_muse.py`, `tests/voice/test_muse_stream.py` | `voice/muse_stream.py` |
| 8 | `tests/voice/fake_sd.py`, `tests/voice/test_mic.py` | `voice/mic.py` |
| 9 | `tests/voice/test_process.py` | `voice/process.py` |
| 10 | `tests/ai/__init__.py`, `tests/ai/fakes.py`, `tests/ai/test_spark_client.py`, `tests/ai/test_incantations.py`, `tests/ai/test_chronicle.py` | `ai/spark_client.py`, `ai/incantations.py`, `ai/chronicle.py` |
| 11 | `ai/worker.py`, `tests/ai/test_worker.py` | `pipeline/loop.py`, `main.py`, `tests/pipeline/test_loop.py` |
| 12 | `tests/replay/test_record_play.py` | `replay/record.py`, `replay/play.py`, `replay/fake_input.py`, `pipeline/sources.py`, `pipeline/loop.py`, `main.py`, `tests/pipeline/test_sources.py`, `tests/pipeline/test_loop.py`, `tests/test_main.py` |
| 13 | | `CLAUDE.md`, `README.md`, `docs/game-design.md`, parent spec, `{intent,voice,ai,replay,pipeline,game,render}/CLAUDE.md` |

Paths under `core/`, `intent/`, `game/`, `voice/`, `ai/`, `replay/`, `pipeline/`, `render/` are relative to `src/magic_box/`. Every test module loads `CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")` like the existing tests.

---

### Task 1: Contract fields and config for this phase

**Files:**
- Modify: `src/magic_box/core/contracts.py`, `src/magic_box/core/config.py`, `config.yaml`
- Test: `tests/core/test_contracts.py`, `tests/core/test_config.py`

**Interfaces:**
- Produces: `ACTION_KINDS` gains `"speech"`; `VOICE_KINDS` gains `"status"`; new `RELEASE_KINDS = ("push", "two_hand_push", "arm_overhead", "hands_together")` in `core/contracts.py`; `Action.two_hand: bool = False`, `Action.text: str = ""`; `SpellView.release: str = "push"` (validated against `RELEASE_KINDS`). Every config key in spec §14, which every later task reads.

- [ ] **Step 1: Write the failing tests**

Append to `tests/core/test_contracts.py`:

```python
def test_speech_and_two_hand_actions_round_trip():
    speech = Action("speech", 0, 1.0, text="my name is ada")
    push = Action("push", 1, 2.0, push=Push("R", 2.0, (1.0, 2.0)), two_hand=True, dist=1.8)
    assert from_json(to_json(speech)) == speech and from_json(to_json(push)) == push
    assert Action("push", 0, 0.0).two_hand is False and Action("push", 0, 0.0).text == ""


def test_status_voice_event_is_valid():
    ev = VoiceEvent(0, 1.0, "status", "connected", None, 0.0)
    assert from_json(to_json(ev)) == ev


def test_spell_view_release_default_and_validation():
    assert SpellView("bolt", "Bolt", "x", 20.0, False).release == "push"
    assert SpellView("heal", "Heal", "x", 40.0, True, "hands_together").release == "hands_together"
    with pytest.raises(ValueError, match="release"):
        SpellView("bolt", "Bolt", "x", 20.0, False, "wave")
    assert RELEASE_KINDS == ("push", "two_hand_push", "arm_overhead", "hands_together")
```

Append to `tests/core/test_config.py`:

```python
def test_repo_config_has_phase_tunables():
    cfg = load_config(ROOT / "config.yaml")
    assert cfg["intent"]["two_hand_window_s"] == 0.1
    for key in ("api_key_env", "chunk_ms", "handshake_timeout_s", "reconnect_backoff_s",
                "reconnect_max_s", "session_max_s", "silence_after_s", "min_keyword_chars",
                "audio_queue_chunks"):
        assert key in cfg["voice"], key
    assert cfg["ai"]["model"] == "muse-spark-1.3" and cfg["ai"]["min_words"] == 3
    for key in ("basic_attack_damage", "basic_attack_travel_s", "perfect_mult", "banner_s",
                "loading_min_s", "loading_max_s", "victory_min_s", "victory_max_s",
                "pause_after_s", "name_max_chars"):
        assert key in cfg["game"], key
    assert cfg["game"]["combat"]["near_mult"] == 1.4
    assert cfg["keys"]["fake"][0]["two_hand_push"] == "v"
    assert cfg["keys"]["fake"][1]["two_hand_push"] == "m"
    assert "projectiles" in cfg["render"] and "scenes" in cfg["render"]


def test_missing_combat_key_rejected(tmp_path):
    cfg = _base()
    del cfg["game"]["combat"]["far_mult"]
    with pytest.raises(ConfigError, match=r"game\.combat\.far_mult"):
        load_config(_write(tmp_path, cfg))


def test_bad_release_rejected(tmp_path):
    cfg = _base()
    cfg["game"]["classes"]["fire_mage"]["spells"][0]["release"] = "wave"
    with pytest.raises(ConfigError, match=r"fireball\.release"):
        load_config(_write(tmp_path, cfg))


def test_min_words_above_max_rejected(tmp_path):
    cfg = _base()
    cfg["ai"]["min_words"] = 9
    with pytest.raises(ConfigError, match=r"ai\.min_words"):
        load_config(_write(tmp_path, cfg))
```

(Add the needed imports: `Action`, `Push`, `VoiceEvent`, `SpellView`, `RELEASE_KINDS` from `magic_box.core.contracts`; `from_json`, `to_json` from `magic_box.core.serde`; `pytest`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/core -v`
Expected: FAIL (`ValueError: kind must be one of ...` for `"speech"`, missing config keys, `ImportError` for `RELEASE_KINDS`).

- [ ] **Step 3: Update `core/contracts.py`**

Add `"speech"` to `ACTION_KINDS`, `"status"` to `VOICE_KINDS`, define `RELEASE_KINDS`, add the fields from spec §6 (new fields last, with defaults), and validate `SpellView.release` in a `__post_init__` with `_check_in("release", ...)`. Comments on the new fields as in spec §6.

- [ ] **Step 4: Update `config.yaml`**

Apply spec §14 exactly, plus `voice.audio_queue_chunks: 25  # per-slot mic buffer (2 s at 80 ms chunks)`. Keep every existing key and owner comment. `ai.base_url` loses its "VERIFY" comment (verified 2026-10-24, spec Appendix A).

- [ ] **Step 5: Add validation to `core/config.py`**

Called from `validate()`, each skipping when its section is missing. Messages:
- `f"game.combat.{key}: missing"` for each of `speed_ref_mps, speed_mult_min, speed_mult_max, near_m, near_mult, far_m, far_mult`.
- `f"voice.{key}: missing"` for `api_key_env`, `chunk_ms`; `f"ai.{key}: missing"` for `api_key_env`.
- `"ai.min_words: must be <= ai.max_words"`.
- In the existing spell loop: `f"game.classes.{cls_name}.spells.{spell_id}.release: must be one of {RELEASE_KINDS}, got {release!r}"` (import `RELEASE_KINDS` from `magic_box.core.contracts`).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/core -v`, then `uv run pytest`
Expected: PASS.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add src/magic_box/core/contracts.py src/magic_box/core/config.py config.yaml tests/core/test_contracts.py tests/core/test_config.py
git commit -m "feat(core): add contract fields and config for intent, voice, spark and the thin engine"
```

---

### Task 2: Intent: pushes, poses, voice and dodges become actions

**Files:**
- Modify: `src/magic_box/intent/fusion.py`, `src/magic_box/intent/dodge.py`
- Create: `tests/intent/__init__.py` (empty), `tests/intent/test_fusion.py`, `tests/intent/test_dodge.py`

**Interfaces:**
- Consumes: Task 1 `Action` fields.
- Produces: `Intent(cfg).update(states: Sequence[PlayerState], voice: Sequence[VoiceEvent], now: float) -> list[Action]`; `DodgeDetector(cfg).update(state: PlayerState) -> str | None` (one window per slot inside).

- [ ] **Step 1: Write the failing tests**

`tests/intent/test_dodge.py`:

```python
from tests.factories import make_state

def st(t, x=0.6, head_y=-0.7, slot=0):
    return make_state(slot, t=t, root=(x, 0.0, 2.0), head=(x, head_y, 2.0))


def test_step_detected_once_then_rearmed():
    d = DodgeDetector(CFG)
    out = [d.update(st(t, x)) for t, x in [(0.0, 0.6), (0.1, 0.65), (0.2, 0.75), (0.3, 0.95)]]
    assert out == [None, None, None, "step"]
    assert d.update(st(0.4, 0.96)) is None  # window cleared after a report


def test_slow_drift_is_not_a_step():
    d = DodgeDetector(CFG)
    assert all(d.update(st(0.1 * i, 0.6 + 0.05 * i)) is None for i in range(20))


def test_duck_detected_and_standing_up_is_not():
    d = DodgeDetector(CFG)
    assert d.update(st(0.0, head_y=-0.7)) is None
    assert d.update(st(0.2, head_y=-0.42)) == "duck"
    d2 = DodgeDetector(CFG)
    d2.update(st(0.0, head_y=-0.4))
    assert d2.update(st(0.2, head_y=-0.7)) is None


def test_step_wins_over_duck_and_slots_are_independent():
    d = DodgeDetector(CFG)
    d.update(st(0.0))
    d.update(st(0.0, slot=1, x=-0.6))
    assert d.update(st(0.2, x=1.0, head_y=-0.3)) == "step"
    assert d.update(st(0.2, slot=1, x=-0.6)) is None
```

`tests/intent/test_fusion.py`:

```python
THR = CFG["perception"]["push_speed_mps"]
W = CFG["intent"]["two_hand_window_s"]
PUSH = Push("R", 2.0, (300.0, 200.0))

def st(t, slot=0, push=None, vz=(0.0, 0.0), flags=(), ok=True, z=2.0):
    return make_state(slot, t=t, push=push, wrist_vz={"L": vz[0], "R": vz[1]},
                      pose_flags=frozenset(flags), tracking_ok=ok,
                      root=(0.6 if slot == 0 else -0.6, 0.0, z))


def kinds(actions):
    return [(a.kind, a.slot, a.two_hand) for a in actions]


def test_single_push_released_after_window():
    it = Intent(CFG)
    assert it.update([st(1.0, push=PUSH, vz=(0.0, -2.0), z=1.8)], [], now=1.0) == []
    acts = it.update([], [], now=1.0 + W)
    assert kinds(acts) == [("push", 0, False)]
    assert acts[0].push == PUSH and acts[0].t == 1.0 and acts[0].dist == 1.8


def test_two_hand_when_other_hand_leads():
    it = Intent(CFG)
    it.update([st(0.95, vz=(-THR - 0.1, 0.0))], [], 0.95)
    assert kinds(it.update([st(1.0, push=PUSH, vz=(-0.5, -2.0))], [], 1.0)) == [("push", 0, True)]


def test_two_hand_when_other_hand_lags():
    it = Intent(CFG)
    assert it.update([st(1.0, push=PUSH, vz=(0.0, -2.0))], [], 1.0) == []
    assert kinds(it.update([st(1.05, vz=(-THR, -1.0))], [], 1.05)) == [("push", 0, True)]
    assert it.update([], [], 2.0) == []


def test_other_hand_outside_window_is_single():
    it = Intent(CFG)
    it.update([st(1.0 - W - 0.05, vz=(-THR - 1.0, 0.0))], [], 1.0 - W - 0.05)
    it.update([st(1.0, push=PUSH, vz=(0.0, -2.0))], [], 1.0)
    assert kinds(it.update([], [], 1.0 + W)) == [("push", 0, False)]
    assert it.update([st(1.0 + W + 0.05, vz=(-THR - 1.0, 0.0))], [], 1.0 + W + 0.05) == []


def test_second_push_while_pending_is_dropped():
    it = Intent(CFG)
    it.update([st(1.0, push=PUSH), st(1.03, push=PUSH)], [], 1.03)
    assert len(it.update([], [], 1.0 + W)) == 1


def test_pose_rising_edges_only():
    it = Intent(CFG)
    seq = [(), ("hands_up",), ("hands_up",), (), ("hands_up",)]
    acts = it.update([st(0.1 * i, flags=f) for i, f in enumerate(seq)], [], 0.5)
    assert [(a.kind, a.pose) for a in acts] == [("pose", "hands_up"), ("pose", "hands_up")]


def test_pose_edge_not_refired_after_tracking_gap():
    it = Intent(CFG)
    it.update([st(0.0, flags=("hands_up",))], [], 0.0)
    it.update([st(0.1, flags=("hands_up",), ok=False)], [], 0.1)
    assert it.update([st(0.2, flags=("hands_up",))], [], 0.2) == []


def test_charge_and_speech_from_voice_status_ignored():
    it = Intent(CFG)
    voice = [
        VoiceEvent(0, 1.1, "incantation", "embers", "fireball", 92.0),
        VoiceEvent(1, 1.1, "transcript", "my name is ada", None, 0.0),
        VoiceEvent(0, 1.1, "status", "connected", None, 0.0),
    ]
    acts = it.update([st(1.0, z=1.8)], voice, now=1.1)
    assert acts == [
        Action("charge", 0, 1.1, spell_id="fireball", match_score=92.0, dist=1.8),
        Action("speech", 1, 1.1, text="my name is ada"),
    ]


def test_untracked_states_never_act():
    it = Intent(CFG)
    it.update([st(1.0, push=PUSH, ok=False, flags=("hands_up",))], [], 1.0)
    assert it.update([], [], 2.0) == []


def test_dodge_becomes_action():
    it = Intent(CFG)
    states = [make_state(0, t=0.0, root=(0.6, 0.0, 2.0)), make_state(0, t=0.2, root=(0.95, 0.0, 2.0))]
    acts = it.update(states, [], 0.2)
    assert [(a.kind, a.dodge) for a in acts] == [("dodge", "step")]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/intent -v`
Expected: FAIL (`NotImplementedError` from `DodgeDetector`, `[]` from `Intent`).

- [ ] **Step 3: Implement `DodgeDetector` in `intent/dodge.py`** per spec §7 (per-slot `collections.deque` of `(t, root.x, head.y)`, trim by `t` to `dodge_lookback_s`, clear the slot's window after a report).

- [ ] **Step 4: Implement `Intent.update` in `intent/fusion.py`** per spec §7. Keep per slot: the last `two_hand_window_s` of `(t, wrist_vz)` per hand (deque), the pending push (state, deadline), the previous tracked `pose_flags`, the latest tracked root Z, and one `DodgeDetector`. Process states first (so charge `dist` sees this tick's states), but return voice actions first, then state actions in order, then pushes released by `now >= deadline`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/intent -v`, then `uv run pytest`
Expected: PASS.

- [ ] **Step 6: Commit (Daniel runs)**

```bash
git add src/magic_box/intent tests/intent
git commit -m "feat(intent): turn pushes, poses, voice and dodges into actions"
```

---

### Task 3: Thin engine: combat formula and fight rules

**Files:**
- Modify: `src/magic_box/game/classes.py`, `spells.py`, `combat.py`, `state.py`
- Create: `tests/game/test_combat.py`, `tests/game/test_state.py`

**Interfaces:**
- Consumes: Task 1 contracts and config.
- Produces:
  - `class_ids(cfg) -> list[str]`, `class_name(cfg, class_id) -> str`.
  - `SpellDef(id, name, cost, damage, travel_s, release, fallback: dict[int, str])` (frozen); `load_spells(cfg, class_id) -> list[SpellDef]`; `BASIC_ATTACK_ID = "basic"`.
  - `speed_mult(speed: float | None, cfg) -> float`, `dist_mult(dist: float, cfg) -> float`, `damage(base, push_speed: float | None, atk_dist, def_dist, buff_mult, cfg) -> float`.
  - `MatchState(cfg, names: Mapping[int, str], now: float)` with `players: tuple[PlayerMatch, PlayerMatch]` (fields `slot, name, class_id, spells, hp, mana, charge: Charge | None, basic_ready_at, last_dist`), `projectiles: list[Projectile]`, `clock: float` (match clock, starts 0), `time_left: float`; methods `apply(action, states, now) -> None`, `advance(dt, states, now) -> None`, `take_events() -> list[GameEvent]`, `result() -> tuple[int | None, str] | None` (`(winner, "ko" | "time")` once over), `banner() -> str | None`, `projectile_views() -> tuple[ProjectileView, ...]`. `now` is used only for `GameEvent.t`; all rules run on `clock`.

- [ ] **Step 1: Write the failing tests**

`tests/game/test_combat.py`:

```python
@pytest.mark.parametrize("dist,mult", [(1.2, 1.4), (2.8, 0.7), (2.0, 1.05), (1.0, 1.4), (3.5, 0.7), (0.0, 1.0)])
def test_dist_mult(dist, mult):
    assert dist_mult(dist, CFG) == pytest.approx(mult)


@pytest.mark.parametrize("speed,mult", [(2.0, 1.0), (1.5, 0.75), (0.5, 0.6), (5.0, 1.8), (None, 1.0)])
def test_speed_mult(speed, mult):
    assert speed_mult(speed, CFG) == pytest.approx(mult)


def test_damage_combines_multipliers():
    assert damage(8, 2.0, 2.0, 2.0, 1.0, CFG) == pytest.approx(8.82)
    assert damage(10, None, 1.2, 2.8, 1.15, CFG) == pytest.approx(10 * 1.4 * 0.7 * 1.15)


def test_spell_table_from_config():
    spells = load_spells(CFG, "fire_mage")
    assert [s.id for s in spells] == ["fireball", "flame_wall", "inferno"]
    assert spells[1].release == "two_hand_push" and spells[0].fallback[0] == "embers of the forty acres burn"
    assert class_ids(CFG) == ["fire_mage", "lightning_mage", "holy_knight"]
    assert class_name(CFG, "holy_knight") == "Holy Knight"
```

`tests/game/test_state.py` (use `CFG0 = copy.deepcopy(CFG); CFG0["game"]["mana_regen_per_s"] = 0` where regen would blur mana checks):

```python
NAMES = {0: "Ada", 1: "Bo"}
STATES = {0: make_state(0, root=(0.6, 0.0, 2.0)), 1: make_state(1, root=(-0.6, 0.0, 2.0))}

def charge(slot, spell, score=90.0):
    return Action("charge", slot, 0.0, spell_id=spell, match_score=score, dist=2.0)

def push(slot, two=False, speed=2.0):
    return Action("push", slot, 0.0, push=Push("R", speed, (480.0, 300.0)), two_hand=two, dist=2.0)

def new(cfg=CFG0):
    ms = MatchState(cfg, NAMES, now=5.0)
    ms.take_events()
    return ms


def test_match_starts_full_and_logs_match_start():
    ms = MatchState(CFG, NAMES, now=5.0)
    p0, p1 = ms.players
    assert (p0.hp, p0.mana, p0.class_id, p1.class_id) == (100, 100, "fire_mage", "lightning_mage")
    assert ms.time_left == 90 and ms.banner() == "FIGHT!"
    [ev] = ms.take_events()
    assert (ev.kind, ev.t) == ("match_start", 5.0)
    assert ev.data == {"names": {0: "Ada", 1: "Bo"}, "classes": {0: "fire_mage", 1: "lightning_mage"}}


def test_charge_reserves_then_expires_with_refund():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    assert ms.players[0].mana == 75 and ms.players[0].charge.spell.id == "fireball"
    ms.advance(CFG["game"]["charge_window_s"] + 0.01, STATES, 0.0)
    assert ms.players[0].charge is None and ms.players[0].mana == 100


def test_new_charge_replaces_and_refunds():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(charge(0, "inferno"), STATES, 0.0)
    assert ms.players[0].mana == 40 and ms.players[0].charge.spell.id == "inferno"


def test_charge_needs_own_class_and_mana():
    ms = new()
    ms.apply(charge(0, "bolt"), STATES, 0.0)
    ms.players[0].mana = 10
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    assert ms.players[0].charge is None and ms.players[0].mana == 10


def test_push_releases_charged_spell_as_projectile():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    [p] = ms.projectiles
    assert (p.spell_id, p.attacker, p.target, p.origin_px) == ("fireball", 0, 1, (480.0, 300.0))
    assert ms.players[0].charge is None
    [ev] = ms.take_events()
    assert ev.kind == "cast" and ev.data == {"spell_id": "fireball", "release": "push", "two_hand": False}


def test_two_hand_spell_needs_two_hands_single_push_is_basic():
    ms = new()
    ms.apply(charge(0, "flame_wall"), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    assert [p.spell_id for p in ms.projectiles] == ["basic"]
    assert ms.players[0].charge.spell.id == "flame_wall"
    ms.apply(push(0, two=True), STATES, 0.0)
    assert ms.players[0].charge is None and ms.banner() == "FLAME WALL!"
    assert [p.spell_id for p in ms.projectiles] == ["basic"]  # no projectile for 0-damage spells


def test_two_hand_push_releases_push_spell():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(push(0, two=True), STATES, 0.0)
    assert [p.spell_id for p in ms.projectiles] == ["fireball"]


def test_pose_releases_matching_spell_only():
    cfg = copy.deepcopy(CFG0)
    cfg["game"]["default_classes"][0] = "holy_knight"
    ms = new(cfg)
    ms.apply(charge(0, "heal"), STATES, 0.0)
    ms.apply(Action("pose", 0, 0.0, pose="hands_up"), STATES, 0.0)
    assert ms.players[0].charge is not None
    ms.apply(Action("pose", 0, 0.0, pose="hands_together"), STATES, 0.0)
    assert ms.players[0].charge is None and ms.banner() == "HEAL!"


def test_pose_released_damage_spell_starts_at_wrist():
    cfg = copy.deepcopy(CFG0)
    cfg["game"]["default_classes"][0] = "holy_knight"
    cfg["game"]["classes"]["holy_knight"]["spells"][0].update(damage=10, travel_s=1.0)
    ms = new(cfg)
    ms.apply(charge(0, "holy_light"), STATES, 0.0)
    ms.apply(Action("pose", 0, 0.0, pose="hands_up"), STATES, 0.0)
    assert ms.projectiles[0].origin_px == STATES[0].keypoints_px["r_wrist"]


def test_basic_attack_cooldown():
    ms = new()
    ms.apply(push(0), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    assert len(ms.projectiles) == 1
    ms.advance(CFG["game"]["basic_attack_cooldown_s"], STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    assert len(ms.projectiles) == 2


def test_projectile_progress_window_and_hit():
    ms = new()
    ms.apply(push(0, speed=2.0), STATES, 0.0)
    travel = CFG["game"]["basic_attack_travel_s"]
    ms.advance(travel / 2, STATES, 0.0)
    [view] = ms.projectile_views()
    assert view.progress == pytest.approx(0.5) and view.target_slot == 1
    assert view.in_dodge_window is (travel / 2 <= CFG["game"]["dodge_window_s"])
    ms.take_events()
    ms.advance(travel / 2 + 0.001, STATES, 9.0)
    assert ms.projectiles == [] and ms.players[1].hp == pytest.approx(100 - 8.82)
    [hit] = ms.take_events()
    assert (hit.kind, hit.slot, hit.t) == ("hit", 0, 9.0)
    assert hit.data == {"spell_id": "basic", "damage": 8.8, "target": 1, "hp_left": 91.2}


def test_dodge_in_window_avoids_hit_and_before_window_does_nothing():
    ms = new()
    ms.apply(charge(0, "fireball"), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    ms.apply(Action("dodge", 1, 0.0, dodge="step"), STATES, 0.0)  # too early
    assert len(ms.projectiles) == 1
    ms.advance(1.6 - 0.3, STATES, 0.0)
    ms.take_events()
    ms.apply(Action("dodge", 1, 0.0, dodge="duck"), STATES, 0.0)
    assert ms.projectiles == []
    [ev] = ms.take_events()
    assert (ev.kind, ev.slot, ev.data) == ("dodge", 1, {"spell_id": "fireball", "dodge": "duck"})


def test_perfect_incantation_bonus():
    ms = new()
    ms.apply(charge(0, "fireball", score=96.0), STATES, 0.0)
    ms.apply(push(0), STATES, 0.0)
    ms.advance(1.61, STATES, 0.0)
    assert ms.players[1].hp == pytest.approx(100 - 18 * 1.05 * 1.05 * 1.15)


def test_ko_ends_match():
    ms = new()
    ms.players[1].hp = 5
    ms.apply(push(0), STATES, 0.0)
    ms.take_events()
    ms.advance(1.0, STATES, 3.0)
    assert ms.players[1].hp == 0 and ms.result() == (0, "ko")
    kinds = [e.kind for e in ms.take_events()]
    assert kinds == ["hit", "ko", "match_end"]


def test_time_out_winner_and_draw():
    ms = new()
    ms.players[0].hp = 50
    ms.advance(91.0, STATES, 0.0)
    assert ms.result() == (1, "time")
    draw = new()
    draw.advance(91.0, STATES, 0.0)
    assert draw.result() == (None, "time")


def test_regen_is_capped():
    ms = MatchState(CFG, NAMES, now=0.0)
    ms.players[0].mana = 90
    ms.advance(10.0, STATES, 0.0)
    assert ms.players[0].mana == 100
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/game/test_combat.py tests/game/test_state.py -v`
Expected: FAIL (`NotImplementedError` / `ImportError` for the new names).

- [ ] **Step 3: Implement `classes.py`, `spells.py`, `combat.py`** per spec §8 and the interfaces above.

- [ ] **Step 4: Implement `MatchState` in `state.py`** per spec §8:
  - `apply` updates each slot's `last_dist` from tracked `states`, then handles `charge` / `push` / `pose` / `dodge` (other kinds ignored). Charge deadlines, `basic_ready_at`, projectile `launched` and the banner expiry are match-clock times.
  - `advance(dt, ...)`: update `last_dist`; `clock += dt`; regen (capped); expire charges (refund); land projectiles with `progress >= 1` in launch order (damage with `atk_dist` at release, target `last_dist` at impact; HP floored at 0; `hit`; `ko` then `match_end` when HP hits 0, after which further impacts are skipped); `time_left -= dt` and, at `<= 0` with no result yet, `match_end` with the higher-HP winner or `None`.
  - Pose release origin: `keypoints_px["r_wrist"]`, else `["l_wrist"]`, else the `bbox_px` center; with no state, the image center from `camera.image_width/height`.
  - `projectile_views()` clamps `progress` to `[0, 1]`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/game -v`, then `uv run pytest`
Expected: PASS (the old `test_engine_stub.py` still passes; Task 4 replaces it).

- [ ] **Step 6: Commit (Daniel runs)**

```bash
git add src/magic_box/game/classes.py src/magic_box/game/spells.py src/magic_box/game/combat.py src/magic_box/game/state.py tests/game/test_combat.py tests/game/test_state.py
git commit -m "feat(game): add the combat formula and fight rules for the thin engine"
```

---

### Task 4: Thin engine: scene flow and the engine facade

**Files:**
- Modify: `src/magic_box/game/scenes.py`, `src/magic_box/game/engine.py`
- Create: `tests/game/test_scenes.py`, `tests/game/test_engine.py`
- Delete: `tests/game/test_engine_stub.py` (`rm`)

**Interfaces:**
- Consumes: Task 3 `MatchState`, `load_spells`, `class_name`.
- Produces:
  - `SceneMachine(cfg, now=0.0)`: `scene: str` (starts `"lobby"`), `entered_at: float`, `elapsed(now) -> float`, `update(now, *, both_ready: bool, incantations_ready: bool, match_over: bool) -> bool` (True when the scene changed). `parse_name(text: str, max_chars: int) -> str | None`.
  - `Engine(cfg)`: `step(actions, states, now) -> tuple[GameView, list[GameEvent]]`, `provide_incantations(dict[int, dict[str, str]])`, `provide_chronicle(str)`, `provide_mic_status(slot: int, ok: bool)`.

- [ ] **Step 1: Write the failing tests**

`tests/game/test_scenes.py`:

```python
G = CFG["game"]

def test_scene_transitions():
    sm = SceneMachine(CFG, now=0.0)
    assert sm.scene == "lobby"
    assert not sm.update(1.0, both_ready=False, incantations_ready=False, match_over=False)
    assert sm.update(1.0, both_ready=True, incantations_ready=False, match_over=False) and sm.scene == "loading"
    assert not sm.update(1.0 + G["loading_min_s"] - 0.01, both_ready=False, incantations_ready=True, match_over=False)
    assert not sm.update(1.0 + G["loading_min_s"], both_ready=False, incantations_ready=False, match_over=False)
    assert sm.update(1.0 + G["loading_min_s"], both_ready=False, incantations_ready=True, match_over=False)
    assert sm.scene == "fight"
    assert sm.update(50.0, both_ready=False, incantations_ready=True, match_over=True) and sm.scene == "victory"
    assert not sm.update(50.0 + G["victory_min_s"] - 0.1, both_ready=True, incantations_ready=True, match_over=True)
    assert sm.update(50.0 + G["victory_min_s"], both_ready=True, incantations_ready=True, match_over=True)
    assert sm.scene == "lobby"


def test_victory_times_out_to_lobby():
    sm = SceneMachine(CFG, now=0.0)
    sm.scene, sm.entered_at = "victory", 0.0
    assert sm.update(G["victory_max_s"], both_ready=False, incantations_ready=False, match_over=True)
    assert sm.scene == "lobby"


@pytest.mark.parametrize("text,name", [
    ("my name is ada lovelace!", "Ada Lovelace"),
    ("I'm Bo.", "Bo"),
    ("It's Zoë", "Zoë"),
    ("call me maximilian the great", "Maximilian T"),
    ("   ", None),
    ("my name is", None),
])
def test_parse_name(text, name):
    assert parse_name(text, 12) == name
```

`tests/game/test_engine.py`:

```python
G = CFG["game"]
UP = frozenset({"hands_up"})

def states(up=(False, False), ok=(True, True)):
    return {s: make_state(s, pose_flags=UP if up[s] else frozenset(), tracking_ok=ok[s]) for s in (0, 1)}

def run(engine, t0, t1, st, actions=(), dt=0.05):
    """Step from t0 to t1 inclusive; returns (last view, all events)."""
    events, view, t, first = [], None, t0, True
    while t <= t1 + 1e-9:
        view, ev = engine.step(list(actions) if first else [], st, t)
        events += ev
        first, t = False, t + dt
    return view, events

def to_fight(engine):
    engine.step([], states(up=(True, True)), 0.0)
    engine.provide_incantations({0: {"fireball": "a b c"}, 1: {}})
    view, events = run(engine, 0.05, G["loading_min_s"] + 0.1, states())
    assert view.scene == "fight"
    return view, events


def test_lobby_view():
    view, events = Engine(CFG).step([], states(), 0.0)
    assert (view.scene, view.banner, view.timer_s) == ("lobby", "SAY YOUR NAME · BOTH RAISE YOUR HANDS", None)
    assert [p.name for p in view.players] == ["P1", "P2"] and events == []
    assert all(s.incantation == "" for s in view.players[0].spells)


def test_speech_sets_names_in_lobby():
    view, _ = Engine(CFG).step([Action("speech", 0, 0.0, text="My name is ada lovelace!")], states(), 0.0)
    assert view.players[0].name == "Ada Lovelace"


def test_one_player_ready_is_not_enough():
    assert Engine(CFG).step([], states(up=(True, False)), 0.0)[0].scene == "lobby"


def test_loading_countdown_then_fight_with_provided_and_fallback_incantations():
    e = Engine(CFG)
    view, _ = e.step([], states(up=(True, True)), 0.0)
    assert view.scene == "loading" and view.timer_s == pytest.approx(G["loading_min_s"])
    e.provide_incantations({0: {"fireball": "a b c"}, 1: {}})
    view, events = run(e, 0.05, G["loading_min_s"] + 0.1, states())
    assert view.scene == "fight" and view.banner == "FIGHT!" and view.timer_s == pytest.approx(G["round_s"], abs=0.2)
    inc0 = {s.id: s.incantation for s in view.players[0].spells}
    assert inc0["fireball"] == "a b c" and inc0["inferno"] == "let the whole sky catch fire"
    assert view.players[1].spells[0].incantation == "lightning answer my call"
    assert [ev.kind for ev in events] == ["match_start"]


def test_loading_falls_back_at_max_time():
    e = Engine(CFG)
    e.step([], states(up=(True, True)), 0.0)
    view, _ = run(e, 0.05, G["loading_max_s"] + 0.1, states(), dt=0.25)
    assert view.scene == "fight"
    assert view.players[0].spells[0].incantation == "embers of the forty acres burn"


def test_late_incantations_ignored():
    e = Engine(CFG)
    to_fight(e)
    e.provide_incantations({0: {"fireball": "late words here"}, 1: {}})
    view, _ = e.step([], states(), G["loading_min_s"] + 0.2)
    assert view.players[0].spells[0].incantation == "a b c"


def test_push_hits_opponent_and_charged_view():
    e = Engine(CFG)
    to_fight(e)
    t = G["loading_min_s"] + 0.2
    view, _ = e.step([Action("charge", 0, t, spell_id="fireball", match_score=90.0, dist=2.0)], states(), t)
    fb = view.players[0].spells[0]
    assert fb.charged and fb.release == "push"
    view, _ = e.step([Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t + 0.05)
    assert [p.spell_id for p in view.projectiles] == ["fireball"]
    view, events = run(e, t + 0.1, t + 2.0, states())
    assert view.players[1].hp < G["hp_max"] and "hit" in [ev.kind for ev in events]


def test_pause_freezes_projectile_and_resumes():
    cfg = copy.deepcopy(CFG)
    cfg["game"]["pause_after_s"] = 0.1  # shorter than the basic attack's flight
    e = Engine(cfg)
    to_fight(e)
    t = G["loading_min_s"] + 0.2
    e.step([Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t)
    e.step([], states(ok=(True, False)), t + 0.1)  # P2 just left
    view, _ = e.step([], states(ok=(True, False)), t + 0.3)  # gone 0.2 s > 0.1 s: paused
    assert view.banner == "STEP INTO VIEW"
    frozen, left = view.projectiles[0].progress, view.timer_s
    view, events = run(e, t + 0.35, t + 3.0, states(ok=(True, False)))
    assert view.projectiles[0].progress == pytest.approx(frozen) and view.timer_s == pytest.approx(left)
    assert "hit" not in [ev.kind for ev in events]
    view, events = run(e, t + 3.05, t + 4.0, states())
    assert "hit" in [ev.kind for ev in events]


def test_ko_to_victory_chronicle_and_back_to_lobby():
    e = Engine(CFG)
    e.step([Action("speech", 0, 0.0, text="ada")], states(), 0.0)
    to_fight(e)
    e._match.players[1].hp = 1  # noqa: SLF001 (white-box shortcut to a KO)
    t = G["loading_min_s"] + 0.2
    e.step([Action("push", 0, t, push=Push("R", 2.0, (480.0, 300.0)), dist=2.0)], states(), t)
    view, events = run(e, t + 0.05, t + 1.0, states())
    assert view.scene == "victory" and view.banner == "ADA WINS" and view.chronicle is None
    assert [ev.kind for ev in events][-2:] == ["ko", "match_end"]
    e.provide_chronicle("A tale.")
    t2 = t + 1.05
    view, _ = e.step([], states(up=(True, True)), t2)
    assert view.chronicle == "A tale." and view.scene == "victory"
    view, _ = e.step([], states(up=(True, True)), t2 + G["victory_min_s"])
    assert view.scene == "lobby" and view.players[0].name == "Ada"


def test_mic_status_reaches_player_view():
    e = Engine(CFG)
    e.provide_mic_status(1, True)
    view, _ = e.step([], states(), 0.0)
    assert (view.players[0].mic_ok, view.players[1].mic_ok) == (False, True)


def test_spell_keys_outside_fight_do_nothing():
    view, _ = Engine(CFG).step([Action("charge", 0, 0.0, spell_id="fireball", match_score=100.0)], states(), 0.0)
    assert view.scene == "lobby" and not view.players[0].spells[0].charged
```

(`e._match` is the engine's current `MatchState` attribute name; keep that name.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/game/test_scenes.py tests/game/test_engine.py -v`
Expected: FAIL (`NotImplementedError`, wrong placeholder scene).

- [ ] **Step 3: Implement `SceneMachine` and `parse_name` in `scenes.py`** per spec §8 (lowercase, strip, remove one leading phrase from `("my name is", "i'm", "i am", "this is", "call me", "it's")`, drop characters that are not letters, spaces, hyphens or apostrophes, collapse spaces, `str.title()`, cap at `max_chars`, `None` when empty).

- [ ] **Step 4: Implement `Engine` in `engine.py`** per spec §8:
  - State: `SceneMachine`, `names` (default `P1`/`P2`, persist), `_incantations: dict | None`, `_match: MatchState | None`, `_chronicle`, `_mic_ok`, `_last_now`, per-slot `untracked_since`, `_result`.
  - `step`: `dt = now - _last_now` (0 on the first call; `_last_now` updates on every step, paused or not, so resuming never jumps); scene work (lobby names; loading fallback at `loading_max_s` using each `SpellDef.fallback[slot]`; fight: paused when a slot has been untracked longer than `pause_after_s`, else apply fight actions and `advance(dt)`; collect `take_events()`); `both_ready` from `states`; `SceneMachine.update`; on entry: loading clears incantations and chronicle, fight creates `MatchState(cfg, names, now)` and collects its `match_start`, victory stores the result, lobby drops the match; build the view.
  - View per spec §8 (banners, `timer_s`, `chronicle`, `SpellView(id, name, incantation, cost, charged, release)`, `ProjectileView`s only in fight, HP/mana from the match in fight and victory, full otherwise; zone/dist/tracking from `states`, defaults `"neutral"`, `0.0`, `False`).
  - `provide_incantations` only in loading (missing ids take the fallback); `provide_chronicle` only in victory.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `rm tests/game/test_engine_stub.py`, then `uv run pytest tests/game -v`, then `uv run pytest`, then `uv run python -m magic_box --fake --headless --max-ticks 60`
Expected: PASS; exit 0. (`tests/pipeline/test_loop.py` still passes: keyboard spells in the lobby only reach intent.)

- [ ] **Step 6: Commit (Daniel runs)**

```bash
git add src/magic_box/game/scenes.py src/magic_box/game/engine.py tests/game
git commit -m "feat(game): add scene flow and the engine facade for a playable match"
```

---

### Task 5: Screen output: projectiles, charged cues, placeholder scenes, fake two-hand key

**Files:**
- Modify: `src/magic_box/render/projectiles.py`, `render/hud.py`, `render/scenes/__init__.py`, `render/scenes/lobby.py`, `render/scenes/loading.py`, `render/scenes/victory.py`, `render/window.py`, `src/magic_box/replay/fake_input.py`
- Create: `tests/render/test_projectiles.py`, `tests/render/test_hud.py`, `tests/render/test_scenes.py`
- Modify tests: `tests/render/test_window.py`, `tests/replay/test_fake_input.py`

**Interfaces:**
- Consumes: Task 1 `SpellView.release`, `render.projectiles` / `render.scenes` config, `keys.fake.<slot>.two_hand_push`.
- Produces:
  - `projectile_screen(p: ProjectileView, half: Rect, crop: Rect, cfg_proj: Mapping) -> tuple[tuple[float, float], float, tuple[int, int, int]]` (center, radius, rgb); `draw_projectiles(surface, half, crop, projectiles, target_slot, cfg_proj, font) -> None`.
  - `RELEASE_CUES: dict[str, str]`, `release_cue(release) -> str`, `spell_line(spell: SpellView) -> str`, `name_line(me: PlayerView) -> str` in `render/hud.py`.
  - `SceneStyle(title_font, text_font, text_rgb, dim_rgb)`, `make_style(scene_cfg) -> SceneStyle` (call after `pygame.init()`), `draw_scene(surface, view, style)`; pure helpers `lobby_lines(view) -> list[str]`, `loading_lines(view, slot) -> list[str]`, `victory_lines(view) -> list[str]`, `wrap_text(text, font, max_w) -> list[str]` in `render/scenes/__init__.py`.

- [ ] **Step 1: Write the failing tests**

`tests/render/test_projectiles.py`:

```python
P = CFG["render"]["projectiles"]
HALF, CROP = Rect(0, 0, 960, 1080), Rect(240, 0, 480, 540)

def pv(progress=0.0, origin=(480.0, 270.0), spell="fireball", window=False, target=0):
    return ProjectileView(spell, target, origin, progress, window)


def test_start_maps_through_crop():
    center, radius, rgb = projectile_screen(pv(), HALF, CROP, P)
    assert center == pytest.approx((480.0, 540.0)) and radius == P["start_radius_px"]
    assert rgb == tuple(P["rgb"]["fireball"])


def test_end_is_bottom_center_and_grows():
    center, radius, _ = projectile_screen(pv(1.0), HALF, CROP, P)
    assert center == pytest.approx((480.0, P["end_y_frac"] * 1080)) and radius == P["end_radius_px"]


def test_origin_outside_crop_is_clamped_to_half():
    center, _, _ = projectile_screen(pv(origin=(0.0, 0.0)), HALF, CROP, P)
    assert center == pytest.approx((0.0, 0.0))


def test_colors_dodge_default_and_basic():
    assert projectile_screen(pv(window=True), HALF, CROP, P)[2] == tuple(P["dodge_rgb"])
    assert projectile_screen(pv(spell="mystery"), HALF, CROP, P)[2] == tuple(P["default_rgb"])
    assert projectile_screen(pv(spell="basic"), HALF, CROP, P)[2] == tuple(P["rgb"]["basic"])


def test_draw_headless_smoke():
    pygame.init()
    try:
        surf = pygame.Surface((1920, 1080))
        font = pygame.font.Font(None, P["font_px"])
        draw_projectiles(surf, HALF, CROP, [pv(0.9, window=True), pv(target=1)], 0, P, font)
        assert tuple(surf.get_at((480, int(0.9 * P["end_y_frac"] * 1080 + 0.1 * 540))))[:3] != (0, 0, 0)
    finally:
        pygame.quit()
```

`tests/render/test_hud.py`:

```python
def test_release_cues_and_spell_lines():
    assert release_cue("two_hand_push") == "TWO-HAND PUSH!" and release_cue("arm_overhead") == "RAISE ARM!"
    assert spell_line(SpellView("heal", "Heal", "mend me", 40.0, True, "hands_together")) == "Heal  CHARGED: HANDS TOGETHER!"
    assert spell_line(SpellView("bolt", "Bolt", "zap now go", 20.0, False)) == 'Bolt: "zap now go"'


def test_name_line_shows_mic_status():
    view = make_view()
    p = dataclasses.replace(view.players[0], mic_ok=False)
    assert name_line(p) == "P1 · mage · MIC OFF"
    assert name_line(view.players[1]).endswith("MIC OK")
```

`tests/render/test_scenes.py`:

```python
def test_lobby_lines_show_names_and_tracking():
    view = make_view(scene="lobby", banner="SAY YOUR NAME · BOTH RAISE YOUR HANDS")
    view = dataclasses.replace(view, players=(view.players[0], dataclasses.replace(view.players[1], tracking_ok=False)))
    lines = lobby_lines(view)
    assert "P1: TRACKED" in lines and "P2: STEP INTO VIEW" in lines


def test_loading_lines_show_incantation_and_cue():
    view = make_view(scene="loading", timer_s=2.4)
    p0 = dataclasses.replace(view.players[0], spells=(
        SpellView("fireball", "Fireball", "embers burn bright", 25.0, False, "push"),
        SpellView("flame_wall", "Flame Wall", "", 30.0, False, "two_hand_push"),
    ))
    lines = loading_lines(dataclasses.replace(view, players=(p0, view.players[1])), 0)
    assert 'Fireball: "embers burn bright", then PUSH!' in lines
    assert 'Flame Wall: "…", then TWO-HAND PUSH!' in lines


def test_victory_lines_wait_for_chronicle():
    assert victory_lines(make_view(scene="victory", chronicle=None)) == ["writing the chronicle…"]
    assert victory_lines(make_view(scene="victory", chronicle="A tale.")) == ["A tale."]


def test_wrap_text_fits_width():
    pygame.init()
    try:
        font = pygame.font.Font(None, 36)
        lines = wrap_text("word " * 200, font, 600)
        assert len(lines) > 1 and all(font.size(line)[0] <= 600 for line in lines)
    finally:
        pygame.quit()
```

Append to `tests/render/test_window.py`:

```python
@pytest.mark.parametrize("scene", ["lobby", "loading", "victory"])
def test_draw_each_placeholder_scene(scene):
    w = Window(CFG, headless=True)
    try:
        w.draw(make_view(scene=scene, chronicle="A long tale. " * 40, timer_s=2.0), None, {}, fps=60.0)
    finally:
        w.close()


def test_draw_fight_with_projectiles():
    w = Window(CFG, headless=True)
    try:
        states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
        view = make_view(projectiles=(ProjectileView("fireball", 0, (480.0, 300.0), 0.5, True),))
        w.draw(view, frame, {s.slot: s for s in states}, fps=60.0)
    finally:
        w.close()
```

Append to `tests/replay/test_fake_input.py`:

```python
def test_two_hand_key_pushes_with_both_wrists():
    fp = FakePlayers(CFG)
    states, _ = fp.step(frozenset({K0["two_hand_push"]}), now=0.0, dt=0.016)
    p1 = _p1(states)
    assert p1.push is not None and p1.wrist_vz == {"L": -FAKE["push_speed_mps"], "R": -FAKE["push_speed_mps"]}
    states, _ = fp.step(frozenset({K0["two_hand_push"]}), now=0.016, dt=0.016)
    assert _p1(states).push is None  # edge-triggered
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/render tests/replay -v`
Expected: FAIL (`ImportError` for the new helpers; `NotImplementedError` from `draw_projectiles`; `KeyError` in fake input).

- [ ] **Step 3: Implement `render/projectiles.py`** per spec §12. `draw_projectiles` skips projectiles for other targets, draws a filled circle per projectile, and for in-window ones renders `"DODGE!"` centered just above the target point in `dodge_rgb`.

- [ ] **Step 4: Implement the HUD helpers and the placeholder scenes**
  - `RELEASE_CUES = {"push": "PUSH!", "two_hand_push": "TWO-HAND PUSH!", "arm_overhead": "RAISE ARM!", "hands_together": "HANDS TOGETHER!"}`; `draw_hud` uses `name_line` and `spell_line`.
  - Scenes: `lobby_lines` = `["MAGIC BOX"]` + per player `f"{name}: TRACKED"` / `f"{name}: STEP INTO VIEW"`; `loading_lines(view, slot)` = `f"{name} · {class_id}"` then per spell `f'{spell.name}: "{spell.incantation or "…"}", then {release_cue(spell.release)}'`, and the countdown line `f"{ceil(timer_s)}"` drawn by `loading.draw`; `victory_lines` = `[chronicle]` or `["writing the chronicle…"]`, wrapped by `victory.draw` to the screen width minus margins, drawn below the window's center banner. Each `draw(surface, view, style)` uses `style` fonts and colors.
  - `window.py`: build `self.scene_style = make_style(self.render_cfg["scenes"])` and `self.proj_font = pygame.font.Font(None, self.render_cfg["projectiles"]["font_px"])` in `__init__`; call `draw_scene(self.screen, view, self.scene_style)` and pass `self.render_cfg["projectiles"], self.proj_font` to `draw_projectiles`.

- [ ] **Step 5: Add the fake two-hand key in `replay/fake_input.py`**: edge-triggered like `push`; on its press the state gets `Push("R", fake.push_speed_mps, r_wrist_px)` and both `wrist_vz` at `-fake.push_speed_mps`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/render tests/replay -v`, then `uv run pytest`, then `uv run python -m magic_box --fake --headless --max-ticks 60`
Expected: PASS; exit 0.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add src/magic_box/render src/magic_box/replay/fake_input.py tests/render tests/replay/test_fake_input.py
git commit -m "feat(render): draw projectiles, charged cues and placeholder scenes"
```

---

### Task 6: Voice: incantation matcher and keywords

**Files:**
- Modify: `src/magic_box/voice/matcher.py`
- Create: `tests/voice/__init__.py` (empty), `tests/voice/test_matcher.py`

**Interfaces:**
- Produces: `normalize(text: str) -> str`; `match_incantation(text: str, incantations: Mapping[str, str], threshold: float) -> tuple[str, float] | None`; `keywords_for(incantations: Mapping[str, str], min_chars: int) -> list[str]` (distinct lowercase words in first-seen order, length `>= min_chars`).

- [ ] **Step 1: Write the failing tests**

```python
INC = {
    "fireball": "embers of the forty acres burn",
    "flame_wall": "rise crimson rampart",
    "inferno": "let the whole sky catch fire",
}
OTHER = {"bolt": "storm of speedway strike", "chain": "thunder binds the tower"}


def test_exact_match_scores_100():
    assert match_incantation("embers of the forty acres burn", INC, 80) == ("fireball", 100.0)


def test_filler_prefix_case_and_punctuation():
    assert match_incantation("Uh, okay... Embers of the Forty Acres burn!", INC, 80) == ("fireball", 100.0)


def test_half_said_partial_does_not_match():
    assert match_incantation("embers of the", INC, 80) is None


def test_misheard_word_still_matches_below_100():
    spell, score = match_incantation("embers of the forty acre burn", INC, 80)
    assert spell == "fireball" and 80 <= score < 100


def test_other_players_incantation_does_not_match():
    assert match_incantation("storm of speedway strike", INC, 80) is None
    assert match_incantation("thunder binds the tower", INC, 80) is None


def test_empty_and_short_incantations():
    assert match_incantation("", INC, 80) is None
    assert match_incantation("rise crimson rampart now", INC, 80) == ("flame_wall", 100.0)


def test_normalize():
    assert normalize("  Hello,   WORLD!! ") == "hello world"


def test_keywords_for():
    assert keywords_for(INC, 4) == [
        "embers", "forty", "acres", "burn", "rise", "crimson", "rampart", "whole", "catch", "fire",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/voice/test_matcher.py -v`
Expected: FAIL (`NotImplementedError` / `ImportError`).

- [ ] **Step 3: Implement `voice/matcher.py`** per spec §9 (`rapidfuzz.fuzz.ratio` over word windows of sizes `n-1, n, n+1` (≥ 1); a transcript shorter than every window size is scored whole; best spell at or above `threshold`, ties to the first spell).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/voice -v`
Expected: PASS.

- [ ] **Step 5: Commit (Daniel runs)**

```bash
git add src/magic_box/voice/matcher.py tests/voice/__init__.py tests/voice/test_matcher.py
git commit -m "feat(voice): match incantations with a sliding word window"
```

---

### Task 7: Voice: Muse realtime WebSocket client

**Files:**
- Modify: `src/magic_box/voice/muse_stream.py`
- Create: `tests/voice/fake_muse.py`, `tests/voice/test_muse_stream.py`

**Interfaces:**
- Produces: `MuseError(Exception)`; `handshake(api_key: str, model: str, keywords: Sequence[str]) -> dict`; `MuseStream(url: str, api_key: str, model: str, handshake_timeout_s: float)` with `session_id: str | None`, `close_code: int | None`, `async connect(keywords: Sequence[str]) -> None`, `async send_audio(pcm: bytes) -> None`, `events() -> AsyncIterator[dict]` (async generator; ends when the socket closes, then `close_code` is set), `async close() -> None`.
- Test helper `tests/voice/fake_muse.py` (docstring `Owner: Nikhil`): `FakeMuse(script)` async context manager running `websockets.asyncio.server.serve` on `127.0.0.1:0`; attributes `url`, `handshakes: list[dict]`, `audio: list[bytes]`, `texts: list[dict]` (text frames after the handshake). `script` is a list of steps run after the handshake frame arrives: `("send", dict)`, `("wait_audio", n)` (until n binary frames arrived), `("wait_text", type)` (until a text frame with that `type` arrived), `("close", code)`, `("sleep", s)`.

- [ ] **Step 1: Write the failing tests**

```python
def arun(coro, timeout=5.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


def test_handshake_fields():
    assert handshake("k", "muse-voice-transcribe-1.0", ["embers"]) == {
        "authorization": {"accessToken": "Bearer k"},
        "audioEncoding": "PCM_16KHZ",
        "model": "muse-voice-transcribe-1.0",
        "mode": "ENDPOINTING",
        "partialMode": "CUMULATIVE",
        "emitAudioProgress": False,
        "keywords": ["embers"],
    }
    assert "keywords" not in handshake("k", "m", [])


def test_connect_reads_session_id():
    async def go():
        async with FakeMuse([("send", {"sessionId": "abc"}), ("sleep", 0.2)]) as srv:
            ms = MuseStream(srv.url, "k", "m", 1.0)
            await ms.connect(["embers"])
            assert ms.session_id == "abc"
            assert srv.handshakes[0]["authorization"]["accessToken"] == "Bearer k"
            await ms.close()
    arun(go())


def test_handshake_timeout_raises():
    async def go():
        async with FakeMuse([("sleep", 2.0)]) as srv:
            with pytest.raises(MuseError):
                await MuseStream(srv.url, "k", "m", 0.2).connect([])
    arun(go())


def test_error_frame_on_handshake_raises():
    async def go():
        async with FakeMuse([("send", {"type": "error", "message": "bad key", "sessionId": ""})]) as srv:
            with pytest.raises(MuseError, match="bad key"):
                await MuseStream(srv.url, "k", "m", 1.0).connect([])
    arun(go())


def test_audio_is_binary_and_events_are_yielded():
    script = [
        ("send", {"sessionId": "s"}), ("wait_audio", 2),
        ("send", {"type": "speechStart", "turnId": 1, "audioProcessedMs": 0}),
        ("send", {"type": "transcript", "transcript": "embers", "final": False, "audioProcessedMs": 80}),
        ("send", {"type": "somethingNew"}),
        ("close", 1000),
    ]
    async def go():
        async with FakeMuse(script) as srv:
            ms = MuseStream(srv.url, "k", "m", 1.0)
            await ms.connect([])
            await ms.send_audio(b"\x00\x01" * 640)
            await ms.send_audio(b"\x00\x01" * 640)
            types = [ev.get("type") async for ev in ms.events()]
            assert types == ["speechStart", "transcript", "somethingNew"]
            assert srv.audio == [b"\x00\x01" * 640] * 2 and ms.close_code == 1000
    arun(go())


def test_close_sends_end_stream():
    async def go():
        async with FakeMuse([("send", {"sessionId": "s"}), ("wait_text", "endStream"), ("close", 1000)]) as srv:
            ms = MuseStream(srv.url, "k", "m", 1.0)
            await ms.connect([])
            await ms.close()
            await asyncio.sleep(0.1)
            assert srv.texts == [{"type": "endStream"}]
    arun(go())


def test_server_close_code_is_exposed():
    async def go():
        async with FakeMuse([("send", {"sessionId": "s"}), ("close", 1011)]) as srv:
            ms = MuseStream(srv.url, "k", "m", 1.0)
            await ms.connect([])
            assert [ev async for ev in ms.events()] == [] and ms.close_code == 1011
    arun(go())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/voice/test_muse_stream.py -v`
Expected: FAIL (`ImportError` / `NotImplementedError`).

- [ ] **Step 3: Write `tests/voice/fake_muse.py`, then implement `voice/muse_stream.py`** per spec §9 with `websockets.asyncio.client.connect` (`open_timeout=handshake_timeout_s`). The handshake reply wait uses `asyncio.wait_for(ws.recv(), handshake_timeout_s)`; a reply with `"type": "error"` raises `MuseError(message)`; a timeout or a close during the wait raises `MuseError`. `events()` parses each text frame with `json.loads` (skips binary frames and invalid JSON) and, on `ConnectionClosed`, records `ws.close_code` and returns. `close()` sends `endStream` when the socket is open (ignoring `ConnectionClosed`) and closes it. Never include the key in exception messages.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/voice -v`
Expected: PASS.

- [ ] **Step 5: Commit (Daniel runs)**

```bash
git add src/magic_box/voice/muse_stream.py tests/voice/fake_muse.py tests/voice/test_muse_stream.py
git commit -m "feat(voice): add the muse realtime websocket client"
```

---

### Task 8: Voice: per-player mic capture

**Files:**
- Modify: `src/magic_box/voice/mic.py` (replace the `MicCapture` stub)
- Create: `tests/voice/fake_sd.py`, `tests/voice/test_mic.py`

**Interfaces:**
- Produces: `MicError(Exception)`; `resample(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray` (int16 in, int16 out, length `round(len * dst / src)`); `MicHub(mics: Sequence[Mapping], sample_rate: int, chunk_ms: int, sink: Callable[[int, bytes], None], sd=None)` with `start() -> None` (raises `MicError`) and `stop() -> None`. `sd` is an injectable `sounddevice`-like module; `None` means `import sounddevice` inside `start()`.
- Test helper `tests/voice/fake_sd.py` (docstring `Owner: Nikhil`): `FakeSD(reject_rates=(), default_rate=48000.0, fail_import=False)` exposing `InputStream` (records its kwargs in `FakeSD.streams`, has `start()`, `stop()`, `close()`, `closed`, and `feed(indata: np.ndarray)` that calls the stream's callback with `(indata, len(indata), None, None)`; raises `FakeSD.PortAudioError` from the constructor when `samplerate` is in `reject_rates`), `query_devices(device, kind)` returning `{"default_samplerate": default_rate}`, and `PortAudioError`.

- [ ] **Step 1: Write the failing tests**

```python
CHUNK = 1280  # 80 ms at 16 kHz

def hub(mics, sd, got):
    return MicHub(mics, 16000, 80, lambda slot, pcm: got.append((slot, pcm)), sd=sd)


def test_one_stream_per_device_and_channel_split():
    sd, got = FakeSD(), []
    h = hub([{"slot": 0, "device": "rx", "channel": 0}, {"slot": 1, "device": "rx", "channel": 1}], sd, got)
    h.start()
    [stream] = sd.streams
    assert stream.kwargs["channels"] == 2 and stream.kwargs["samplerate"] == 16000 and stream.kwargs["dtype"] == "int16"
    data = np.zeros((CHUNK, 2), np.int16)
    data[:, 0], data[:, 1] = 1, 2
    stream.feed(data)
    assert [(s, np.frombuffer(p, np.int16)[0], len(p)) for s, p in got] == [(0, 1, CHUNK * 2), (1, 2, CHUNK * 2)]


def test_two_devices_two_streams():
    sd, got = FakeSD(), []
    hub([{"slot": 0, "device": "a", "channel": 0}, {"slot": 1, "device": "b", "channel": 0}], sd, got).start()
    assert [s.kwargs["device"] for s in sd.streams] == ["a", "b"]


def test_rate_fallback_resamples_to_16k():
    sd, got = FakeSD(reject_rates=(16000,), default_rate=48000.0), []
    hub([{"slot": 0, "device": None, "channel": 0}], sd, got).start()
    stream = sd.streams[-1]  # the retry at the device's default rate
    assert stream.kwargs["samplerate"] == 48000
    stream.feed(np.full((CHUNK * 3, 1), 7, np.int16))
    assert len(got) == 1 and got[0][0] == 0 and len(got[0][1]) == CHUNK * 2
    assert set(np.frombuffer(got[0][1], np.int16)) == {7}


def test_chunks_buffered_across_callbacks():
    sd, got = FakeSD(), []
    hub([{"slot": 0, "device": None, "channel": 0}], sd, got).start()
    sd.streams[0].feed(np.ones((CHUNK // 2, 1), np.int16))
    assert got == []
    sd.streams[0].feed(np.ones((CHUNK // 2, 1), np.int16))
    assert len(got) == 1


def test_missing_portaudio_raises_mic_error_and_stop_closes():
    with pytest.raises(MicError):
        hub([{"slot": 0, "device": None, "channel": 0}], FakeSD(fail_import=True), []).start()
    sd = FakeSD()
    h = hub([{"slot": 0, "device": None, "channel": 0}], sd, [])
    h.start()
    h.stop()
    assert all(s.closed for s in sd.streams)


def test_resample():
    out = resample(np.full(4800, 5, np.int16), 48000, 16000)
    assert out.dtype == np.int16 and len(out) == 1600 and set(out) == {5}
```

(`FakeSD(fail_import=True)` makes `InputStream` raise `OSError("PortAudio library not found")`, which is what `sounddevice` raises without PortAudio. `FakeSD.streams` records only streams that were constructed successfully.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/voice/test_mic.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Write `tests/voice/fake_sd.py`, then implement `voice/mic.py`** per spec §9. `start()`: `sd = self._sd or import sounddevice` (an `OSError`/`ImportError` on import → `MicError`); per device, open `InputStream(device=..., channels=max(channel)+1, samplerate=sample_rate, dtype="int16", blocksize=rate*chunk_ms//1000, callback=...)`; on any exception, read `query_devices(device, "input")["default_samplerate"]` and retry once at that rate; a second failure → `MicError`. The callback takes column `channel` per slot, resamples when the stream rate differs, appends to that slot's buffer, and calls `sink(slot, chunk.tobytes())` for every full `sample_rate * chunk_ms // 1000`-sample chunk. Never raise from the callback.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/voice -v`
Expected: PASS.

- [ ] **Step 5: Commit (Daniel runs)**

```bash
git add src/magic_box/voice/mic.py tests/voice/fake_sd.py tests/voice/test_mic.py
git commit -m "feat(voice): capture per-player mics with one stream per device"
```

---

### Task 9: Voice process: per-player Muse sessions

**Files:**
- Modify: `src/magic_box/voice/process.py`
- Create: `tests/voice/test_process.py`

**Interfaces:**
- Consumes: Task 6 `match_incantation`, `keywords_for`; Task 7 `MuseStream`, `MuseError`; Task 8 `MicHub`, `MicError`.
- Produces:
  - `async serve(cfg, publish: Callable[[VoiceEvent], None], drain_control: Callable[[], list], should_stop: Callable[[], bool], *, env: Mapping[str, str], stream_factory: Callable[[int, str], object], mic_factory: Callable[[Callable[[int, bytes], None]], object], sleep=asyncio.sleep, clock=time.monotonic) -> None`. `stream_factory(slot, api_key)` returns a fresh object with `MuseStream`'s async interface; `mic_factory(sink)` returns an object with `start()` / `stop()`; the sink is called from the audio thread. The injected `sleep` is used **only** for reconnect backoff delays (polling uses `asyncio.sleep` directly), so tests can record backoffs.
  - `run(cfg, voice_q, control_q, stop) -> None`: `asyncio.run(serve(cfg, voice_q.put, control_q.drain, stop.is_set, env=os.environ, stream_factory=lambda slot, key: MuseStream(<cfg.voice url, model, handshake_timeout_s>), mic_factory=lambda sink: MicHub(<cfg.voice mics, sample_rate, chunk_ms>, sink)))`.

- [ ] **Step 1: Write the failing tests**

Test doubles in the test module: `FakeStream` (records `keywords` per `connect`, `audio` frames and `closed`; `connect` can be scripted to raise `MuseError`; `events()` yields dicts pushed into an `asyncio.Queue` by the test and ends with a scripted `close_code` when the test pushes `None`), a `StreamFactory(scripts: dict[int, list])` whose `__call__(slot, api_key)` hands out that slot's scripted `FakeStream`s in order (a healthy idle stream once a slot's script runs out) and records them per slot (`streams_for_slot`, `keywords_for_slot`, `streams`), and `FakeMic` (stores the sink; `start()` can raise `MicError`). `fast_cfg()` deep-copies `CFG` with `silence_after_s=0.05`, `reconnect_backoff_s=0.01`, `reconnect_max_s=0.04`, `session_max_s=60`. Each test runs `serve` in `asyncio.wait_for(..., 5)` and flips `should_stop` when its condition is met (helper `until(cond)` polls every 10 ms).

```python
INC = {0: {"fireball": "embers of the forty acres burn"}, 1: {"bolt": "storm of speedway strike"}}
ENV = {"META_MODEL_API_KEY": "k"}

def test_no_api_key_publishes_status_and_idles():
    events = run_serve(env={}, stop_after=0.3)
    assert [(e.slot, e.kind, e.text) for e in events] == [(0, "status", "no api key"), (1, "status", "no api key")]


def test_no_mic_publishes_status_and_idles():
    events = run_serve(mic=FakeMic(fail=True), stop_after=0.3)
    assert {(e.slot, e.text) for e in events} == {(0, "no mic"), (1, "no mic")}


def test_incantation_mode_one_event_per_turn():
    # configs: [VoiceConfig("incantation", INC)] before the first poll; slot 0's second stream gets:
    # speechStart, transcript "embers of the", transcript "embers of the forty acres burn",
    # transcript "embers of the forty acres burn now", speechComplete, speechStart,
    # transcript "embers of the forty acres burn"
    inc = [e for e in events if e.kind == "incantation"]
    assert [(e.slot, e.spell_id, e.match_score) for e in inc] == [(0, "fireball", 100.0), (0, "fireball", 100.0)]


def test_final_text_matched_when_no_partial_matched():
    # speechStart, speechComplete "embers of the forty acres burn"
    assert [e.spell_id for e in events if e.kind == "incantation"] == ["fireball"]


def test_only_own_players_set_matches():
    # slot 0 hears speechStart, transcript "storm of speedway strike", speechComplete same
    assert [e for e in events if e.kind == "incantation"] == []


def test_transcript_mode_emits_final_text_only():
    # no config (starts in transcript mode); slot 1: speechStart, transcript "my name", speechComplete "my name is ada"
    assert [(e.slot, e.kind, e.text) for e in events if e.kind == "transcript"] == [(1, "transcript", "my name is ada")]


def test_config_change_restarts_with_new_keywords():
    # first connect per slot has keywords []; after VoiceConfig("incantation", INC) each slot reconnects once
    assert factory.keywords_for_slot(0) == [[], ["embers", "forty", "acres", "burn"]]
    assert factory.keywords_for_slot(1) == [[], ["storm", "speedway", "strike"]]


def test_burst_of_configs_restarts_once_with_newest():
    # three VoiceConfigs queued before one poll: incantation(other), transcript, incantation(INC)
    assert factory.keywords_for_slot(0) == [[], ["embers", "forty", "acres", "burn"]]


def test_drop_reconnects_with_backoff_and_status():
    # slot 0's first stream closes with 1011 right after connect
    statuses = [e.text for e in events if e.kind == "status" and e.slot == 0]
    assert statuses[:3] == ["connected", "reconnecting", "connected"]
    assert sleeps[0] == pytest.approx(0.01)


def test_close_1008_uses_max_backoff():
    # slot 0's first stream closes with 1008
    assert sleeps[0] == pytest.approx(0.04)


def test_handshake_failure_retries_and_never_exits():
    # slot 0: connect raises MuseError twice, then succeeds
    statuses = [e.text for e in events if e.kind == "status" and e.slot == 0]
    assert statuses[:3] == ["reconnecting", "reconnecting", "connected"]
    assert sleeps[:2] == pytest.approx([0.01, 0.02])


def test_mic_chunks_forwarded_and_silence_when_quiet():
    # FakeMic.sink(0, b"\x01\x00" * 1280) once; then nothing for 0.2 s
    frames = factory.streams_for_slot(0)[0].audio
    assert frames[0] == b"\x01\x00" * 1280
    assert b"\x00" * 2560 in frames[1:]


def test_session_reopened_at_max_age():
    # session_max_s = 0.1: slot 0 connects at least twice, with no "reconnecting" status
    assert len(factory.streams_for_slot(0)) >= 2
    assert "reconnecting" not in [e.text for e in events if e.slot == 0]


def test_stop_closes_streams():
    assert all(s.closed for s in factory.streams)


def test_run_without_key_returns_on_stop(monkeypatch):
    monkeypatch.delenv("META_MODEL_API_KEY", raising=False)
    q, stop = ListQueue(), threading.Event()
    threading.Timer(0.3, stop.set).start()
    run(CFG, q, ListQueue(), stop)
    assert [e.text for e in q.items] == ["no api key", "no api key"]
```

(The comments describe each test's script; write each fully with the doubles above. Only slot 0 is scripted to fail, so `sleeps` (the delays passed to a recording `sleep` given to `serve`) are all slot 0's backoffs. `ListQueue` has `put(item)` → `items.append` and `drain()` → pop all.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/voice/test_process.py -v`
Expected: FAIL (`ImportError` for `serve`).

- [ ] **Step 3: Implement `voice/process.py`** per spec §9:
  - Startup checks (key → `"no api key"`; `MicError` from `mic.start()` → `"no mic"`) publish one status per slot, then idle until `should_stop()` (poll every 0.1 s). Mic chunks reach per-slot `asyncio.Queue(maxsize=voice.audio_queue_chunks)` through `loop.call_soon_threadsafe`, dropping a chunk when the queue is full.
  - Mode starts as `("transcript", {})` and the session tasks start at once (the loop's first transcript `VoiceConfig` is then a no-op). A control task drains every 0.1 s and applies only the newest config; a change bumps a generation counter and wakes both sessions.
  - Per-slot session loop, sender, receiver, statuses, backoff (reset after a session lasts 30 s), 1008 handling, `session_max_s` reopen (publishes `"connected"` again, no `"reconnecting"`), and stop handling exactly as spec §9. Any exception from `connect` / `send_audio` / `events` counts as a drop; the loop never exits until stop.
  - `publish` gets `VoiceEvent(slot, clock(), kind, text, spell_id, score)`; statuses use `spell_id=None`, `match_score=0.0`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/voice -v`, then `uv run pytest`
Expected: PASS. The suite stays fast (each process test well under 1 s).

- [ ] **Step 5: Commit (Daniel runs)**

```bash
git add src/magic_box/voice/process.py tests/voice/test_process.py
git commit -m "feat(voice): run per-player muse sessions with reconnects and mode changes"
```

---

### Task 10: Spark: client, incantations, chronicle

**Files:**
- Modify: `src/magic_box/ai/spark_client.py`, `ai/incantations.py`, `ai/chronicle.py`
- Create: `tests/ai/__init__.py` (empty), `tests/ai/fakes.py`, `tests/ai/test_spark_client.py`, `tests/ai/test_incantations.py`, `tests/ai/test_chronicle.py`

**Interfaces:**
- Produces:
  - `SparkUnavailable(RuntimeError)`; `SparkClient(cfg, env: Mapping[str, str] | None = None, openai_factory: Callable[..., object] | None = None)` with `complete(system: str, user: str) -> str`. `env` defaults to `os.environ`; `openai_factory` defaults to `openai.OpenAI` (imported inside).
  - `fallback_incantations(classes: Mapping[int, str], cfg) -> dict[int, dict[str, str]]`; `validate_incantations(raw: object, classes, cfg) -> dict[int, dict[str, str]]`; `generate_incantations(client, classes, names: Mapping[int, str], cfg) -> dict[int, dict[str, str]]`.
  - `summarize(events: Sequence[GameEvent], names, cfg) -> dict`; `template_chronicle(events, names, cfg) -> str`; `write_chronicle(client, events, names, cfg) -> str`.
- Test helpers `tests/ai/fakes.py` (docstring `Owner: Nikhil`): `FakeOpenAI(reply: str | Exception)` usable as `openai_factory` (records the constructor kwargs; `.chat.completions.create(**kw)` records kw and returns an object with `.choices[0].message.content == reply`, or raises); `FakeClient(reply: str | Exception)` with `complete(system, user)` recording calls.

- [ ] **Step 1: Write the failing tests**

`tests/ai/test_spark_client.py`:

```python
def test_complete_uses_config_and_env_key():
    fake = FakeOpenAI("hello")
    client = SparkClient(CFG, env={"META_MODEL_API_KEY": "k"}, openai_factory=fake)
    assert client.complete("sys", "usr") == "hello"
    assert fake.kwargs == {"base_url": "https://api.meta.ai/v1", "api_key": "k", "timeout": 8, "max_retries": 0}
    call = fake.calls[0]
    assert call["model"] == "muse-spark-1.3" and call["temperature"] == 0.9
    assert call["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]


def test_missing_key_or_disabled_raises_unavailable():
    with pytest.raises(SparkUnavailable):
        SparkClient(CFG, env={}, openai_factory=FakeOpenAI("x")).complete("s", "u")
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["enabled"] = False
    with pytest.raises(SparkUnavailable):
        SparkClient(cfg, env={"META_MODEL_API_KEY": "k"}, openai_factory=FakeOpenAI("x")).complete("s", "u")
```

`tests/ai/test_incantations.py`:

```python
CLASSES = {0: "fire_mage", 1: "lightning_mage"}
NAMES = {0: "Ada", 1: "Bo"}
GOOD = {
    "0": {"fireball": "embers dance on the drag", "flame_wall": "rise wall of cedar smoke", "inferno": "let sixth street blaze tonight"},
    "1": {"bolt": "thunder over zilker hill", "chain": "lightning links the river bridges", "static_field": "hum across the capitol dome"},
}

def test_fallback_from_config():
    fb = fallback_incantations(CLASSES, CFG)
    assert fb[0]["fireball"] == "embers of the forty acres burn" and fb[1]["bolt"] == "lightning answer my call"


def test_generate_accepts_valid_reply():
    client = FakeClient(json.dumps(GOOD))
    out = generate_incantations(client, CLASSES, NAMES, CFG)
    assert out == {0: GOOD["0"], 1: GOOD["1"]}
    system, user = client.calls[0]
    assert "Ada" in user and "fire_mage" in user and "fireball" in user


def test_code_fence_is_stripped():
    out = generate_incantations(FakeClient("```json\n" + json.dumps(GOOD) + "\n```"), CLASSES, NAMES, CFG)
    assert out[1]["bolt"] == "thunder over zilker hill"


def test_invalid_entries_fall_back_per_spell():
    raw = copy.deepcopy(GOOD)
    raw["0"]["fireball"] = "one two three four five six seven eight"   # too long
    raw["0"]["flame_wall"] = "too short"                                # too short
    raw["0"]["inferno"] = "fire 2 go now"                               # digit
    raw["1"]["chain"] = raw["1"]["bolt"]                                # duplicate in own set
    del raw["1"]["static_field"]                                        # missing
    out = validate_incantations(raw, CLASSES, CFG)
    fb = fallback_incantations(CLASSES, CFG)
    assert out[0] == fb[0]
    assert out[1] == {"bolt": GOOD["1"]["bolt"], "chain": fb[1]["chain"], "static_field": fb[1]["static_field"]}


def test_identical_sets_force_fallback_for_slot_1():
    raw = {"0": GOOD["0"], "1": dict(zip(GOOD["1"], GOOD["0"].values(), strict=True))}
    out = validate_incantations(raw, CLASSES, CFG)
    assert out[0] == GOOD["0"] and out[1] == fallback_incantations(CLASSES, CFG)[1]


@pytest.mark.parametrize("reply", ["not json", "[]", '{"0": 5}', RuntimeError("boom")])
def test_garbage_or_exception_gives_full_fallback(reply):
    assert generate_incantations(FakeClient(reply), CLASSES, NAMES, CFG) == fallback_incantations(CLASSES, CFG)
```

`tests/ai/test_chronicle.py`:

```python
NAMES = {0: "Ada", 1: "Bo"}

def ev(kind, slot=None, **data):
    return GameEvent(0.0, kind, slot, data)

KO_LOG = [
    ev("match_start", names={0: "Ada", 1: "Bo"}, classes={0: "fire_mage", 1: "lightning_mage"}),
    ev("cast", 0, spell_id="fireball", release="push", two_hand=False),
    ev("hit", 0, spell_id="fireball", damage=19.8, target=1, hp_left=80.2),
    ev("dodge", 1, spell_id="basic", dodge="duck"),
    ev("ko", 0, winner=0),
    ev("match_end", None, winner=0, reason="ko", hp={0: 100.0, 1: 0.0}),
]


def test_template_ko_mentions_names_classes_big_hit_and_ending():
    text = template_chronicle(KO_LOG, NAMES, CFG)
    for part in ("Ada", "Bo", "Fire Mage", "Lightning Mage", "Fireball", "19.8", "knocked out"):
        assert part in text


def test_template_time_out_and_draw():
    timeout = KO_LOG[:4] + [ev("match_end", None, winner=1, reason="time", hp={0: 40.0, 1: 60.0})]
    assert "time" in template_chronicle(timeout, NAMES, CFG) and "Bo" in template_chronicle(timeout, NAMES, CFG)
    draw = KO_LOG[:1] + [ev("match_end", None, winner=None, reason="time", hp={0: 100.0, 1: 100.0})]
    assert "draw" in template_chronicle(draw, NAMES, CFG).lower()


def test_template_handles_empty_log():
    assert "Ada" in template_chronicle([], NAMES, CFG)


def test_write_chronicle_uses_client_then_falls_back():
    client = FakeClient("A short tale of Ada and Bo.")
    assert write_chronicle(client, KO_LOG, NAMES, CFG) == "A short tale of Ada and Bo."
    assert "Ada" in client.calls[0][1] and "fireball" in client.calls[0][1].lower()
    for bad in ("", "   ", RuntimeError("down")):
        assert write_chronicle(FakeClient(bad), KO_LOG, NAMES, CFG) == template_chronicle(KO_LOG, NAMES, CFG)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/ai -v`
Expected: FAIL (`ImportError` / `NotImplementedError`).

- [ ] **Step 3: Implement `ai/spark_client.py`** per spec §10. Create the OpenAI client lazily on the first `complete`; raise `SparkUnavailable` before touching the factory when disabled or keyless; return `choices[0].message.content or ""`.

- [ ] **Step 4: Implement `ai/incantations.py`** per spec §10. Prompt: a system message saying it writes short spoken incantations for a two-player magic duel game at HackTX in Austin, Texas, and must reply with only JSON; a user message listing each player's name, class id and spells (id, display name, damage) and the rules (min–max words, letters/spaces/apostrophes only, easy to say, Texas / Austin / HackTX flavor, the two players' sets clearly different). `validate_incantations` accepts string or int slot keys, normalizes with `rapidfuzz.utils.default_process` for the uniqueness and `fuzz.ratio` checks, validates slot 0 then slot 1 (against slot 0's final set), and replaces each failing entry with its fallback.

- [ ] **Step 5: Implement `ai/chronicle.py`** per spec §10. `summarize` returns names, class display names (read from `cfg["game"]["classes"][id]["name"]`; `ai/` does not import `game/`), spell display names the same way, casts and hits per slot, the biggest hit, dodges per slot, winner and reason. The template's ending sentence uses "knocked out" for a KO, "when time ran out" for a time-out, and "a draw" for no winner; with no `match_start`, it uses `names` and omits classes.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/ai -v`, then `uv run pytest`
Expected: PASS.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add src/magic_box/ai tests/ai
git commit -m "feat(ai): generate incantations and the duel chronicle with spark and fallbacks"
```

---

### Task 11: AI worker and game-loop wiring

**Files:**
- Create: `src/magic_box/ai/worker.py`, `tests/ai/test_worker.py`
- Modify: `src/magic_box/pipeline/loop.py`, `src/magic_box/main.py`, `tests/pipeline/test_loop.py`

**Interfaces:**
- Consumes: Task 10 functions; Task 4 `Engine.provide_*`; Task 1 `VoiceConfig` (unchanged).
- Produces:
  - `AiWorker(cfg, client=None)` (default `SparkClient(cfg)`): `start_incantations(classes: Mapping[int, str], names: Mapping[int, str], now: float) -> None`, `start_chronicle(events: Sequence[GameEvent], names, now) -> None`, `poll(now) -> list[tuple[str, object]]` (`"incantations"` → dict, `"chronicle"` → str), `close() -> None`.
  - `GameLoop(cfg, sources, display, intent, engine, keyboard_voice, on_tick=None, *, ai=None, voice_control=None, clock=time.monotonic)`. `voice_control` is anything with `put(item)`.

- [ ] **Step 1: Write the failing tests**

`tests/ai/test_worker.py` (`BlockingClient` blocks `complete` on a `threading.Event`):

```python
CLASSES, NAMES = {0: "fire_mage", 1: "lightning_mage"}, {0: "Ada", 1: "Bo"}

def wait_poll(w, now, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        out = w.poll(now)
        if out:
            return out
        time.sleep(0.01)
    return []


def test_finished_job_returned_once():
    w = AiWorker(CFG, client=FakeClient(RuntimeError("down")))
    w.start_incantations(CLASSES, NAMES, now=0.0)
    assert wait_poll(w, 0.1) == [("incantations", fallback_incantations(CLASSES, CFG))]
    assert w.poll(0.2) == []
    w.close()


def test_timeout_returns_fallback_and_drops_late_result():
    client = BlockingClient(json.dumps(GOOD))
    w = AiWorker(CFG, client=client)
    w.start_incantations(CLASSES, NAMES, now=0.0)
    assert w.poll(1.0) == []
    assert w.poll(CFG["ai"]["timeout_s"] + 0.01) == [("incantations", fallback_incantations(CLASSES, CFG))]
    client.release.set()
    time.sleep(0.1)
    assert w.poll(20.0) == []
    w.close()


def test_new_job_replaces_pending_of_same_kind():
    client = BlockingClient("A tale.")
    w = AiWorker(CFG, client=client)
    w.start_chronicle([], NAMES, now=0.0)
    w.start_chronicle([], {0: "Cy", 1: "Di"}, now=1.0)
    client.release.set()
    out = wait_poll(w, 1.5)
    assert out == [("chronicle", "A tale.")] and w.poll(2.0) == []
    w.close()


def test_disabled_resolves_to_fallbacks():
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["enabled"] = False
    w = AiWorker(cfg)
    w.start_chronicle([], NAMES, now=0.0)
    assert wait_poll(w, 0.1) == [("chronicle", template_chronicle([], NAMES, cfg))]
    w.close()
```

(Import `GOOD` from `tests/ai/test_incantations.py` or redefine it; import `FakeClient` from `tests/ai/fakes.py`.)

Append to `tests/pipeline/test_loop.py` (`SceneEngine` returns `make_view(scene=...)` from a script and records `provide_*` calls; `FakeAi` records `start_*` calls and returns scripted `poll` results; `ListQueue` records `put`; `FakeClock` returns 0, 1/60, 2/60, … per call):

```python
def test_voice_configs_on_first_tick_and_scene_changes():
    q = ListQueue()
    engine = SceneEngine(["lobby", "lobby", "loading", "fight", "fight", "victory", "lobby"])
    GameLoop(CFG, FakeSources(CFG), ScriptedDisplay([]), Intent(CFG), engine, KeyboardVoiceSource(CFG),
             ai=FakeAi(), voice_control=q).run(max_ticks=7)
    assert [(c.mode, c.incantations) for c in q.items] == [
        ("transcript", {}),
        ("incantation", {0: {"fireball": "embers burn"}, 1: {"fireball": "embers burn"}}),
        ("transcript", {}),
    ]


def test_ai_jobs_on_loading_and_victory_and_results_delivered():
    ai = FakeAi(poll_results=[[], [], [("incantations", {0: {}, 1: {}})], [], [("chronicle", "A tale.")]])
    engine = SceneEngine(["lobby", "loading", "loading", "fight", "victory"], events={3: ["match_start", "hit"]})
    GameLoop(CFG, FakeSources(CFG), ScriptedDisplay([]), Intent(CFG), engine, KeyboardVoiceSource(CFG),
             ai=ai).run(max_ticks=5)
    assert ai.started == [("incantations", {0: "mage", 1: "mage"}, {0: "P1", 1: "P2"}),
                          ("chronicle", ["match_start", "hit"], {0: "P1", 1: "P2"})]
    assert engine.provided == [("incantations", {0: {}, 1: {}}), ("chronicle", "A tale.")]


def test_status_events_reach_engine_and_intent():
    class StatusSources(FakeSources):
        def poll(self, keys, now, dt):
            got = super().poll(keys, now, dt)
            return replace(got, voice=[VoiceEvent(1, now, "status", "connected", None, 0.0)])
    engine, intent = SceneEngine(["lobby"]), SpyIntent(CFG)
    GameLoop(CFG, StatusSources(CFG), ScriptedDisplay([]), intent, engine, KeyboardVoiceSource(CFG)).run(max_ticks=1)
    assert engine.mic == [(1, True)] and [e.kind for e in intent.voice] == ["status"]


def test_full_fake_match_reaches_a_hit():
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["enabled"] = False
    k0 = cfg["keys"]["fake"]
    script = [{k0[0]["hands_up"], k0[1]["hands_up"]}] * 5 + [set()] * 620 + [{"1"}, set(), {k0[0]["push"]}] + [set()] * 150
    display = RecordingDisplay(script)   # ScriptedDisplay that also keeps every view
    loop = GameLoop(cfg, FakeSources(cfg), display, Intent(cfg), Engine(cfg), KeyboardVoiceSource(cfg),
                    ai=AiWorker(cfg), clock=FakeClock(1 / 60))
    loop.run(max_ticks=len(script))
    scenes = [v.scene for v in display.views]
    assert scenes[0] == "lobby" and "loading" in scenes and scenes[-1] == "fight"
    assert display.views[-1].players[1].hp < cfg["game"]["hp_max"]
```

(The worker result arrives on a real thread. The 620 idle ticks are ≈ 10.3 s of fake time, past `loading_max_s`, so the fight starts even if the result lags; with the result on time the fight starts at `loading_min_s` and the rest of the idle ticks pass in the fight.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/ai/test_worker.py tests/pipeline/test_loop.py -v`
Expected: FAIL (`ImportError` for `AiWorker`; `GameLoop` has no `ai` / `voice_control` / `clock`).

- [ ] **Step 3: Implement `ai/worker.py`** per spec §10 (single-thread `ThreadPoolExecutor`; per kind, the pending `(future, deadline, fallback_fn)`; `poll` returns the result for a done future, or the fallback once `now >= deadline` while marking that future abandoned; a replaced or abandoned future's result is never returned).

- [ ] **Step 4: Wire `pipeline/loop.py`** per spec §11: `now = clock()`; the previous scene starts as `None`, so the first tick counts as entering its scene (the engine starts in `lobby`, which sends the transcript config, satisfying spec §11's first-tick rule without a duplicate); compare `view.scene` with the previous tick's and act on entry (configs built from the view, jobs started with `{p.slot: p.class_id}` and `{p.slot: p.name}`); keep the current match's events (reset when a `match_start` event arrives); deliver `ai.poll(now)` results; call `engine.provide_mic_status(e.slot, e.text == "connected")` for status events before `engine.step`. Remove the two `TODO(Nikhil)` comments.

- [ ] **Step 5: Wire `main.py`**: build `AiWorker(cfg)` for every mode and pass `ai=`; pass `voice_control=runtime.control_q` in live mode; close the worker in `finally`. Remove the `VoiceConfig` `TODO(Nikhil)` comment.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/ai tests/pipeline -v`, then `uv run pytest`, then `uv run python -m magic_box --fake --headless --max-ticks 600`
Expected: PASS; exit 0.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add src/magic_box/ai/worker.py src/magic_box/pipeline/loop.py src/magic_box/main.py tests/ai/test_worker.py tests/pipeline/test_loop.py
git commit -m "feat(pipeline): wire spark jobs, voice config and mic status into the game loop"
```

---

### Task 12: Replay: record and play sessions

**Files:**
- Modify: `src/magic_box/replay/record.py`, `replay/play.py`, `replay/fake_input.py`, `src/magic_box/pipeline/sources.py`, `pipeline/loop.py`, `src/magic_box/main.py`
- Create: `tests/replay/test_record_play.py`
- Modify tests: `tests/pipeline/test_sources.py` (replace `test_replay_sources_not_implemented_yet`), `tests/pipeline/test_loop.py`, `tests/test_main.py` (replace `test_replay_not_implemented_exits_2`)

**Interfaces:**
- Consumes: `core/serde.py` `to_json` / `from_json`; Task 11 `GameLoop`.
- Produces:
  - `SessionRecorder(out_dir: Path, cfg, mode: str)` with `write_state`, `write_voice`, `write_event`, `close()` (no `write_frame`).
  - `SessionPlayer(session_dir: Path, cfg)` with `poll(now) -> tuple[list[PlayerState], list[VoiceEvent], Frame | None]`; raises `FileNotFoundError` when `states.jsonl` is missing.
  - `draw_silhouettes(image: np.ndarray, states: Sequence[PlayerState], focal_px: float) -> None` in `replay/fake_input.py`.
  - `ReplaySources(session_dir: Path, cfg)`; `GameLoop(..., recorder=None)`.

- [ ] **Step 1: Write the failing tests**

`tests/replay/test_record_play.py`:

```python
def record(tmp_path):
    out = tmp_path / "s"
    rec = SessionRecorder(out, CFG, "fake")
    rec.write_state(make_state(0, t=100.0, cam_t=7.0, frame_idx=3))
    rec.write_state(make_state(1, t=100.5, cam_t=7.5, frame_idx=4))
    rec.write_voice(VoiceEvent(0, 100.2, "incantation", "x", "fireball", 90.0))
    rec.write_event(GameEvent(100.3, "cast", 0, {"spell_id": "fireball"}))
    rec.close()
    return out


def test_recorder_writes_files_and_meta(tmp_path):
    out = record(tmp_path)
    assert len((out / "states.jsonl").read_text().splitlines()) == 2
    assert len((out / "events.jsonl").read_text().splitlines()) == 1
    meta = json.loads((out / "meta.json").read_text())
    assert meta["version"] == 1 and meta["mode"] == "fake" and meta["config"]["game"]["round_s"] == 90
    assert {"started_t", "started_wall"} <= set(meta)


def test_replay_rebases_t_and_keeps_cam_t(tmp_path):
    player = SessionPlayer(record(tmp_path), CFG)
    states, voice, frame = player.poll(5.0)
    assert [(s.slot, s.t, s.cam_t) for s in states] == [(0, 5.0, 7.0)] and voice == []
    assert frame is not None and frame.frame_idx == 3
    states, voice, _ = player.poll(5.25)
    assert states == [] and [(v.spell_id, v.t) for v in voice] == [("fireball", pytest.approx(5.2))]
    states, _, _ = player.poll(6.0)
    assert [s.slot for s in states] == [1]
    assert player.poll(60.0) == ([], [], None)


def test_replay_frame_draws_silhouettes(tmp_path):
    _, _, frame = SessionPlayer(record(tmp_path), CFG).poll(5.0)
    x, y, w, h = make_state(0).bbox_px
    bg = tuple(reversed(CFG["render"]["background_rgb"]))
    assert tuple(frame.image[y + h // 2, x + w // 2, :3]) != bg


def test_missing_session_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        SessionPlayer(tmp_path / "nope", CFG)


def test_recorder_does_not_block_and_flushes_everything(tmp_path):
    rec = SessionRecorder(tmp_path / "s", CFG, "live")
    start = time.monotonic()
    for i in range(5000):
        rec.write_state(make_state(0, t=float(i)))
    assert time.monotonic() - start < 1.0
    rec.close()
    assert len((tmp_path / "s" / "states.jsonl").read_text().splitlines()) == 5000
```

In `tests/pipeline/test_sources.py`, replace `test_replay_sources_not_implemented_yet` with:

```python
def test_replay_sources_poll_a_recording(tmp_path):
    rec = SessionRecorder(tmp_path / "s", CFG, "fake")
    rec.write_state(make_state(0, t=10.0))
    rec.close()
    inputs = ReplaySources(tmp_path / "s", CFG).poll(frozenset(), now=1.0, dt=0.0)
    assert [s.slot for s in inputs.states] == [0] and inputs.frame is not None
```

Append to `tests/pipeline/test_loop.py`:

```python
def test_recorder_gets_states_voice_and_events():
    rec = SpyRecorder()   # records ("state", slot) / ("voice", kind) / ("event", kind)
    display = ScriptedDisplay([set(), {"1"}])
    GameLoop(CFG, FakeSources(CFG), display, Intent(CFG), SceneEngine(["lobby", "lobby"], events={1: ["match_start"]}),
             KeyboardVoiceSource(CFG), recorder=rec).run(max_ticks=2)
    assert rec.items.count(("state", 0)) == 2 and ("event", "match_start") in rec.items
```

(The keyboard voice event needs the view's spells; `SceneEngine` views carry a `fireball` spell, so `{"1"}` on tick 2 yields `("voice", "incantation")`. Assert it too.)

In `tests/test_main.py`, replace `test_replay_not_implemented_exits_2` with:

```python
def test_record_then_replay_round_trip(tmp_path):
    out = tmp_path / "session"
    assert run(["--fake", "--headless", "--max-ticks", "20", "--record", str(out)]) == 0
    assert (out / "states.jsonl").read_text().strip()
    assert run(["--replay", str(out), "--headless", "--max-ticks", "20"]) == 0


def test_replay_missing_session_exits_2(capsys):
    assert run(["--replay", "nowhere", "--headless", "--max-ticks", "1"]) == 2
    assert "no session" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/replay tests/pipeline tests/test_main.py -v`
Expected: FAIL (`NotImplementedError` from the stubs; signature errors).

- [ ] **Step 3: Extract `draw_silhouettes` in `replay/fake_input.py`**: move the bbox and head-box fill out of `FakePlayers._player` into the module function (head radius `_HEAD_RADIUS_M * focal_px / root z`, color by slot, tracked states only). `FakePlayers.step` draws after building both states. Existing fake-input tests stay green.

- [ ] **Step 4: Implement `replay/record.py` and `replay/play.py`** per spec §13. Recorder: one writer thread draining a `queue.SimpleQueue` of `(file_key, line)` and a sentinel; files opened once; `close()` puts the sentinel, joins, closes files. Player: read and `from_json` all lines, sort each list by `t`, rebase on the first `poll`, return due items with `dataclasses.replace(item, t=item.t + offset)`; build the frame (background from `render.background_rgb` like `FakePlayers`, then `draw_silhouettes` with `fake.focal_px`) from the newest due state per slot when any state was due, with `frame_idx` and `cam_t` from the newest due state.

- [ ] **Step 5: Wire it up**
  - `pipeline/sources.py`: `ReplaySources(session_dir, cfg)` passes `cfg` to `SessionPlayer`.
  - `pipeline/loop.py`: optional `recorder`; each tick write every drained state, every voice event (keyboard and status included), every `GameEvent` from `engine.step`.
  - `main.py`: `--replay DIR` → `ReplaySources(args.replay, cfg)`, and a `FileNotFoundError` from it prints `f"replay: no session at {args.replay}"` to stderr and returns 2; `--record DIR` → `SessionRecorder(args.record, cfg, mode)` with `mode` `"fake"`, `"replay"` or `"live"`, passed to `GameLoop` and closed in `finally`. Remove the recorder `TODO(Nikhil)`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/replay tests/pipeline tests/test_main.py -v`, then `uv run pytest`
Expected: PASS.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add src/magic_box/replay src/magic_box/pipeline/sources.py src/magic_box/pipeline/loop.py src/magic_box/main.py tests/replay tests/pipeline tests/test_main.py
git commit -m "feat(replay): record and replay sessions with silhouettes from recorded states"
```

---

### Task 13: Docs

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/game-design.md`, `docs/superpowers/specs/2026-10-24-magic-box-design.md` (§8 rows only), `src/magic_box/{intent,voice,ai,replay,pipeline,game,render}/CLAUDE.md`

**Interfaces:** none (docs only). `tests/test_blueprint.py` keeps passing: every package `CLAUDE.md` keeps its six headings.

- [ ] **Step 1: Update root `CLAUDE.md`** per spec §16:
  - Contracts: the new field notes (6) `Action.two_hand` (and the 0.1 s hold), (7) `Action(kind="speech", text)`, (8) `VoiceEvent(kind="status")` and `Engine.provide_mic_status`, (9) `SpellView.release`. Heads-up line: Adetola (engine, HUD, scenes) and Enoch (two-hand rule now lives in intent).
  - "Working without the Jetson": `--record` / `--replay` work (no frames; replay draws silhouettes); voice and Spark need `META_MODEL_API_KEY` and fall back without it; remove "Not implemented yet" and "The voice process is still a stub".
  - Fake-mode key table: a "Two-hand push" row (`v` / `m`); the full fake match walkthrough from spec §2 item 1.
  - Open decisions: add "Muse keyword format (words vs phrases) and `charge_window_s`, after measuring partial latency | Nikhil"; note the thin engine in `game/` is Adetola's to replace.
- [ ] **Step 2: Update `README.md`**: the fake-mode key table gains the two-hand push row; one line on how a match starts (both raise hands).
- [ ] **Step 3: Rewrite the package `CLAUDE.md` files** for `intent/`, `voice/`, `ai/`, `replay/`, `pipeline/`, `game/`, `render/`: files and what each does now, the rules from spec §7–§13, how to test, and what is left (`TODO(owner)` items: spell effects, class pick, boot scene, real HUD and scenes for Adetola; live verification and latency measurement for Nikhil).
- [ ] **Step 4: Update `docs/game-design.md`**: a short "Thin engine (2026-10-24)" note: Appendix A minus the effects of spells that do no damage, lobby start by both raising hands, and the new `game` numbers with their values.
- [ ] **Step 5: Parent spec §8**: append `Details: \`2026-10-24-nikhil-pipeline-design.md\`.` to the `intent/`, `voice/`, `ai/`, `replay/` rows. Do not rewrite the rows.
- [ ] **Step 6: Verify**

Run: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run python -m magic_box --fake --headless --max-ticks 600`
Expected: all clean; exit 0.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add CLAUDE.md README.md docs/game-design.md docs/superpowers/specs/2026-10-24-magic-box-design.md src/magic_box/intent/CLAUDE.md src/magic_box/voice/CLAUDE.md src/magic_box/ai/CLAUDE.md src/magic_box/replay/CLAUDE.md src/magic_box/pipeline/CLAUDE.md src/magic_box/game/CLAUDE.md src/magic_box/render/CLAUDE.md
git commit -m "doc(repo): document intent, voice, spark, replay and the thin engine"
```

---

## After the plan: on the Jetson (Daniel, with Nikhil if available)

1. `cp .env.example .env` and set `META_MODEL_API_KEY`; set `voice.mics` in `config.local.yaml` (device names from `check_env.py`).
2. `uv run --env-file .env python -m magic_box`: both say their names in the lobby (HUD shows MIC OK), both raise hands, check the loading card shows Spark-written incantations (not the config fallback), speak one and push.
3. Measure the time from the end of an incantation to the charge (partial latency) and set `game.charge_window_s`; tune `intent.two_hand_window_s` with real arms.
4. `--record recordings/<name>` a match, copy it to a laptop, and `--replay` it there.
