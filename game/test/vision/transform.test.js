import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createViewTransform } from '../../src/vision/transform.js';

const EPS = 1e-9;
const close = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-6, `${msg}: ${a} != ${b}`);

test('should_fill_wide_screen_by_cropping_top_and_bottom', () => {
  const t = createViewTransform({ srcW: 960, srcH: 600, dstW: 1920, dstH: 1080, mirror: false });
  close(t.scale, 2, 'scale');
  close(t.offsetX, 0, 'offsetX');
  close(t.offsetY, (1080 - 1200) / 2, 'offsetY');
});

test('should_fill_tall_screen_by_cropping_left_and_right', () => {
  const t = createViewTransform({ srcW: 1280, srcH: 720, dstW: 800, dstH: 900, mirror: false });
  close(t.scale, 1.25, 'scale');
  close(t.offsetX, (800 - 1600) / 2, 'offsetX');
  close(t.offsetY, 0, 'offsetY');
});

test('should_map_camera_center_to_screen_center_with_and_without_mirror', () => {
  for (const mirror of [true, false]) {
    const t = createViewTransform({ srcW: 1280, srcH: 720, dstW: 1000, dstH: 1000, mirror });
    const p = t.camToScreen(0.5, 0.5);
    close(p.x, 500, 'x');
    close(p.y, 500, 'y');
  }
});

test('should_mirror_camera_left_edge_to_screen_right', () => {
  const t = createViewTransform({ srcW: 1000, srcH: 500, dstW: 1000, dstH: 500, mirror: true });
  close(t.camToScreen(0, 0.5).x, 1000, 'left edge goes right');
  close(t.camToScreen(1, 0.5).x, 0, 'right edge goes left');
  close(t.camToScreen(0.25, 0.1).y, 50, 'y is not mirrored');
});

test('should_place_feed_sprite_so_its_pixels_match_camToScreen', () => {
  for (const mirror of [true, false]) {
    const srcW = 960;
    const srcH = 600;
    const t = createViewTransform({ srcW, srcH, dstW: 1366, dstH: 768, mirror });
    const f = t.feedPlacement();
    for (const [u, v] of [[0, 0], [0.2, 0.7], [1, 1]]) {
      // A sprite pixel at texture coords (u*srcW, v*srcH) lands at position + scale * coords.
      const spriteX = f.x + f.scaleX * u * srcW;
      const spriteY = f.y + f.scaleY * v * srcH;
      const p = t.camToScreen(u, v);
      close(spriteX, p.x, `x mirror=${mirror} u=${u}`);
      close(spriteY, p.y, `y mirror=${mirror} v=${v}`);
    }
  }
});

test('should_round_trip_screen_and_camera_coordinates', () => {
  const sizes = [[640, 480], [1920, 1080], [500, 1200]];
  for (const [dstW, dstH] of sizes) {
    for (const mirror of [true, false]) {
      const t = createViewTransform({ srcW: 1280, srcH: 720, dstW, dstH, mirror });
      for (const [u, v] of [[0.1, 0.9], [0.5, 0.5], [0.77, 0.03]]) {
        const s = t.camToScreen(u, v);
        const back = t.screenToCam(s.x, s.y);
        assert.ok(Math.abs(back.u - u) < EPS && Math.abs(back.v - v) < EPS);
      }
    }
  }
});

test('should_reject_degenerate_sizes', () => {
  assert.throws(() => createViewTransform({ srcW: 0, srcH: 720, dstW: 100, dstH: 100 }), RangeError);
});
