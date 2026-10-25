from pathlib import Path

import pytest
import yaml

from magic_box.core.config import (
    BODY_FORMATS,
    CAMERA_MODES,
    REQUIRED_SECTIONS,
    ConfigError,
    load_config,
)

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
    cfg["game"]["classes"]["fire_mage"]["spells"][0]["fallback"] = {
        0: "same words",
        1: "Same Words",
    }
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


def test_repo_config_targets_zed_x():
    cam = load_config(ROOT / "config.yaml")["camera"]
    assert (cam["model"], cam["resolution"], cam["image_width"], cam["image_height"]) == (
        "ZED_X",
        "SVGA",
        960,
        600,
    )
    assert cam["body_format"] == "BODY_34" and cam["body_fitting"] is True
    assert cam["svo_path"] is None and cam["record_svo"] is None


def test_repo_config_has_perception_tunables():
    p = load_config(ROOT / "config.yaml")["perception"]
    for key in (
        "push_speed_mps",
        "push_min_travel_m",
        "push_window_s",
        "push_rearm_ratio",
        "push_cooldown_s",
        "motion_window_s",
        "slot_hold_s",
        "hands_up_margin_m",
        "hands_together_max_m",
        "open_retry_s",
        "max_grab_failures",
        "stats_every_s",
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
