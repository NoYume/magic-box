"""Config loading, local-override merging and validation.

Owner: Nikhil
"""

from pathlib import Path
from typing import Any

import yaml

from magic_box.core.contracts import RELEASE_KINDS

Config = dict[str, Any]

REQUIRED_SECTIONS: tuple[str, ...] = (
    "display",
    "camera",
    "perception",
    "pipeline",
    "intent",
    "voice",
    "ai",
    "game",
    "render",
    "keys",
    "fake",
)

SLOTS = {0, 1}

CAMERA_MODES: dict[str, tuple[int, int]] = {
    "HD2K": (2208, 1242),
    "HD1200": (1920, 1200),
    "HD1080": (1920, 1080),
    "HD720": (1280, 720),
    "SVGA": (960, 600),
    "VGA": (672, 376),
}
BODY_FORMATS: tuple[str, ...] = ("BODY_18", "BODY_34", "BODY_38")
COMBAT_KEYS: tuple[str, ...] = (
    "speed_ref_mps",
    "speed_mult_min",
    "speed_mult_max",
    "near_m",
    "near_mult",
    "far_m",
    "far_mult",
)


class ConfigError(ValueError):
    """Raised when the merged config has one or more problems."""


def deep_merge(base: dict, override: dict) -> dict:
    """Return a new dict with `override` merged recursively onto `base`."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _get(node: Any, *path: str) -> Any:
    """Walk nested dicts; return None if any step is missing or not a dict."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _check_zones(cfg: Config, problems: list[str]) -> None:
    zones = _get(cfg, "perception", "zones")
    if zones is None:
        if "perception" in cfg:
            problems.append("perception.zones: missing")
        return
    danger = _get(zones, "danger_max_m")
    far = _get(zones, "far_min_m")
    if not isinstance(danger, (int, float)) or not isinstance(far, (int, float)):
        problems.append("perception.zones: danger_max_m and far_min_m must be numbers")
    elif not danger < far:
        problems.append(f"perception.zones: danger_max_m ({danger}) must be < far_min_m ({far})")


def _check_push_peak_wait(cfg: Config, problems: list[str]) -> None:
    wait = _get(cfg, "perception", "push_peak_wait_s")
    if wait is None:
        if "perception" in cfg:
            problems.append("perception.push_peak_wait_s: missing")
    elif isinstance(wait, bool) or not isinstance(wait, (int, float)) or not 0 <= wait <= 0.1:
        problems.append(
            f"perception.push_peak_wait_s: must be a number from 0 to 0.1, got {wait!r}"
        )


def _check_camera(cfg: Config, problems: list[str]) -> None:
    if "camera" not in cfg:
        return
    res = _get(cfg, "camera", "resolution")
    if res not in CAMERA_MODES:
        problems.append(
            f"camera.resolution: unknown mode {res!r} (known: {', '.join(CAMERA_MODES)})"
        )
    else:
        w = _get(cfg, "camera", "image_width")
        h = _get(cfg, "camera", "image_height")
        mw, mh = CAMERA_MODES[res]
        if (w, h) != (mw, mh):
            problems.append(
                f"camera.image_width/image_height: {w}x{h} does not match {res} ({mw}x{mh})"
            )
    fmt = _get(cfg, "camera", "body_format")
    if fmt not in BODY_FORMATS:
        problems.append(f"camera.body_format: must be one of {BODY_FORMATS}, got {fmt!r}")


def _check_mics(cfg: Config, problems: list[str]) -> None:
    if "voice" not in cfg:
        return
    mics = _get(cfg, "voice", "mics")
    if not isinstance(mics, list):
        problems.append("voice.mics: must be a list with one entry per slot 0 and 1")
        return
    slots = [m.get("slot") if isinstance(m, dict) else None for m in mics]
    if len(slots) != len(SLOTS) or set(slots) != SLOTS:
        problems.append(f"voice.mics: slots must be exactly {{0, 1}}, got {slots}")


def _check_key_spells(cfg: Config, problems: list[str]) -> None:
    if "keys" not in cfg:
        return
    spells = _get(cfg, "keys", "spells")
    if not isinstance(spells, dict) or not SLOTS <= set(spells):
        problems.append("keys.spells: must define slots 0 and 1")


def _check_combat(cfg: Config, problems: list[str]) -> None:
    if "game" not in cfg:
        return
    combat = _get(cfg, "game", "combat")
    if not isinstance(combat, dict):
        combat = {}
    for key in COMBAT_KEYS:
        if key not in combat:
            problems.append(f"game.combat.{key}: missing")


