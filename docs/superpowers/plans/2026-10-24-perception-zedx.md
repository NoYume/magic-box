# Perception on the Jetson and ZED X Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill in `perception/` so the Jetson turns a live ZED X into two `PlayerState` streams plus camera frames; add the `F1` perception overlay and the Jetson tools (environment check, two-person tracking benchmark, SVO recorder); switch config and docs from the ZED 2 to the ZED X.

**Architecture:**
- `zed_source.py` is the only file that imports `pyzed`. It turns each grab into plain `Capture` / `RawBody` data.
- `PlayerTracker` (slots → motion → push → poses → zone) turns a `Capture` into `PlayerState`s. It is plain Python, tested on simulated bodies.
- `process.run_loop` owns opening, retrying, reopening and publishing. The overlay and the scripts reuse the same pieces.

**Tech Stack:** Python 3.10 (uv), numpy<2, pygame-ce, PyYAML, pytest, ruff. ZED SDK (`pyzed`) on the Jetson only.

**Spec:** `docs/superpowers/specs/2026-10-24-perception-zedx-design.md`. Read all of it; §7 (per-frame processing) and §8 (camera setup) are the core. Parent spec: `docs/superpowers/specs/2026-10-24-magic-box-design.md` §6–§8.

## Global Constraints

**Python and dependencies**
- Python `==3.10.*`. Use uv only (`uv run`, `uv sync`). Add no dependencies.

**Git**
- **Never run git commands that change the repo** (`add`, `commit`, `push`, `checkout`, `stash`, `restore`, …). At the end of each task, print the commit commands for Daniel to run. Format: `<type>(<scope>): <lowercase summary>`, one line, no body, no trailer.

**Import boundaries** (`tests/test_boundaries.py` enforces these for `src/`)
- `pyzed` is imported only under `src/magic_box/perception/` (and in `scripts/`), and only inside functions, never at module top level. Same for `cv2`.
- `pygame` only under `src/magic_box/render/`. `core/` imports only `magic_box.core`.
- Absolute imports only (`from magic_box.x import y`).

**Conventions**
- Every module docstring has a line `Owner: <Name>`:
  - Enoch: `perception/*`, `render/debug_overlay.py`, `scripts/bench_tracking.py`, `scripts/record_session.py`, and the new `tests/perception/` helper modules.
  - Daniel: `scripts/check_env.py`.
  - Nikhil: `core/*`.
  - Adetola + Nikhil: `render/window.py`.
- Every tunable lives in `config.yaml`; code reads it from `cfg`. Numbers marked "(guess)" are untuned.
- Units are meters and seconds. ZED `COORDINATE_SYSTEM.IMAGE`: +X image-right, +Y down, +Z away from the camera. Motion toward the camera has negative velocity.
- Slot 0 = P1, on the image's *right* (root x > 0).
- Velocities, windows and the slot hold use `cam_t` (camera seconds). `PlayerState.t` is `time.monotonic()` at publish.
- `l_` / `r_` keypoints and `"L"` / `"R"` wrists are the person's own left and right (ZED convention).

**Done criteria for each task**
- `uv run ruff check` and `uv run ruff format --check` are clean.
- `uv run pytest` is green.
- Tests run headless (`tests/conftest.py` sets the SDL dummy drivers) and never need `pyzed`.

## Review Focus

1. **An SVO recording loops and `cam_t` jumps backwards.** Velocities must restart instead of producing a huge false push, and the slot hold must still expire. Tested in Task 2 (`test_time_going_backwards_restarts_window`) and Task 3 (`test_cam_t_rewind_does_not_break_hold`).
2. **The neck keypoint flickers in and out.** The push reference then switches between neck z and root z. That jump must never fire a push. Tested in Task 5 (`test_reference_switch_does_not_fire_push`).
3. **A player stands close to the camera, with pelvis and legs out of frame.** They must still be tracked: root falls back to the body position, head to the neck, and the skeleton just has fewer points. Tested in Task 5 (`test_partial_body_still_tracked`).
4. **The SDK hands back a body with a NaN or infinite position.** It is ignored, and it never crashes the tracker or poisons velocities. Tested in Task 3 (`test_far_untracked_and_nan_bodies_ignored`).
5. **The camera vanishes mid-match (GMSL glitch).** The loop reopens it and keeps retrying while open fails. The process never exits on its own, and it stays responsive to `stop`. Tested in Task 7 (`test_camera_lost_mid_run_retries_until_back`).

---

## File Map

| Task | Creates | Modifies |
|---|---|---|
| 1 | | `config.yaml`, `src/magic_box/core/config.py`, `tests/core/test_config.py`, `tests/replay/test_fake_input.py` |
| 2 | `perception/raw.py`, `perception/keypoints.py`, `perception/kinematics.py`, `tests/perception/__init__.py`, `tests/perception/test_keypoints.py`, `tests/perception/test_kinematics.py` | `perception/__init__.py` |
| 3 | `tests/perception/fakes.py`, `tests/perception/test_bodies.py` | `perception/bodies.py` |
| 4 | `tests/perception/test_push.py`, `tests/perception/test_motion.py` | `perception/push.py`, `perception/motion.py` |
| 5 | `perception/tracker.py`, `tests/perception/test_poses.py`, `tests/perception/test_tracker.py` | `perception/poses.py`, `core/contracts.py` (comments) |
| 6 | `tests/perception/fake_sl.py`, `tests/perception/test_zed_source.py` | `perception/zed_source.py` |
| 7 | `tests/perception/test_process.py` | `perception/process.py`, `tests/perception/fakes.py` |
| 8 | `tests/render/test_debug_overlay.py` | `render/debug_overlay.py`, `render/window.py`, `tests/render/test_window.py` |
| 9 | | `scripts/check_env.py`, `scripts/bench_tracking.py`, `scripts/record_session.py`, `tests/scripts/test_scripts.py` |
| 10 | | `CLAUDE.md`, `README.md`, `docs/hardware.md`, `docs/game-design.md`, parent spec, `perception/CLAUDE.md`, `render/CLAUDE.md`, `pyproject.toml`, `tests/test_blueprint.py` |

Paths under `perception/`, `render/` and `core/` are relative to `src/magic_box/`.

---

### Task 1: ZED X config and camera validation

**Files:**
- Modify: `config.yaml` (sections `camera`, `perception`, `render`, `fake`)
- Modify: `src/magic_box/core/config.py`
- Modify: `tests/core/test_config.py`, `tests/replay/test_fake_input.py:24`

**Interfaces:**
- Produces: `CAMERA_MODES: dict[str, tuple[int, int]]` and `BODY_FORMATS: tuple[str, ...]` in `magic_box.core.config`. Also the config keys below, which every later task reads.

- [ ] **Step 1: Write the failing tests** (append to `tests/core/test_config.py`; import `BODY_FORMATS, CAMERA_MODES` from `magic_box.core.config`)

```python
def test_repo_config_targets_zed_x():
    cam = load_config(ROOT / "config.yaml")["camera"]
    assert (cam["model"], cam["resolution"], cam["image_width"], cam["image_height"]) == (
        "ZED_X", "SVGA", 960, 600,
    )
    assert cam["body_format"] == "BODY_34" and cam["body_fitting"] is True
    assert cam["svo_path"] is None and cam["record_svo"] is None


def test_repo_config_has_perception_tunables():
    p = load_config(ROOT / "config.yaml")["perception"]
    for key in (
        "push_speed_mps", "push_min_travel_m", "push_window_s", "push_rearm_ratio",
        "push_cooldown_s", "motion_window_s", "slot_hold_s", "hands_up_margin_m",
        "hands_together_max_m", "open_retry_s", "max_grab_failures", "stats_every_s",
    ):
        assert key in p, key
    assert "wrist_vz_smoothing" not in p


def test_camera_tables():
    assert CAMERA_MODES["SVGA"] == (960, 600) and CAMERA_MODES["HD1200"] == (1920, 1200)
    assert BODY_FORMATS == ("BODY_18", "BODY_34", "BODY_38")


def test_image_size_must_match_resolution(tmp_path):
    cfg = _base()
    cfg["camera"]["image_width"] = 1280
    with pytest.raises(ConfigError, match=r"camera\.image_width.*SVGA"):
        load_config(_write(tmp_path, cfg))


def test_unknown_resolution_rejected(tmp_path):
    cfg = _base()
    cfg["camera"]["resolution"] = "HD4K"
    with pytest.raises(ConfigError, match=r"camera\.resolution"):
        load_config(_write(tmp_path, cfg))


def test_unknown_body_format_rejected(tmp_path):
    cfg = _base()
    cfg["camera"]["body_format"] = "BODY_70"
    with pytest.raises(ConfigError, match=r"camera\.body_format"):
        load_config(_write(tmp_path, cfg))
```

In `tests/replay/test_fake_input.py`, replace the hard-coded `(720, 1280, 4)` with `(CFG["camera"]["image_height"], CFG["camera"]["image_width"], 4)`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/core/test_config.py -v`
Expected: FAIL. `ImportError` for `CAMERA_MODES`, and the repo config still says HD720.

- [ ] **Step 3: Update `config.yaml`**

Replace the `camera:` and `perception:` sections with these, keeping the owner comments:

```yaml
camera:             # owner: Enoch
  model: ZED_X                # scripts/check_env.py compares the connected camera's model
  resolution: SVGA            # ZED X: SVGA (960x600) | HD1080 | HD1200; image size must match
  image_width: 960
  image_height: 600
  fps: 30
  depth_mode: PERFORMANCE
  body_format: BODY_34        # BODY_18 | BODY_34 | BODY_38 (34 and 38 need body_fitting)
  body_model: HUMAN_BODY_FAST
  body_fitting: true
  detection_confidence: 40
  max_range_m: 3.5            # (guess) depth and bodies beyond this are ignored (bystanders)
  svo_path: null              # play this .svo2 instead of the live camera (Jetson only)
  record_svo: null            # record the live camera to this .svo2 path

perception:         # owner: Enoch
  push_speed_mps: 1.5         # (guess) wrist speed toward the camera, relative to the neck
  push_min_travel_m: 0.12     # (guess) wrist travel toward the camera within the window
  push_window_s: 0.15         # (guess)
  push_rearm_ratio: 0.35      # (guess) re-arm once speed drops below this share of push_speed_mps
  push_cooldown_s: 0.4        # (guess)
  motion_window_s: 0.2        # (guess)
  slot_hold_s: 1.0            # (guess) a lost body keeps its slot this long
  hands_up_margin_m: 0.10     # (guess) wrist above the head by this much
  hands_together_max_m: 0.25  # (guess) wrists closer than this
  open_retry_s: 2.0
  max_grab_failures: 30
  stats_every_s: 5.0
  zones:                      # root Z thresholds, meters (guess)
    danger_max_m: 1.6         # z < this -> danger
    far_min_m: 2.4            # z >= this -> far
```

Append under `render:`:

```yaml
  debug_overlay:    # owner: Enoch
    graph_s: 3.0
    vz_range_mps: 4.0
    push_flash_s: 0.3
    topdown_x_m: 2.0
    topdown_z_m: 4.0
    font_px: 22
    panel_w_px: 420
    graph_h_px: 120
    map_px: 240
    panel_rgba: [0, 0, 0, 170]
    text_rgb: [240, 240, 240]
    slot_rgb: {0: [255, 140, 40], 1: [40, 140, 255]}
    threshold_rgb: [230, 60, 60]
    zone_rgb: {danger: [110, 30, 30], neutral: [70, 70, 40], far: [30, 50, 90]}
```

Change `fake.focal_px` from `700` to `525`, so fake mode looks the same at 960×600.

- [ ] **Step 4: Add camera validation to `src/magic_box/core/config.py`**

- Add `CAMERA_MODES = {"HD2K": (2208, 1242), "HD1200": (1920, 1200), "HD1080": (1920, 1080), "HD720": (1280, 720), "SVGA": (960, 600), "VGA": (672, 376)}` and `BODY_FORMATS = ("BODY_18", "BODY_34", "BODY_38")`.
- Add `_check_camera(cfg, problems)`, called from `validate()`. It skips when `"camera"` is missing. Messages:
  - `f"camera.resolution: unknown mode {res!r} (known: {', '.join(CAMERA_MODES)})"`
  - `f"camera.image_width/image_height: {w}x{h} does not match {res} ({mw}x{mh})"`
  - `f"camera.body_format: must be one of {BODY_FORMATS}, got {fmt!r}"`

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/core tests/replay -v`, then `uv run pytest`
Expected: PASS. The full suite stays green: fake mode, the window and render tests read their size from config.

- [ ] **Step 6: Commit (Daniel runs)**

