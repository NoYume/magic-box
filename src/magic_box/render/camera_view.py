"""Camera image to screen: opponent crop, mirrored self-view, crop math (spec section 9).

Owner: Nikhil
"""

from collections.abc import Mapping, Sequence

import pygame

from magic_box.core.contracts import SKELETON_EDGES, Frame, Px
from magic_box.render.layout import Rect

SKELETON_RGB = (80, 255, 160)
SKELETON_WIDTH = 3


def crop_rect_for_bbox(
    bbox_px: tuple[int, int, int, int],
    aspect: Sequence[int],
    padding: float,
    image_w: int,
    image_h: int,
) -> Rect:
    """Crop around a padded bbox with the target aspect, kept inside the image."""
    aw, ah = aspect[0], aspect[1]
    x, y, w, h = bbox_px
    cx, cy = x + w / 2, y + h / 2
    w, h = w * (1 + 2 * padding), h * (1 + 2 * padding)
    if w * ah < h * aw:  # too narrow: grow width
        w = h * aw / ah
    else:  # too wide: grow height
        h = w * ah / aw
    scale = min(1.0, image_w / w, image_h / h)
    w, h = w * scale, h * scale
    ih = min(image_h, max(1, round(h)))
    iw = round(ih * aw / ah)
    if iw > image_w:
        iw = image_w
        ih = round(iw * ah / aw)
    ix = min(max(round(cx - iw / 2), 0), image_w - iw)
    iy = min(max(round(cy - ih / 2), 0), image_h - ih)
    return Rect(ix, iy, iw, ih)


class CropSmoother:
    """Exponential moving average over crop rectangles."""

    def __init__(self, alpha: float) -> None:
        self.alpha = alpha
        self._state: tuple[float, float, float, float] | None = None

    def update(self, target: Rect) -> Rect:
        t = tuple(float(v) for v in target.as_tuple())
        if self._state is None:
            self._state = t  # type: ignore[assignment]
        else:
            a = self.alpha
            self._state = tuple(s + a * (v - s) for s, v in zip(self._state, t, strict=True))  # type: ignore[assignment]
        x, y, w, h = (round(v) for v in self._state)
        return Rect(x, y, w, h)


def map_point_to_dest(p: Px, crop: Rect, dest: Rect, mirror: bool) -> tuple[int, int]:
    """Map an image pixel inside `crop` to a screen pixel inside `dest`."""
    u = (p[0] - crop.x) / crop.w
    v = (p[1] - crop.y) / crop.h
    if mirror:
        u = 1.0 - u
    return round(dest.x + u * dest.w), round(dest.y + v * dest.h)


def frame_to_surface(frame: Frame) -> pygame.Surface:
    h, w = frame.image.shape[:2]
    return pygame.image.frombuffer(frame.image, (w, h), "BGRA")


_opts: dict = {"smooth": False, "self_view": True, "crop_cache": True, "crop_cache_px": 2}
# One entry per placement (dest rect and mirroring): (crop tuple, scaled surface). Tied to
# `_cache_owner`, the frame surface they were cut from; a new frame surface empties it.
_cache: dict[tuple, tuple[tuple[int, int, int, int], pygame.Surface]] = {}
_cache_owner: pygame.Surface | None = None
_CACHE_MAX_ENTRIES = 8  # safety net; normally at most 4 (two opponent crops, two self-views)


def configure(render_cfg: Mapping) -> None:
    """Apply the Jetson fps fallbacks: `camera_scale_quality`, `self_view`, `crop_cache*`."""
    _opts["smooth"] = render_cfg["camera_scale_quality"] == "smooth"
    _opts["self_view"] = bool(render_cfg["self_view"])
    _opts["crop_cache"] = bool(render_cfg["crop_cache"])
    _opts["crop_cache_px"] = render_cfg["crop_cache_px"]
    _cache.clear()


def _crop_close(a: tuple[int, int, int, int], b: tuple[int, int, int, int], tol: float) -> bool:
    moved = max(abs(p - q) for p, q in zip(a, b, strict=True))
    return moved == 0 or moved < tol


def _scaled_crop(
    frame_surf: pygame.Surface, dest: Rect, crop: Rect, flip: bool = False
) -> pygame.Surface:
    """Scaled (and optionally mirrored) crop.

    The smoothed crop rect drifts a little every drawn frame, so an exact-match key would
    rarely hit. An entry is reused while the frame surface is the same and the crop moved
    less than `render.crop_cache_px` in every coordinate.
    """
    global _cache_owner
    key = (dest.x, dest.y, dest.w, dest.h, flip)
    crop_t = crop.as_tuple()
    if _opts["crop_cache"]:
        if _cache_owner is not frame_surf:
            _cache.clear()
            _cache_owner = frame_surf
        hit = _cache.get(key)
        if hit is not None and _crop_close(hit[0], crop_t, _opts["crop_cache_px"]):
            return hit[1]
    clipped = pygame.Rect(crop_t).clip(frame_surf.get_rect())
    scale = pygame.transform.smoothscale if _opts["smooth"] else pygame.transform.scale
    out = scale(frame_surf.subsurface(clipped), (dest.w, dest.h))
    if flip:
        out = pygame.transform.flip(out, True, False)
    if _opts["crop_cache"]:
        if len(_cache) >= _CACHE_MAX_ENTRIES and key not in _cache:
            _cache.clear()
        _cache[key] = (crop_t, out)
    return out


def draw_opponent(surface, dest: Rect, frame_surf, crop: Rect) -> None:
    surface.blit(_scaled_crop(frame_surf, dest, crop), (dest.x, dest.y))


def draw_selfview(
    surface, dest: Rect, frame_surf, crop: Rect, keypoints_px: Mapping[str, Px]
) -> None:
    """Mirrored view of the viewer (like a mirror), with the skeleton on top."""
    if not _opts["self_view"]:
        return
    old_clip = surface.get_clip()
    surface.set_clip(pygame.Rect(dest.as_tuple()))  # keypoints can fall outside the image
    try:
        surface.blit(_scaled_crop(frame_surf, dest, crop, flip=True), (dest.x, dest.y))
        for a, b in SKELETON_EDGES:
            if a in keypoints_px and b in keypoints_px:
                pygame.draw.line(
                    surface,
                    SKELETON_RGB,
                    map_point_to_dest(keypoints_px[a], crop, dest, mirror=True),
                    map_point_to_dest(keypoints_px[b], crop, dest, mirror=True),
                    SKELETON_WIDTH,
                )
    finally:
        surface.set_clip(old_clip)
