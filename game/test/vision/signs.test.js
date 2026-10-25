import assert from 'node:assert/strict';
import { test } from 'node:test';

import { SIGNS, SignSmoother, classifyHand, scoreSigns, scoreTriangle } from '../../src/vision/signs.js';
import { makeHand, makeTrianglePair, placeHand } from '../../src/vision/synthetic-hand.js';
import { SIGN } from '../../src/vision/tuning.js';
import { vec } from '../../src/vision/vec.js';
import { FRAME, NOISE_M, NOISE_SEEDS, VARIATIONS, handFixture } from '../helpers/hands.js';

const CANONICAL = { open: SIGNS.WARD, fist: SIGNS.GATHER, sword: SIGNS.AIM, peace: SIGNS.AIM };
const NEGATIVES = ['point', 'claw', 'relaxed', 'thumbsUp', 'rock'];

for (const [pose, expected] of Object.entries(CANONICAL)) {
  test(`should_classify_${pose}_as_${expected}_across_orientations_and_noise`, () => {
    for (const variation of VARIATIONS) {
      for (const seed of NOISE_SEEDS) {
        const result = classifyHand(handFixture(pose, { ...variation, noise: NOISE_M, seed }));
        assert.equal(result.sign, expected, `${pose} ${JSON.stringify(variation)} seed ${seed}: ${JSON.stringify(result.scores)}`);
      }
    }
  });
}

for (const pose of NEGATIVES) {
  test(`should_not_classify_${pose}_as_any_sign`, () => {
    for (const variation of VARIATIONS) {
      for (const seed of NOISE_SEEDS) {
        const result = classifyHand(handFixture(pose, { ...variation, noise: NOISE_M, seed }));
        assert.equal(result.sign, SIGNS.NONE, `${pose} ${JSON.stringify(variation)} seed ${seed}: ${JSON.stringify(result.scores)}`);
      }
    }
  });
}

// Regressions from the first ZED X debug log (logs/20261024-235023): this is how real hands read.
test('should_aim_when_the_ring_finger_only_half_folds', () => {
  const world = makeHand({ curls: [0, 0, 0.48, 0.75], thumb: 0.95, spread: 0 });
  const { image3d } = placeHand(world, { cx: 0.3, cy: 0.5, depth: 0.7, ...FRAME });
  assert.equal(classifyHand({ world, image3d }).sign, SIGNS.AIM);
  // seq 5435 of that log: index and middle out, ring half folded, scored 0.51 before
  const scores = scoreSigns({ ext: { index: 0.91, middle: 0.92, ring: 0.49, pinky: 0.25 }, facing: 0.97, thumbRise: -0.01 });
  assert.ok(scores.aim >= SIGN.MIN_SCORE, JSON.stringify(scores));
});

test('should_gather_when_the_fist_thumb_rests_beside_the_knuckles', () => {
  const fist = { ext: { index: 0, middle: 0, ring: 0, pinky: 0 }, facing: 0.94 };
  assert.ok(scoreSigns({ ...fist, thumbRise: 0.2 }).gather >= SIGN.MIN_SCORE);
  assert.ok(scoreSigns({ ...fist, thumbRise: 0.37 }).gather < SIGN.MIN_SCORE, 'a thumbs-up stays out');
});

test('should_not_ward_when_open_palm_is_edge_on_to_camera', () => {
  for (const yaw of [1.2, -1.3, 1.5]) {
    assert.equal(classifyHand(handFixture('open', { yaw })).sign, SIGNS.NONE, `yaw ${yaw}`);
  }
});

test('should_not_classify_random_landmark_clouds', () => {
  let seed = 11;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 200; i++) {
    const world = Array.from({ length: 21 }, () => vec(rand() * 0.15, rand() * 0.15, rand() * 0.05));
    const { image3d } = placeHand(world, { cx: 0.5, cy: 0.5, depth: 0.7, ...FRAME });
    const result = classifyHand({ world, image3d });
    assert.equal(result.sign, SIGNS.NONE, JSON.stringify(result.scores));
  }
});

function trianglePair(separation = 0, { depths = [0.7, 0.7], zShift = 0 } = {}) {
  const { left, right } = makeTrianglePair();
  const shift = (points, dx) => points.map((p) => vec(p.x + dx, p.y, p.z));
  const opts = { cx: 0.5, cy: 0.5, depth: 0.7, ...FRAME, anchor: vec() };
  const a = shift(left, -separation);
  const b = shift(right, separation);
  return [
    { world: a, image3d: placeHand(a, opts).image3d, depth: depths[0] },
    { world: b, image3d: placeHand(b, opts).image3d.map((p) => vec(p.x, p.y, p.z + zShift)), depth: depths[1] },
  ];
}

test('should_score_touching_diamond_as_ultimate_triangle', () => {
  assert.ok(scoreTriangle(...trianglePair()) > 0.9);
});

test('should_reject_triangle_when_hands_are_apart', () => {
  assert.equal(scoreTriangle(...trianglePair(0.05)), 0);
});

// Regression (review P2): MediaPipe z is relative to each hand's own wrist, so it can't be
// compared across hands. Touch is tested in 2D; metric depth decides whether the hands meet.
test('should_accept_touching_diamond_regardless_of_per_hand_relative_z', () => {
  assert.ok(scoreTriangle(...trianglePair(0, { zShift: 400 })) > 0.9);
});

test('should_reject_diamond_when_hands_are_at_different_metric_depths', () => {
  assert.equal(scoreTriangle(...trianglePair(0, { depths: [0.5, 0.9] })), 0);
});

test('should_reject_diamond_when_a_hand_has_no_metric_depth', () => {
  assert.equal(scoreTriangle(...trianglePair(0, { depths: [0.7, null] })), 0);
});

test('should_reject_two_open_palms_side_by_side_as_triangle', () => {
  const a = handFixture('open', { cx: 0.45 });
  const b = handFixture('open', { cx: 0.55, handedness: 'Left' });
  assert.equal(scoreTriangle(a, b), 0);
});

test('smoother_should_require_majority_before_switching', () => {
  const s = new SignSmoother();
  const out = ['aim', 'aim', 'aim', 'aim'].map((x) => s.push(x));
  assert.deepEqual(out, ['none', 'none', 'none', 'aim']);
});

test('smoother_should_ignore_single_frame_flicker', () => {
  const s = new SignSmoother();
  for (let i = 0; i < 6; i++) s.push('ward');
  assert.equal(s.push('gather'), 'ward');
  assert.equal(s.push('ward'), 'ward');
});

test('smoother_should_hold_current_sign_with_hysteresis_then_release', () => {
  const s = new SignSmoother();
  for (let i = 0; i < 6; i++) s.push('aim');
  const seq = ['none', 'none', 'none', 'none', 'none'].map((x) => s.push(x));
  assert.deepEqual(seq, ['aim', 'aim', 'aim', 'aim', 'none']);
});