```bash
git add config.yaml src/magic_box/core/config.py tests/core/test_config.py tests/replay/test_fake_input.py
git commit -m "feat(config): switch camera settings to the zed x and add perception and overlay tunables"
```

---

### Task 2: Plain capture types, ZED keypoint map, windowed velocity

**Files:**
- Create: `src/magic_box/perception/raw.py`, `src/magic_box/perception/keypoints.py`, `src/magic_box/perception/kinematics.py`
- Modify: `src/magic_box/perception/__init__.py` (docstring first line → `"""ZED X perception: camera, body tracking, pushes, poses (perception spec)."""`)
- Create: `tests/perception/__init__.py` (empty), `tests/perception/test_keypoints.py`, `tests/perception/test_kinematics.py`

**Interfaces:**
- Produces (all frozen dataclasses; `Capture` also `eq=False`, like `Frame`):
  - `raw.RawBody(id: int, tracking_ok: bool, confidence: float, position: Vec3, kp3d: dict[str, Vec3], kp2d: dict[str, Px], bbox_px: tuple[int, int, int, int])`
  - `raw.Capture(frame: Frame, bodies: list[RawBody])`
  - `raw.CameraInfo(model: str, serial: int, width: int, height: int, fps: float, sdk_version: str, source: str)`
  - `keypoints.PART_NAMES: dict[str, tuple[str, ...]]`: the SDK's part order per format.
  - `keypoints.SOURCES: dict[str, dict[str, tuple[str, ...]]]`: our name → SDK part names (several parts = mean).
  - `keypoints.part_indices(body_format: str) -> dict[str, tuple[int, ...]]`
  - `keypoints.map_keypoints(body_format: str, kp3d: np.ndarray, kp2d: np.ndarray) -> tuple[dict[str, Vec3], dict[str, Px]]`
  - `kinematics.WindowedVelocity(window_s: float)` with methods:
    - `add(t: float, value: float) -> None`
    - `velocity() -> float`
    - `travel() -> float`
    - `clear() -> None`

- [ ] **Step 1: Write the failing tests**

`tests/perception/test_keypoints.py`:

```python
import math

import numpy as np
import pytest

from magic_box.core.contracts import KEYPOINT_NAMES
from magic_box.perception.keypoints import PART_NAMES, SOURCES, map_keypoints, part_indices


@pytest.mark.parametrize("fmt,n", [("BODY_18", 18), ("BODY_34", 34), ("BODY_38", 38)])
def test_part_tables_cover_every_keypoint(fmt, n):
    assert len(PART_NAMES[fmt]) == n == len(set(PART_NAMES[fmt]))
    assert set(SOURCES[fmt]) == set(KEYPOINT_NAMES) == set(part_indices(fmt))


def test_known_indices():
    b34 = part_indices("BODY_34")  # the beta tracker used these on the device
    assert [b34[k] for k in ("pelvis", "neck", "l_shoulder", "l_wrist", "r_shoulder", "r_wrist", "head")] == [
        (0,), (3,), (5,), (7,), (12,), (14,), (26,),
    ]
    b18 = part_indices("BODY_18")
    assert [b18[k] for k in ("head", "neck", "pelvis", "r_wrist", "l_wrist")] == [
        (0,), (1,), (11, 8), (4,), (7,),
    ]
    b38 = part_indices("BODY_38")
    assert [b38[k] for k in ("head", "neck", "l_wrist", "r_wrist", "l_ankle")] == [
        (5,), (4,), (16,), (17,), (22,),
    ]


def _arrays(n):
    kp3d = np.arange(n * 3, dtype=np.float32).reshape(n, 3) / 10 + 1.0
    kp2d = np.arange(n * 2, dtype=np.float32).reshape(n, 2) + 5.0
    return kp3d, kp2d


def test_map_keypoints_returns_float_tuples_by_name():
    kp3d, kp2d = _arrays(34)
    pts3, pts2 = map_keypoints("BODY_34", kp3d, kp2d)
    assert pts3["neck"] == pytest.approx(tuple(kp3d[3])) and pts2["neck"] == pytest.approx(tuple(kp2d[3]))
    assert all(type(v) is float for v in pts3["neck"] + pts2["neck"])


@pytest.mark.parametrize(
    "bad3,bad2", [((math.nan, 0, 0), None), ((math.inf, 0, 0), None), (None, (-1.0, 5.0))]
)
def test_invalid_points_are_dropped(bad3, bad2):
    kp3d, kp2d = _arrays(34)
    if bad3:
        kp3d[7] = bad3
    if bad2:
        kp2d[7] = bad2
    pts3, pts2 = map_keypoints("BODY_34", kp3d, kp2d)
    assert "l_wrist" not in pts3 and "l_wrist" not in pts2 and "r_wrist" in pts3


def test_body18_pelvis_is_the_hip_mean_and_needs_both_hips():
    kp3d, kp2d = _arrays(18)
    pts3, _ = map_keypoints("BODY_18", kp3d, kp2d)
    assert pts3["pelvis"] == pytest.approx(tuple((kp3d[11] + kp3d[8]) / 2))
    kp3d[8] = (math.nan, 0, 0)
    pts3, pts2 = map_keypoints("BODY_18", kp3d, kp2d)
    assert "pelvis" not in pts3 and "pelvis" not in pts2
```

`tests/perception/test_kinematics.py`:

```python
import pytest

from magic_box.perception.kinematics import WindowedVelocity


def _filled(window_s, samples):
    v = WindowedVelocity(window_s)
    for t, x in samples:
        v.add(t, x)
    return v


def test_velocity_and_travel_over_the_window():
    v = _filled(0.15, [(0.0, 0.0), (0.05, 0.1), (0.1, 0.2)])
    assert v.velocity() == pytest.approx(2.0) and v.travel() == pytest.approx(0.2)


def test_old_samples_leave_the_window():
    v = _filled(0.15, [(0.0, 0.0), (0.06, 0.1), (0.1, 0.2), (0.2, 0.2)])  # t=0 is older than 0.2-0.15
    assert v.travel() == pytest.approx(0.1) and v.velocity() == pytest.approx(0.1 / 0.14)


def test_too_few_samples_or_zero_dt_give_zero():
    v = WindowedVelocity(0.15)
    assert v.velocity() == v.travel() == 0.0
    v.add(1.0, 5.0)
    assert v.velocity() == 0.0
    v.add(1.0, 6.0)
    assert v.velocity() == 0.0


def test_time_going_backwards_restarts_window():  # Review Focus 1: an SVO loop rewinds cam_t
    v = _filled(0.15, [(10.0, 0.0), (10.05, 0.0)])
    v.add(0.0, -1.0)
    assert v.velocity() == 0.0 and v.travel() == 0.0
    v.add(0.05, -1.0)
    assert v.velocity() == 0.0


def test_clear():
    v = _filled(0.15, [(0.0, 0.0), (0.05, 0.1)])
    v.clear()
    assert v.velocity() == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/perception -v`
Expected: FAIL with `ModuleNotFoundError: magic_box.perception.keypoints`.

- [ ] **Step 3: Implement `raw.py` and `kinematics.py`**

`WindowedVelocity`:
- `add` first clears the samples if `t` is earlier than the newest sample (a rewind). It then appends, and drops samples with `sample_t < t - window_s`.
- `velocity()` is `(last_v − first_v) / (last_t − first_t)`, or 0.0 with fewer than two samples or `dt <= 0`.
- `travel()` is `last_v − first_v` (signed), or 0.0 with fewer than two samples.
- Use a `collections.deque`.

- [ ] **Step 4: Implement `keypoints.py`**

`PART_NAMES` is the SDK's documented order. Use these exact tuples:

```python
PART_NAMES = {
    "BODY_18": (
        "NOSE", "NECK", "RIGHT_SHOULDER", "RIGHT_ELBOW", "RIGHT_WRIST", "LEFT_SHOULDER",
        "LEFT_ELBOW", "LEFT_WRIST", "RIGHT_HIP", "RIGHT_KNEE", "RIGHT_ANKLE", "LEFT_HIP",
        "LEFT_KNEE", "LEFT_ANKLE", "RIGHT_EYE", "LEFT_EYE", "RIGHT_EAR", "LEFT_EAR",
    ),
    "BODY_34": (
        "PELVIS", "NAVAL_SPINE", "CHEST_SPINE", "NECK", "LEFT_CLAVICLE", "LEFT_SHOULDER",
        "LEFT_ELBOW", "LEFT_WRIST", "LEFT_HAND", "LEFT_HANDTIP", "LEFT_THUMB", "RIGHT_CLAVICLE",
        "RIGHT_SHOULDER", "RIGHT_ELBOW", "RIGHT_WRIST", "RIGHT_HAND", "RIGHT_HANDTIP",
        "RIGHT_THUMB", "LEFT_HIP", "LEFT_KNEE", "LEFT_ANKLE", "LEFT_FOOT", "RIGHT_HIP",
        "RIGHT_KNEE", "RIGHT_ANKLE", "RIGHT_FOOT", "HEAD", "NOSE", "LEFT_EYE", "LEFT_EAR",
        "RIGHT_EYE", "RIGHT_EAR", "LEFT_HEEL", "RIGHT_HEEL",
    ),
    "BODY_38": (
        "PELVIS", "SPINE_1", "SPINE_2", "SPINE_3", "NECK", "NOSE", "LEFT_EYE", "RIGHT_EYE",
        "LEFT_EAR", "RIGHT_EAR", "LEFT_CLAVICLE", "RIGHT_CLAVICLE", "LEFT_SHOULDER",
        "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP",
        "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_BIG_TOE",
        "RIGHT_BIG_TOE", "LEFT_SMALL_TOE", "RIGHT_SMALL_TOE", "LEFT_HEEL", "RIGHT_HEEL",
        "LEFT_HAND_THUMB_4", "RIGHT_HAND_THUMB_4", "LEFT_HAND_INDEX_1", "RIGHT_HAND_INDEX_1",
        "LEFT_HAND_MIDDLE_4", "RIGHT_HAND_MIDDLE_4", "LEFT_HAND_PINKY_1", "RIGHT_HAND_PINKY_1",
    ),
}
```

`SOURCES` follows the table in spec §8:
- `head`: `NOSE` for 18 and 38, `HEAD` for 34.
- `pelvis`: `("LEFT_HIP", "RIGHT_HIP")` for 18, `PELVIS` otherwise.
- The rest: `NECK`, then `LEFT_`/`RIGHT_` + `SHOULDER` / `WRIST` / `ANKLE`.

`map_keypoints` behavior:
- A part is valid when its 3D and 2D values are all finite and both 2D coordinates are ≥ 0.
- A mapped point is valid only if all its parts are, and it is their mean.
- It returns Python `float` tuples.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/perception -v`, then `uv run pytest`
Expected: PASS.

- [ ] **Step 6: Commit (Daniel runs)**

```bash
git add src/magic_box/perception/__init__.py src/magic_box/perception/raw.py src/magic_box/perception/keypoints.py src/magic_box/perception/kinematics.py tests/perception
git commit -m "feat(perception): add plain capture types, the zed keypoint map and windowed velocity"
```

---

### Task 3: Slot assignment and the simulated-body helper

**Files:**
- Create: `tests/perception/fakes.py`, `tests/perception/test_bodies.py`
- Modify: `src/magic_box/perception/bodies.py` (replace the stub)

**Interfaces:**
- Consumes: `RawBody`, `Capture` (Task 2); `project_point` (`core/geometry.py`).
- Produces:
  - `bodies.filter_bodies(bodies: Sequence[RawBody], max_range_m: float) -> list[RawBody]`. It keeps `tracking_ok` bodies whose position is finite with `0 < z <= max_range_m`, then returns up to two of them, nearest first.
  - `bodies.SlotAssigner(cfg)` has:
    - `assign(bodies: Sequence[RawBody], cam_t: float) -> dict[int, RawBody]`: filters with `camera.max_range_m`, returns slot → body for bound slots present this frame.
    - `bound_id(slot: int) -> int | None`
  - `tests/perception/fakes.py`:
    - `FOCAL_PX`, `SIZE`
    - `body_points(x, z, duck=0.0) -> dict[str, Vec3]`
    - `make_body(...) -> RawBody`
    - `make_capture(...) -> Capture`

- [ ] **Step 1: Write the test helper `tests/perception/fakes.py`**

It is test infrastructure, and its numbers matter to every later test, so write it as given:

```python
"""Simulated ZED bodies and captures for perception tests (no pyzed).

Owner: Enoch
"""

from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from magic_box.core.contracts import Frame, Vec3
from magic_box.core.geometry import project_point
from magic_box.perception.raw import Capture, RawBody

