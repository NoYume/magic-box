import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PostureDetector, STANCE } from '../../src/vision/posture.js';
import { makeBody } from '../../src/vision/synthetic-body.js';

const FRAME_MS = 33;
const NEUTRAL_Z = 0.85;
const CX = 0.72;

// Feeds a list of { z, cx } torso samples at 30 fps after a calibrated neutral.
function run(samples, { seed = 3 } = {}) {
  const detector = new PostureDetector();
  let s = seed;
  const noise = () => ((s = (s * 16807) % 2147483647) / 2147483647 - 0.5) * 0.01; // +-5 mm / +-0.005
  let t = 0;
  for (let i = 0; i < 15; i++, t += FRAME_MS) detector.update(makeBody({ cx: CX, z: NEUTRAL_Z }).kp, t);
  detector.calibrate();
  const out = [];
  for (const { z = NEUTRAL_Z, cx = CX } of samples) {
    out.push(detector.update(makeBody({ cx: cx + noise() * 0.2, z: z + noise() }).kp, t));
    t += FRAME_MS;
  }
  return out;
}

const hold = (n, sample) => Array.from({ length: n }, () => sample);
const ramp = (n, from, to, key) => Array.from({ length: n }, (_, i) => ({ [key]: from + ((to - from) * (i + 1)) / n }));
const stances = (out) => [...new Set(out.map((o) => o.stance))];
const dodges = (out) => out.filter((o) => o.dodge !== 0);

test('should_detect_held_lean_in_after_hold_time', () => {
  const out = run([...ramp(5, NEUTRAL_Z, NEUTRAL_Z - 0.18, 'z'), ...hold(15, { z: NEUTRAL_Z - 0.18 })]);
  assert.equal(out.at(-1).stance, STANCE.LEAN_IN);
  assert.equal(out[3].stance, STANCE.NEUTRAL, 'not instantly');
});

test('should_detect_lean_back_and_release_with_hysteresis', () => {
  const out = run([...hold(15, { z: NEUTRAL_Z + 0.15 }), ...hold(10, { z: NEUTRAL_Z + 0.08 }), ...hold(15, { z: NEUTRAL_Z })]);
  assert.equal(out[14].stance, STANCE.LEAN_BACK);
  assert.equal(out[24].stance, STANCE.LEAN_BACK, 'inside the hysteresis band it stays braced');
  assert.equal(out.at(-1).stance, STANCE.NEUTRAL);
});

test('should_ignore_casual_sway_and_breathing', () => {
  const sway = Array.from({ length: 150 }, (_, i) => ({ z: NEUTRAL_Z + 0.06 * Math.sin(i / 9), cx: CX + 0.02 * Math.sin(i / 13) }));
  const out = run(sway);
  assert.deepEqual(stances(out), [STANCE.NEUTRAL]);
  assert.equal(dodges(out).length, 0);
});

test('should_ignore_brief_lean_shorter_than_hold', () => {
  const out = run([...hold(3, { z: NEUTRAL_Z - 0.2 }), ...hold(15, { z: NEUTRAL_Z })]);
  assert.deepEqual(stances(out), [STANCE.NEUTRAL]);
});

test('should_dodge_once_on_quick_sideways_shift', () => {
  const out = run([...ramp(5, CX, CX + 0.12, 'cx'), ...hold(20, { cx: CX + 0.12 })]);
  assert.equal(dodges(out).length, 1);
  assert.equal(dodges(out)[0].dodge, 1);
});

test('should_not_dodge_on_slow_drift_to_the_side', () => {
  const out = run([...ramp(90, CX, CX + 0.12, 'cx'), ...hold(10, { cx: CX + 0.12 })]);
  assert.equal(dodges(out).length, 0);
});

test('should_rearm_dodge_only_after_returning_to_center', () => {
  const out = run([
    ...ramp(4, CX, CX + 0.12, 'cx'), ...hold(10, { cx: CX + 0.12 }),
    ...ramp(4, CX + 0.12, CX + 0.07, 'cx'), ...hold(10, { cx: CX + 0.07 }), // part way back: still disarmed
    ...ramp(4, CX + 0.07, CX + 0.12, 'cx'), ...hold(10, { cx: CX + 0.12 }),
    ...ramp(20, CX + 0.12, CX, 'cx'), ...hold(20, {}), // back to center: re-armed
    ...ramp(4, CX, CX - 0.12, 'cx'), ...hold(10, { cx: CX - 0.12 }),
  ]);
  assert.deepEqual(dodges(out).map((o) => o.dodge), [1, -1]);
});

test('should_report_untracked_without_shoulders', () => {
  const detector = new PostureDetector();
  assert.equal(detector.update({ neck: { x: 0.5, y: 0.4, z: 0.8 } }, 0).isTracked, false);
});
