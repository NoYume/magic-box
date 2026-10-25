import pytest

from magic_box.render.camera_view import CropSmoother, crop_rect_for_bbox, map_point_to_dest
from magic_box.render.layout import Rect

IMG = (1280, 720)


@pytest.mark.parametrize(
    "bbox", [(600, 200, 100, 300), (0, 0, 50, 50), (1200, 600, 80, 120), (0, 0, 1280, 720)]
)
def test_crop_has_aspect_and_stays_in_image(bbox):
    r = crop_rect_for_bbox(bbox, (8, 9), 0.15, *IMG)
    assert abs(r.w * 9 - r.h * 8) <= 9
    assert r.x >= 0 and r.y >= 0 and r.x + r.w <= IMG[0] and r.y + r.h <= IMG[1]


def test_crop_contains_padded_bbox_when_it_fits():
    r = crop_rect_for_bbox((600, 200, 100, 300), (8, 9), 0.15, *IMG)
    assert r.contains(Rect(585, 155, 130, 390))


def test_smoother():
    s = CropSmoother(0.5)
    assert s.update(Rect(0, 0, 100, 100)) == Rect(0, 0, 100, 100)
    assert s.update(Rect(100, 0, 100, 100)) == Rect(50, 0, 100, 100)


def test_map_point_mirrors():
    crop, dest = Rect(100, 100, 200, 200), Rect(0, 0, 100, 100)
    assert map_point_to_dest((150.0, 200.0), crop, dest, mirror=False) == (25, 50)
    assert map_point_to_dest((150.0, 200.0), crop, dest, mirror=True) == (75, 50)


def test_selfview_skeleton_is_clipped_to_dest():
    import pygame

    from magic_box.core.contracts import SKELETON_EDGES
    from magic_box.render.camera_view import SKELETON_RGB, draw_selfview

    surface = pygame.Surface((400, 400))
    surface.fill((0, 0, 0))
    frame_surf = pygame.Surface((640, 360))
    frame_surf.fill((10, 10, 10))
    dest = Rect(100, 100, 50, 50)
    a, b = SKELETON_EDGES[0]
    keypoints = {a: (-3000.0, 300.0), b: (4000.0, 300.0)}  # line crosses the whole surface
    draw_selfview(surface, dest, frame_surf, Rect(0, 0, 640, 360), keypoints)
    inside = pygame.Rect(dest.as_tuple())
    drawn = [
        (x, y)
        for x in range(400)
        for y in range(400)
        if tuple(surface.get_at((x, y)))[:3] == SKELETON_RGB
    ]
    assert any(inside.collidepoint(p) for p in drawn)
    assert not [p for p in drawn if not inside.collidepoint(p)]


def _cfg(**over):
    base = {
        "camera_scale_quality": "fast",
        "self_view": True,
        "crop_cache": True,
        "crop_cache_px": 2,
    }
    return {**base, **over}


@pytest.fixture
def cv():
    from magic_box.render import camera_view

    camera_view.configure(_cfg())
    yield camera_view
    camera_view.configure(_cfg())


def test_crop_cache_reuses_while_crop_moves_less_than_threshold(cv):
    import pygame

    frame = pygame.Surface((640, 360))
    dest = Rect(0, 0, 50, 50)
    first = cv._scaled_crop(frame, dest, Rect(10, 10, 320, 320))
    assert cv._scaled_crop(frame, dest, Rect(10, 10, 320, 320)) is first
    assert cv._scaled_crop(frame, dest, Rect(11, 10, 320, 320)) is first  # moved 1 px < 2
    assert cv._scaled_crop(frame, dest, Rect(12, 10, 320, 320)) is not first  # 2 px: rescaled


def test_crop_cache_threshold_zero_needs_an_exact_match(cv):
    import pygame

    cv.configure(_cfg(crop_cache_px=0))
    frame = pygame.Surface((640, 360))
    dest = Rect(0, 0, 50, 50)
    first = cv._scaled_crop(frame, dest, Rect(10, 10, 320, 320))
    assert cv._scaled_crop(frame, dest, Rect(10, 10, 320, 320)) is first
    assert cv._scaled_crop(frame, dest, Rect(11, 10, 320, 320)) is not first


def test_crop_cache_new_frame_surface_invalidates(cv):
    import pygame

    dest, crop = Rect(0, 0, 50, 50), Rect(0, 0, 320, 320)
    first = cv._scaled_crop(pygame.Surface((640, 360)), dest, crop)
    assert cv._scaled_crop(pygame.Surface((640, 360)), dest, crop) is not first


def test_crop_cache_flip_has_its_own_entry(cv):
    import pygame

    frame = pygame.Surface((640, 360))
    dest, crop = Rect(0, 0, 50, 50), Rect(0, 0, 320, 320)
    plain = cv._scaled_crop(frame, dest, crop, flip=False)
    mirrored = cv._scaled_crop(frame, dest, crop, flip=True)
    assert mirrored is not plain
    assert cv._scaled_crop(frame, dest, crop, flip=False) is plain
    assert cv._scaled_crop(frame, dest, crop, flip=True) is mirrored


def test_crop_cache_keeps_one_entry_per_placement_and_is_bounded(cv):
    import pygame

    frame = pygame.Surface((640, 360))
    dest = Rect(0, 0, 50, 50)
    for x in range(0, 200, 5):  # a drifting crop never grows the cache
        cv._scaled_crop(frame, dest, Rect(x, 0, 320, 320))
    assert len(cv._cache) == 1
    for i in range(30):  # many distinct placements hit the safety cap
        cv._scaled_crop(frame, Rect(i, 0, 50, 50), Rect(0, 0, 320, 320))
    assert len(cv._cache) <= cv._CACHE_MAX_ENTRIES


def test_scale_quality_and_self_view_options(cv):
    import pygame

    cv.configure(_cfg(camera_scale_quality="smooth", self_view=False, crop_cache=False))
    frame = pygame.Surface((640, 360))
    dest, crop = Rect(0, 0, 50, 50), Rect(0, 0, 320, 320)
    a = cv._scaled_crop(frame, dest, crop)
    assert cv._scaled_crop(frame, dest, crop) is not a and a.get_size() == (50, 50)
    assert not cv._cache
    target = pygame.Surface((100, 100))
    target.fill((1, 2, 3))
    cv.draw_selfview(target, dest, frame, crop, {})
    assert tuple(target.get_at((10, 10)))[:3] == (1, 2, 3)  # self-view off draws nothing