FOCAL_PX = 525.0
SIZE = (960, 600)  # camera.image_width x image_height (SVGA)


def body_points(x: float, z: float, duck: float = 0.0) -> dict[str, Vec3]:
    """A standing person: pelvis at (x, 0, z), +y down, hands out at shoulder height."""
    return {
        "head": (x, -0.75 + duck, z),
        "neck": (x, -0.6 + duck, z),
        "pelvis": (x, 0.0, z),
        "l_shoulder": (x + 0.2, -0.5 + duck, z),
        "r_shoulder": (x - 0.2, -0.5 + duck, z),
        "l_wrist": (x + 0.35, -0.5 + duck, z),
        "r_wrist": (x - 0.35, -0.5 + duck, z),
        "l_ankle": (x + 0.15, 0.9, z),
        "r_ankle": (x - 0.15, 0.9, z),
    }


def make_body(
    id: int = 1,
    x: float = 0.6,
    z: float = 2.0,
    *,
    duck: float = 0.0,
    overrides: Mapping[str, Vec3] | None = None,
    drop: Iterable[str] = (),
    tracking_ok: bool = True,
    position: Vec3 | None = None,
) -> RawBody:
    kp3d = body_points(x, z, duck) | dict(overrides or {})
    kp3d = {k: v for k, v in kp3d.items() if k not in set(drop)}
    w, h = SIZE
    kp2d = {k: project_point(p, FOCAL_PX, FOCAL_PX, w / 2, h / 2) for k, p in kp3d.items()}
    xs = [p[0] for p in kp2d.values()] or [0.0]
    ys = [p[1] for p in kp2d.values()] or [0.0]
    bbox = (int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))
    return RawBody(
        id=id,
        tracking_ok=tracking_ok,
        confidence=80.0,
        position=position or (x, -0.3, z),
        kp3d=kp3d,
        kp2d=kp2d,
        bbox_px=bbox,
    )


def make_capture(bodies: Sequence[RawBody], frame_idx: int = 0, cam_t: float = 0.0) -> Capture:
    w, h = SIZE
    image = np.zeros((h, w, 4), np.uint8)
    return Capture(frame=Frame(frame_idx=frame_idx, cam_t=cam_t, image=image), bodies=list(bodies))
```

- [ ] **Step 2: Write the failing tests** (`tests/perception/test_bodies.py`)

```python
import math
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception.bodies import SlotAssigner, filter_bodies
from tests.perception.fakes import make_body

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
HOLD = CFG["perception"]["slot_hold_s"]


def _ids(result):
    return {slot: body.id for slot, body in result.items()}


def _bound(a, t=0.0):
    a.assign([make_body(7, x=0.6), make_body(9, x=-0.6)], t)
    return a


def test_two_new_bodies_bind_by_image_x():
    assert _ids(SlotAssigner(CFG).assign([make_body(9, x=-0.6), make_body(7, x=0.6)], 0.0)) == {0: 7, 1: 9}


def test_ids_stick_when_players_cross():
    a = _bound(SlotAssigner(CFG))
    assert _ids(a.assign([make_body(7, x=-0.4), make_body(9, x=0.4)], 0.1)) == {0: 7, 1: 9}


@pytest.mark.parametrize("x,slot", [(0.2, 0), (-0.3, 1)])
def test_single_new_body_binds_by_side(x, slot):
    assert _ids(SlotAssigner(CFG).assign([make_body(5, x=x)], 0.0)) == {slot: 5}


def test_lost_id_is_held_then_freed():
    a = _bound(SlotAssigner(CFG))
    assert _ids(a.assign([make_body(9, x=-0.6)], HOLD / 2)) == {1: 9} and a.bound_id(0) == 7
    assert _ids(a.assign([make_body(7, x=0.6), make_body(9, x=-0.6)], HOLD * 0.8)) == {0: 7, 1: 9}
    a.assign([make_body(9, x=-0.6)], HOLD * 0.9 + HOLD + 0.01)
    assert a.bound_id(0) is None


def test_newcomer_takes_the_only_free_slot():
    a = _bound(SlotAssigner(CFG))
    a.assign([make_body(9, x=-0.6)], HOLD + 0.01)  # 7 is freed
    assert _ids(a.assign([make_body(9, x=-0.6), make_body(11, x=-0.2)], HOLD + 0.05)) == {0: 11, 1: 9}


def test_two_newcomers_and_one_free_slot_pick_by_that_side():
    a = SlotAssigner(CFG)
    a.assign([make_body(9, x=-0.6)], 0.0)  # 9 -> slot 1, then disappears (held)
    got = a.assign([make_body(11, x=0.5, z=2.0), make_body(12, x=-0.5, z=2.1)], 0.1)
    assert _ids(got) == {0: 11} and a.bound_id(1) == 9


def test_far_untracked_and_nan_bodies_ignored():  # Review Focus 4
    bodies = [
        make_body(1, z=4.0),
        make_body(2, tracking_ok=False),
        make_body(3, position=(math.nan, 0.0, math.nan)),
        make_body(4, position=(0.1, 0.0, math.inf)),
    ]
    assert SlotAssigner(CFG).assign(bodies, 0.0) == {}


def test_only_the_two_closest_bodies_count():
    bodies = [make_body(1, x=0.6, z=1.8), make_body(2, x=-0.6, z=2.0), make_body(3, x=0.0, z=3.0)]
    assert filter_bodies(bodies, 3.5) == [bodies[0], bodies[1]]
    assert set(_ids(SlotAssigner(CFG).assign(bodies, 0.0)).values()) == {1, 2}


def test_cam_t_rewind_does_not_break_hold():  # Review Focus 1
    a = _bound(SlotAssigner(CFG), t=10.0)
    a.assign([make_body(9, x=-0.6)], 0.5)  # the SVO looped: camera time jumped back
    a.assign([make_body(9, x=-0.6)], 0.5 + HOLD + 0.01)
    assert a.bound_id(0) is None and a.bound_id(1) == 9
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/perception/test_bodies.py -v`
Expected: FAIL with `ImportError: cannot import name 'filter_bodies'`.

- [ ] **Step 4: Implement `filter_bodies` and `SlotAssigner` in `bodies.py`**

Each binding stores `(id, last_seen_cam_t)`. Each `assign` call:
1. Clamp any `last_seen` that is later than `cam_t` down to `cam_t` (a rewind).
2. Refresh the bindings whose id is present.
3. Free the bindings that have been absent for more than `perception.slot_hold_s`.
4. Fill free slots from the unbound present bodies (spec §7.2 rule 3):
   - Both slots free with two newcomers: the larger `position[0]` goes to slot 0.
   - Both free with one newcomer: slot 0 if x ≥ 0, else slot 1.
   - One free slot: slot 0 takes the newcomer with the larger x, slot 1 the one with the smaller x.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/perception -v`, then `uv run pytest`
Expected: PASS.

- [ ] **Step 6: Commit (Daniel runs)**

```bash
git add src/magic_box/perception/bodies.py tests/perception/fakes.py tests/perception/test_bodies.py
git commit -m "feat(perception): assign tracked bodies to player slots"
```

---

### Task 4: Push detector and sideways speed

**Files:**
- Modify: `src/magic_box/perception/push.py`, `src/magic_box/perception/motion.py` (replace the stubs)
- Create: `tests/perception/test_push.py`, `tests/perception/test_motion.py`

**Interfaces:**
- Consumes: `WindowedVelocity` (Task 2).
- Produces (one instance per player slot):
  - `push.PushDetector(cfg)` has:
    - `update(cam_t: float, wrists: Mapping[str, Vec3], wrists_px: Mapping[str, Px], ref_z: float) -> tuple[Push | None, dict[str, float]]`. The second value is `wrist_vz`, always with keys `"L"` and `"R"`.
    - `reset() -> None`
  - `motion.MotionTracker(cfg)` has:
    - `update(root: Vec3, cam_t: float) -> float`, returning `root_vx`
    - `reset() -> None`

- [ ] **Step 1: Write the failing tests**

`tests/perception/test_push.py`:

```python
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception.push import PushDetector

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
P = CFG["perception"]
DT = 1 / 30
PX = {"L": (700.0, 200.0), "R": (540.0, 210.0)}


def _wrists(l_dz=0.0, r_dz=0.0, z=2.0):
    return {"L": (0.95, -0.5, z + l_dz), "R": (0.25, -0.5, z + r_dz)}


def _run(det, frames, ref_z=2.0):
    """frames: (l_dz, r_dz) per camera frame -> [(push, wrist_vz)]."""
    return [det.update(i * DT, _wrists(l, r), PX, ref_z) for i, (l, r) in enumerate(frames)]


def _pushes(out):
    return [p for p, _ in out if p]


def test_fast_push_fires_once():
    out = _run(PushDetector(CFG), [(0.0, -0.1 * i) for i in range(8)] + [(0.0, -0.7)] * 10)
    pushes = _pushes(out)
    assert len(pushes) == 1 and out[2][0] is pushes[0]  # fires once travel passes 0.12 m
    assert pushes[0].hand == "R" and pushes[0].speed == pytest.approx(3.0)
    assert pushes[0].origin_px == PX["R"]


def test_slow_reach_does_not_fire():
    out = _run(PushDetector(CFG), [(0.0, -0.02 * i) for i in range(15)])
    assert not _pushes(out) and out[-1][1]["R"] == pytest.approx(-0.6)


def test_walking_toward_the_camera_does_not_fire():
    det = PushDetector(CFG)
    out = [det.update(i * DT, _wrists(z=2.0 - 0.1 * i), PX, 2.0 - 0.1 * i) for i in range(10)]
    assert not _pushes(out) and out[-1][1] == {"L": 0.0, "R": 0.0}


def test_one_long_push_fires_once_even_past_the_cooldown():
    assert len(_pushes(_run(PushDetector(CFG), [(0.0, -0.1 * i) for i in range(20)]))) == 1


def test_fires_again_after_rearm_and_cooldown():
    frames = [(0.0, -0.1 * i) for i in range(8)] + [(0.0, -0.7)] * 20
    frames += [(0.0, -0.7 - 0.1 * i) for i in range(8)]
    assert len(_pushes(_run(PushDetector(CFG), frames))) == 2


def test_cooldown_spans_both_hands():
    frames = [(0.0, -0.1 * i) for i in range(4)] + [(-0.1 * i, -0.3) for i in range(1, 6)]
    assert [p.hand for p in _pushes(_run(PushDetector(CFG), frames))] == ["R"]


def test_other_hand_fires_after_the_cooldown():
    frames = [(0.0, -0.1 * i) for i in range(4)] + [(0.0, -0.3)] * 12
    frames += [(-0.1 * i, -0.3) for i in range(8)]
    assert [p.hand for p in _pushes(_run(PushDetector(CFG), frames))] == ["R", "L"]


def test_both_hands_on_one_frame_report_the_faster_and_both_disarm():
    out = _run(PushDetector(CFG), [(-0.13 * i, -0.15 * i) for i in range(20)])
    hits = [(p, vz) for p, vz in out if p]
    assert len(hits) == 1
    push, vz = hits[0]
    assert push.hand == "R" and vz["L"] < -P["push_speed_mps"] and vz["R"] < -P["push_speed_mps"]


def test_missing_wrist_adds_no_sample_and_both_keys_present():
    det = PushDetector(CFG)
    push, vz = det.update(0.0, {"L": (0.9, -0.5, 2.0)}, {"L": (700.0, 200.0)}, 2.0)
    assert push is None and vz == {"L": 0.0, "R": 0.0}
    assert det.update(DT, {}, {}, 2.0)[1] == {"L": 0.0, "R": 0.0}


def test_reset_forgets_history():
    det = PushDetector(CFG)
    det.update(0.0, _wrists(), PX, 2.0)
    det.reset()
    assert det.update(DT, _wrists(r_dz=-0.3), PX, 2.0)[0] is None
```

`tests/perception/test_motion.py`:

```python
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception.motion import MotionTracker

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_root_vx_from_root_x_over_the_window():
    m = MotionTracker(CFG)
    assert m.update((0.0, 0.0, 2.0), 0.0) == 0.0
    for i in range(1, 6):
        vx = m.update((0.03 * i, 0.0, 2.0), i / 30)
    assert vx == pytest.approx(0.9)


def test_reset_forgets_history():
    m = MotionTracker(CFG)
    m.update((0.0, 0.0, 2.0), 0.0)
    m.reset()
    assert m.update((0.5, 0.0, 2.0), 1 / 30) == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/perception/test_push.py tests/perception/test_motion.py -v`
Expected: FAIL. The stubs raise `NotImplementedError`, or the signatures don't match.

