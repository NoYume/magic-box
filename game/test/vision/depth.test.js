import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  ProtocolError, calibrationScale, depthFromPalmSize, encodeDepthMessage, handDepthFromMap, isInPlayRange,
  parseBinaryMessage, sampleDepth,
} from '../../src/vision/depth.js';
import { handFixture } from '../helpers/hands.js';

function flatMap(width, height, mm) {
  return { width, height, data: new Uint16Array(width * height).fill(mm) };
}

test('should_round_trip_depth_message_through_wire_format', () => {
  const data = Uint16Array.from({ length: 12 }, (_, i) => 500 + i);
  const parsed = parseBinaryMessage(encodeDepthMessage(4, 3, data));
  assert.equal(parsed.type, 'depth');
  assert.equal(parsed.width, 4);
  assert.equal(parsed.height, 3);
  assert.deepEqual([...parsed.data], [...data]);
});

test('should_split_jpeg_frame_message', () => {
  const buffer = Uint8Array.from([0x01, 0xff, 0xd8, 0xff]).buffer;
  const parsed = parseBinaryMessage(buffer);
  assert.equal(parsed.type, 'frame');
  assert.deepEqual([...parsed.jpeg], [0xff, 0xd8, 0xff]);
});

test('should_reject_unknown_and_truncated_messages', () => {
  assert.throws(() => parseBinaryMessage(Uint8Array.from([0x07, 1]).buffer), ProtocolError);
  const short = encodeDepthMessage(4, 3, new Uint16Array(12)).slice(0, 20);
  assert.throws(() => parseBinaryMessage(short), ProtocolError);
});

test('should_take_median_of_patch_ignoring_invalid_pixels', () => {
  const map = flatMap(5, 5, 0);
  // 3x3 patch around (2, 2): five valid values, four invalid (0).
  [[1, 1, 700], [2, 1, 710], [3, 1, 2000], [1, 2, 690], [2, 2, 705]].forEach(([x, y, mm]) => (map.data[y * 5 + x] = mm));
  assert.equal(sampleDepth(map, 0.5, 0.5), 0.705);
});

test('should_return_null_when_patch_has_no_depth', () => {
  assert.equal(sampleDepth(flatMap(8, 8, 0), 0.5, 0.5), null);
});

test('should_clamp_patch_at_image_border', () => {
  assert.equal(sampleDepth(flatMap(8, 8, 900), 0, 0), 0.9);
  assert.equal(sampleDepth(flatMap(8, 8, 900), 0.999, 0.999), 0.9);
});

test('should_read_hand_depth_from_palm_landmarks', () => {
  const map = flatMap(160, 100, 2400); // wall
  const hand = handFixture('open', { cx: 0.3, cy: 0.5 });
  for (let y = 30; y < 70; y++) for (let x = 30; x < 70; x++) map.data[y * 160 + x] = 650; // hand blob
  assert.equal(handDepthFromMap(map, hand.landmarks), 0.65);
});

test('should_estimate_closer_depth_for_bigger_apparent_palm', () => {
  const far = handFixture('open', { depth: 1.0 });
  const near = handFixture('open', { depth: 0.5 });
  const dFar = depthFromPalmSize(far.image3d, 1280);
  const dNear = depthFromPalmSize(near.image3d, 1280);
  assert.ok(Math.abs(dFar / dNear - 2) < 0.01);
  const k = calibrationScale(dFar);
  assert.ok(Math.abs(dNear * k - 0.375) < 0.01, 'calibrated at 0.75 m, half distance reads 0.375 m');
});

test('should_gate_bystanders_by_play_range', () => {
  assert.equal(isInPlayRange(0.8), true);
  assert.equal(isInPlayRange(2.4), false);
  assert.equal(isInPlayRange(null), false);
});
