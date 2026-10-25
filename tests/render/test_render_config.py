import copy
from pathlib import Path

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
