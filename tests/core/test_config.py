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
