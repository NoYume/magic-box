# magic-box Repo Blueprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the empty repo into the team blueprint from spec §13. That means tooling, Claude files, owned folders, tested foundation code, and stubs everywhere else, so `uv run python -m magic_box --fake` shows layout C on any laptop.

**Architecture:**
- Leaf packages:
  - `core/` holds the contracts, JSON serde, config and geometry, and imports nothing else from the project.
  - `pipeline/` handles transport: drop-oldest queues, the shared-memory frame bus, sources, the game loop, and the process supervisor.
- The game process loop polls a `Sources` object (live, replay or fake), runs `intent` and then `game.engine`, and draws through `render.window`. `render/` is the only package that imports `pygame`.
- Owned modules that aren't foundation are typed stubs carrying `TODO(<Owner>)`.

**Tech Stack:** Python 3.10 (uv), pygame-ce, numpy<2, PyYAML, rapidfuzz, websockets, sounddevice, openai, pytest, ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-24-magic-box-design.md`. Read §6, §7, §8 and §13 before starting.

## Global Constraints

**Python and dependencies**
- Python `==3.10.*` (`.python-version` = `3.10`). Use uv only (`uv sync`, `uv run`, `uv add`). Never use pip, conda or poetry.
- Do not add dependencies beyond the spec §13.2 list. `numpy` is pinned `>=1.24,<2`.

**Git**
- **Never run git commands that change the repo** (`add`, `commit`, `push`, `checkout`, …). At the end of each task, print the commit command for Daniel to run. Use the format `<type>(<scope>): <lowercase summary>`, one line, no body, no trailer.

**Import boundaries** (`tests/test_boundaries.py` enforces these)
- `pyzed` is imported only under `src/magic_box/perception/`.
- `pygame` is imported only under `src/magic_box/render/`.
- `game/` never imports `pygame`, `pyzed` or `cv2`.
- `core/` imports nothing from `magic_box` outside `core/`.
- `pyzed`, `cv2` and `sounddevice` are never imported at module top level; import them inside functions.
- Absolute imports only. Ruff `TID252` is set to `ban-relative-imports = "all"`.

**Conventions**
- Every module's docstring has a line `Owner: <Name>`. Owners: Daniel, Enoch, Nikhil, Adetola.
- A stub raises `NotImplementedError("TODO(<Owner>): <what>")`, unless this plan says it returns a placeholder.
- Units are meters and seconds. Camera frame is ZED `COORDINATE_SYSTEM.IMAGE`: +X is image-right, +Y is down, +Z is away from the camera.
- Slot 0 = P1, who stands on the left from the players' view. P1 appears on the image's *right*, so their root x is greater than 0.
- Every tunable lives in `config.yaml`. Code reads values from `cfg`; it never hard-codes thresholds, keys, sizes or colors.
- Use `multiprocessing` only through `magic_box.pipeline.streams.spawn_context()`.

**Done criteria for each task**
- `uv run ruff check` and `uv run ruff format --check` are clean.
- `uv run pytest` is green.
- Tests run with `SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy` and `PYGAME_HIDE_SUPPORT_PROMPT=1`, all set in `tests/conftest.py`.

## Review Focus

1. **A child process that attaches to the frame bus exits.** On Python < 3.13, the resource tracker unlinks the segment and the camera feed dies for everyone. `FrameBus.attach` must unregister from the tracker. This is tested in Task 5.
2. **The perception writer is mid-write when the game reads.** The reader must never get half of one frame and half of the next (seqlock). This is tested in Task 5.
3. **Both players pick the same class, so their fallback incantations would collide.** If the fallback for slot 0 matched slot 1, one mic hearing the other player would cast for them. Config validation rejects identical per-slot fallbacks, case-insensitively. This is tested in Task 3.
4. **The camera stalls or is unplugged.** The last `PlayerState` stays frozen and would look tracked. States older than `pipeline.stale_state_s` must become `tracking_ok=False`. This is tested in Task 10.
5. **A held key repeats casts or pushes every frame.** Keyboard spells and fake pushes must be edge-triggered. This is tested in Tasks 6 and 8.

---

## File Map

| Task | Creates |
|---|---|
| 1 | `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, `.env.example`, `.github/workflows/ci.yml`, `src/magic_box/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_smoke.py`, `recordings/.gitkeep`, `assets/{sprites,fonts,sounds}/.gitkeep` |
| 2 | `src/magic_box/core/{__init__,contracts,serde}.py`, `tests/factories.py`, `tests/core/{__init__,test_contracts}.py` |
| 3 | `config.yaml`, `src/magic_box/core/config.py`, `tests/core/test_config.py` |
| 4 | `src/magic_box/pipeline/{__init__,streams}.py`, `tests/helpers.py`, `tests/pipeline/{__init__,test_streams}.py` |
| 5 | `src/magic_box/pipeline/frame_bus.py`, `tests/pipeline/test_frame_bus.py` |
| 6 | `src/magic_box/core/geometry.py`, `src/magic_box/replay/{__init__,fake_input}.py`, `tests/replay/{__init__,test_fake_input}.py`, `tests/core/test_geometry.py` |
| 7 | stubs in `perception/`, `intent/`, `voice/`, `ai/`, `game/`, `replay/{record,play}.py`, `render/{projectiles,debug_overlay}.py`, `render/scenes/`; `tests/test_boundaries.py`, `tests/test_imports.py`, `tests/game/{__init__,test_engine_stub}.py` |
| 8 | `src/magic_box/pipeline/sources.py`, `tests/pipeline/test_sources.py` |
| 9 | `src/magic_box/render/{__init__,layout,camera_view,hud,window}.py`, `tests/render/{__init__,test_layout,test_camera_view,test_window}.py` |
| 10 | `src/magic_box/pipeline/loop.py`, `src/magic_box/main.py`, `src/magic_box/__main__.py`, `tests/pipeline/test_loop.py`, `tests/test_main.py` |
| 11 | `src/magic_box/pipeline/processes.py`, `tests/pipeline/test_processes.py`; modify `main.py` (live mode) |
| 12 | `scripts/{check_env,bench_tracking,record_session}.py`, `scripts/sync_to_jetson.sh`, `tests/scripts/{__init__,test_scripts}.py` |
| 13 | `CLAUDE.md`, nine `src/magic_box/<pkg>/CLAUDE.md`, `.claude/settings.json`, `README.md`, `docs/game-design.md`, `docs/hardware.md`, `tests/test_blueprint.py` |

---

### Task 1: Tooling, package skeleton, CI

**Files:** see the File Map.

**Interfaces:**
- Produces: the importable package `magic_box` with `__version__ = "0.1.0"`, and the test env vars in `tests/conftest.py`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "magic-box"
version = "0.1.0"
description = "Camera-only 1v1 magic duel console: ZED 2 + Jetson Orin Nano"
readme = "README.md"
requires-python = "==3.10.*"
dependencies = [
  "numpy>=1.24,<2",  # must match the numpy pyzed was built against; scripts/check_env.py verifies
  "pygame-ce>=2.5",
  "pyyaml>=6",
  "rapidfuzz>=3",
  "websockets>=12",
  "sounddevice>=0.4",
  "openai>=1.40",
]

[project.optional-dependencies]
laptop = ["opencv-python>=4.8"]  # never install on the Jetson: it shadows JetPack's cv2

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/magic_box"]