- [ ] **Step 3: Implement `PushDetector` and `MotionTracker`**

`PushDetector` (spec §7.5):
- Per hand: a `WindowedVelocity(push_window_s)` of `d = wrist_z − ref_z`, plus an `armed` flag (starts `True`). Per player: `last_push_t`, starting at `-inf`.
- On each update, for each hand present: `add(cam_t, d)`, then `v = velocity()`, `travel = −travel()`.
- A hand **qualifies** when all of these hold:
  - it is armed;
  - `−v ≥ push_speed_mps`;
  - `travel ≥ push_min_travel_m`;
  - `cam_t − last_push_t ≥ push_cooldown_s`.
- If any hand qualifies: emit `Push(hand, speed=−v, origin_px=wrists_px[hand])` for the qualifying hand with the larger `−v`. Disarm every qualifying hand and set `last_push_t = cam_t`.
- A disarmed hand re-arms when `−v < push_speed_mps × push_rearm_ratio`.
- `wrist_vz[hand] = v` for each hand (0.0 when absent or with fewer than two samples).
- `reset()` clears both windows, re-arms both hands, and resets `last_push_t`.

`MotionTracker`: a `WindowedVelocity(motion_window_s)` of root x. `update` returns its velocity.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/perception -v`, then `uv run pytest`
Expected: PASS.

- [ ] **Step 5: Commit (Daniel runs)**

```bash
git add src/magic_box/perception/push.py src/magic_box/perception/motion.py tests/perception/test_push.py tests/perception/test_motion.py
git commit -m "feat(perception): detect pushes relative to the torso and compute sideways speed"
```

---

### Task 5: Poses and the player tracker

**Files:**
- Modify: `src/magic_box/perception/poses.py` (replace the stub)
- Create: `src/magic_box/perception/tracker.py`
- Modify: `src/magic_box/core/contracts.py`: field comments only.
- Create: `tests/perception/test_poses.py`, `tests/perception/test_tracker.py`

**Interfaces:**
- Consumes:
  - `SlotAssigner` (Task 3);
  - `PushDetector` and `MotionTracker` (Task 4);
  - `Capture` and `RawBody` (Task 2);
  - `zone_for_distance` (`core/geometry.py`);
  - `make_body`, `make_capture` and `body_points` (`tests/perception/fakes.py`).
- Produces:
  - `poses.detect_poses(kp3d: Mapping[str, Vec3], head: Vec3, perception: Mapping[str, Any]) -> frozenset[str]`
  - `tracker.PlayerTracker(cfg)` has:
    - `step(capture: Capture, now: float) -> list[PlayerState]`, sorted by slot;
    - `bound_ids -> dict[int, int | None]` (property).

- [ ] **Step 1: Write the failing tests**

`tests/perception/test_poses.py`:

```python
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.perception.poses import detect_poses
from tests.perception.fakes import body_points

P = load_config(Path(__file__).resolve().parents[2] / "config.yaml")["perception"]
HEAD = (0.6, -0.75, 2.0)
BASE = body_points(0.6, 2.0)


def test_one_arm_overhead_is_hands_up():
    kp = BASE | {"r_wrist": (0.25, -0.75 - P["hands_up_margin_m"] - 0.01, 2.0)}
    assert detect_poses(kp, HEAD, P) == {"hands_up"}


def test_wrist_inside_the_margin_is_not_hands_up():
    kp = BASE | {"r_wrist": (0.25, -0.75 - P["hands_up_margin_m"] + 0.02, 2.0)}
    assert detect_poses(kp, HEAD, P) == frozenset()


def test_hands_together_at_the_chest():
    kp = BASE | {"l_wrist": (0.7, -0.4, 1.8), "r_wrist": (0.55, -0.4, 1.8)}
    assert detect_poses(kp, HEAD, P) == {"hands_together"}


def test_hands_together_needs_both_wrists_between_head_and_pelvis():
    overhead = BASE | {"l_wrist": (0.65, -0.9, 2.0), "r_wrist": (0.55, -0.9, 2.0)}
    low = BASE | {"l_wrist": (0.65, 0.1, 2.0), "r_wrist": (0.55, 0.1, 2.0)}
    one = {k: v for k, v in BASE.items() if k != "r_wrist"} | {"l_wrist": (0.6, -0.4, 2.0)}
    assert "hands_together" not in detect_poses(overhead, HEAD, P)
    assert detect_poses(low, HEAD, P) == frozenset()
    assert detect_poses(one, HEAD, P) == frozenset()


def test_without_a_pelvis_only_the_head_bounds_hands_together():
    kp = {k: v for k, v in BASE.items() if k != "pelvis"}
    kp |= {"l_wrist": (0.65, 0.1, 2.0), "r_wrist": (0.55, 0.1, 2.0)}
    assert detect_poses(kp, HEAD, P) == {"hands_together"}
```

`tests/perception/test_tracker.py`:

```python
import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception.tracker import PlayerTracker
from tests.perception.fakes import make_body, make_capture

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def _one(body, **kw):
    return PlayerTracker(CFG).step(make_capture([body], **kw), 0.0)[0]


def test_two_bodies_give_two_states_in_slot_order():
    b7, b9 = make_body(7, x=0.6), make_body(9, x=-0.6)
    states = PlayerTracker(CFG).step(make_capture([b9, b7], frame_idx=4, cam_t=1.5), now=100.0)
    assert [s.slot for s in states] == [0, 1] and [s.player_id for s in states] == [7, 9]
    s = states[0]
    assert s.tracking_ok and (s.t, s.cam_t, s.frame_idx) == (100.0, 1.5, 4)
    assert s.root == b7.kp3d["pelvis"] and s.head == b7.kp3d["head"]
    assert s.wrists == {"L": b7.kp3d["l_wrist"], "R": b7.kp3d["r_wrist"]}
    assert s.zone == "neutral" and s.push is None and s.pose_flags == frozenset()
    assert s.bbox_px == b7.bbox_px and s.keypoints_px == b7.kp2d
    assert s.finger_gesture == {"L": None, "R": None} and s.wrist_vz == {"L": 0.0, "R": 0.0}


def test_partial_body_still_tracked():  # Review Focus 3: legs and pelvis out of frame
    b = make_body(7, x=0.3, z=1.0, drop=("pelvis", "l_ankle", "r_ankle", "head"))
    s = _one(b)
    assert s.tracking_ok and s.root == b.position and s.head == b.kp3d["neck"]
    assert "pelvis" not in s.keypoints_px and s.zone == "danger"


def test_wrists_hold_only_valid_points():
    s = _one(make_body(7, drop=("l_wrist",)))
    assert set(s.wrists) == {"R"} and set(s.wrist_vz) == {"L", "R"}


@pytest.mark.parametrize("z,zone", [(1.2, "danger"), (2.0, "neutral"), (3.0, "far")])
def test_zone_from_root_depth(z, zone):
    assert _one(make_body(7, z=z)).zone == zone


def test_hands_up_flag_flows_through():
    assert "hands_up" in _one(make_body(7, overrides={"r_wrist": (0.25, -1.0, 2.0)})).pose_flags


def _punch(tracker, n=8, drop=()):
    """Slot 0 punches its right wrist toward the camera at 3 m/s."""
    out = []
    for i in range(n):
        b = make_body(7, x=0.6, overrides={"r_wrist": (0.25, -0.5, 2.0 - 0.1 * i)}, drop=drop)
        out += tracker.step(make_capture([b], frame_idx=i, cam_t=i / 30), now=float(i))
    return [s.push for s in out if s.push]


def test_push_reaches_the_player_state():
    pushes = _punch(PlayerTracker(CFG))
    assert len(pushes) == 1 and pushes[0].hand == "R" and pushes[0].speed == pytest.approx(3.0)


def test_missing_neck_uses_root_for_push():
    assert len(_punch(PlayerTracker(CFG), drop=("neck",))) == 1


def test_reference_switch_does_not_fire_push():  # Review Focus 2: the neck flickers
    tracker, out = PlayerTracker(CFG), []
    for i in range(12):
        b = make_body(
            7, x=0.6, overrides={"neck": (0.6, -0.6, 1.85)}, drop=("neck",) if i % 2 else ()
        )  # the neck reads 15 cm closer than the pelvis
        out += tracker.step(make_capture([b], frame_idx=i, cam_t=i / 30), now=float(i))
    assert not any(s.push for s in out)


def test_lost_player_is_republished_untracked():
    tracker = PlayerTracker(CFG)
    tracker.step(make_capture([make_body(7, x=0.6), make_body(9, x=-0.6)]), 0.0)
    states = tracker.step(make_capture([make_body(9, x=-0.6)], frame_idx=1, cam_t=1 / 30), 1.0)
    lost = states[0]
    assert [s.slot for s in states] == [0, 1] and not lost.tracking_ok and states[1].tracking_ok
    assert (lost.t, lost.frame_idx, lost.push, lost.root_vx, lost.player_id) == (1.0, 1, None, 0.0, 7)
    assert lost.wrist_vz == {"L": 0.0, "R": 0.0}


def test_a_slot_never_seen_publishes_nothing():
    assert [s.slot for s in PlayerTracker(CFG).step(make_capture([make_body(9, x=-0.6)]), 0.0)] == [1]


def test_new_id_in_a_slot_starts_fresh_history():
    cfg = copy.deepcopy(CFG)
    cfg["perception"]["slot_hold_s"] = 0.0
    tracker = PlayerTracker(cfg)
    tracker.step(make_capture([make_body(7, x=0.6)]), 0.0)
    b8 = make_body(8, x=0.6, overrides={"r_wrist": (0.25, -0.5, 1.7)})  # a different person
    s = tracker.step(make_capture([b8], frame_idx=1, cam_t=1 / 30), 1.0)[0]
    assert s.player_id == 8 and s.push is None


def test_bound_ids():
    tracker = PlayerTracker(CFG)
    tracker.step(make_capture([make_body(7, x=0.6)]), 0.0)
    assert tracker.bound_ids == {0: 7, 1: None}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/perception/test_poses.py tests/perception/test_tracker.py -v`
Expected: FAIL with `ModuleNotFoundError: magic_box.perception.tracker`.

- [ ] **Step 3: Implement `detect_poses`** (spec §7.6; IMAGE coordinates, so +y is down)

- `hands_up`: any present wrist with `y < head[1] − hands_up_margin_m`.
- `hands_together`: requires all of these:
  - both wrists present;
  - Euclidean distance `< hands_together_max_m`;
  - both wrists `y > head[1]`;
  - if `pelvis` is present, both wrists `y < pelvis[1]`.

- [ ] **Step 4: Implement `PlayerTracker` in `tracker.py`** (spec §7.1–§7.8)

- It holds one `SlotAssigner`. Per slot it holds:
  - a `PushDetector` and a `MotionTracker`;
  - the last processed body id;
  - the last push reference kind (`"neck"` or `"root"`);
  - the last published `PlayerState`.
- For each bound slot with a body this frame:
  - If the id changed: reset that slot's push and motion.
  - Pick the reference: `neck` z when `neck` is present, else root z. If the reference kind changed since the last frame: reset that slot's push (Review Focus 2).
  - Compute:
    - root: `pelvis`, else `position`;
    - head: `head`, else `neck`, else root;
    - wrists: the present `l_wrist` → `"L"` and `r_wrist` → `"R"`;
    - `root_vx`, push and `wrist_vz`, poses, zone.
  - Build the `PlayerState`. `wrists_px` for the push comes from `kp2d` (`l_wrist`/`r_wrist`).
- For each slot without a body this frame that has a last state, publish `dataclasses.replace(last, tracking_ok=False, push=None, root_vx=0.0, wrist_vz={"L": 0.0, "R": 0.0}, t=now, cam_t=..., frame_idx=...)`.

- [ ] **Step 5: Add field comments in `core/contracts.py`** (comments only; types unchanged)

- `Push.speed`: `# m/s toward the camera relative to the torso (positive number)`
- `PlayerState.player_id`: `# ZED tracking id (fake mode: slot + 1)`
- `PlayerState.wrists`: `# "L"/"R" (person's own), valid points only: read with .get()`
- `PlayerState.wrist_vz`: `# m/s relative to the neck, negative toward the camera; both keys always`
- `PlayerState.keypoints_px`: `# valid points only`

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/perception -v`, then `uv run pytest`
Expected: PASS.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add src/magic_box/perception/poses.py src/magic_box/perception/tracker.py src/magic_box/core/contracts.py tests/perception/test_poses.py tests/perception/test_tracker.py
git commit -m "feat(perception): build player states with poses, zones and push events"
```

---

