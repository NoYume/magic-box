import assert from 'node:assert/strict';
import { test } from 'node:test';

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

test('should_not_flip_slot_when_hand_barely_crosses_seam', () => {
  const roster = new HandRoster();
  roster.update([observation('open', { cx: 0.55 })], 0); // view x 0.45 -> slot 0
  const { slots } = roster.update([observation('open', { cx: 0.49 })], FRAME_MS); // view x 0.51
  assert.equal(slots[0].length, 1);
});