[tool.ruff]
line-length = 100
target-version = "py310"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "TID"]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the remaining Task 1 files**
- `.python-version`: `3.10`.
- `.env.example`: `META_MODEL_API_KEY=`.
- `.gitignore` covers `.venv/`, `.env`, `config.local.yaml`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.ruff_cache/`, `recordings/*` with `!recordings/.gitkeep`, `*.svo`, `*.svo2`, `.superpowers/`, `.DS_Store`, `dist/`.
- `src/magic_box/__init__.py`: docstring (`Owner: Daniel`) plus `__version__ = "0.1.0"`.
- `tests/conftest.py`: `os.environ.setdefault(...)` for the three SDL and pygame variables listed under Global Constraints.
- `.gitkeep` files as listed in the File Map.

- [ ] **Step 3: Write the smoke test** `tests/test_smoke.py`

```python
import magic_box


def test_package_imports():
    assert magic_box.__version__ == "0.1.0"
```

- [ ] **Step 4: Sync and run**

Run: `uv sync --extra laptop && uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: `uv.lock` created, `1 passed`, ruff reports no issues.

- [ ] **Step 5: Write `.github/workflows/ci.yml`**
- Trigger on `push` and `pull_request`, job runs on `ubuntu-latest`.
- Set `env` to `SDL_VIDEODRIVER: dummy` and `SDL_AUDIODRIVER: dummy`.
- Steps:
  1. `actions/checkout@v4`
  2. `astral-sh/setup-uv@v6`
  3. `uv sync --extra laptop --locked`
  4. `uv run ruff check`
  5. `uv run ruff format --check`
  6. `uv run pytest`

Verify: `uv run python -c "import yaml; print(yaml.safe_load(open('.github/workflows/ci.yml'))['jobs'])"` prints the job dict.

- [ ] **Step 6: Print commit command for Daniel**

```bash
git add pyproject.toml uv.lock .python-version .gitignore .env.example .github src/magic_box/__init__.py tests recordings/.gitkeep assets
git commit -m "chore(repo): add uv project, ruff, pytest and ci skeleton"
```

---

### Task 2: Data contracts and JSON-lines serde

**Files:** `src/magic_box/core/{__init__,contracts,serde}.py`, `tests/factories.py`, `tests/core/{__init__,test_contracts}.py`

**Interfaces:**
- Produces, in `magic_box.core.contracts`:
  - **Dataclasses:** the spec §7 dataclasses, verbatim fields and order: `Push`, `PlayerState`, `VoiceEvent`, `Action`, `GameEvent`, `SpellView`, `PlayerView`, `ProjectileView`, `GameView`.
  - **Two additional frozen dataclasses:**
    - `VoiceConfig(mode: str, incantations: dict[int, dict[str, str]])`, where `mode ∈ VOICE_MODES` and `incantations` maps slot → spell_id → text.
    - `Frame(frame_idx: int, cam_t: float, image: np.ndarray)`, with `eq=False`. Image is HxWx4 uint8 BGRA, unmirrored. It is not serializable.
  - **Type aliases:** `Vec3`, `Px`.
  - **Constants:**

    | Name | Value |
    |---|---|
    | `SLOTS` | `(0, 1)` |
    | `ZONES` | `("danger", "neutral", "far")` |
    | `SCENES` | `("boot", "lobby", "loading", "fight", "victory")` |
    | `VOICE_KINDS` | `("incantation", "transcript")` |
    | `VOICE_MODES` | `("transcript", "incantation")` |
    | `ACTION_KINDS` | `("charge", "push", "pose", "dodge")` |
    | `DODGE_KINDS` | `("step", "duck")` |
    | `GAME_EVENT_KINDS` | the nine kinds in spec §7 |
    | `KEYPOINT_NAMES` | `("head", "neck", "pelvis", "l_shoulder", "r_shoulder", "l_wrist", "r_wrist", "l_ankle", "r_ankle")` |
    | `SKELETON_EDGES` | `(("head","neck"), ("neck","pelvis"), ("neck","l_shoulder"), ("neck","r_shoulder"), ("l_shoulder","l_wrist"), ("r_shoulder","r_wrist"), ("pelvis","l_ankle"), ("pelvis","r_ankle"))` |
- Produces, in `magic_box.core.serde`:
  - `to_json(obj) -> str`
  - `from_json(line: str) -> Any`
  - `SERIALIZABLE: dict[str, type]`, which holds every dataclass above except `Frame`.
- Produces, in `tests/factories.py`:
  - `make_state(slot: int = 0, **overrides) -> PlayerState`. Defaults: `tracking_ok=True`, `root=(0.6 if slot == 0 else -0.6, 0.0, 2.0)`, `zone="neutral"`, `push=None`, `pose_flags=frozenset()`, `keypoints_px` filled for every `KEYPOINT_NAMES` entry, `finger_gesture={"L": None, "R": None}`.
  - `make_view(**overrides) -> GameView`. Defaults: scene `"fight"`, two `PlayerView`s with slots 0 and 1, each with one `SpellView`; `projectiles=()`; `timer_s=90.0`.

- [ ] **Step 1: Write the failing tests** `tests/core/test_contracts.py`

```python
import json

import pytest

from magic_box.core.contracts import Action, GameEvent, ProjectileView, Push, VoiceConfig, VoiceEvent
from magic_box.core.serde import from_json, to_json
from tests.factories import make_state, make_view

ROUND_TRIP = [
    make_state(),
    make_state(slot=1, push=Push("L", 2.5, (100.0, 200.0)), pose_flags=frozenset({"hands_up", "hands_together"})),
    VoiceEvent(slot=0, t=1.0, kind="incantation", text="embers burn", spell_id="fireball", match_score=91.5),
    VoiceEvent(slot=1, t=2.0, kind="transcript", text="priya", spell_id=None, match_score=0.0),
    Action(kind="push", slot=0, t=3.0, push=Push("R", 3.0, (1.0, 2.0)), dist=1.9),
    Action(kind="charge", slot=1, t=3.5, spell_id="bolt", match_score=88.0),
    GameEvent(t=4.0, kind="hit", slot=1, data={"spell_id": "fireball", "damage": 18.0}),
    VoiceConfig(mode="incantation", incantations={0: {"fireball": "embers burn"}, 1: {"bolt": "storm strike"}}),
    make_view(),
    make_view(projectiles=(ProjectileView("fireball", 1, (640.0, 300.0), 0.5, False),)),
]


@pytest.mark.parametrize("obj", ROUND_TRIP, ids=lambda o: type(o).__name__)
def test_round_trip(obj):
    line = to_json(obj)
    assert "\n" not in line
    assert from_json(line) == obj


def test_envelope_and_sorted_frozenset():
    data = json.loads(to_json(make_state(pose_flags=frozenset({"b", "a"}))))
    assert data["type"] == "PlayerState"
    assert data["data"]["pose_flags"] == ["a", "b"]


def test_unknown_type_rejected():
    with pytest.raises(ValueError):
        from_json('{"type": "Nope", "data": {}}')


@pytest.mark.parametrize("kwargs", [{"slot": 2}, {"zone": "close"}])
def test_player_state_validates(kwargs):
    with pytest.raises(ValueError):
        make_state(**kwargs)


def test_action_kind_validated():
    with pytest.raises(ValueError):
        Action(kind="punch", slot=0, t=0.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/core/test_contracts.py`
Expected: FAIL, `ModuleNotFoundError: magic_box.core`.

- [ ] **Step 3: Implement `contracts.py`, `serde.py` and `factories.py`**
- **Validation:** every dataclass's `__post_init__` raises `ValueError` when:
  - a slot isn't in `SLOTS` (`GameEvent.slot` may be `None`);
  - an enumerated string isn't in its constant tuple;
  - `GameView.players` isn't ordered by slot (`players[i].slot == i`). Render indexes players by slot.
- **Envelope:** `to_json` writes `{"type": <class name>, "data": {...}}` using `json.dumps(..., separators=(",", ":"))`.
- **Encoding:** frozensets become sorted lists; tuples become lists.
- **Decoding:** `from_json` rebuilds generically from `typing.get_type_hints`. It must handle nested dataclasses, fixed and variadic tuples, `dict[int, ...]` keys (stringified by JSON), `frozenset[str]` and `X | None`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/core/test_contracts.py`
Expected: all pass.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box/core tests/factories.py tests/core
git commit -m "feat(core): add shared data contracts with json-lines serde"
```

---

### Task 3: `config.yaml` and the validating loader

**Files:** `config.yaml`, `src/magic_box/core/config.py`, `tests/core/test_config.py`

**Interfaces:**
- Produces, in `magic_box.core.config`:
  - `Config = dict[str, Any]`
  - `class ConfigError(ValueError)`
  - `REQUIRED_SECTIONS: tuple[str, ...]`, which is `("display", "camera", "perception", "pipeline", "intent", "voice", "ai", "game", "render", "keys", "fake")`
  - `deep_merge(base: dict, override: dict) -> dict`
  - `validate(cfg: Config) -> list[str]`, which returns every problem
  - `load_config(path: str | Path = "config.yaml") -> Config`. It deep-merges `config.local.yaml` from the same directory if that file exists, then raises `ConfigError` with all problems joined by `"; "`.
- Key paths that later tasks rely on are the ones in the YAML below.

- [ ] **Step 1: Write `config.yaml`.** All values come from the spec. Keep the comments.

```yaml
# ALL tunables live here. "(guess)" = untuned until tested on recordings.
# Per-machine overrides (mic devices, fullscreen) go in config.local.yaml (gitignored), deep-merged on top.

display:            # owner: Adetola + Nikhil
  width: 1920
  height: 1080
  fps: 60
  fullscreen: false

camera:             # owner: Enoch
  resolution: HD720           # HD720 | HD1080
  image_width: 1280
  image_height: 720
  fps: 30
  depth_mode: PERFORMANCE     # use the fastest mode the installed ZED SDK offers
  body_format: BODY_18        # BODY_18 | BODY_34 | BODY_38, decide after scripts/bench_tracking.py
  body_model: HUMAN_BODY_FAST
  max_range_m: 3.5            # (guess) ignore bodies farther than this

perception:         # owner: Enoch
  push_speed_mps: 1.5         # (guess) wrist speed toward camera that counts as a push
  push_cooldown_s: 0.4        # (guess)
  wrist_vz_smoothing: 0.5     # (guess) EMA alpha
  zones:                      # root Z thresholds, meters (guess)
    danger_max_m: 1.6         # z < this -> danger
    far_min_m: 2.4            # z >= this -> far

pipeline:           # owner: Nikhil
  state_queue_size: 256
  voice_queue_size: 64
  control_queue_size: 8
  stale_state_s: 0.2
  restart_backoff_s: 1.0
  max_restarts: 5

intent:             # owner: Nikhil
  dodge_step_m: 0.3           # (guess)
  dodge_duck_m: 0.25          # (guess)
  dodge_lookback_s: 0.4       # (guess)

voice:              # owner: Nikhil (devices: Daniel)
  enabled: true
  url: wss://api.meta.ai/v1/asr/realtime
  model: muse-voice-transcribe-1.0
  sample_rate: 16000
  match_threshold: 80
  perfect_threshold: 95
  mics:                       # device null = system default; set real devices in config.local.yaml
    - {slot: 0, device: null, channel: 0}
    - {slot: 1, device: null, channel: 1}

ai:                 # owner: Nikhil
  enabled: true
  base_url: https://api.meta.ai/v1   # VERIFY against dev.meta.ai docs before first use
  model: muse-spark-1.1
  timeout_s: 8
  api_key_env: META_MODEL_API_KEY

game:               # owner: Adetola. DRAFT numbers, see docs/game-design.md
  round_s: 90
  hp_max: 100
  mana_max: 100
  mana_regen_per_s: 8
  charge_window_s: 3.0
  dodge_window_s: 0.6
  basic_attack_cooldown_s: 0.8
  default_classes: {0: fire_mage, 1: lightning_mage}
  classes:
    fire_mage:
      name: Fire Mage
      spells:
        - {id: fireball, name: Fireball, cost: 25, damage: 18, travel_s: 1.6, release: push,
           fallback: {0: "embers of the forty acres burn", 1: "ignite the longhorn flame"}}
        - {id: flame_wall, name: Flame Wall, cost: 30, damage: 0, travel_s: 0, release: two_hand_push,
           fallback: {0: "rise crimson rampart", 1: "wall of burning cedar"}}       # blocks next hit 4 s
        - {id: inferno, name: Inferno, cost: 60, damage: 35, travel_s: 2.2, release: push,
           fallback: {0: "let the whole sky catch fire", 1: "summon the sixth street inferno"}}
    lightning_mage:
      name: Lightning Mage
      spells:
        - {id: bolt, name: Bolt, cost: 20, damage: 12, travel_s: 0.9, release: push,
           fallback: {0: "storm of speedway strike", 1: "lightning answer my call"}}
        - {id: chain, name: Chain, cost: 35, damage: 7, travel_s: 1.2, release: push,
           fallback: {0: "thunder binds the tower", 1: "chain the storm across the river"}}  # 3 hits
        - {id: static_field, name: Static Field, cost: 30, damage: 0, travel_s: 1.4, release: two_hand_push,
           fallback: {0: "static fills the air", 1: "hum of the restless grid"}}    # slows mana regen 5 s
    holy_knight:
      name: Holy Knight
      spells:
        - {id: holy_light, name: Holy Light, cost: 30, damage: 0, travel_s: 0, release: arm_overhead,
           fallback: {0: "light of the tower guide my blade", 1: "dawn breaks upon my sword"}}  # x1.5 dmg 6 s
        - {id: heal, name: Heal, cost: 40, damage: 0, travel_s: 0, release: hands_together,
           fallback: {0: "mend me gentle light", 1: "breath of the hill country heal"}}  # +25 HP
        - {id: judgment, name: Judgment, cost: 45, damage: 25, travel_s: 1.5, release: push,
           fallback: {0: "judgment falls from above", 1: "steel and sunlight strike true"}}

render:             # owner: Adetola (hud, scenes) + Nikhil (camera_view, projectiles)
  crop_aspect: [8, 9]
  crop_padding: 0.15
  crop_smoothing: 0.25        # EMA alpha per drawn frame
  selfview_width_frac: 0.26
  margin_px: 16
  hud_height_frac: 0.26
  divider_px: 4
  divider_rgb: [201, 162, 39]
  background_rgb: [11, 8, 20]

keys:               # owner: Nikhil. pygame key names
  spells: {0: ["1", "2", "3"], 1: ["8", "9", "0"]}   # keyboard fallback, always active
  debug_overlay: f1
  quit: escape
  fake:
    0: {left: a, right: d, closer: w, farther: s, push: f, duck: c, hands_up: r, hands_together: t}
    1: {left: j, right: l, closer: i, farther: k, push: h, duck: n, hands_up: y, hands_together: u}

fake:               # owner: Nikhil. --fake mode players
  start_x_m: 0.6              # slot 0 at +x (image right), slot 1 at -x
  start_z_m: 2.0
  min_z_m: 0.8
  max_z_m: 3.5
  move_speed_mps: 1.0
  push_speed_mps: 3.0
  duck_m: 0.4
  focal_px: 700
```

- [ ] **Step 2: Write the failing tests** `tests/core/test_config.py`

```python
from pathlib import Path

import pytest
import yaml

from magic_box.core.config import REQUIRED_SECTIONS, ConfigError, load_config

ROOT = Path(__file__).resolve().parents[2]


def _base():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def _write(tmp_path, cfg, name="config.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(cfg))
    return path


def test_repo_config_is_valid():
    cfg = load_config(ROOT / "config.yaml")
    assert set(REQUIRED_SECTIONS) <= set(cfg)
    assert (cfg["display"]["width"], cfg["display"]["height"]) == (1920, 1080)


def test_missing_sections_all_reported(tmp_path):
    cfg = _base()
    del cfg["voice"], cfg["ai"]
    with pytest.raises(ConfigError) as err:
        load_config(_write(tmp_path, cfg))
    assert "voice" in str(err.value) and "ai" in str(err.value)


def test_zone_thresholds_must_be_ordered(tmp_path):
    cfg = _base()
    cfg["perception"]["zones"] = {"danger_max_m": 2.5, "far_min_m": 2.0}
    with pytest.raises(ConfigError, match="zones"):
        load_config(_write(tmp_path, cfg))


def test_mics_must_cover_both_slots(tmp_path):
    cfg = _base()
    cfg["voice"]["mics"] = [{"slot": 0, "device": None, "channel": 0}]
    with pytest.raises(ConfigError, match="mics"):
        load_config(_write(tmp_path, cfg))


def test_fallback_incantations_differ_per_slot(tmp_path):
    cfg = _base()
    cfg["game"]["classes"]["fire_mage"]["spells"][0]["fallback"] = {0: "same words", 1: "Same Words"}
    with pytest.raises(ConfigError, match="fallback"):
        load_config(_write(tmp_path, cfg))


def test_default_classes_must_exist(tmp_path):
    cfg = _base()
    cfg["game"]["default_classes"][1] = "necromancer"
    with pytest.raises(ConfigError, match="necromancer"):
        load_config(_write(tmp_path, cfg))


def test_local_override_deep_merges(tmp_path):
    _write(tmp_path, _base())
    _write(tmp_path, {"display": {"fullscreen": True}}, name="config.local.yaml")
    cfg = load_config(tmp_path / "config.yaml")
    assert cfg["display"]["fullscreen"] is True
    assert cfg["display"]["width"] == 1920
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/core/test_config.py`
Expected: FAIL, `ModuleNotFoundError: magic_box.core.config`.

- [ ] **Step 4: Implement `config.py`**

`validate` checks:
- the required sections;
- `zones.danger_max_m < zones.far_min_m`;
- the mic slots are exactly `{0, 1}`;
- `keys.spells` has slots 0 and 1;
- each spell's `fallback[0].lower() != fallback[1].lower()`;
- every `default_classes` value is a key of `game.classes`.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/core`
Expected: all pass.

- [ ] **Step 6: Print commit command for Daniel**

```bash
git add config.yaml src/magic_box/core/config.py tests/core/test_config.py
git commit -m "feat(core): add config.yaml with validating loader and local overrides"
```

---

### Task 4: Drop-oldest stream queue

**Files:** `src/magic_box/pipeline/{__init__,streams}.py`, `tests/helpers.py`, `tests/pipeline/{__init__,test_streams}.py`

**Interfaces:**
- Produces, in `magic_box.pipeline.streams`:
  - `spawn_context() -> multiprocessing.context.BaseContext`, which returns the `"spawn"` context.
  - `class DropOldestQueue(maxsize: int, ctx: BaseContext | None = None)`, with these members:
    - `put(item) -> None`: never blocks.
    - `drain(max_items: int | None = None) -> list`: never blocks; returns items in FIFO order.
    - `dropped -> int` (property).
  - It must be picklable as a `Process` argument.
- Produces, in `tests/helpers.py` (top-level so spawned children can import it):
  - `drain_until(q, n, timeout=2.0) -> list`: polls `drain()` until `n` items have arrived or the timeout passes.
  - `produce_ints(q, n) -> None`

- [ ] **Step 1: Write the failing tests** `tests/pipeline/test_streams.py`

```python
from magic_box.pipeline.streams import DropOldestQueue, spawn_context
from tests.helpers import drain_until, produce_ints


def test_drain_empty_returns_empty_list():
    assert DropOldestQueue(4).drain() == []


def test_overflow_drops_oldest():
    q = DropOldestQueue(3)
    for i in range(5):
        q.put(i)
    assert drain_until(q, 3) == [2, 3, 4]
    assert q.dropped == 2


def test_cross_process_order_preserved():
    ctx = spawn_context()
    q = DropOldestQueue(256, ctx)
    proc = ctx.Process(target=produce_ints, args=(q, 100))
    proc.start()
    proc.join(10)
    assert drain_until(q, 100) == list(range(100))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/pipeline/test_streams.py`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `streams.py`**
- Back it with `ctx.Queue(maxsize)` and a `ctx.Value("i", 0)` drop counter.
- `put` calls `put_nowait`. On `queue.Full`, it discards one item with `get(timeout=0.05)` (because the feeder thread may not have flushed yet), increments `dropped`, and retries once.
- `drain` loops `get_nowait` until `queue.Empty`.
- Never call `qsize()`; it is unimplemented on macOS.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/pipeline/test_streams.py`
Expected: 3 passed.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box/pipeline tests/helpers.py tests/pipeline
git commit -m "feat(pipeline): add drop-oldest multiprocessing stream queue"
```

---

### Task 5: Shared-memory frame bus

**Files:** `src/magic_box/pipeline/frame_bus.py`, `tests/pipeline/test_frame_bus.py`; modify `tests/helpers.py`

**Interfaces:**
- Consumes: `Frame` (Task 2) and `spawn_context` (Task 4).
- Produces, in `magic_box.pipeline.frame_bus`, `class FrameBus` with these members:
  - `FrameBus.create(width: int, height: int, channels: int = 4) -> FrameBus`
  - `FrameBus.attach(name: str, width: int, height: int, channels: int = 4) -> FrameBus`
  - `.name: str`
  - `.write(frame: Frame) -> None`: raises `ValueError` on a shape or dtype mismatch.
  - `.read_latest() -> Frame | None`: returns `None` before the first write and always returns a copy.
  - `.close() -> None`
  - `.unlink() -> None`
- Adds to `tests/helpers.py`: `write_frames(name: str, w: int, h: int, n: int) -> None`. It attaches, writes frames `0..n-1` with every pixel equal to `i % 256` and `cam_t = i / 30`, then closes without unlinking.

- [ ] **Step 1: Write the failing tests** `tests/pipeline/test_frame_bus.py`

```python
import numpy as np
import pytest

from magic_box.core.contracts import Frame
from magic_box.pipeline.frame_bus import FrameBus
from magic_box.pipeline.streams import spawn_context
from tests.helpers import write_frames

W, H = 64, 48


def _frame(i):
    return Frame(frame_idx=i, cam_t=i / 30, image=np.full((H, W, 4), i % 256, np.uint8))


@pytest.fixture
def bus():
    b = FrameBus.create(W, H)
    yield b
    b.close()
    b.unlink()


def test_read_before_write_is_none(bus):
    assert bus.read_latest() is None


def test_write_then_read(bus):
    bus.write(_frame(7))
    f = bus.read_latest()
    assert f.frame_idx == 7 and f.cam_t == pytest.approx(7 / 30) and (f.image == 7).all()


def test_read_returns_copy(bus):
    bus.write(_frame(1))
    f = bus.read_latest()
    bus.write(_frame(2))
    assert (f.image == 1).all()


def test_wrong_shape_rejected(bus):
    with pytest.raises(ValueError):
        bus.write(Frame(0, 0.0, np.zeros((H, W, 3), np.uint8)))


def test_child_writer_no_torn_reads_and_segment_survives(bus):
    ctx = spawn_context()
    proc = ctx.Process(target=write_frames, args=(bus.name, W, H, 300))
    proc.start()
    seen = []
    while proc.is_alive():
        f = bus.read_latest()
        if f is not None:
            assert (f.image == f.frame_idx % 256).all()  # never half of two frames
            seen.append(f.frame_idx)
    proc.join(10)
    assert seen == sorted(seen)
    bus.write(_frame(999))  # child exit must not have unlinked the segment
    assert bus.read_latest().frame_idx == 999
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/pipeline/test_frame_bus.py`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `frame_bus.py`**

Layout and algorithm (the signature doesn't determine these):
- One `SharedMemory` block holds an int64 `latest` slot index (-1 = never written), then two slots. Each slot is a header (`seq: uint64`, `frame_idx: int64`, `cam_t: float64`) followed by H×W×C bytes.
- **Writer:** pick the slot that isn't `latest`; set `seq += 1` (odd = writing); copy the header and image; set `seq += 1` (even); set `latest` to that slot.
- **Reader:** read `latest`, then read `seq`. If `seq` is odd, retry. Copy the header and image, then re-read `seq`. If it changed, retry (at most 10 times, then return the last good copy or `None`).
- **`attach` on Python < 3.13:** call `multiprocessing.resource_tracker.unregister(shm._name, "shared_memory")` so a child exiting can't unlink the segment.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/pipeline/test_frame_bus.py`
Expected: 5 passed.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box/pipeline/frame_bus.py tests/pipeline/test_frame_bus.py tests/helpers.py
git commit -m "feat(pipeline): add seqlocked shared-memory frame bus"
```

---

### Task 6: Geometry helpers and keyboard-driven fake players

**Files:** `src/magic_box/core/geometry.py`, `src/magic_box/replay/{__init__,fake_input}.py`, `tests/core/test_geometry.py`, `tests/replay/{__init__,test_fake_input}.py`

**Interfaces:**
- Consumes: contracts (Task 2) and `load_config` (Task 3).
- Produces, in `magic_box.core.geometry`:
  - `zone_for_distance(z: float, zones: Mapping[str, float]) -> str`: `z < danger_max_m` gives `"danger"`, `z >= far_min_m` gives `"far"`, anything else gives `"neutral"`.
  - `project_point(p: Vec3, fx: float, fy: float, cx: float, cy: float) -> Px`
- Produces, in `magic_box.replay.fake_input`:
  - `class FakePlayers(cfg: Config)`
  - `.step(keys: frozenset[str], now: float, dt: float) -> tuple[list[PlayerState], Frame]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_geometry.py
import pytest

from magic_box.core.geometry import project_point, zone_for_distance

ZONES = {"danger_max_m": 1.6, "far_min_m": 2.4}


@pytest.mark.parametrize("z,zone", [(1.0, "danger"), (1.6, "neutral"), (2.0, "neutral"), (2.4, "far")])
def test_zone_for_distance(z, zone):
    assert zone_for_distance(z, ZONES) == zone


def test_project_point():
    assert project_point((0.0, 0.0, 2.0), 700, 700, 640, 360) == (640.0, 360.0)
    assert project_point((1.0, 0.0, 2.0), 700, 700, 640, 360) == (990.0, 360.0)
```

```python
# tests/replay/test_fake_input.py
from pathlib import Path

import numpy as np
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import KEYPOINT_NAMES
from magic_box.replay.fake_input import FakePlayers

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
K0 = CFG["keys"]["fake"][0]
FAKE = CFG["fake"]


def _p1(states):
    return next(s for s in states if s.slot == 0)


def test_initial_layout_p1_on_image_right():
    states, frame = FakePlayers(CFG).step(frozenset(), now=0.0, dt=0.0)
    p1, p2 = _p1(states), next(s for s in states if s.slot == 1)
    assert p1.root[0] > 0 > p2.root[0]
    assert p1.bbox_px[0] > CFG["camera"]["image_width"] / 2 > p2.bbox_px[0] + p2.bbox_px[2]
    assert frame.image.shape == (720, 1280, 4) and frame.image.dtype == np.uint8
    assert set(p1.keypoints_px) == set(KEYPOINT_NAMES) and p1.tracking_ok


def test_closer_moves_toward_camera_and_grows():
    fp = FakePlayers(CFG)
    before = _p1(fp.step(frozenset(), 0.0, 0.0)[0])
    for i in range(10):
        states, _ = fp.step(frozenset({K0["closer"]}), now=0.1 * (i + 1), dt=0.1)
    assert _p1(states).root[2] == pytest.approx(FAKE["start_z_m"] - FAKE["move_speed_mps"])
    assert _p1(states).bbox_px[3] > before.bbox_px[3]


def test_distance_clamped():
    fp = FakePlayers(CFG)
    for i in range(100):
        states, _ = fp.step(frozenset({K0["farther"]}), now=0.1 * i, dt=0.1)
    assert _p1(states).root[2] == pytest.approx(FAKE["max_z_m"])


def test_push_is_edge_triggered():
    fp = FakePlayers(CFG)
    first = _p1(fp.step(frozenset({K0["push"]}), 0.0, 0.016)[0])
    held = _p1(fp.step(frozenset({K0["push"]}), 0.016, 0.016)[0])
    assert first.push is not None and first.push.speed == FAKE["push_speed_mps"]
    assert first.wrist_vz["R"] < 0
    assert held.push is None


def test_duck_and_pose_flags():
    fp = FakePlayers(CFG)
    start = _p1(fp.step(frozenset(), 0.0, 0.0)[0])
    s = _p1(fp.step(frozenset({K0["duck"], K0["hands_up"]}), 0.1, 0.1)[0])
    assert s.head[1] == pytest.approx(start.head[1] + FAKE["duck_m"])
    assert "hands_up" in s.pose_flags


def test_frame_idx_and_time_advance():
    fp = FakePlayers(CFG)
    s0, f0 = fp.step(frozenset(), 0.0, 0.0)
    s1, f1 = fp.step(frozenset(), 0.5, 0.5)
    assert (f0.frame_idx, f1.frame_idx) == (0, 1)
    assert _p1(s1).frame_idx == 1 and _p1(s1).t == 0.5
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/core/test_geometry.py tests/replay`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `geometry.py` and `fake_input.py`**

`fake_input.py` details (the tests don't pin these):
- **Body model:** pelvis at y = 0, head at y = −0.75 m, ankles at y = +0.9 m, wrists at shoulder height ±0.35 m in x.
- **Projection:** use `project_point` with `fx = fy = fake.focal_px` and the image center.
- **Movement:** `left`/`right` move toward the player's own left/right, which is camera +x/−x. `root_vx` is the x change divided by `dt`, or 0 when `dt` is 0.
- **Frame:** a numpy BGRA image filled with `render.background_rgb` (as BGR), plus filled rectangles for each player's body and head bbox. P1 is orange (`[40,140,255]` BGR) and P2 is blue (`[255,140,40]`).
- **Push:** spawns at the `r_wrist` pixel, with `hand="R"`.
- **Other fields:** `player_id = slot + 1`, `cam_t = now`, `zone` from `zone_for_distance`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/core/test_geometry.py tests/replay`
Expected: all pass.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box/core/geometry.py src/magic_box/replay tests/core/test_geometry.py tests/replay
git commit -m "feat(replay): add keyboard-driven fake players with synthetic frames"
```

---

### Task 7: Owned-module stubs, import boundaries, engine placeholder

**Files:** the stub modules listed below, `tests/test_boundaries.py`, `tests/test_imports.py`, `tests/game/{__init__,test_engine_stub}.py`

**Interfaces:**
- Consumes: contracts and config.
- Produces the following. Each module gets a docstring with `Owner:`, a purpose line, and the spec section it implements. Every name below raises `NotImplementedError("TODO(<Owner>): …")` unless the Behavior column says otherwise.

| Module (Owner) | Signatures | Behavior |
|---|---|---|
| `perception/process.py` (Enoch) | `run(cfg: Config, state_q: DropOldestQueue, frame_bus_name: str, stop: Event) -> None` | stub |
| `perception/zed_source.py` (Enoch) | `class ZedSource(cfg, svo_path: str \| None = None)`: `open()`, `grab() -> bool`, `retrieve_frame() -> Frame`, `retrieve_bodies() -> list[Any]`, `close()` | stub; `pyzed` imported inside methods |
| `perception/bodies.py` (Enoch) | `class SlotAssigner(cfg)`: `assign(bodies: list[Any], now: float) -> dict[int, Any]` | stub; docstring: slot 0 = larger image x |
| `perception/push.py` (Enoch) | `class PushDetector(cfg)`: `update(slot: int, hand: str, wrist: Vec3, cam_t: float, wrist_px: Px) -> Push \| None` | stub |
| `perception/poses.py` (Enoch) | `detect_poses(keypoints: Mapping[str, Vec3]) -> frozenset[str]` | stub |
| `perception/motion.py` (Enoch) | `class MotionTracker(cfg)`: `update(slot: int, root: Vec3, head: Vec3, cam_t: float) -> float` (root_vx) | stub |
| `perception/hands.py` (Enoch) | `detect_finger_gestures(frame: Frame, wrists_px: Mapping[str, Px]) -> dict[str, str \| None]` | stub, optional feature |
| `intent/fusion.py` (Nikhil) | `class Intent(cfg)`: `update(states: Sequence[PlayerState], voice: Sequence[VoiceEvent], now: float) -> list[Action]` | **placeholder: returns `[]`** |
| `intent/dodge.py` (Nikhil) | `class DodgeDetector(cfg)`: `update(state: PlayerState) -> str \| None` | stub |
| `voice/process.py` (Nikhil) | `run(cfg, voice_q: DropOldestQueue, control_q: DropOldestQueue, stop: Event) -> None` | stub |
| `voice/mic.py` (Nikhil) | `class MicCapture(device: str \| int \| None, channel: int, sample_rate: int)`: `start()`, `read() -> bytes`, `stop()` | stub; `sounddevice` lazy |
| `voice/muse_stream.py` (Nikhil) | `class MuseStream(cfg, api_key: str)`: `async connect(keywords: list[str])`, `async send_audio(pcm: bytes)`, `events() -> AsyncIterator[dict]`, `async close()` | stub |
| `voice/matcher.py` (Nikhil) | `match_incantation(text: str, incantations: Mapping[str, str], threshold: float) -> tuple[str, float] \| None` | stub |
| `ai/spark_client.py` (Nikhil) | `class SparkClient(cfg)`: `complete(system: str, user: str) -> str` | stub |
| `ai/incantations.py` (Nikhil) | `generate_incantations(client: SparkClient, classes: Mapping[int, str], cfg) -> dict[int, dict[str, str]]`, `fallback_incantations(classes: Mapping[int, str], cfg) -> dict[int, dict[str, str]]` | stubs |
| `ai/chronicle.py` (Nikhil) | `write_chronicle(client, events: Sequence[GameEvent], names: Mapping[int, str]) -> str`, `template_chronicle(events, names) -> str` | stubs |
| `game/classes.py` (Adetola) | `class_ids(cfg) -> list[str]` | stub |
| `game/spells.py` (Adetola) | `@dataclass(frozen=True) SpellDef(id: str, name: str, cost: float, damage: float, travel_s: float, release: str)`, `load_spells(cfg, class_id: str) -> list[SpellDef]` | dataclass real; `load_spells` stub |
| `game/state.py` (Adetola) | `class MatchState(cfg)`: HP, mana, charges, buffs, projectiles in flight (docstring lists them) | stub (constructor raises) |
| `game/combat.py` (Adetola) | `damage(base: float, push_speed: float, atk_dist: float, def_dist: float, buff_mult: float, cfg) -> float` | stub; docstring quotes the Appendix A formula |
| `game/scenes.py` (Adetola) | `class SceneMachine(cfg)`: `.scene: str`, `update(actions: Sequence[Action], states: Mapping[int, PlayerState], now: float) -> str` | stub (constructor raises) |
| `game/engine.py` (Adetola) | `class Engine(cfg)`: `step(actions: Sequence[Action], states: Mapping[int, PlayerState], now: float) -> tuple[GameView, list[GameEvent]]`, `provide_incantations(incantations: dict[int, dict[str, str]]) -> None`, `provide_chronicle(text: str) -> None` | **placeholder:** see the engine test; `provide_*` store and ignore |
| `replay/record.py` (Nikhil) | `class SessionRecorder(out_dir: Path)`: `write_state`, `write_voice`, `write_event`, `write_frame`, `close` | stub (constructor raises) |
| `replay/play.py` (Nikhil) | `class SessionPlayer(session_dir: Path)`: `poll(now: float) -> tuple[list[PlayerState], list[VoiceEvent], Frame \| None]` | stub (constructor raises) |
| `render/projectiles.py` (Nikhil) | `draw_projectiles(surface, half: Rect, crop: Rect, projectiles: Sequence[ProjectileView], target_slot: int) -> None` | **returns immediately when no projectile targets `target_slot`**, otherwise stub |
| `render/debug_overlay.py` (Enoch) | `draw_debug_overlay(surface, states: Mapping[int, PlayerState], fps: float, dropped: int) -> None` | **placeholder:** draws `f"fps {fps:.0f}  dropped {dropped}"` top-left |
| `render/scenes/{lobby,loading,victory}.py` (Adetola) + `render/scenes/__init__.py` | each `draw(surface, view: GameView) -> None`; `__init__`: `draw_scene(surface, view)` dispatches on `view.scene` | **placeholder:** centered scene name text |

`render/*` stubs import `Rect` from `magic_box.render.layout`, which Task 9 creates. In this task, create `render/layout.py` with only the `Rect` dataclass (`x, y, w, h: int`), `as_tuple() -> tuple[int, int, int, int]` and `contains(other: Rect) -> bool`. Task 9 extends it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_boundaries.py
import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "src" / "magic_box"
FILES = sorted(PKG.rglob("*.py"))


def _rel(p):
    return p.relative_to(PKG).as_posix()


def _imports(path, top_level_only=False):
    tree = ast.parse(path.read_text())
    nodes = tree.body if top_level_only else ast.walk(tree)
    names = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _roots(path, **kw):
    return {n.split(".")[0] for n in _imports(path, **kw)}


@pytest.mark.parametrize("path", FILES, ids=_rel)
def test_boundaries(path):
    rel, roots = _rel(path), _roots(path)
    if "pyzed" in roots:
        assert rel.startswith("perception/"), "pyzed only in perception/"
    if "pygame" in roots:
        assert rel.startswith("render/"), "pygame only in render/"
    if rel.startswith("game/"):
        assert not roots & {"pygame", "pyzed", "cv2"}
    if rel.startswith("core/"):
        project = {n for n in _imports(path) if n.startswith("magic_box.")}
        assert all(n.startswith("magic_box.core") for n in project)
    assert not _roots(path, top_level_only=True) & {"pyzed", "cv2", "sounddevice"}, "lazy-import heavy deps"
```

```python
# tests/test_imports.py
import importlib
import pkgutil

import pytest

import magic_box

MODULES = sorted(m.name for m in pkgutil.walk_packages(magic_box.__path__, "magic_box."))


@pytest.mark.parametrize("name", MODULES)
def test_module_imports_and_names_owner(name):
    module = importlib.import_module(name)
    assert module.__doc__ and "Owner:" in module.__doc__
```

```python
# tests/game/test_engine_stub.py
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_engine_placeholder_view():
    view, events = Engine(CFG).step([], {0: make_state(slot=0, zone="danger", root=(0.6, 0.0, 1.2))}, now=0.0)
    p1, p2 = view.players
    cls = CFG["game"]["default_classes"][0]
    assert view.scene == "fight" and events == [] and view.timer_s == CFG["game"]["round_s"]
    assert p1.hp == p1.hp_max == CFG["game"]["hp_max"]
    assert p1.zone == "danger" and p1.dist == pytest.approx(1.2) and p1.tracking_ok
    assert p2.tracking_ok is False  # no state for slot 1 yet
    assert [s.incantation for s in p1.spells] == [sp["fallback"][0] for sp in CFG["game"]["classes"][cls]["spells"]]
    assert view.projectiles == ()


def test_intent_placeholder_returns_no_actions():
    assert Intent(CFG).update([], [], 0.0) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_boundaries.py tests/test_imports.py tests/game`
Expected: FAIL. `tests/game` errors with `ModuleNotFoundError: magic_box.game`. `test_boundaries` and `test_imports` may already pass for the modules that exist so far.

- [ ] **Step 3: Write every stub module and the `__init__.py` docstrings.** Each `__init__.py` gets a docstring with `Owner:`, matching the package owner from spec §13. The engine placeholder fills `PlayerView` from the config defaults:
- `name = f"P{slot + 1}"`;
- `class_id = default_classes[slot]`;
- HP and mana at their maximums;
- `spells` built from that class's spells, with `incantation = fallback[slot]` and `charged=False`;
- `zone`, `dist` (`root[2]`) and `tracking_ok` from `states.get(slot)` (no state means `"neutral"`, `0.0`, `False`);
- `mic_ok=False`.

The `GameView` itself uses `scene="fight"`, `projectiles=()`, `banner=None`, `timer_s=round_s` and `chronicle=None`.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest && uv run ruff check`
Expected: all pass, ruff clean.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box tests/test_boundaries.py tests/test_imports.py tests/game
git commit -m "feat(repo): add owned-module stubs with import-boundary tests"
```

---

### Task 8: Sources (fake, live, replay) and keyboard voice

**Files:** `src/magic_box/pipeline/sources.py`, `tests/pipeline/test_sources.py`

**Interfaces:**
- Consumes: `FakePlayers` (Task 6), `DropOldestQueue` (Task 4), `FrameBus` (Task 5), `SessionPlayer` (Task 7).
- Produces, in `magic_box.pipeline.sources`:
  - `@dataclass class Inputs: states: list[PlayerState]; voice: list[VoiceEvent]; frame: Frame | None`
  - `class Sources(Protocol)`: `poll(keys: frozenset[str], now: float, dt: float) -> Inputs`; `close() -> None`
  - `FakeSources(cfg)`
  - `LiveSources(state_q: DropOldestQueue, voice_q: DropOldestQueue, frame_bus: FrameBus)`. `close()` does nothing; the runtime owns cleanup.
  - `ReplaySources(session_dir: Path)`, which wraps `SessionPlayer`.
  - `KeyboardVoiceSource(cfg)`:
    - `set_spells(spells: Mapping[int, Sequence[str]]) -> None`
    - `poll(keys: frozenset[str], now: float) -> list[VoiceEvent]`. It is edge-triggered. Key index *i* in `keys.spells[slot]` maps to `spells[slot][i]`. It emits `VoiceEvent(slot, now, "incantation", f"<key {k}>", spell_id, 100.0)`.

- [ ] **Step 1: Write the failing tests** `tests/pipeline/test_sources.py`

```python
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.pipeline.frame_bus import FrameBus
from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource, LiveSources, ReplaySources
from magic_box.pipeline.streams import DropOldestQueue
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
SPELLS = {0: ["fireball", "flame_wall", "inferno"], 1: ["bolt", "chain", "static_field"]}


def test_fake_sources_poll():
    inputs = FakeSources(CFG).poll(frozenset(), now=0.0, dt=0.0)
    assert sorted(s.slot for s in inputs.states) == [0, 1]
    assert inputs.voice == [] and inputs.frame is not None


def test_keyboard_voice_edge_triggered():
    kb = KeyboardVoiceSource(CFG)
    kb.set_spells(SPELLS)
    first = kb.poll(frozenset({"1"}), now=1.0)
    assert [(e.slot, e.spell_id, e.match_score) for e in first] == [(0, "fireball", 100.0)]
    assert kb.poll(frozenset({"1"}), now=1.1) == []  # held: no repeat
    assert [e.spell_id for e in kb.poll(frozenset({"0"}), now=1.2)] == ["static_field"]


def test_keyboard_voice_without_spells_is_silent():
    assert KeyboardVoiceSource(CFG).poll(frozenset({"1"}), now=0.0) == []


def test_live_sources_read_queues_and_bus():
    bus = FrameBus.create(64, 48)
    try:
        state_q, voice_q = DropOldestQueue(8), DropOldestQueue(8)
        state_q.put(make_state())
        src = LiveSources(state_q, voice_q, bus)
        got = []
        for _ in range(200):
            got += src.poll(frozenset(), 0.0, 0.0).states
            if got:
                break
        assert got == [make_state()]
        assert src.poll(frozenset(), 0.0, 0.0).frame is None
    finally:
        bus.close()
        bus.unlink()


def test_replay_sources_not_implemented_yet():
    with pytest.raises(NotImplementedError, match="TODO\\(Nikhil\\)"):
        ReplaySources(Path("nowhere"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/pipeline/test_sources.py`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `sources.py`.**
- `FakeSources` returns `voice=[]` and the fake frame.
- `LiveSources` drains both queues and calls `frame_bus.read_latest()`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/pipeline/test_sources.py`
Expected: 5 passed.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box/pipeline/sources.py tests/pipeline/test_sources.py
git commit -m "feat(pipeline): add fake, live and replay sources with keyboard voice fallback"
```

---

### Task 9: Layout C renderer (layout, camera view, placeholder HUD, window)

**Files:** `src/magic_box/render/{__init__,layout,camera_view,hud,window}.py`, `tests/render/{__init__,test_layout,test_camera_view,test_window}.py`

**Interfaces:**
- Consumes: contracts, config, `FakePlayers` (tests only), `make_view` (tests), and the Task 7 render stubs.
- Produces:
  - **`render.layout`** (pure, no pygame):
    - `Rect` from Task 7.
    - `@dataclass(frozen=True) HalfLayout(viewer_slot: int, shows_slot: int, half: Rect, enemy_bar: Rect, selfview: Rect, hud: Rect)`
    - `compute_layout(width: int, height: int, render_cfg: Mapping) -> tuple[HalfLayout, HalfLayout]`
  - **`render.camera_view`:**
    - Pure functions:
      - `crop_rect_for_bbox(bbox_px: tuple[int, int, int, int], aspect: Sequence[int], padding: float, image_w: int, image_h: int) -> Rect`
      - `class CropSmoother(alpha: float)` with `update(target: Rect) -> Rect`
      - `map_point_to_dest(p: Px, crop: Rect, dest: Rect, mirror: bool) -> tuple[int, int]`
    - pygame functions:
      - `frame_to_surface(frame: Frame) -> pygame.Surface`, using `pygame.image.frombuffer(image, (w, h), "BGRA")`
      - `draw_opponent(surface, dest: Rect, frame_surf, crop: Rect) -> None`
      - `draw_selfview(surface, dest: Rect, frame_surf, crop: Rect, keypoints_px: Mapping[str, Px]) -> None`, which mirrors the image and draws `SKELETON_EDGES`
  - **`render.hud`** (placeholder, Adetola replaces it):
    - `draw_hud(surface, rect: Rect, me: PlayerView, font) -> None`: name · class, `f"{dist:.1f} m · {zone.upper()}"`, HP and mana bars, one line per spell `f"{name}: \"{incantation}\""`.
    - `draw_enemy_bar(surface, rect: Rect, enemy: PlayerView, font) -> None`
  - **`render.window`:** `class Window(cfg, headless: bool = False)` with:
    - `.screen: pygame.Surface`
    - `pump() -> tuple[frozenset[str], bool]`: held key names (`pygame.key.name`) and whether quit was requested (window close or `keys.quit`). Pressing `keys.debug_overlay` toggles `.debug` internally.
    - `tick() -> float`: `clock.tick(display.fps) / 1000`.
    - `draw(view: GameView, frame: Frame | None, states: Mapping[int, PlayerState], fps: float, dropped: int = 0) -> None`
    - `close() -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/render/test_layout.py
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.render.layout import Rect, compute_layout

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_halves_and_slots():
    left, right = compute_layout(1920, 1080, CFG["render"])
    assert left.half == Rect(0, 0, 960, 1080) and right.half == Rect(960, 0, 960, 1080)
    assert (left.viewer_slot, left.shows_slot, right.viewer_slot, right.shows_slot) == (0, 1, 1, 0)


def test_regions_inside_half():
    for h in compute_layout(1920, 1080, CFG["render"]):
        for r in (h.enemy_bar, h.selfview, h.hud):
            assert h.half.contains(r)
        assert h.selfview.x + h.selfview.w > h.half.x + h.half.w / 2  # top-right corner
        assert h.hud.y + h.hud.h <= 1080 and h.hud.y > 540              # bottom
```

```python
# tests/render/test_camera_view.py
import pytest

from magic_box.render.camera_view import CropSmoother, crop_rect_for_bbox, map_point_to_dest
from magic_box.render.layout import Rect

IMG = (1280, 720)


@pytest.mark.parametrize("bbox", [(600, 200, 100, 300), (0, 0, 50, 50), (1200, 600, 80, 120), (0, 0, 1280, 720)])
def test_crop_has_aspect_and_stays_in_image(bbox):
    r = crop_rect_for_bbox(bbox, (8, 9), 0.15, *IMG)
    assert abs(r.w * 9 - r.h * 8) <= 9
    assert r.x >= 0 and r.y >= 0 and r.x + r.w <= IMG[0] and r.y + r.h <= IMG[1]


def test_crop_contains_padded_bbox_when_it_fits():
    r = crop_rect_for_bbox((600, 200, 100, 300), (8, 9), 0.15, *IMG)
    assert r.contains(Rect(585, 155, 130, 390))


def test_smoother():
    s = CropSmoother(0.5)
    assert s.update(Rect(0, 0, 100, 100)) == Rect(0, 0, 100, 100)
    assert s.update(Rect(100, 0, 100, 100)) == Rect(50, 0, 100, 100)


def test_map_point_mirrors():
    crop, dest = Rect(100, 100, 200, 200), Rect(0, 0, 100, 100)
    assert map_point_to_dest((150.0, 200.0), crop, dest, mirror=False) == (25, 50)
    assert map_point_to_dest((150.0, 200.0), crop, dest, mirror=True) == (75, 50)
```

```python
# tests/render/test_window.py
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.render.window import Window
from magic_box.replay.fake_input import FakePlayers
from tests.factories import make_view

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_draw_fight_view_with_fake_frame():
    w = Window(CFG, headless=True)
    try:
        states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
        w.draw(make_view(), frame, {s.slot: s for s in states}, fps=60.0)
        assert w.screen.get_size() == (1920, 1080)
        assert tuple(w.screen.get_at((960, 540)))[:3] == tuple(CFG["render"]["divider_rgb"])
    finally:
        w.close()


def test_draw_without_frame_or_states_and_pump():
    w = Window(CFG, headless=True)
    try:
        w.draw(make_view(), None, {}, fps=60.0)
        assert w.pump() == (frozenset(), False)
    finally:
        w.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/render`
Expected: FAIL. `compute_layout` and `camera_view` don't exist yet.

- [ ] **Step 3: Implement the four modules**

`compute_layout` geometry, where `m = margin_px` and half width `hw = width // 2`:
- `enemy_bar`: x = half.x + hw·0.24, y = m, w = hw·0.52, h = 28.
- `selfview`: w = hw·`selfview_width_frac`, h = w·3/4, top-right inset by `m`, y = m + 44.
- `hud`: x = half.x + m, w = hw − 2m, h = height·`hud_height_frac`, bottom inset by `m`.

`crop_rect_for_bbox` steps:
1. Pad each side of the bbox by `padding × size`.
2. Grow the short dimension to the target aspect ratio, keeping the center.
3. If the result is larger than the image, shrink it to the largest aspect-correct rect that fits.
4. Shift it inside the image bounds.

`Window` behavior:
- **Init:** with `headless=True`, set `SDL_VIDEODRIVER=dummy` before `pygame.init()`.
- **Output mode:** fullscreen from config; fonts from `pygame.font.Font(None, size)`.
- **Smoothing:** one `CropSmoother` per half for the opponent crop, and one for the self-view.
- **Fight scene:** draw each half in this order:
  1. the opponent crop from `states[half.shows_slot]`, or "STEP INTO VIEW" when the frame or state is missing or `tracking_ok` is false;
  2. `draw_enemy_bar(screen, half.enemy_bar, view.players[half.shows_slot], font)`;
  3. the self-view of `states[half.viewer_slot]`, only when that state is OK;
  4. `draw_hud(screen, half.hud, view.players[half.viewer_slot], font)`;
  5. `draw_projectiles(screen, half.half, opponent_crop, view.projectiles, half.viewer_slot)`. Spells are drawn on the target's half, and the target is that half's viewer.

  Then draw the divider, then the banner, then the debug overlay if `.debug` is on.
- **Other scenes:** `draw_scene`.
- **Frame surface cache:** keyed by `frame_idx`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/render`
Expected: all pass.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box/render tests/render
git commit -m "feat(render): add layout c window with opponent crops, mirrored self-view and placeholder hud"
```

---

### Task 10: Game loop and `python -m magic_box` (fake mode)

**Files:** `src/magic_box/pipeline/loop.py`, `src/magic_box/main.py`, `src/magic_box/__main__.py`, `tests/pipeline/test_loop.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `Sources`, `Inputs`, `KeyboardVoiceSource`, `FakeSources`, `ReplaySources` (Task 8), `Window` (Task 9), `Intent` and `Engine` (Task 7).
- Produces, in `magic_box.pipeline.loop`:
  - `latest_states(prev: Mapping[int, PlayerState], new: Sequence[PlayerState], now: float, stale_s: float) -> dict[int, PlayerState]`. It keeps the newest state per slot, and returns any state with `now - t > stale_s` as `dataclasses.replace(s, tracking_ok=False)`.
  - `class Display(Protocol)`: `pump`, `tick`, `draw`, `close`, matching `Window`'s signatures.
  - `class GameLoop(cfg, sources: Sources, display: Display, intent: Intent, engine: Engine, keyboard_voice: KeyboardVoiceSource, on_tick: Callable[[], None] | None = None)`, with `run(max_ticks: int | None = None) -> int` (the number of ticks run).
- Produces, in `magic_box.main`:
  - `parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace`, with these flags:
    - `--fake` and `--replay DIR`, mutually exclusive;
    - `--record DIR`, `--debug`, `--headless`;
    - `--config PATH` (default `config.yaml`);
    - `--max-ticks N`.
  - `run(argv: Sequence[str] | None = None) -> int`.
  - `__main__.py`: under `if __name__ == "__main__":`, `raise SystemExit(run())`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_loop.py
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.loop import GameLoop, latest_states
from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_latest_keeps_newest_per_slot():
    out = latest_states({}, [make_state(t=1.0), make_state(t=1.05)], now=1.1, stale_s=0.2)
    assert out[0].t == 1.05 and out[0].tracking_ok


def test_stalled_camera_marks_tracking_lost():
    fresh = latest_states({}, [make_state(t=1.0)], now=1.1, stale_s=0.2)
    stale = latest_states(fresh, [], now=1.3, stale_s=0.2)
    assert stale[0].tracking_ok is False and stale[0].root == fresh[0].root


class ScriptedDisplay:
    def __init__(self, script):
        self.script, self.draws = list(script), 0

    def pump(self):
        keys = self.script.pop(0) if self.script else frozenset()
        return frozenset(keys), False

    def tick(self):
        return 1 / 60

    def draw(self, view, frame, states, fps, dropped=0):
        self.draws += 1

    def close(self):
        pass


class SpyIntent(Intent):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.voice = []

    def update(self, states, voice, now):
        self.voice += list(voice)
        return super().update(states, voice, now)


def test_loop_merges_keyboard_voice_from_second_tick():
    display, intent = ScriptedDisplay([set(), {"1"}, set()]), SpyIntent(CFG)
    loop = GameLoop(CFG, FakeSources(CFG), display, intent, Engine(CFG), KeyboardVoiceSource(CFG))
    assert loop.run(max_ticks=3) == 3
    assert [(e.slot, e.spell_id) for e in intent.voice] == [(0, "fireball")]
    assert display.draws == 3
```

```python
# tests/test_main.py
import pytest

from magic_box.main import parse_args, run


def test_fake_mode_runs_headless():
    assert run(["--fake", "--headless", "--max-ticks", "30"]) == 0


def test_replay_not_implemented_exits_2(capsys):
    assert run(["--replay", "nowhere", "--headless", "--max-ticks", "1"]) == 2
    assert "not implemented" in capsys.readouterr().err.lower()


def test_fake_and_replay_are_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--fake", "--replay", "x"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/pipeline/test_loop.py tests/test_main.py`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `loop.py`, `main.py`, `__main__.py`**

Each tick runs in this order:
1. `keys, quit = display.pump()`; stop if `quit`.
2. `dt = display.tick()`; `now = time.monotonic()`.
3. `inputs = sources.poll(keys, now, dt)`.
4. `voice = inputs.voice + keyboard_voice.poll(keys, now)`.
5. `latest = latest_states(...)`.
6. `actions = intent.update(inputs.states, voice, now)`.
7. `view, _events = engine.step(actions, latest, now)`.
8. `keyboard_voice.set_spells({p.slot: [s.id for s in p.spells] for p in view.players})`.
9. `display.draw(view, inputs.frame or last_frame, latest, fps)`.
10. Call `on_tick()` if it was given.

At the point where the scene changes, leave `# TODO(Nikhil): submit Spark jobs on loading/victory (spec §6)`.

`main.run` behavior:
- Loads the config, enables debug mode if `--debug`, and builds the sources for the mode. Live mode is added in Task 11; until then it prints `"live mode: TODO(Nikhil) Task 11"` to stderr and returns 2.
- Wraps setup and the loop in `try/except NotImplementedError as e`, which prints `f"not implemented yet: {e}"` to stderr and returns 2.
- `--record` constructs `SessionRecorder` (still a stub).
- Always closes the window and sources.

- [ ] **Step 4: Run to verify it passes, then look at it**

Run: `uv run pytest && uv run python -m magic_box --fake`
Expected: all tests pass. A 1920×1080 window shows layout C with two silhouettes. `W`/`S` resize P1, `F1` toggles the fps overlay, and `Esc` quits. Report what you saw.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box/pipeline/loop.py src/magic_box/main.py src/magic_box/__main__.py tests/pipeline/test_loop.py tests/test_main.py
git commit -m "feat(pipeline): add game loop and python -m magic_box with fake mode"
```

---

### Task 11: Process supervisor and live-mode wiring

**Files:** `src/magic_box/pipeline/processes.py`, `tests/pipeline/test_processes.py`; modify `src/magic_box/main.py` and `tests/helpers.py`

**Interfaces:**
- Consumes: `spawn_context`, `DropOldestQueue`, `FrameBus`, `LiveSources`, `perception.process.run`, `voice.process.run`.
- Produces, in `magic_box.pipeline.processes`:
  - `@dataclass ProcSpec(name: str, target: Callable[..., None], args: tuple, restart: bool = True)`
  - `class Supervisor(specs: Sequence[ProcSpec], ctx: BaseContext, backoff_s: float, max_restarts: int)`, with:
    - `start() -> None`
    - `poll() -> None`: non-blocking. It restarts dead processes with `restart=True` once `backoff_s` has passed since they died, up to `max_restarts`, and logs each restart to stderr.
    - `restarts(name: str) -> int`
    - `alive(name: str) -> bool`
    - `stop(timeout: float = 2.0) -> None`: sets `stop_event`, joins, and terminates stragglers.
    - `.stop_event`: created in `__init__` from `ctx` and passed to targets as their last argument.
  - `@dataclass LiveRuntime(supervisor: Supervisor, sources: LiveSources, control_q: DropOldestQueue, frame_bus: FrameBus)`, with `close() -> None` (stops the supervisor, then closes and unlinks the bus).
  - `start_live(cfg: Config) -> LiveRuntime`. It creates the queues from the `pipeline.*_queue_size` values and a bus sized `camera.image_width × camera.image_height`. It defines the `perception` spec and, only if `voice.enabled`, the `voice` spec, then starts them.
- Adds to `tests/helpers.py`:
  - `crash_immediately(stop) -> None`: `raise SystemExit(1)`.
  - `wait_for_stop(stop) -> None`: `stop.wait(10)`.

- [ ] **Step 1: Write the failing tests** `tests/pipeline/test_processes.py`

```python
import time
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.pipeline.processes import ProcSpec, Supervisor, start_live
from magic_box.pipeline.streams import spawn_context
from tests.helpers import crash_immediately, wait_for_stop

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def _poll_for(sup, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        sup.poll()
        time.sleep(0.02)


def test_crashing_process_restarted_up_to_limit():
    sup = Supervisor([ProcSpec("crash", crash_immediately, ())], spawn_context(), backoff_s=0.05, max_restarts=2)
    sup.start()
    _poll_for(sup, 4.0)
    assert sup.restarts("crash") == 2 and not sup.alive("crash")
    sup.stop()


def test_stop_joins_well_behaved_process():
    sup = Supervisor([ProcSpec("ok", wait_for_stop, ())], spawn_context(), backoff_s=0.05, max_restarts=0)
    sup.start()
    _poll_for(sup, 0.5)
    assert sup.alive("ok")
    sup.stop(timeout=5.0)
    assert not sup.alive("ok")


def test_start_live_wires_sources_with_stubbed_perception():
    cfg = {**CFG, "voice": {**CFG["voice"], "enabled": False}, "pipeline": {**CFG["pipeline"], "max_restarts": 0}}
    rt = start_live(cfg)
    try:
        inputs = rt.sources.poll(frozenset(), 0.0, 0.0)
        assert inputs.states == [] and inputs.frame is None
    finally:
        rt.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/pipeline/test_processes.py`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `processes.py` and wire live mode in `main.run`.** Live mode should:
- call `rt = start_live(cfg)`;
- create `GameLoop(..., sources=rt.sources, on_tick=rt.supervisor.poll)`;
- call `rt.close()` in `finally`.

Replace the Task 10 "live mode TODO" path. In live mode on a laptop, the perception stub's `NotImplementedError` traceback shows up in the child process, and the window shows "STEP INTO VIEW". That is expected.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest`
Expected: all pass.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add src/magic_box/pipeline/processes.py src/magic_box/main.py tests/pipeline/test_processes.py tests/helpers.py
git commit -m "feat(pipeline): add process supervisor and live-mode wiring"
```

---

### Task 12: Jetson scripts

**Files:** `scripts/{check_env,bench_tracking,record_session}.py`, `scripts/sync_to_jetson.sh`, `tests/scripts/{__init__,test_scripts}.py`

**Interfaces:**
- Produces, in `scripts/check_env.py` (Owner: Daniel):
  - `@dataclass Check(name: str, ok: bool, detail: str, required: bool)`
  - `run_checks(laptop: bool, network: bool) -> list[Check]`
  - `main(argv: Sequence[str] | None = None) -> int`, with flags `--laptop` and `--network`. It prints one line per check (`OK` / `FAIL` / `WARN` plus the detail) and returns 1 if any required check failed, otherwise 0.
- Checks, by name:

  | Name | What it checks | Required |
  |---|---|---|
  | `python` | 3.10.x | always |
  | `arch` | `aarch64` | unless `--laptop` |
  | `jetpack` | contents of `/etc/nv_tegra_release` | unless `--laptop` |
  | `ram` | `/proc/meminfo` or `os.sysconf` | info only |
  | `pyzed` | `import pyzed.sl` inside this venv, plus the SDK version | unless `--laptop` |
  | `numpy` | version | info only |
  | `cv2` | version and whether `getBuildInformation` reports CUDA | info only |
  | `sounddevice` | the input-device list | unless `--laptop` |
  | `api_key` | `ai.api_key_env` is set | never required (WARN) |
  | `meta_api` | GET `{ai.base_url}/models` with a 5 s timeout | only with `--network`; never required |

  All of these are imported lazily, inside their check.
- Produces stubs:
  - `bench_tracking.py` (Owner: Enoch), flags `--seconds` and `--body-format`. Docstring: run body tracking with two people and print the fps for the go/no-go call.
  - `record_session.py` (Owner: Enoch + Nikhil), flags `--out` and `--seconds`.

  Both parse their args and then raise `NotImplementedError("TODO(...)")`.
- `sync_to_jetson.sh` (Owner: Daniel) runs `rsync -az --delete --exclude .venv --exclude .git --exclude recordings --exclude .env --exclude .superpowers ./ "${JETSON_HOST:-jetson}:${JETSON_DIR:-~/magic-box}/"`. It uses `set -euo pipefail` and prints the target first.

- [ ] **Step 1: Write the failing tests** `tests/scripts/test_scripts.py`

```python
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_check_env_laptop_mode_passes():
    assert _load("check_env").main(["--laptop"]) == 0


def test_check_env_jetson_checks_optional_on_laptop():
    checks = {c.name: c for c in _load("check_env").run_checks(laptop=True, network=False)}
    assert {"python", "arch", "jetpack", "pyzed", "numpy", "sounddevice", "api_key"} <= set(checks)
    assert checks["python"].required and checks["python"].ok
    assert not any(checks[n].required for n in ("arch", "jetpack", "pyzed", "sounddevice", "api_key"))


@pytest.mark.parametrize("name", ["bench_tracking", "record_session"])
def test_stub_scripts_have_help(name):
    with pytest.raises(SystemExit) as err:
        _load(name).main(["--help"])
    assert err.value.code == 0


def test_sync_script_syntax():
    assert subprocess.run(["bash", "-n", str(SCRIPTS / "sync_to_jetson.sh")]).returncode == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/scripts`
Expected: FAIL, file not found.

- [ ] **Step 3: Implement the four scripts.**
- Every check catches all exceptions and reports `ok=False` with the exception text. On a laptop or CI, `sounddevice` without PortAudio raises `OSError`.
- Python scripts end with `if __name__ == "__main__": raise SystemExit(main())`.
- Make `sync_to_jetson.sh` executable (`chmod +x`).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/scripts && uv run python scripts/check_env.py --laptop`
Expected: tests pass. The script prints the check table with `python OK` and exits 0.

- [ ] **Step 5: Print commit command for Daniel**

```bash
git add scripts tests/scripts
git commit -m "feat(scripts): add jetson env check, sync script and tracking bench stubs"
```

---

### Task 13: Claude files, README and docs

**Files:** `CLAUDE.md`, `src/magic_box/{core,perception,pipeline,intent,voice,ai,game,render,replay}/CLAUDE.md`, `.claude/settings.json`, `README.md`, `docs/game-design.md`, `docs/hardware.md`, `tests/test_blueprint.py`

**Interfaces:**
- Consumes: every name, command and flag above. Every command written in these docs must be one that exists after Tasks 1–12.

- [ ] **Step 1: Write the failing test** `tests/test_blueprint.py`

```python
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ["core", "perception", "pipeline", "intent", "voice", "ai", "game", "render", "replay"]


@pytest.mark.parametrize("pkg", PACKAGES)
def test_package_claude_md(pkg):
    text = (ROOT / "src" / "magic_box" / pkg / "CLAUDE.md").read_text()
    for heading in ("**Owner:**", "## Inputs → Outputs", "## Hard rules", "## Files", "## Test without the Jetson", "## Open TODOs"):
        assert heading in text, f"{pkg}/CLAUDE.md missing {heading}"


def test_root_claude_md_maps_every_package():
    text = (ROOT / "CLAUDE.md").read_text()
    assert all(f"{pkg}/" in text for pkg in PACKAGES)
    assert "python -m magic_box --fake" in text


def test_shared_claude_settings():
    allow = json.loads((ROOT / ".claude" / "settings.json").read_text())["permissions"]["allow"]
    assert "Bash(uv run pytest:*)" in allow


@pytest.mark.parametrize("doc", ["README.md", "docs/game-design.md", "docs/hardware.md"])
def test_docs_exist(doc):
    assert (ROOT / doc).read_text().strip()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_blueprint.py`
Expected: FAIL, file not found.

- [ ] **Step 3: Write root `CLAUDE.md`.** It starts from the team's mock CLAUDE.md, updated to match the spec, with these sections in order:
1. **What this is:** two or three sentences from spec §1.
2. **Why ZED + Jetson:** keep the mock's five points; add "speech-to-text and Spark run in Meta's cloud; video never leaves the box".
3. **Hardware:** spec §4 table.
4. **Architecture:** spec §6 diagram, transport rules, clock rule, units, slot convention (P1 = image right).
5. **Contracts:** a pointer to `core/contracts.py` and the change rule from spec §7.
6. **Team and ownership:** the spec §13 tree with owners.
7. **Conventions:** the Global Constraints of this plan, as team rules.
8. **Working without the Jetson:** `--fake`, `--replay`, recordings.
9. **Commands:** only real ones:
   - `uv sync --extra laptop`
   - `uv run python -m magic_box --fake`
   - `uv run --env-file .env python -m magic_box`
   - `uv run pytest`
   - `uv run ruff check`
   - `uv run python scripts/check_env.py [--laptop]`
   - `scripts/sync_to_jetson.sh`
10. **Milestones:** spec §14.
11. **Risks:** spec §15.
12. **Open decisions:** spec §16 with owners.

- [ ] **Step 4: Write the nine package `CLAUDE.md` files.** Each one has, in order:
- the title;
- `**Owner:** <Name>`;
- a one-line purpose;
- `## Inputs → Outputs`, naming the contracts from spec §7 and §8;
- `## Hard rules`, the boundary and lazy-import rules that apply to that package, plus "never block the game loop" where relevant;
- `## Files`, one line per file in the package;
- `## Test without the Jetson`, with exact `uv run pytest tests/<pkg>` and `--fake` usage;
- `## Open TODOs`, listing the package's `TODO(owner)` items and its spec §16 open decisions.

Keep each one under about 60 lines.

- [ ] **Step 5: Write `.claude/settings.json`, `README.md` and the two docs**
- **`.claude/settings.json`:** `permissions.allow` = `Bash(uv sync:*)`, `Bash(uv run pytest:*)`, `Bash(uv run ruff:*)`, `Bash(uv run python -m magic_box:*)`, `Bash(uv run python scripts/check_env.py:*)`, `Bash(git status:*)`, `Bash(git diff:*)`, `Bash(git log:*)`, `Bash(git show:*)`.
- **`README.md`:**
  - **Laptop quickstart:** `uv sync --extra laptop`, `uv run python -m magic_box --fake`, and a table of the fake-mode keys from `config.yaml`.
  - **Jetson quickstart:**
    1. Install the ZED SDK and its Python API.
    2. `sudo apt install libportaudio2`
    3. `uv venv --system-site-packages --python /usr/bin/python3`
    4. `uv sync` (no laptop extra)
    5. `uv run python scripts/check_env.py`
    6. `cp .env.example .env`
    7. `uv run --env-file .env python -m magic_box`
  - **Team table.**
- **`docs/game-design.md`:** `**Owner:** Adetola`, a `DRAFT: open for discussion` banner, spec Appendix A, spec §10 scene flow, and an "Open questions" list.
- **`docs/hardware.md`:** `**Owner:** Daniel + Enoch`, with:
  - the parts table (spec §4, including the DisplayPort note);
  - mic routing via `config.local.yaml` `voice.mics`;
  - ZED placement and play-area tape marks at the `perception.zones` distances;
  - Jetson setup (power mode via `sudo nvpmodel -q` / `-m`, `sudo jetson_clocks`);
  - Wi-Fi plus a phone-hotspot backup;
  - TODOs (enclosure, mic model).

- [ ] **Step 6: Run the whole suite and lint**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: all pass, ruff clean.

- [ ] **Step 7: Print commit command for Daniel**

```bash
git add CLAUDE.md src/magic_box/*/CLAUDE.md .claude/settings.json README.md docs/game-design.md docs/hardware.md tests/test_blueprint.py
git commit -m "doc(repo): add root and per-package claude files, readme and team docs"
```
