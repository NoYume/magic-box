import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PHASE, PlayerCaster, measureThrust } from '../../src/game/caster.js';
import { createCombat } from '../../src/game/rules.js';
import { HandRoster } from '../../src/vision/roster.js';
import { FRAME_MS, observation } from '../helpers/hands.js';

// Runs a scripted sequence of frames for player 0 through roster + caster.
// frames: [{ pose, depth, cx?, cy? }] at 30 fps. Returns all casts and the last hand phases.
function play(frames, { charge = 0 } = {}) {
  const roster = new HandRoster();
  const caster = new PlayerCaster();
  const combat = createCombat();
  combat.players[0].charge = charge;
  const casts = [];
  const phases = [];
  frames.forEach((f, i) => {
    const tMs = i * FRAME_MS;
    const depth = 'depth' in f ? f.depth : 0.7;
    const obs = f.pose ? [observation(f.pose, { depth, placeDepth: f.placeDepth, cx: f.cx ?? 0.7, cy: f.cy ?? 0.5, seed: i + 1, noise: 0.002 })] : [];
    const { slots, triangles } = roster.update(obs, tMs);
    const out = caster.update({ hands: slots[0], triangle: triangles[0], tMs, player: combat.players[0], now: tMs });
    casts.push(...out.casts);
    phases.push([...out.handStates.values()].map((h) => h.phase)[0] ?? PHASE.IDLE);
  });
  return { casts, phases };
}

const hold = (pose, count, depth = 0.7) => Array.from({ length: count }, () => ({ pose, depth }));
// A thrust: hand moves toward the camera by `travel` meters over `count` frames.
const thrust = (pose, count, from = 0.7, travel = 0.2) =>
  Array.from({ length: count }, (_, i) => ({ pose, depth: from - (travel * (i + 1)) / count }));

test('should_cast_bolt_after_aim_sign_is_held_and_hand_thrusts', () => {
  const { casts, phases } = play([...hold('sword', 15), ...thrust('sword', 5), ...hold('sword', 5, 0.5)]);
  assert.equal(casts.length, 1);
  assert.equal(casts[0].type, 'bolt');
  assert.ok(phases.includes(PHASE.DETECTED) && phases.includes(PHASE.READY) && phases.includes(PHASE.CAST));
});

test('should_not_cast_when_thrust_comes_before_confirm_window', () => {
  const { casts } = play([...hold('sword', 4), ...thrust('sword', 4)]);
  assert.equal(casts.length, 0);
});

test('should_not_cast_from_casual_motion_without_aim_sign', () => {
  const casual = [
    ...hold('relaxed', 10), ...thrust('relaxed', 4), // reaching for something
    ...hold('open', 10), ...thrust('open', 4), // waving / pushing an open hand
    ...hold('fist', 12), ...thrust('fist', 4), // a punch
    ...hold('point', 12), ...thrust('point', 4), // pointing at the screen
    ...hold('claw', 10), ...thrust('claw', 5),
  ];
  assert.equal(play(casual).casts.length, 0);
});

test('should_not_cast_when_aimed_hand_drifts_slowly_toward_camera', () => {
  const { casts } = play([...hold('sword', 15), ...thrust('sword', 30, 0.8, 0.2)]);
  assert.equal(casts.length, 0);
});

test('should_not_cast_when_hands_leave_frame_mid_sequence', () => {
  const { casts } = play([...hold('sword', 15), ...Array(10).fill({}), ...thrust('sword', 4)]);
  assert.equal(casts.length, 0);
});

test('should_fire_once_per_thrust_and_respect_recock', () => {
  const { casts } = play([...hold('sword', 15), ...thrust('sword', 4), ...thrust('sword', 4, 0.5, 0.15)]);
  assert.equal(casts.length, 1);
});

test('should_report_charging_phase_while_fist_is_held', () => {
  const { phases } = play(hold('fist', 20));
  assert.equal(phases.at(-1), PHASE.CHARGING);
});

test('should_measure_approach_speed_over_window', () => {
  const history = [{ t: 0, z: 0.7 }, { t: 33, z: 0.65 }, { t: 66, z: 0.6 }, { t: 100, z: 0.55 }];
  const { speed, travel } = measureThrust(history, 100);
  assert.ok(Math.abs(travel - 0.15) < 1e-9);
  assert.ok(Math.abs(speed - 1.5) < 1e-9);
});

// Regression (review P1): a one-frame stereo dropout on a stationary armed hand fired a bolt.
test('should_not_cast_when_stereo_depth_drops_out_on_a_still_hand', () => {
  const dropout = { pose: 'sword', depth: null, placeDepth: 0.9 / 1.15 };
  const { casts } = play([...hold('sword', 18, 0.9), dropout, ...hold('sword', 2, 0.9), dropout, ...hold('sword', 8, 0.9)]);
  assert.equal(casts.length, 0);
});

// Regression (review P2): travel made while the aim sign was still confirming must not count.
test('should_only_count_thrust_travel_after_aim_is_armed', () => {
  const approach = Array.from({ length: 12 }, (_, i) => ({ pose: 'sword', depth: 0.9 - 0.03 * (i + 1) }));
  const { casts } = play([...hold('sword', 4, 0.9), ...approach, ...hold('sword', 12, 0.54)]);
  assert.equal(casts.length, 0);
});

// A sideways jab: player 0 sits on the left of the mirrored view, so toward the opponent is
// decreasing camera x. Depth stays put, like a finger gun swung at the other player.
const jab = (pose, count, from = 0.7, travel = 0.1) =>
  Array.from({ length: count }, (_, i) => ({ pose, cx: from - (travel * (i + 1)) / count }));

test('should_cast_bolt_on_sideways_jab_toward_opponent', () => {
  const { casts } = play([...hold('sword', 15), ...jab('sword', 4), ...hold('sword', 5).map((f) => ({ ...f, cx: 0.6 }))]);
  assert.equal(casts.length, 1);
});

// The ZED X lens is ~110 degrees wide: at 1 m, 0.045 of the view is ~13 cm, a firm finger-gun
// flick. The first ZED X debug log never saw a jab clear the old 0.06-width bar.
test('should_cast_bolt_on_a_short_jab_sized_for_the_zed_x_wide_lens', () => {
  const { casts } = play([...hold('sword', 15), ...jab('sword', 4, 0.7, 0.045), ...hold('sword', 5).map((f) => ({ ...f, cx: 0.655 }))]);
  assert.equal(casts.length, 1);
});

test('should_not_cast_on_slow_slide_or_jab_away_from_opponent', () => {
  const slow = play([...hold('sword', 15), ...jab('sword', 30, 0.7, 0.1)]);
  const away = play([...hold('sword', 15), ...jab('sword', 4, 0.7, -0.1)]);
  assert.equal(slow.casts.length + away.casts.length, 0);
});
