import assert from 'node:assert/strict';
import { test } from 'node:test';

import { measureThrust } from '../../src/game/caster.js';
import { REJECT, HandRoster } from '../../src/vision/roster.js';
import { FRAME_MS, observation } from '../helpers/hands.js';

test('should_assign_slots_by_mirrored_half_of_frame', () => {
  const roster = new HandRoster();
  // cam x 0.75 shows on the LEFT of the mirrored screen -> player 1 (slot 0).
  const { slots } = roster.update([observation('open', { cx: 0.75 }), observation('open', { cx: 0.25 })], 0);
  assert.equal(slots[0].length, 1);
  assert.equal(slots[1].length, 1);
  assert.ok(slots[0][0].view.x < 0.5);
});

test('should_ignore_bystander_beyond_play_depth', () => {
  const roster = new HandRoster();
  const { slots, rejected } = roster.update([observation('open', { depth: 2.4 })], 0);
  assert.equal(slots[0].length, 0);
  assert.equal(rejected[0].reason, REJECT.RANGE);
});

test('should_ignore_hand_partly_out_of_frame', () => {
  const roster = new HandRoster();
  const { slots, rejected } = roster.update([observation('open', { cx: 0.99 })], 0);
  assert.equal(slots[0].length, 0);
  assert.equal(rejected[0].reason, REJECT.EDGE);
});

test('should_keep_track_identity_while_hand_moves', () => {
  const roster = new HandRoster();
  const first = roster.update([observation('open', { cx: 0.7 })], 0).slots[0][0].id;
  const second = roster.update([observation('open', { cx: 0.72 })], FRAME_MS).slots[0][0].id;
  assert.equal(first, second);
});

test('should_keep_only_two_nearest_hands_per_player', () => {
  const roster = new HandRoster();
  const hands = [0.6, 0.8, 1.1].map((depth, i) => observation('open', { cx: 0.6 + i * 0.15, cy: 0.5, depth }));
  const { slots } = roster.update(hands, 0);
  assert.deepEqual(slots[0].map((h) => h.depth).sort(), [0.6, 0.8]);
});

test('should_smooth_sign_over_frames', () => {
  const roster = new HandRoster();
  const signs = [];
  for (let i = 0; i < 6; i++) signs.push(roster.update([observation('fist')], i * FRAME_MS).slots[0][0].sign);
  assert.deepEqual(signs, ['none', 'none', 'none', 'gather', 'gather', 'gather']);
});

// Regression from the first ZED X debug log: 30% of real frames failed the plausibility gate,
// mostly one frame at a time, and each one voted "none", so a sign rarely got the 4 of 6 votes
// it needs to start.
const unreadable = () => {
  const obs = observation('open');
  return { ...obs, world: obs.world.map((p) => ({ ...p, x: p.x * 0.2 })) }; // palm far too narrow
};

test('should_recognize_a_sign_when_every_other_frame_is_unreadable', () => {
  const roster = new HandRoster();
  const signs = [];
  for (let i = 0; i < 12; i++) {
    const frame = i % 2 === 0 ? observation('open') : unreadable();
    signs.push(roster.update([frame], i * FRAME_MS).slots[0][0].sign);
  }
  assert.equal(signs.at(-1), 'ward', signs.join(' '));
});

test('should_release_a_sign_after_a_long_unreadable_run', () => {
  const roster = new HandRoster();
  let t = 0;
  for (let i = 0; i < 6; i++) roster.update([observation('open')], (t += FRAME_MS));
  let sign;
  for (let i = 0; i < 9; i++) sign = roster.update([unreadable()], (t += FRAME_MS)).slots[0][0].sign;
  assert.equal(sign, 'none');
});

test('should_start_a_track_on_an_unreadable_frame_without_a_sign', () => {
  const roster = new HandRoster();
  const hand = roster.update([unreadable()], 0).slots[0][0];
  assert.equal(hand.sign, 'none');
});

test('should_not_flip_slot_when_hand_barely_crosses_seam', () => {
  const roster = new HandRoster();
  roster.update([observation('open', { cx: 0.55 })], 0); // view x 0.45 -> slot 0
  const { slots } = roster.update([observation('open', { cx: 0.49 })], FRAME_MS); // view x 0.51
  assert.equal(slots[0].length, 1);
});

// Regression (review P1): a stereo dropout must not fall back to palm-size depth.
test('should_report_unknown_depth_when_stereo_sample_drops_out', () => {
  const roster = new HandRoster();
  for (let i = 0; i < 6; i++) roster.update([observation('sword', { depth: 0.9 })], i * FRAME_MS);
  // The palm looks 15% larger than the 0.9 m it really is: palm-size depth would read ~0.78 m.
  const { slots } = roster.update([observation('sword', { depth: null, placeDepth: 0.9 / 1.15 })], 6 * FRAME_MS);
  assert.equal(slots[0].length, 1, 'the hand stays tracked through a dropout');
  assert.equal(slots[0][0].depth, null);
  const { travel } = measureThrust(slots[0][0].depthHistory, 6 * FRAME_MS);
  assert.equal(travel, 0);
});

test('should_reset_thrust_history_when_depth_source_changes', () => {
  const roster = new HandRoster();
  for (let i = 0; i < 4; i++) roster.update([observation('sword', { depth: 0.9 })], i * FRAME_MS);
  const { slots } = roster.update([observation('sword', { depth: null, placeDepth: 0.78, depthSource: 'palm' })], 4 * FRAME_MS);
  assert.equal(slots[0][0].depthHistory.length, 1);
});

// Regression (review P1): a different hand near an armed one must not inherit its state.
test('should_start_a_new_track_when_handedness_changes', () => {
  const roster = new HandRoster();
  let first;
  for (let i = 0; i < 8; i++) first = roster.update([observation('sword', { depth: 0.6 })], i * FRAME_MS).slots[0][0];
  assert.equal(first.sign, 'aim');
  const next = roster.update([observation('sword', { depth: 0.6, handedness: 'Left' })], 8 * FRAME_MS).slots[0][0];
  assert.notEqual(next.id, first.id);
  assert.equal(next.sign, 'none');
  assert.equal(next.depthHistory.length, 1);
});

test('should_start_a_new_track_when_depth_jumps', () => {
  const roster = new HandRoster();
  let first;
  for (let i = 0; i < 8; i++) first = roster.update([observation('sword', { depth: 0.55 })], i * FRAME_MS).slots[0][0];
  const next = roster.update([observation('sword', { depth: 1.0 })], 8 * FRAME_MS).slots[0][0];
  assert.notEqual(next.id, first.id);
  assert.equal(next.sign, 'none');
});

test('should_start_a_new_track_when_hand_changes_body', () => {
  const roster = new HandRoster();
  const owner = (slot) => ({ slotForHand: () => slot });
  let first;
  for (let i = 0; i < 8; i++) first = roster.update([observation('sword', { cx: 0.52 })], i * FRAME_MS, owner(0)).slots[0][0];
  const next = roster.update([observation('sword', { cx: 0.52 })], 8 * FRAME_MS, owner(1)).slots[1][0];
  assert.notEqual(next.id, first.id);
  assert.equal(next.sign, 'none');
});
