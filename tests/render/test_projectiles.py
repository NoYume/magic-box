from pathlib import Path

import pygame
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import ProjectileView
from magic_box.render.layout import Rect
from magic_box.render.projectiles import draw_projectiles, projectile_screen

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
P = CFG["render"]["projectiles"]
HALF, CROP = Rect(0, 0, 960, 1080), Rect(240, 0, 480, 540)


def pv(progress=0.0, origin=(480.0, 270.0), spell="fireball", window=False, target=0):
    return ProjectileView(spell, target, origin, progress, window)


def test_start_maps_through_crop():
    center, radius, rgb = projectile_screen(pv(), HALF, CROP, P)
    assert center == pytest.approx((480.0, 540.0)) and radius == P["start_radius_px"]
    assert rgb == tuple(P["rgb"]["fireball"])


def test_end_is_bottom_center_and_grows():
    center, radius, _ = projectile_screen(pv(1.0), HALF, CROP, P)
    assert center == pytest.approx((480.0, P["end_y_frac"] * 1080))
    assert radius == P["end_radius_px"]


def test_origin_outside_crop_is_clamped_to_half():
    center, _, _ = projectile_screen(pv(origin=(0.0, 0.0)), HALF, CROP, P)
    assert center == pytest.approx((0.0, 0.0))


def test_colors_dodge_default_and_basic():
    assert projectile_screen(pv(window=True), HALF, CROP, P)[2] == tuple(P["dodge_rgb"])
    assert projectile_screen(pv(spell="mystery"), HALF, CROP, P)[2] == tuple(P["default_rgb"])
    assert projectile_screen(pv(spell="basic"), HALF, CROP, P)[2] == tuple(P["rgb"]["basic"])


def test_draw_headless_smoke():
    pygame.init()
    try:
        surf = pygame.Surface((1920, 1080))
        font = pygame.font.Font(None, P["font_px"])
        draw_projectiles(surf, HALF, CROP, [pv(0.9, window=True), pv(target=1)], 0, P, font)
        y = int(0.9 * P["end_y_frac"] * 1080 + 0.1 * 540)
        assert tuple(surf.get_at((480, y)))[:3] != (0, 0, 0)
    finally:
        pygame.quit()
