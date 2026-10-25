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


@pytest.mark.parametrize("bad", [-0.01, 0.2, "x", True])
def test_push_peak_wait_must_be_between_0_and_0_1(tmp_path, bad):
    cfg = _base()
    cfg["perception"]["push_peak_wait_s"] = bad
    with pytest.raises(ConfigError, match="push_peak_wait_s"):
        load_config(_write(tmp_path, cfg))


@pytest.mark.parametrize("key", ["stop_timeout_s", "terminate_timeout_s"])
@pytest.mark.parametrize("bad", [0, -1.0, "x"])
def test_pipeline_stop_timeouts_must_be_positive(tmp_path, key, bad):
    cfg = _base()
    cfg["pipeline"][key] = bad
    with pytest.raises(ConfigError, match=key):
        load_config(_write(tmp_path, cfg))


@pytest.mark.parametrize("bad", [-1, "x", True, None])
def test_crop_cache_px_must_be_a_non_negative_number(tmp_path, bad):
    cfg = _base()
    cfg["render"]["crop_cache_px"] = bad
    with pytest.raises(ConfigError, match="crop_cache_px"):
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
        "push_peak_wait_s",
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


def test_repo_config_has_phase_tunables():
    cfg = load_config(ROOT / "config.yaml")
    assert cfg["intent"]["two_hand_window_s"] == 0.1
    for key in (
        "api_key_env",
        "chunk_ms",
        "handshake_timeout_s",
        "reconnect_backoff_s",
        "reconnect_max_s",
        "session_max_s",
        "silence_after_s",
        "min_keyword_chars",
        "audio_queue_chunks",
    ):
        assert key in cfg["voice"], key
    assert cfg["ai"]["model"] == "muse-spark-1.3" and cfg["ai"]["min_words"] == 3
    for key in (
        "basic_attack_damage",
        "basic_attack_travel_s",
        "perfect_mult",
        "banner_s",
        "loading_min_s",
        "loading_max_s",
        "victory_min_s",
        "victory_max_s",
        "pause_after_s",
        "name_max_chars",
    ):
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