### Task 6: ZED X camera wrapper

**Files:**
- Modify: `src/magic_box/perception/zed_source.py` (replace the stub; docstring first line → `"""ZED X camera source, live or SVO playback (perception spec §8)."""`)
- Create: `tests/perception/fake_sl.py`, `tests/perception/test_zed_source.py`

**Interfaces:**
- Consumes:
  - `Capture`, `RawBody` and `CameraInfo` (Task 2);
  - `PART_NAMES`, `part_indices` and `map_keypoints` (Task 2);
  - `Frame` (contracts).
- Produces:
  - `class CameraError(Exception)`: opening failed in a way worth retrying.
  - `OPEN_HINT = "ZED X not detected? Run \`sudo systemctl restart zed_x_daemon\`, or reboot with the camera plugged in."`
  - `grab_succeeded(status, success) -> bool`
  - `bbox_from_corners(corners) -> tuple[int, int, int, int]`
  - `check_part_indices(body_format: str, parts_enum) -> None`
  - `ZedSource(cfg)` has:
    - properties `is_open: bool` and `info: CameraInfo | None`;
    - `open() -> None`, `grab() -> Capture | None`, `close() -> None`.
  - `tests/perception/fake_sl.py`: `make_fake_sl() -> types.ModuleType`, `install_fake_sl(monkeypatch) -> types.ModuleType`, and `fake_body(...)`.

**SDK calls `ZedSource` makes** (exact `pyzed.sl` names; `sl` is imported inside methods):

| Step | Calls |
|---|---|
| import | `import pyzed.sl as sl`. An `ImportError` becomes `RuntimeError("pyzed is not installed: live mode needs the ZED SDK (use --fake on a laptop)")` (fatal). |
| init | `sl.InitParameters()`, setting:<br>- `.camera_resolution = getattr(sl.RESOLUTION, cam["resolution"])`<br>- `.camera_fps`<br>- `.depth_mode = getattr(sl.DEPTH_MODE, cam["depth_mode"])`<br>- `.coordinate_units = sl.UNIT.METER`<br>- `.coordinate_system = sl.COORDINATE_SYSTEM.IMAGE`<br>- `.depth_maximum_distance = cam["max_range_m"]`<br><br>When `svo_path` is set: `.set_from_svo_file(path)` and `.svo_real_time_mode = True`. |
| open | `zed = sl.Camera()`, then `zed.open(init)`. A result other than `sl.ERROR_CODE.SUCCESS` raises `CameraError(f"ZED open failed: {status}. {OPEN_HINT}")`. |
| info | `zed.get_camera_information()`:<br>- `.camera_model`: use `.name` if present, else `str()`<br>- `.serial_number`<br>- `.camera_configuration.resolution.width/.height`<br>- `.camera_configuration.fps`<br><br>Plus `sl.Camera.get_sdk_version()`. The size must equal `image_width`×`image_height`, else close and raise `RuntimeError(f"camera opened at {w}x{h} but config expects {cw}x{ch} (camera.resolution {res})")`. |
| parts | `check_part_indices(fmt, getattr(sl, f"{fmt}_PARTS"))`. On a mismatch, close and re-raise. |
| record | When `record_svo` is set: `zed.enable_recording(sl.RecordingParameters(path, sl.SVO_COMPRESSION_MODE.H264))`. A result other than `SUCCESS` closes and raises `RuntimeError`. |
| tracking | `p = sl.PositionalTrackingParameters()`, `p.set_as_static = True`, `zed.enable_positional_tracking(p)`. A result other than `SUCCESS` raises `CameraError`. |
| bodies | `sl.BodyTrackingParameters()`, setting:<br>- `.enable_tracking = True`<br>- `.enable_body_fitting = cam["body_fitting"]`<br>- `.detection_model = getattr(sl.BODY_TRACKING_MODEL, cam["body_model"])`<br>- `.body_format = getattr(sl.BODY_FORMAT, fmt)`<br>- `.max_range = cam["max_range_m"]`<br><br>Then `zed.enable_body_tracking(p)`; a result other than `SUCCESS` closes and raises `CameraError`. Runtime: `sl.BodyTrackingRuntimeParameters()` with `.detection_confidence_threshold = cam["detection_confidence"]`. |
| runtime | `sl.RuntimeParameters()` with `.measure3D_reference_frame = sl.REFERENCE_FRAME.CAMERA` |
| grab | `status = zed.grab(runtime)`:<br>- `sl.ERROR_CODE.END_OF_SVOFILE_REACHED`: `zed.set_svo_position(0)`, return `None`.<br>- Not `grab_succeeded(status, sl.ERROR_CODE.SUCCESS)`: return `None`. |
| retrieve | `zed.retrieve_bodies(bodies, body_runtime)` (with `bodies = sl.Bodies()`) and `zed.retrieve_image(mat, sl.VIEW.LEFT)` (with `mat = sl.Mat()`); `mat.get_data()` is H×W×4 uint8. `cam_t = zed.get_timestamp(sl.TIME_REFERENCE.IMAGE).get_nanoseconds() / 1e9`. |
| per body | From `bodies.body_list`:<br>- `.id`<br>- `.tracking_state == sl.OBJECT_TRACKING_STATE.OK`<br>- `.confidence`<br>- `.position` (3)<br>- `.keypoint` (N×3), `.keypoint_2d` (N×2)<br>- `.bounding_box_2d` (4×2) |
| close | `zed.disable_recording()` if recording, then `zed.close()`. Idempotent. |

`frame_idx` is a counter on the `ZedSource` instance. It starts at 0 and keeps counting across `close()` and `open()`.

- [ ] **Step 1: Write the fake SDK module `tests/perception/fake_sl.py`** (`Owner: Enoch`)

`make_fake_sl()` builds a fresh `types.ModuleType("pyzed.sl")` on each call, so per-test knobs never leak. It provides:
- **Enums** (`enum.Enum`, members named as used above):
  - `RESOLUTION`: `SVGA`, `HD1080`, `HD1200`
  - `DEPTH_MODE`: `PERFORMANCE`
  - `UNIT`: `METER`
  - `COORDINATE_SYSTEM`: `IMAGE`
  - `BODY_FORMAT`: `BODY_18`, `BODY_34`, `BODY_38`
  - `BODY_TRACKING_MODEL`: `HUMAN_BODY_FAST`
  - `REFERENCE_FRAME`: `CAMERA`
  - `VIEW`: `LEFT`
  - `TIME_REFERENCE`: `IMAGE`
  - `SVO_COMPRESSION_MODE`: `H264`
  - `OBJECT_TRACKING_STATE`: `OK`, `SEARCHING`
  - `MODEL`: `ZED2`, `ZED_X`
  - `CAMERA_STATE`: `AVAILABLE`
- `ERROR_CODE` as an `IntEnum`: `CORRUPTED_FRAME = -1` (a warning), `SUCCESS = 0`, `CAMERA_NOT_DETECTED = 1`, `END_OF_SVOFILE_REACHED = 2`, `FAILURE = 3`.
- `BODY_18_PARTS`, `BODY_34_PARTS` and `BODY_38_PARTS`: `Enum`s built from `keypoints.PART_NAMES` (value = index).
- **Attribute bags**: `InitParameters` (its `set_from_svo_file(path)` stores `svo_file`), `RuntimeParameters`, `PositionalTrackingParameters`, `BodyTrackingParameters`, `BodyTrackingRuntimeParameters`, `RecordingParameters(video_filename, compression_mode)`.
- `Mat`, whose `get_data()` returns the camera's image.
- `Bodies`, with a `body_list`.
- `Camera`, with class-level knobs and their defaults:
  - `open_status = SUCCESS`
  - `resolution = (960, 600)`, `model = MODEL.ZED_X`, `serial = 4242`, `fps = 30.0`
  - `grab_statuses = []`: consumed per grab; `SUCCESS` when empty.
  - `bodies = []`, `timestamp_ns = 12_500_000_000`
  - `devices = []`
  - `last`: the latest instance.

  Each instance records `init`, `positional`, `body_params`, `runtime`, `body_runtime`, `recording`, `svo_positions` (a list) and `closed`. The static methods are `get_sdk_version() -> "5.0.0"` and `get_device_list() -> Camera.devices`.
- `device(model_name: str, serial: int)` returns `SimpleNamespace(camera_model=MODEL[model_name], serial_number=serial, camera_state=CAMERA_STATE.AVAILABLE)`.

`fake_body(id, *, ok=True, x=0.5, z=2.0)` returns a `SimpleNamespace`:
- `id`, `confidence = 80.0`
- `tracking_state`: `OK` or `SEARCHING`
- `position = np.array([x, -0.3, z])`
- `keypoint`: a 34×3 NaN array with `body_points(x, z)` written at `part_indices("BODY_34")`
- `keypoint_2d`: 34×2, those points projected with `FOCAL_PX` (NaN elsewhere)
- `bounding_box_2d`: 4×2 corners

`install_fake_sl(monkeypatch)` builds the module, creates `pkg = types.ModuleType("pyzed")`, sets `pkg.sl = sl`, `monkeypatch.setitem`s both `sys.modules["pyzed"]` and `sys.modules["pyzed.sl"]`, and returns `sl`.

- [ ] **Step 2: Write the failing tests** (`tests/perception/test_zed_source.py`)

```python
import copy
import sys
from enum import Enum, IntEnum
from pathlib import Path

import numpy as np
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import KEYPOINT_NAMES
from magic_box.perception.keypoints import PART_NAMES
from magic_box.perception.raw import CameraInfo
from magic_box.perception.zed_source import (
    CameraError, ZedSource, bbox_from_corners, check_part_indices, grab_succeeded,
)
from tests.perception.fake_sl import fake_body, install_fake_sl
from tests.perception.fakes import body_points

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


@pytest.fixture
def sl(monkeypatch):
    return install_fake_sl(monkeypatch)


def test_grab_succeeded_orders_or_falls_back():
    E = IntEnum("E", {"WARN": -1, "SUCCESS": 0, "FAIL": 1})
    assert grab_succeeded(E.WARN, E.SUCCESS) and grab_succeeded(E.SUCCESS, E.SUCCESS)
    assert not grab_succeeded(E.FAIL, E.SUCCESS)
    ok, bad = object(), object()  # SDK 4 enums: no ordering
    assert grab_succeeded(ok, ok) and not grab_succeeded(bad, ok)


def test_bbox_from_corners():
    assert bbox_from_corners([[10, 20], [110, 20], [110, 220], [10, 220]]) == (10, 20, 100, 200)
    corners = np.array([[110.6, 220.2], [10.0, 20.9], [110, 20], [10, 220]])
    assert bbox_from_corners(corners) == (10, 20, 100, 200)


def test_check_part_indices():
    names = list(PART_NAMES["BODY_34"])
    check_part_indices("BODY_34", Enum("BODY_34_PARTS", {n: i for i, n in enumerate(names)}))
    names[3], names[5] = names[5], names[3]
    with pytest.raises(RuntimeError, match="BODY_34"):
        check_part_indices("BODY_34", Enum("BODY_34_PARTS", {n: i for i, n in enumerate(names)}))


def test_open_configures_the_zed_x(sl):
    src = ZedSource(CFG)
    src.open()
    cam = sl.Camera.last
    assert (cam.init.camera_resolution, cam.init.camera_fps) == (sl.RESOLUTION.SVGA, 30)
    assert cam.init.coordinate_units == sl.UNIT.METER
    assert cam.init.coordinate_system == sl.COORDINATE_SYSTEM.IMAGE
    assert cam.init.depth_maximum_distance == CFG["camera"]["max_range_m"]
    assert cam.positional.set_as_static is True
    bp = cam.body_params
    assert (bp.body_format, bp.detection_model, bp.enable_tracking, bp.enable_body_fitting) == (
        sl.BODY_FORMAT.BODY_34, sl.BODY_TRACKING_MODEL.HUMAN_BODY_FAST, True, True,
    )
    assert bp.max_range == CFG["camera"]["max_range_m"]
    assert src.is_open and src.info == CameraInfo("ZED_X", 4242, 960, 600, 30.0, "5.0.0", "live")


def test_open_failure_raises_camera_error_with_the_daemon_hint(sl):
    sl.Camera.open_status = sl.ERROR_CODE.CAMERA_NOT_DETECTED
    with pytest.raises(CameraError, match="zed_x_daemon"):
        ZedSource(CFG).open()


def test_resolution_mismatch_is_fatal(sl):
    sl.Camera.resolution = (1920, 1200)
    src = ZedSource(CFG)
    with pytest.raises(RuntimeError, match="960x600") as err:
        src.open()
    assert not isinstance(err.value, CameraError)
    assert sl.Camera.last.closed and not src.is_open


def test_missing_pyzed_is_a_clear_fatal_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyzed", None)
    with pytest.raises(RuntimeError, match="--fake"):
        ZedSource(CFG).open()


def test_grab_converts_bodies_and_frame(sl):
    sl.Camera.bodies = [fake_body(7, ok=True), fake_body(8, ok=False, x=-0.5)]
    src = ZedSource(CFG)
    src.open()
    cap = src.grab()
    assert cap.frame.image.shape == (600, 960, 4) and cap.frame.frame_idx == 0
    assert cap.frame.cam_t == pytest.approx(12.5)
    b = cap.bodies[0]
    assert (b.id, b.tracking_ok, b.position) == (7, True, pytest.approx((0.5, -0.3, 2.0)))
    assert set(b.kp3d) == set(KEYPOINT_NAMES)
    assert b.kp3d["neck"] == pytest.approx(body_points(0.5, 2.0)["neck"])
    assert cap.bodies[1].tracking_ok is False
    assert sl.Camera.last.runtime.measure3D_reference_frame == sl.REFERENCE_FRAME.CAMERA
    assert sl.Camera.last.body_runtime.detection_confidence_threshold == 40
    assert src.grab().frame.frame_idx == 1


def test_warnings_pass_and_failures_return_none(sl):
    sl.Camera.grab_statuses = [sl.ERROR_CODE.CORRUPTED_FRAME, sl.ERROR_CODE.FAILURE]
    src = ZedSource(CFG)
    src.open()
    assert src.grab() is not None and src.grab() is None


def test_svo_end_rewinds(sl):
    sl.Camera.grab_statuses = [sl.ERROR_CODE.END_OF_SVOFILE_REACHED]
    src = ZedSource(CFG)
    src.open()
    assert src.grab() is None and sl.Camera.last.svo_positions == [0]


def test_svo_playback_and_recording(sl, tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["camera"]["svo_path"] = "in.svo2"
    cfg["camera"]["record_svo"] = str(tmp_path / "out.svo2")
    src = ZedSource(cfg)
    src.open()
    cam = sl.Camera.last
    assert cam.init.svo_file == "in.svo2" and cam.init.svo_real_time_mode is True
    assert src.info.source == "in.svo2"
    assert cam.recording.video_filename == str(tmp_path / "out.svo2")


def test_close_is_idempotent_and_reopen_keeps_counting(sl):
    src = ZedSource(CFG)
    src.open()
    src.grab()
    src.close()
    src.close()
    assert not src.is_open
    src.open()
    assert src.grab().frame.frame_idx == 1
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/perception/test_zed_source.py -v`
Expected: FAIL with `ImportError: cannot import name 'CameraError'`.

