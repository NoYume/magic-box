import copy
from pathlib import Path

import pytest
import yaml

from magic_box.core.config import validate

RAW = yaml.safe_load((Path(__file__).resolve().parents[2] / "config.yaml").read_text())


def test_shipped_render_config_is_valid():
    assert validate(RAW) == []


def test_render_validation_reports_bad_keys():
    cfg = copy.deepcopy(RAW)
    del cfg["render"]["theme"]["colors"]["gold"]
    del cfg["render"]["theme"]["font_px"]["huge"]
    cfg["render"]["fx"]["max_particles"] = -1
    cfg["render"]["audio"]["volume"] = 3
    problems = " ".join(validate(cfg))
    assert "render.theme.colors: missing gold" in problems
    assert "render.theme.font_px: missing huge" in problems
    assert "render.fx.max_particles" in problems and "render.audio.volume" in problems


@pytest.mark.parametrize(
    "path",
    [
        ("hud", "ease_per_s"),
        ("hud", "zone_meter_m"),
        ("hud", "effect_rgb"),
        ("fx", "shake_s"),
        ("fx", "speed_px"),
        ("fx", "hit_rgb"),
        ("audio", "mix_channels"),
        ("audio", "enabled"),
        ("projectiles", "glow_step_px"),
        ("projectiles", "family"),
        ("scenes", "countdown_px"),
        ("theme", "stars"),
    ],
)
def test_every_runtime_render_key_is_required(path):
    cfg = copy.deepcopy(RAW)
    del cfg["render"][path[0]][path[1]]
    assert any(p.startswith(f"render.{path[0]}.{path[1]}") for p in validate(cfg))


@pytest.mark.parametrize(
    "path, value",
    [
        (("hud", "ease_per_s"), True),
        (("fx", "ko_s"), "2"),
        (("fx", "max_particles"), True),
        (("audio", "volume"), False),
        (("audio", "enabled"), 1),
        (("hud", "hp_rgb"), [300, 0, 0]),
        (("hud", "zone_meter_m"), [3.5, 0.8]),
        (("projectiles", "glow_max_px"), 0),
        (("fx", "burst_size_px"), [14]),
    ],
)
def test_bad_render_values_are_rejected(path, value):
    cfg = copy.deepcopy(RAW)
    cfg["render"][path[0]][path[1]] = value
    assert any(p.startswith(f"render.{path[0]}.{path[1]}") for p in validate(cfg))


def test_nested_render_keys_are_checked():
    cfg = copy.deepcopy(RAW)
    del cfg["render"]["fx"]["speed_px"]["dodge"]
    del cfg["render"]["hud"]["effect_rgb"]["slow"]
    cfg["render"]["hud"]["zone_rgb"]["far"] = "blue"
    problems = " ".join(validate(cfg))
    assert "render.fx.speed_px" in problems and "dodge" in problems
    assert "render.hud.effect_rgb" in problems and "slow" in problems
    assert "render.hud.zone_rgb" in problems