def _check_voice_and_ai(cfg: Config, problems: list[str]) -> None:
    if "voice" in cfg:
        for key in ("api_key_env", "chunk_ms"):
            if _get(cfg, "voice", key) is None:
                problems.append(f"voice.{key}: missing")
    if "ai" in cfg:
        if _get(cfg, "ai", "api_key_env") is None:
            problems.append("ai.api_key_env: missing")
        min_words = _get(cfg, "ai", "min_words")
        max_words = _get(cfg, "ai", "max_words")
        if isinstance(min_words, (int, float)) and isinstance(max_words, (int, float)):
            if min_words > max_words:
                problems.append("ai.min_words: must be <= ai.max_words")
        # Muse Spark chat completions; "none" is rejected with HTTP 400 (dev.meta.ai docs).
        efforts = ("minimal", "low", "medium", "high", "xhigh")
        effort = _get(cfg, "ai", "reasoning_effort")
        if effort is not None and effort not in efforts:
            problems.append(f"ai.reasoning_effort: must be null or one of {efforts}: {effort!r}")


def _check_game(cfg: Config, problems: list[str]) -> None:
    if "game" not in cfg:
        return
    classes = _get(cfg, "game", "classes")
    if not isinstance(classes, dict):
        problems.append("game.classes: missing or not a mapping")
        classes = {}
    defaults = _get(cfg, "game", "default_classes")
    if not isinstance(defaults, dict):
        problems.append("game.default_classes: missing or not a mapping")
    else:
        for slot, name in defaults.items():
            if name not in classes:
                problems.append(f"game.default_classes[{slot}]: unknown class {name!r}")
    for cls_name, cls in classes.items():
        spells = _get(cls, "spells")
        if not isinstance(spells, list):
            problems.append(f"game.classes.{cls_name}.spells: missing or not a list")
            continue
        for spell in spells:
            spell_id = _get(spell, "id")
            release = _get(spell, "release")
            if release not in RELEASE_KINDS:
                problems.append(
                    f"game.classes.{cls_name}.spells.{spell_id}.release: "
                    f"must be one of {RELEASE_KINDS}, got {release!r}"
                )
            where = f"game.classes.{cls_name}.spells.{spell_id}.fallback"
            fallback = _get(spell, "fallback")
            if not isinstance(fallback, dict) or not SLOTS <= set(fallback):
                problems.append(f"{where}: must define slots 0 and 1")
                continue
            if str(fallback[0]).lower() == str(fallback[1]).lower():
                problems.append(f"{where}: slot 0 and slot 1 incantations must differ")


def _check_pipeline_render(cfg: Config, problems: list[str]) -> None:
    for key in (
        "camera_stale_s",
        "camera_boot_timeout_s",
        "network_probe_timeout_s",
        "perf_window_s",
        "stop_timeout_s",
        "terminate_timeout_s",
    ):
        value = _get(cfg, "pipeline", key)
        if "pipeline" in cfg and (not isinstance(value, (int, float)) or value <= 0):
            problems.append(f"pipeline.{key}: must be a positive number")
    if "render" in cfg:
        quality = _get(cfg, "render", "camera_scale_quality")
        if quality not in ("fast", "smooth"):
            problems.append("render.camera_scale_quality: must be 'fast' or 'smooth'")
        px = _get(cfg, "render", "crop_cache_px")
        if isinstance(px, bool) or not isinstance(px, (int, float)) or px < 0:
            problems.append("render.crop_cache_px: must be a number >= 0")
        for key in ("self_view", "crop_cache"):
            if not isinstance(_get(cfg, "render", key), bool):
                problems.append(f"render.{key}: must be true or false")
    if "display" in cfg and not isinstance(_get(cfg, "display", "vsync"), bool):
        problems.append("display.vsync: must be true or false")


def validate(cfg: Config) -> list[str]:
    """Return every problem found in `cfg` (empty list means valid)."""
    problems = [f"{name}: missing section" for name in REQUIRED_SECTIONS if name not in cfg]
    _check_zones(cfg, problems)
    _check_push_peak_wait(cfg, problems)
    _check_camera(cfg, problems)
    _check_mics(cfg, problems)
    _check_key_spells(cfg, problems)
    _check_game(cfg, problems)
    _check_combat(cfg, problems)
    _check_voice_and_ai(cfg, problems)
    _check_pipeline_render(cfg, problems)
    return problems


def load_config(path: str | Path = "config.yaml") -> Config:
    """Load `path`, deep-merge `config.local.yaml` beside it, validate, return."""
    path = Path(path)
    cfg = yaml.safe_load(path.read_text()) or {}
    local = path.parent / "config.local.yaml"
    if local.exists():
        cfg = deep_merge(cfg, yaml.safe_load(local.read_text()) or {})
    problems = validate(cfg)
    if problems:
        raise ConfigError("; ".join(problems))
    return cfg