- [ ] **Step 4: Implement `zed_source.py`** following the SDK table above

- `grab_succeeded`: try `status <= success`; on `TypeError`, fall back to `status == success`.
- `bbox_from_corners`: `(int(min x), int(min y), int(max x − min x), int(max y − min y))`.
- `check_part_indices`: raises `RuntimeError(f"{body_format}: SDK part {name} is index {sdk}, keypoints.py says {ours}")` on the first mismatch.
- Conversion: `map_keypoints(fmt, np.asarray(body.keypoint), np.asarray(body.keypoint_2d))`, `bbox_from_corners(body.bounding_box_2d)`, and a position of three Python floats.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/perception -v`, `uv run pytest tests/test_boundaries.py -v` (no top-level `pyzed`), then `uv run pytest`
Expected: PASS.

- [ ] **Step 6: Commit (Daniel runs)**

```bash
git add src/magic_box/perception/zed_source.py tests/perception/fake_sl.py tests/perception/test_zed_source.py
git commit -m "feat(perception): wrap the zed x camera behind a plain capture source"
```

---

### Task 7: Perception loop

**Files:**
- Modify: `src/magic_box/perception/process.py` (replace the stub)
- Modify: `tests/perception/fakes.py` (add `FakeStop`, `FakeSource`, `FakeBus`, `ListQueue`)
- Create: `tests/perception/test_process.py`

**Interfaces:**
- Consumes:
  - `ZedSource` and `CameraError` (Task 6);
  - `PlayerTracker` (Task 5);
  - `FrameBus.attach(name, w, h)` (`pipeline/frame_bus.py`);
  - `DropOldestQueue.put` (`pipeline/streams.py`).
- Produces:
  - `log_line(msg: str) -> None`: prints `perception: {msg}` to stderr.
  - `run_loop(source, tracker, write_frame: Callable[[Frame], None], put_state: Callable[[PlayerState], None], stop, cfg: Config, clock: Callable[[], float] = time.monotonic, log: Callable[[str], None] = log_line) -> None`
  - `run(cfg, state_q, frame_bus_name, stop) -> None`: signature unchanged, since the supervisor spawns it. `ZedSource` and `FrameBus` are module-level names in `process.py`, so tests can monkeypatch them.

- [ ] **Step 1: Add the fakes to `tests/perception/fakes.py`**

- **`FakeStop`:**
  - `is_set()` and `set()`;
  - `wait(timeout)` appends `timeout` to `self.waits` and returns `is_set()`, so it never sleeps.
- **`FakeSource(stop, grabs, opens=())`**, a scripted camera:
  - **`open()`**:
    - increments `open_calls`;
    - pops the next item from `opens`, treating an exhausted list as `None`;
    - raises the item if it is an exception, else sets `is_open = True`.
  - **`grab()`**: pops the next item from `grabs`. When `grabs` is empty, it calls `stop.set()` and returns `None`.
  - **`close()`**: increments `close_calls` and sets `is_open = False`.
  - **`info`** is `CameraInfo("ZED_X", 1, 960, 600, 30.0, "5.0.0", "fake")`.
- **`FakeBus`**, standing in for `FrameBus`:
  - class attribute `instances: list`;
  - `attach(cls, name, width, height)` classmethod: makes an instance with `name`, `size = (width, height)`, `frames = []` and `closed = False`, and appends it to `instances`;
  - `write(frame)` appends to `frames`; `close()` sets `closed`.
- **`ListQueue`**: `put(item)` appends to `items`.

- [ ] **Step 2: Write the failing tests** (`tests/perception/test_process.py`)

```python
import copy
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.perception import process
from magic_box.perception.process import run_loop
from magic_box.perception.tracker import PlayerTracker
from magic_box.perception.zed_source import CameraError
from tests.perception.fakes import (
    FakeBus, FakeSource, FakeStop, ListQueue, make_body, make_capture,
)

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
RETRY = CFG["perception"]["open_retry_s"]


def _cfg(**perception):
    cfg = copy.deepcopy(CFG)
    cfg["perception"].update(perception)
    return cfg


def _loop(src, stop, cfg=CFG, tracker=None, logs=None, clock=None):
    events = []
    kw = {"clock": clock} if clock else {}
    run_loop(
        src,
        tracker or PlayerTracker(cfg),
        lambda f: events.append(("frame", f.frame_idx)),
        lambda s: events.append(("state", s.slot)),
        stop,
        cfg,
        log=(logs.append if logs is not None else lambda m: None),
        **kw,
    )
    return events


def test_frame_is_written_before_its_states():
    stop = FakeStop()
    cap = make_capture([make_body(7, x=0.6), make_body(9, x=-0.6)], frame_idx=3)
    assert _loop(FakeSource(stop, [cap]), stop) == [("frame", 3), ("state", 0), ("state", 1)]


def test_open_retries_after_camera_error():
    stop, logs = FakeStop(), []
    src = FakeSource(stop, [make_capture([])], opens=[CameraError("not detected")] * 2 + [None])
    _loop(src, stop, logs=logs)
    assert src.open_calls == 3 and stop.waits == [RETRY, RETRY]
    assert sum("not detected" in m for m in logs) == 2
    assert any(m.startswith("opened ZED_X serial 1 960x600@30") for m in logs)


def test_reopens_after_max_grab_failures():
    stop = FakeStop()
    src = FakeSource(stop, [None, None, None, make_capture([], frame_idx=1)])
    assert _loop(src, stop, cfg=_cfg(max_grab_failures=3)) == [("frame", 1)]
    assert (src.open_calls, src.close_calls) == (2, 1)


def test_failure_count_resets_after_a_good_grab():
    stop = FakeStop()
    grabs = [None, None, make_capture([]), None, None, make_capture([], frame_idx=1)]
    src = FakeSource(stop, grabs)
    _loop(src, stop, cfg=_cfg(max_grab_failures=3))
    assert (src.open_calls, src.close_calls) == (1, 0)


def test_camera_lost_mid_run_retries_until_back():  # Review Focus 5
    stop = FakeStop()
    grabs = [make_capture([]), None, None, make_capture([], frame_idx=1)]
    src = FakeSource(stop, grabs, opens=[None, CameraError("gone"), CameraError("gone"), None])
    assert _loop(src, stop, cfg=_cfg(max_grab_failures=2)) == [("frame", 0), ("frame", 1)]
    assert src.open_calls == 4 and stop.waits == [RETRY, RETRY]


def test_returns_at_once_when_stop_is_set():
    stop = FakeStop()
    stop.set()
    src = FakeSource(stop, [make_capture([])])
    assert _loop(src, stop) == [] and src.open_calls == 0


def test_tracker_errors_propagate():
    class Boom:
        bound_ids = {0: None, 1: None}

        def step(self, capture, now):
            raise ValueError("bug")

    stop = FakeStop()
    with pytest.raises(ValueError):
        _loop(FakeSource(stop, [make_capture([])]), stop, tracker=Boom())


def test_logs_stats_every_period():
    stop, logs = FakeStop(), []
    caps = [make_capture([make_body(7, x=0.6)], frame_idx=i, cam_t=i / 30) for i in range(60)]
    times = iter([i / 10 for i in range(60)])
    _loop(FakeSource(stop, caps), stop, logs=logs, clock=lambda: next(times))
    assert "10.0 fps, 1 bodies, P1=7 P2=-" in logs


def test_run_wires_camera_tracker_bus_and_queue(monkeypatch):
    stop = FakeStop()
    src = FakeSource(stop, [make_capture([make_body(7, x=0.6)])])
    monkeypatch.setattr(process, "ZedSource", lambda cfg: src)
    monkeypatch.setattr(process, "FrameBus", FakeBus)
    q = ListQueue()
    process.run(CFG, q, "bus-name", stop)
    bus = FakeBus.instances[-1]
    assert (bus.name, bus.size, bus.closed) == ("bus-name", (960, 600), True)
    assert [f.frame_idx for f in bus.frames] == [0] and [s.slot for s in q.items] == [0]
    assert src.close_calls >= 1
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/perception/test_process.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_loop'`.

- [ ] **Step 4: Implement `run_loop` and `run` in `process.py`** (spec §9)

`run_loop`, in order, until `stop.is_set()`:
1. If `not source.is_open`:
   - Try `source.open()`.
   - On `CameraError as err`: log `f"camera open failed: {err}; retrying in {retry:g} s"`, call `stop.wait(open_retry_s)`, and `continue`.
   - On success: log `f"opened {i.model} serial {i.serial} {i.width}x{i.height}@{i.fps:g} SDK {i.sdk_version} ({i.source})"`.
2. `capture = source.grab()`. On `None`:
   - Increment the failure count.
   - When it reaches `max_grab_failures`: log `f"{n} grab failures in a row; reopening the camera"`, call `source.close()`, and reset the count.
   - `continue`.
3. On a capture:
   - Reset the count and set `now = clock()` (exactly one `clock()` call per capture).
   - `write_frame(capture.frame)`, then `put_state(s)` for each state of `tracker.step(capture, now)`.
4. Stats:
   - The first capture's `now` is the reference.
   - Count captures after it. When `now − ref ≥ stats_every_s`, log `f"{frames / (now - ref):.1f} fps, {len(capture.bodies)} bodies, P1={id or '-'} P2={id or '-'}"` (ids from `tracker.bound_ids`).
   - Then reset the reference to `now` and the count to 0.

Any other exception propagates.

