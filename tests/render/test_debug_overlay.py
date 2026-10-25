from pathlib import Path

import pygame
import pytest

from magic_box.core.config import load_config
from magic_box.core.contracts import Push
from magic_box.render.debug_overlay import (
    DebugOverlay,
    SlotHistory,
    camera_fps,
    overlay_rects,
    topdown_point,
    vz_to_y,
)
from magic_box.render.layout import Rect
from tests.factories import make_state

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


def test_history_dedupes_frames_and_trims_to_the_window():
    h = SlotHistory(graph_s=1.0)
    assert h.add(make_state(frame_idx=0, cam_t=0.0, wrist_vz={"L": -1.0, "R": 0.0}))
    assert not h.add(make_state(frame_idx=0, cam_t=0.0))
    for i in range(1, 40):
        h.add(make_state(frame_idx=i, cam_t=i / 30))
    assert h.samples[0][0] >= 39 / 30 - 1.0 and h.samples[-1][0] == pytest.approx(39 / 30)


def test_history_resets_after_a_rewind_or_restart():
    for new_idx, new_t in ((3, 0.1), (0, 5.0)):  # SVO rewind (cam_t back); restart (idx back)
        h = SlotHistory(graph_s=3.0)
        for i in range(100, 130):
            h.add(make_state(frame_idx=i, cam_t=10.0 + i / 30))
        h.add(make_state(frame_idx=new_idx, cam_t=new_t))
        assert list(h.samples) == [(new_t, 0.0, 0.0)] and list(h.frames) == [(new_idx, new_t)]
        for k in range(1, 6):
            h.add(make_state(frame_idx=new_idx + k, cam_t=new_t + k / 30))
        assert camera_fps(h.frames) == pytest.approx(30.0)


def test_history_remembers_the_last_push():
    h = SlotHistory(1.0)
    h.add(make_state(frame_idx=1, t=5.0, push=Push("R", 2.3, (10.0, 20.0))))
    h.add(make_state(frame_idx=2, t=5.1))
    assert h.last_push.speed == 2.3 and h.last_push_t == 5.0


def test_camera_fps():
    assert camera_fps([(i, i / 30) for i in range(31)]) == pytest.approx(30.0)
    assert camera_fps([(0, 0.0)]) == 0.0 and camera_fps([]) == 0.0


def test_vz_to_y_puts_pushes_above_the_middle():
    r = Rect(0, 100, 200, 100)
    assert (vz_to_y(0.0, r, 4.0), vz_to_y(-4.0, r, 4.0), vz_to_y(4.0, r, 4.0)) == (150, 100, 200)
    assert vz_to_y(-9.0, r, 4.0) == 100  # clamped


def test_topdown_point_is_mirrored_like_the_players_view():
    r = Rect(0, 0, 200, 400)
    assert topdown_point(0.0, 0.0, r, 2.0, 4.0) == (100, 400)  # camera at the bottom center
    assert topdown_point(2.0, 4.0, r, 2.0, 4.0) == (0, 0)  # P1 (x > 0) is on the left
    assert topdown_point(-5.0, 9.0, r, 2.0, 4.0) == (200, 0)  # clamped


def test_draw_tracked_lost_and_pushing_players():
    pygame.init()
    try:
        surface = pygame.Surface((1920, 1080))
        surface.fill((50, 50, 50))
        overlay = DebugOverlay(CFG)
        push = Push("R", 2.3, (10.0, 20.0))
        states = {
            0: make_state(0, frame_idx=1, t=1.0, push=push),
            1: make_state(1, frame_idx=1, tracking_ok=False),
        }
        overlay.draw(surface, states, fps=60.0, dropped=2, now=1.1)
        assert tuple(surface.get_at((2, 2)))[:3] != (50, 50, 50)  # header panel at the top-left
        overlay.draw(surface, {}, fps=60.0, dropped=0, now=2.0)
    finally:
        pygame.quit()


def _intersects(a: Rect, b: Rect) -> bool:
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def test_map_does_not_cover_the_panels():
    pygame.init()
    try:
        line_h = pygame.font.Font(None, CFG["render"]["debug_overlay"]["font_px"]).get_linesize()
    finally:
        pygame.quit()
    header, panels, map_rect = overlay_rects(1920, 1080, CFG, line_h)
    screen = Rect(0, 0, 1920, 1080)
    assert len(panels) == 2
    for rect in (header, map_rect, *panels.values()):
        assert screen.contains(rect)
    for panel in panels.values():
        assert not _intersects(map_rect, panel)
