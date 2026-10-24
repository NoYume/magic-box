"""Config loading, local-override merging and validation.

Owner: Nikhil
"""

from pathlib import Path
from typing import Any

import yaml

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
            where = f"game.classes.{cls_name}.spells.{spell_id}.fallback"
            fallback = _get(spell, "fallback")
            if not isinstance(fallback, dict) or not SLOTS <= set(fallback):
                problems.append(f"{where}: must define slots 0 and 1")
                continue
            if str(fallback[0]).lower() == str(fallback[1]).lower():
                problems.append(f"{where}: slot 0 and slot 1 incantations must differ")


def validate(cfg: Config) -> list[str]:
    """Return every problem found in `cfg` (empty list means valid)."""
    problems = [f"{name}: missing section" for name in REQUIRED_SECTIONS if name not in cfg]
    _check_zones(cfg, problems)
    _check_mics(cfg, problems)
    _check_key_spells(cfg, problems)
    _check_game(cfg, problems)
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