`run`: `bus = FrameBus.attach(frame_bus_name, cam["image_width"], cam["image_height"])`, `source = ZedSource(cfg)`, then `run_loop(source, PlayerTracker(cfg), bus.write, state_q.put, stop, cfg)` inside `try` / `finally: source.close(); bus.close()`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/perception -v`, then `uv run pytest`
Expected: PASS. `tests/pipeline/test_processes.py` still passes: it never spawns the real perception target.

- [ ] **Step 6: Commit (Daniel runs)**

```bash
git add src/magic_box/perception/process.py tests/perception/fakes.py tests/perception/test_process.py
git commit -m "feat(perception): run the perception loop with camera retry and reopen"
```

---

### Task 8: Perception debug overlay

**Files:**
- Modify: `src/magic_box/render/debug_overlay.py` (replace the placeholder)
- Modify: `src/magic_box/render/window.py:19` (import) and `:110` (draw call), plus `__init__`
- Create: `tests/render/test_debug_overlay.py`
- Modify: `tests/render/test_window.py`

**Interfaces:**
- Consumes:
  - `PlayerState` and `Push` (contracts);
  - `compute_layout` and `Rect` (`render/layout.py`);
  - `cfg["render"]["debug_overlay"]`, `cfg["render"]["margin_px"]`;
  - `cfg["perception"]["push_speed_mps"]` and `cfg["perception"]["zones"]`;
  - `make_state` (`tests/factories.py`).
- Produces:
  - `SlotHistory(graph_s: float)`:
    - `add(state: PlayerState) -> bool`: `False` if this `frame_idx` was already seen.
    - `samples`: a deque of `(cam_t, vz_l, vz_r)`, trimmed to `graph_s`.
    - `frames`: a deque of `(frame_idx, cam_t)`, trimmed the same way.
    - `last_push: Push | None` and `last_push_t: float` (that state's `t`).
  - `camera_fps(frames: Sequence[tuple[int, float]]) -> float`
  - `vz_to_y(vz: float, rect: Rect, vz_range: float) -> int`
  - `topdown_point(x: float, z: float, rect: Rect, x_m: float, z_m: float) -> tuple[int, int]`
  - `DebugOverlay(cfg)`, which must be built after `pygame.init()`: `draw(surface, states: Mapping[int, PlayerState], fps: float, dropped: int, now: float | None = None) -> None`, where `now` defaults to `time.monotonic()`.

- [ ] **Step 1: Write the failing tests** (`tests/render/test_debug_overlay.py`)

```python
from pathlib import Path

import pygame
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Push
from magic_box.render.debug_overlay import (
    DebugOverlay, SlotHistory, camera_fps, topdown_point, vz_to_y,
)
from magic_box.render.layout import Rect
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_history_dedupes_frames_and_trims_to_the_window():
    h = SlotHistory(graph_s=1.0)
    assert h.add(make_state(frame_idx=0, cam_t=0.0, wrist_vz={"L": -1.0, "R": 0.0}))
    assert not h.add(make_state(frame_idx=0, cam_t=0.0))
    for i in range(1, 40):
        h.add(make_state(frame_idx=i, cam_t=i / 30))
    assert h.samples[0][0] >= 39 / 30 - 1.0 and h.samples[-1][0] == pytest.approx(39 / 30)


def test_history_remembers_the_last_push():
    h = SlotHistory(1.0)
    h.add(make_state(frame_idx=1, t=5.0, push=Push("R", 2.3, (10.0, 20.0))))
    h.add(make_state(frame_idx=2, t=5.1))
    assert h.last_push.speed == 2.3 and h.last_push_t == 5.0


def test_camera_fps():
    assert camera_fps([(i, i / 30) for i in range(31)]) == pytest.approx(30.0)
    assert camera_fps([(0, 0.0)]) == 0.0 and camera_fps([]) == 0.0


def test_vz_to_y_puts_pushes_above_the_middle():
    r = Rect(0, 100, 200, 100)
    assert (vz_to_y(0.0, r, 4.0), vz_to_y(-4.0, r, 4.0), vz_to_y(4.0, r, 4.0)) == (150, 100, 200)
    assert vz_to_y(-9.0, r, 4.0) == 100  # clamped


def test_topdown_point_is_mirrored_like_the_players_view():
    r = Rect(0, 0, 200, 400)
    assert topdown_point(0.0, 0.0, r, 2.0, 4.0) == (100, 400)  # camera at the bottom center
    assert topdown_point(2.0, 4.0, r, 2.0, 4.0) == (0, 0)  # P1 (x > 0) is on the left
    assert topdown_point(-5.0, 9.0, r, 2.0, 4.0) == (200, 0)  # clamped


def test_draw_tracked_lost_and_pushing_players():
    pygame.init()
    try:
        surface = pygame.Surface((1920, 1080))
        surface.fill((50, 50, 50))
        overlay = DebugOverlay(CFG)
        push = Push("R", 2.3, (10.0, 20.0))
        states = {
            0: make_state(0, frame_idx=1, t=1.0, push=push),
            1: make_state(1, frame_idx=1, tracking_ok=False),
        }
        overlay.draw(surface, states, fps=60.0, dropped=2, now=1.1)
        assert tuple(surface.get_at((2, 2)))[:3] != (50, 50, 50)  # header panel at the top-left
        overlay.draw(surface, {}, fps=60.0, dropped=0, now=2.0)
    finally:
        pygame.quit()
```

Append to `tests/render/test_window.py`:

```python
def test_draw_with_the_debug_overlay_on():
    w = Window(CFG, headless=True)
    try:
        w.debug = True
        states, frame = FakePlayers(CFG).step(frozenset({CFG["keys"]["fake"][0]["push"]}), 0.0, 0.016)
        w.draw(make_view(), frame, {s.slot: s for s in states}, fps=60.0, dropped=1)
    finally:
        w.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/render -v`
Expected: FAIL with `ImportError: cannot import name 'DebugOverlay'`.

- [ ] **Step 3: Implement the pure helpers**

- `vz_to_y`: `round(rect.y + rect.h / 2 + (vz / vz_range) * rect.h / 2)`, clamped to `[rect.y, rect.y + rect.h]`.
- `topdown_point`: `px = rect.x + rect.w / 2 − (x / x_m) · rect.w / 2` and `py = rect.y + rect.h − (z / z_m) · rect.h`, both rounded and clamped to the rect.
- `camera_fps`: `(last_idx − first_idx) / (last_t − first_t)`, or 0.0 with fewer than two entries or `dt ≤ 0`.
- `SlotHistory.add` stores the push when `state.push` is set, then trims both deques to `cam_t ≥ newest − graph_s`.

- [ ] **Step 4: Implement `DebugOverlay.draw`**

All sizes and colors come from `cfg["render"]["debug_overlay"]`; `margin` is `render.margin_px`. Fonts are created once in `__init__`. Translucent panels are blitted from a `pygame.SRCALPHA` surface filled with `panel_rgba`.

- **Histories:** a `SlotHistory` per slot. Every draw adds each present state.
- **Header panel** at `(0, 0)`: `f"render {fps:.0f} fps | camera {cam_fps:.1f} fps | dropped {dropped}"`. `cam_fps` is the largest `camera_fps(h.frames)` over the slots.
- **Panels:** `compute_layout(surface width, height, cfg["render"])` gives each half. In each half, a `panel_w_px`-wide panel sits at `(half.half.x + margin, header bottom + margin)`, describing the player that half shows (`half.shows_slot`):
  - **Line 1:** `f"P{slot + 1}  id {player_id}  {'TRACKED' if ok else 'LOST'}"`, or `f"P{slot + 1}  not seen"` with no state.
  - **Line 2:** `f"{root_z:.2f} m  {zone}  {' '.join(sorted(pose_flags))}"`.
  - **Graph:** a `graph_h_px` box.
    - Polylines of `vz_r` in `slot_rgb[slot]` and `vz_l` in `text_rgb`, with x over the last `graph_s` and y from `vz_to_y(…, vz_range_mps)`.
    - A horizontal line at `−push_speed_mps` in `threshold_rgb`.
  - **Flash:** while `now − last_push_t < push_flash_s`, draw `f"PUSH {hand} {speed:.1f} m/s"` in `threshold_rgb`.
- **Top-down map:** a square of side `map_px`, centered horizontally under the header.
  - **Zone bands**, colored `zone_rgb`: z from 0 to `danger_max_m`, from there to `far_min_m`, then to `topdown_z_m`.
  - **Players:** for each tracked state, a radius-8 dot in `slot_rgb[slot]` at `topdown_point(root x, root z, …)`, labeled `P1` / `P2`.

- [ ] **Step 5: Wire it into `window.py`**

- Import `DebugOverlay` instead of `draw_debug_overlay`.
- In `__init__`, after `pygame.init()`: `self._debug_overlay = DebugOverlay(cfg)`.
- In `draw`, replace the old call with `self._debug_overlay.draw(self.screen, states, fps, dropped)`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/render -v`, `uv run pytest`, then `uv run python -m magic_box --fake --headless --max-ticks 60`
Expected: PASS, and the headless run exits 0.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add src/magic_box/render/debug_overlay.py src/magic_box/render/window.py tests/render/test_debug_overlay.py tests/render/test_window.py
git commit -m "feat(render): add the perception debug overlay with a wrist speed graph and top-down map"
```

---

### Task 9: Jetson tools

**Files:**
- Modify: `scripts/check_env.py`, `scripts/bench_tracking.py`, `scripts/record_session.py` (docstring: `Record an SVO2 from the ZED X for offline replay on the Jetson.` and `Owner: Enoch`)
- Modify: `tests/scripts/test_scripts.py`

**Interfaces:**
- Consumes:
  - `ZedSource` and `CameraError` (Task 6);
  - `PlayerTracker` (Task 5);
  - `filter_bodies` (Task 3);
  - `CAMERA_MODES` (Task 1);
  - `install_fake_sl` (Task 6).
- Produces:
  - `check_env`:
    - `_load_config() -> dict` (full config; `_load_ai_config` calls it);
    - `_zed_camera() -> tuple[bool, str]`;
    - `_zed_x_daemon() -> tuple[bool, str]`;
    - `run_checks` adds `zed_camera` (required when not `--laptop`) and `zed_x_daemon` (never required), right after `pyzed`.
  - `bench_tracking`:
    - `resolve_body_format` (unchanged);
    - `bench_config(cfg, body_format=None, resolution=None, svo=None) -> dict`;
    - dataclass `FrameSample(grab_ms: float, track_ms: float, bodies: int, slots: int)`;
    - dataclass `Summary(frames: int, elapsed_s: float, fps: float, grab_p50_ms: float, grab_p95_ms: float, track_p50_ms: float, track_p95_ms: float, two_share: float, go: bool, reason: str)`;
    - `summarize(samples, elapsed_s, min_fps, min_two) -> Summary`;
    - `format_summary(s: Summary) -> str`;
    - `main(argv) -> int`: 0 GO, 1 NO-GO, 2 camera error.
  - `record_session`:
    - `default_out(now: datetime) -> Path`;
    - `main(argv) -> int`: 0 OK, 2 camera error.

- [ ] **Step 1: Write the failing tests** (add to `tests/scripts/test_scripts.py`; import `datetime` and `install_fake_sl` from `tests.perception.fake_sl`)

```python
def test_zed_checks_listed_and_only_the_camera_required_on_the_jetson():
    mod = _load("check_env")
    jetson = {c.name: c for c in mod.run_checks(laptop=False, network=False)}
    laptop = {c.name: c for c in mod.run_checks(laptop=True, network=False)}
    assert jetson["zed_camera"].required and not jetson["zed_x_daemon"].required
    assert not laptop["zed_camera"].required and not laptop["zed_x_daemon"].required
    names = list(jetson)
    assert names.index("zed_camera") == names.index("pyzed") + 1


@pytest.mark.parametrize(
    "devices,ok,text",
    [([], False, "zed_x_daemon"), ([("ZED2", 1)], False, "ZED_X"), ([("ZED_X", 4242)], True, "ZED_X serial 4242")],
)
def test_zed_camera_check(monkeypatch, devices, ok, text):
    sl = install_fake_sl(monkeypatch)
    sl.Camera.devices = [sl.device(model, serial) for model, serial in devices]
    got_ok, detail = _load("check_env")._zed_camera()
    assert got_ok is ok and text in detail


