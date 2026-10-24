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
        assert h.hud.y + h.hud.h <= 1080 and h.hud.y > 540  # bottom
