"""Config loading, local-override merging and validation.

Owner: Nikhil
"""

from pathlib import Path
from typing import Any

import yaml

from magic_box.core.contracts import EFFECT_KINDS, RELEASE_KINDS, ZONES

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
        hold = _get(cfg, "voice", "perfect_hold_s")
        if not isinstance(hold, (int, float)) or isinstance(hold, bool) or hold < 0:
            problems.append(f"voice.perfect_hold_s: must be a number >= 0, got {hold!r}")
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
    _check_game_effects(cfg, classes, problems)


GAME_TIMING_KEYS: tuple[str, ...] = (
    "boot_min_s",
    "boot_max_s",
    "hands_up_hold_s",
    "abandon_after_s",
    "empowered_mult",
    "mana_slow_mult",
    "slow_charge_mult",
    "release_grace_s",
    "ko_hold_s",
    "loading_read_s",
)


def _is_num(value: Any) -> bool:
    """A real number; YAML booleans (on/off/yes/no) don't count."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_game_effects(cfg: Config, classes: dict, problems: list[str]) -> None:
    """Boot, debounce, abandon and spell-effect keys (Adetola, 2026-10-25)."""
    for key in GAME_TIMING_KEYS:
        value = _get(cfg, "game", key)
        if not _is_num(value) or value < 0:
            problems.append(f"game.{key}: must be a number >= 0")
    lo, hi = _get(cfg, "game", "boot_min_s"), _get(cfg, "game", "boot_max_s")
    if _is_num(lo) and _is_num(hi) and lo > hi:
        problems.append("game.boot_min_s: must be <= game.boot_max_s")
    words = _get(cfg, "game", "name_max_words")
    if not isinstance(words, int) or isinstance(words, bool) or words < 1:
        problems.append("game.name_max_words: must be an integer >= 1")
    stop = _get(cfg, "game", "name_stop_words")
    if not isinstance(stop, list) or not all(
        isinstance(w, str) and w and not any(c.isspace() for c in w) for w in stop
    ):
        problems.append("game.name_stop_words: must be a list of single words, quoted")
    seen: dict[str, str] = {}
    for cls_name, cls in classes.items():
        _check_keywords(cls_name, _get(cls, "keywords"), seen, problems)
        for spell in _get(cls, "spells") or []:
            if isinstance(spell, dict):
                where = f"game.classes.{cls_name}.spells.{spell.get('id')}"
                _check_spell_effects(where, spell, problems)


def _check_keywords(
    cls_name: str, keywords: Any, seen: dict[str, str], problems: list[str]
) -> None:
    where = f"game.classes.{cls_name}.keywords"
    if not isinstance(keywords, list) or not keywords:
        problems.append(f"{where}: must be a non-empty list")
        return
    for kw in keywords:
        if not isinstance(kw, str) or not kw.isalpha():
            problems.append(f"{where}: {kw!r} must be one word, quoted if YAML reads it as a bool")
            continue
        word = kw.lower()
        if word in seen:
            problems.append(f"{where}: {kw!r} is already a keyword of {seen[word]}")
        seen[word] = cls_name


def _check_spell_effects(where: str, spell: dict, problems: list[str]) -> None:
    effect = spell.get("effect")
    if effect is not None:
        if effect not in EFFECT_KINDS:
            problems.append(f"{where}.effect: must be one of {EFFECT_KINDS}, got {effect!r}")
        effect_s = spell.get("effect_s")
        if not _is_num(effect_s) or effect_s <= 0:
            problems.append(f"{where}.effect_s: must be a number > 0 with an effect")
    if "heal_hp" in spell and (not _is_num(spell["heal_hp"]) or spell["heal_hp"] < 0):
        problems.append(f"{where}.heal_hp: must be a number >= 0")
    hits = spell.get("hits", 1)
    if not isinstance(hits, int) or isinstance(hits, bool) or hits < 1:
        problems.append(f"{where}.hits: must be an integer >= 1")
        hits = 1
    if "chain_gap_s" in spell or hits > 1:
        gap = spell.get("chain_gap_s")
        if not _is_num(gap) or gap <= 0:
            problems.append(f"{where}.chain_gap_s: must be a number > 0 (required when hits > 1)")


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


THEME_COLORS: tuple[str, ...] = (
    "text",
    "dim",
    "faint",
    "shadow",
    "gold",
    "ok",
    "bad",
    "warn",
    "panel",
    "panel_edge",
    "card",
    "card_hi",
    "p1",
    "p2",
    "bg_top",
    "bg_bottom",
    "fire",
    "lightning",
    "holy",
    "basic",
    "mana",
    "white",
    "black",
    "ink",
    "icon_bg",
    "fire_hot",
    "fire_core",
)
THEME_FONTS: tuple[str, ...] = ("tiny", "small", "text", "big", "huge", "giant")
THEME_TITLES: tuple[str, ...] = ("boot", "lobby", "headline", "ko", "banner")


RENDER_NUMBERS: dict[str, tuple[str, ...]] = {
    "theme": ("shadow_px", "panel_alpha", "radius_px", "text_cache_max"),
    "hud": (
        "pad_px",
        "hp_bar_h_px",
        "mana_bar_h_px",
        "enemy_bar_h_px",
        "ease_per_s",
        "ghost_hold_s",
        "ghost_per_s",
        "low_hp_frac",
        "spell_row_h_px",
        "effect_icon_px",
        "timer_low_s",
    ),
    "fx": (
        "max_particles",
        "max_texts",
        "shake_px",
        "shake_s",
        "flash_s",
        "flash_alpha",
        "number_s",
        "number_rise_px",
        "sparkle_count",
        "burst_count",
        "particle_s",
        "glow_s",
        "ko_s",
        "ko_slowmo",
        "banner_pop_s",
        "glow_heal_s",
        "glow_cast_s",
        "glow_start_s",
        "particle_gravity_px",
        "ring_size_px",
        "sparkle_drift_px",
    ),
    "audio": ("volume", "sample_rate", "buffer", "tick_last_s", "mix_channels"),
    "projectiles": (
        "start_radius_px",
        "end_radius_px",
        "end_y_frac",
        "font_px",
        "glow_scale",
        "glow_max_px",
        "glow_step_px",
        "glow_big_from_px",
        "glow_big_step_px",
        "trail_steps",
        "trail_spacing",
        "dodge_ring_px",
    ),
    "scenes": ("title_px", "text_px", "card_w_frac", "countdown_px", "chronicle_w_frac"),
}
RENDER_POSITIVE: tuple[tuple[str, str], ...] = (
    ("audio", "sample_rate"),
    ("audio", "buffer"),
    ("audio", "mix_channels"),
    ("projectiles", "glow_max_px"),
    ("projectiles", "glow_step_px"),
    ("projectiles", "glow_big_from_px"),
    ("projectiles", "glow_big_step_px"),
    ("theme", "text_cache_max"),
)
RENDER_COLORS: dict[str, tuple[str, ...]] = {
    "hud": (
        "hp_rgb",
        "hp_low_rgb",
        "ghost_rgb",
        "mana_rgb",
        "bar_back_rgb",
        "charge_rgb",
        "cooldown_rgb",
    ),
    "fx": ("hit_rgb", "damage_rgb", "dodge_rgb", "block_rgb", "heal_rgb", "buff_rgb", "ko_rgb"),
    "projectiles": ("default_rgb", "dodge_rgb"),
    "scenes": ("text_rgb", "dim_rgb"),
}
RENDER_RANGES: tuple[tuple[str, str], ...] = (
    ("hud", "zone_meter_m"),
    ("fx", "burst_size_px"),
    ("fx", "sparkle_size_px"),
    ("fx", "sparkle_rise_px"),
)
# (section, key): (required sub-keys, value kind); an empty tuple means any keys
RENDER_MAPS: dict[tuple[str, str], tuple[tuple[str, ...], str]] = {
    ("theme", "colors"): (THEME_COLORS, "rgb"),
    ("theme", "font_px"): (THEME_FONTS, "number"),
    ("theme", "title_px"): (THEME_TITLES, "number"),
    ("hud", "zone_rgb"): (ZONES, "rgb"),
    ("hud", "effect_rgb"): (EFFECT_KINDS, "rgb"),
    ("fx", "speed_px"): (("hit", "hit_side", "graze", "dodge", "block"), "number"),
    ("fx", "ring_count"): (("dodge", "block"), "number"),
    ("projectiles", "rgb"): ((), "rgb"),
    ("projectiles", "family"): ((), "str"),
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_rgb(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) in (3, 4)
        and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255 for v in value)
    )


def _is_range(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(_is_number(v) for v in value)
        and value[0] <= value[1]
    )


_KINDS = {"rgb": _is_rgb, "number": _is_number, "str": lambda v: isinstance(v, str)}
_KIND_TEXT = {"rgb": "[r, g, b] with 0-255 ints", "number": "numbers", "str": "strings"}


def _check_render_map(cfg: Config, section: str, key: str, problems: list[str]) -> None:
    where = f"render.{section}.{key}"
    required, kind = RENDER_MAPS[(section, key)]
    node = _get(cfg, "render", section, key)
    if not isinstance(node, dict):
        problems.append(f"{where}: missing or not a mapping")
        return
    missing = [k for k in required if k not in node]
    if missing:
        problems.append(f"{where}: missing {', '.join(missing)}")
    bad = [str(k) for k, v in node.items() if not _KINDS[kind](v)]
    if bad:
        problems.append(f"{where}: {', '.join(bad)} must be {_KIND_TEXT[kind]}")


def _check_render(cfg: Config, problems: list[str]) -> None:
    """Every render key read at runtime: present, the right type (bools are not numbers)."""
    if "render" not in cfg:
        return
    for section, keys in RENDER_NUMBERS.items():
        for key in keys:
            if not _is_number(_get(cfg, "render", section, key)):
                problems.append(f"render.{section}.{key}: missing or not a number")
    for section, key in RENDER_POSITIVE:
        value = _get(cfg, "render", section, key)
        if _is_number(value) and value <= 0:
            problems.append(f"render.{section}.{key}: must be > 0")
    for section, keys in RENDER_COLORS.items():
        for key in keys:
            if not _is_rgb(_get(cfg, "render", section, key)):
                problems.append(f"render.{section}.{key}: missing or not [r, g, b] (0-255 ints)")
    for section, key in RENDER_RANGES:
        if not _is_range(_get(cfg, "render", section, key)):
            problems.append(f"render.{section}.{key}: must be [low, high] numbers, low <= high")
    for section, key in RENDER_MAPS:
        _check_render_map(cfg, section, key, problems)
    if not isinstance(_get(cfg, "render", "theme", "stars"), dict):
        problems.append("render.theme.stars: missing or not a mapping")
    else:
        for key in ("count", "blue"):
            if not _is_number(_get(cfg, "render", "theme", "stars", key)):
                problems.append(f"render.theme.stars.{key}: missing or not a number")
        if not _is_range(_get(cfg, "render", "theme", "stars", "brightness")):
            problems.append("render.theme.stars.brightness: must be [low, high] numbers")
    if not isinstance(_get(cfg, "render", "audio", "enabled"), bool):
        problems.append("render.audio.enabled: must be true or false")
    cap = _get(cfg, "render", "fx", "max_particles")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        problems.append("render.fx.max_particles: must be an integer >= 0")
    volume = _get(cfg, "render", "audio", "volume")
    if not _is_number(volume) or not 0 <= volume <= 1:
        problems.append("render.audio.volume: must be a number from 0 to 1")


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
    _check_render(cfg, problems)
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