def test_zed_x_daemon_check(monkeypatch):
    mod = _load("check_env")

    def fake_run(state, code):
        return lambda *a, **k: subprocess.CompletedProcess(a, code, stdout=f"{state}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run("inactive", 3))
    ok, detail = mod._zed_x_daemon()
    assert not ok and "inactive" in detail and "systemctl restart zed_x_daemon" in detail
    monkeypatch.setattr(subprocess, "run", fake_run("active", 0))
    assert mod._zed_x_daemon() == (True, "active")


def _samples(mod, n, bodies=2):
    return [mod.FrameSample(20.0, 2.0, bodies, min(bodies, 2)) for _ in range(n)]


def test_bench_summary_go():
    mod = _load("bench_tracking")
    s = mod.summarize(_samples(mod, 300), elapsed_s=10.0, min_fps=25.0, min_two=0.9)
    assert s.go and s.fps == pytest.approx(30.0) and s.two_share == 1.0
    assert s.grab_p95_ms == pytest.approx(20.0) and s.track_p50_ms == pytest.approx(2.0)
    assert mod.format_summary(s).splitlines()[-1] == "GO"


def test_bench_summary_no_go_reasons():
    mod = _load("bench_tracking")
    slow = mod.summarize(_samples(mod, 200), 10.0, 25.0, 0.9)
    lonely = mod.summarize(_samples(mod, 150) + _samples(mod, 150, bodies=1), 10.0, 25.0, 0.9)
    empty = mod.summarize([], 10.0, 25.0, 0.9)
    assert not slow.go and slow.reason.startswith("fps 20.0")
    assert not lonely.go and "two people" in lonely.reason
    assert not empty.go and empty.reason == "no frames"
    assert mod.format_summary(slow).splitlines()[-1].startswith("NO-GO: fps")


def test_bench_config_overrides_a_copy():
    from magic_box.core.config import load_config

    mod = _load("bench_tracking")
    cfg = load_config(SCRIPTS.parent / "config.yaml")
    cam = mod.bench_config(cfg, body_format="BODY_18", resolution="HD1200", svo="a.svo2")["camera"]
    assert (cam["body_format"], cam["resolution"], cam["image_width"], cam["image_height"]) == (
        "BODY_18", "HD1200", 1920, 1200,
    )
    assert cam["svo_path"] == "a.svo2" and cfg["camera"]["resolution"] == "SVGA"


def test_bench_main_runs_on_a_fake_camera(monkeypatch, capsys):
    install_fake_sl(monkeypatch)
    assert _load("bench_tracking").main(["--seconds", "0.05"]) in (0, 1)
    assert "fps" in capsys.readouterr().out


def test_record_default_out_name():
    out = _load("record_session").default_out(datetime(2026, 10, 24, 14, 5, 9))
    assert out == SCRIPTS.parent / "recordings" / "session-20261024-140509.svo2"


def test_record_main_records_with_a_fake_camera(monkeypatch, tmp_path):
    sl = install_fake_sl(monkeypatch)
    out = tmp_path / "x.svo2"
    assert _load("record_session").main(["--seconds", "0.05", "--out", str(out)]) == 0
    assert sl.Camera.last.recording.video_filename == str(out) and sl.Camera.last.closed
```

Rename `test_stub_scripts_have_help` to `test_scripts_have_help`; it stays parametrized over both scripts.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/scripts -v`
Expected: FAIL. There is no `zed_camera` check and no `summarize`, and `main` still raises `NotImplementedError`.

- [ ] **Step 3: Implement the `check_env.py` additions**

- **`_zed_camera`:**
  - Imports `pyzed.sl` inside the function, then calls `sl.Camera.get_device_list()`.
  - No devices: `(False, "no ZED camera found (try: sudo systemctl restart zed_x_daemon)")`.
  - Otherwise, reports the first device with `model = getattr(d.camera_model, "name", str(...))`:
    - wrong model: `(False, f"found {model}, config expects {expected}")`;
    - right model: `(True, f"{model} serial {serial} ({state name})")`.
- **`_zed_x_daemon`:**
  - Runs `subprocess.run(["systemctl", "is-active", "zed_x_daemon"], capture_output=True, text=True, timeout=5)` without `check`.
  - `"active"`: returns `(True, "active")`.
  - Otherwise: `(False, f"{state} (sudo systemctl restart zed_x_daemon)")`.

- [ ] **Step 4: Implement `bench_tracking.py`**

- **`bench_config`:** `copy.deepcopy`, then the overrides. `resolution` also sets `image_width`/`image_height` from `CAMERA_MODES`, and `svo` sets `svo_path`.
- **`summarize`:**
  - Basic numbers:
    - `fps = frames / elapsed_s`;
    - p50/p95 come from `numpy.percentile`;
    - `two_share` is the share of samples with `bodies >= 2`.
  - Reason, checked in this order:
    - `"no frames"`;
    - `f"fps {fps:.1f} < {min_fps:g}"`;
    - `f"two people in {two_share:.0%} of frames < {min_two:.0%}"`.
  - `go` is true when there is no reason.
- **`format_summary`** prints these lines, in order:
  - `f"frames {n} in {elapsed:.1f} s: {fps:.1f} fps"`;
  - grab+retrieve p50/p95 ms;
  - tracker p50/p95 ms;
  - `f"two people in {share:.0%} of frames"`;
  - then `GO` or `f"NO-GO: {reason}"`.
- **Flags:** `--seconds` (30.0), `--body-format`, `--resolution`, `--svo`, `--min-fps` (25.0), `--min-two` (0.9).
- **`main`:**
  - **Setup:** `load_config`, then `bench_config` with the flags, then `ZedSource` and `PlayerTracker`.
  - **Open:** on `CameraError`, print it and return 2.
  - **Loop:** until `--seconds` pass on `time.monotonic()`, time each `grab()` and `tracker.step()` with `time.perf_counter()`, skipping `None` grabs. Each `FrameSample` records `len(filter_bodies(capture.bodies, max_range_m))` bodies and the count of tracked states.
  - **Finish:** print the summary, close the camera in `finally`, and return 0 or 1.

- [ ] **Step 5: Implement `record_session.py`**

- `REPO_ROOT` as in the other scripts. `default_out(now)` is `REPO_ROOT / "recordings" / f"session-{now:%Y%m%d-%H%M%S}.svo2"`.
- Flags: `--out` (default `None`, meaning `default_out(datetime.now())`) and `--seconds` (30.0).
- `main`:
  - **Setup:** `load_config`, then a deep copy with `camera.record_svo = str(out)` and `camera.svo_path = None`.
  - **Open:** `ZedSource`; on `CameraError`, print it and return 2.
  - **Record:** grab until `--seconds` pass.
  - **Finish:** print `f"recorded {n} frames to {out}"`, close in `finally`, and return 0.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/scripts -v`, then `uv run pytest`
Expected: PASS. `test_check_env_laptop_mode_passes` still returns 0, because the new checks are not required with `--laptop`.

- [ ] **Step 7: Commit (Daniel runs)**

```bash
git add scripts/check_env.py scripts/bench_tracking.py scripts/record_session.py tests/scripts/test_scripts.py
git commit -m "feat(scripts): add zed x env checks, a two-person tracking benchmark and an svo recorder"
```

---

### Task 10: Docs for the ZED X switch and the perception layer

**Files:**
- Modify:
  - `CLAUDE.md`, `README.md`, `docs/hardware.md`, `docs/game-design.md`
  - `docs/superpowers/specs/2026-10-24-magic-box-design.md` (§1, §4, the §6 diagram and §8 only)
  - `src/magic_box/perception/CLAUDE.md`, `src/magic_box/render/CLAUDE.md`
  - `pyproject.toml` (`description` only)
- Modify: `tests/test_blueprint.py`

**Interfaces:**
- Consumes: everything above. Docs must match the code, so read the final modules first.

- [ ] **Step 1: Write the failing test** (append to `tests/test_blueprint.py`)

```python
@pytest.mark.parametrize(
    "doc", ["CLAUDE.md", "README.md", "docs/hardware.md", "src/magic_box/perception/CLAUDE.md"]
)
def test_docs_name_the_zed_x(doc):
    text = (ROOT / doc).read_text()
    assert "ZED X" in text and "ZED 2" not in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_blueprint.py -v`
Expected: FAIL; the docs still say "ZED 2".

- [ ] **Step 3: Update the docs** (follow spec §15; keep each file's existing structure and voice)

- **Root `CLAUDE.md`:**
  - "What this is": ZED X.
  - "Why ZED + Jetson" item 4: the ZED X has an IMU and connects over GMSL2 through a ZED Link capture card.
  - Hardware row: GMSL2 via ZED Link, has an IMU, not hot-pluggable (`sudo systemctl restart zed_x_daemon` or reboot after re-plugging).
  - Diagram: `ZED X ──GMSL2──▶`.
  - Contracts: a "Field notes" list with the five notes from spec §13.
  - "Working without the Jetson": live mode on a laptop exits the perception process with "pyzed is not installed", and the window shows STEP INTO VIEW.
  - Commands: rows for `scripts/bench_tracking.py` (go/no-go, flags), `scripts/record_session.py`, and SVO replay via `camera.svo_path` in `config.local.yaml`. Drop the "stubs today" line.
  - Risks: Orin Nano fallbacks become `BODY_18` or body fitting off; the crop-upscaling line names SVGA, with HD1200 as the fallback; add GMSL2 not hot-pluggable.
  - Open decisions: body format defaults to `BODY_34`, confirmed by the benchmark. Remove the MediaPipe row and the "Cut first: MediaPipe finger gestures" line; finger gestures are out.
- **`README.md`:**
  - Intro: "ZED X camera".
  - Jetson quickstart, step 1: ZED SDK + ZED X driver (ZED Link) + Python API, and check `systemctl is-active zed_x_daemon`.
  - After `check_env`: run `bench_tracking.py` with two people.
- **`docs/hardware.md`:**
  - ZED X row and mounting notes.
  - New "ZED X troubleshooting" section: `sudo systemctl restart zed_x_daemon`, `sudo dmesg | grep zedx` (both cameras' entries "bound"), `ZED_Diagnostic`, and never re-plug GMSL while running.
- **`src/magic_box/perception/CLAUDE.md`:**
  - Rewrite it for the new files: `raw.py`, `keypoints.py`, `kinematics.py`, `bodies.py`, `motion.py`, `push.py`, `poses.py`, `tracker.py`, `zed_source.py`, `process.py`, `hands.py` (out).
  - Keep the six headings `tests/test_blueprint.py` checks.
  - Hard rules:
    - `cam_t` for velocities;
    - the `wrist_vz` meaning;
    - only `zed_source.py` touches `pyzed`;
    - SDK calls stay in `zed_source.py`, so tests use `tests/perception/fake_sl.py`.
  - "Test without the Jetson": `uv run pytest tests/perception`.
  - Open TODOs: tune the "(guess)" values on the device with the overlay and SVO replays; confirm the body format and resolution with `bench_tracking.py`.
- **`src/magic_box/render/CLAUDE.md`:** the `debug_overlay.py` line describes the new overlay. Remove the `TODO(Enoch)` overlay item.
- **`docs/game-design.md`:** the `BODY_18` question becomes "Which gestures are reliable with the default `BODY_34` keypoints (Enoch confirms after the benchmark)?". Delete the MediaPipe question; finger gestures are out.
- **Parent spec:**
  - §1 summary, the §6 diagram (`ZED X ──GMSL2──▶`) and the §8 perception row read "ZED X".
  - §4: the camera row becomes the ZED X, with "Changed 2026-10-24 from the ZED 2; see `2026-10-24-perception-zedx-design.md`."
- **`pyproject.toml`:** `description = "Camera-only 1v1 magic duel console: ZED X + Jetson Orin Nano"`.

- [ ] **Step 4: Run the full verification**

Run: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run python -m magic_box --fake --headless --max-ticks 60`, then `grep -rn "ZED 2" --include='*.md' --include='*.py' --include='*.toml' . | grep -v -e '^./.venv' -e '^./.superpowers' -e '^./docs/superpowers/'` and `grep -n "ZED 2" docs/superpowers/specs/2026-10-24-magic-box-design.md`
Expected: all clean, and the headless run exits 0. The first grep prints nothing. The second prints only the §4 "Changed … from the ZED 2" note. Historical plans and the perception spec keep their "ZED 2" history lines.

- [ ] **Step 5: Commit (Daniel runs)**

```bash
git add CLAUDE.md README.md docs/hardware.md docs/game-design.md docs/superpowers/specs/2026-10-24-magic-box-design.md src/magic_box/perception/CLAUDE.md src/magic_box/render/CLAUDE.md pyproject.toml tests/test_blueprint.py
git commit -m "doc(repo): document the zed x switch, perception contract notes and jetson tools"
```

---

## After the plan: on the Jetson (Daniel and Enoch)

Not a task for agents; the device is needed.
1. `uv run python scripts/check_env.py`: `zed_camera` must show `ZED_X serial …`.
2. `uv run python scripts/bench_tracking.py` with two people standing 1–3 m away. On NO-GO, retry with `--body-format BODY_18`.
3. `MAGIC_BOX_STRESS=1 uv run pytest tests/pipeline/test_frame_bus.py`.
4. `uv run --env-file .env python -m magic_box`, press `F1`, punch toward the camera, and tune the `perception:` "(guess)" values in `config.local.yaml`.
5. `uv run python scripts/record_session.py --seconds 60` to keep an SVO for later tuning via `camera.svo_path`.
