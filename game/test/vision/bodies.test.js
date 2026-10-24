import assert from 'node:assert/strict';
import { test } from 'node:test';

import { BodyRoster } from '../../src/vision/bodies.js';
import { HandRoster } from '../../src/vision/roster.js';
import { makeBody } from '../../src/vision/synthetic-body.js';
import { observation } from '../helpers/hands.js';

test('should_seat_one_body_per_half_of_mirrored_frame', () => {
  const roster = new BodyRoster();
  const { slots } = roster.update([makeBody({ id: 4, cx: 0.75, z: 0.8 }), makeBody({ id: 9, cx: 0.25, z: 0.85 })]);
  assert.equal(slots[0].id, 4, 'camera-right person shows on the left: player I');
  assert.equal(slots[1].id, 9);
});

test('should_ignore_bystander_behind_and_keep_nearest_torso', () => {
  const roster = new BodyRoster();
  const { slots } = roster.update([makeBody({ id: 1, cx: 0.7, z: 0.9 }), makeBody({ id: 2, cx: 0.8, z: 2.4 })]);
  assert.equal(slots[0].id, 1);
  const crowd = roster.update([makeBody({ id: 2, cx: 0.8, z: 2.4 })]);
  assert.equal(crowd.slots[0], null, 'a person beyond the play depth never takes a slot');
});

test('should_ignore_body_partly_out_of_frame', () => {
  const roster = new BodyRoster();
  const { slots, rejected } = roster.update([makeBody({ id: 3, cx: 0.97, z: 0.8 })]);
  assert.equal(slots[0], null);
  assert.equal(rejected.length, 1);
});

test('should_keep_body_in_slot_until_it_clearly_crosses_the_seam', () => {
  const roster = new BodyRoster();
  roster.update([makeBody({ id: 5, cx: 0.55, z: 0.8 })]);
  const { slots } = roster.update([makeBody({ id: 5, cx: 0.49, z: 0.8 })]);
  assert.equal(slots[0]?.id, 5);
});

test('should_attach_hand_to_the_body_whose_wrist_is_nearest', () => {
  const hand = observation('open', { cx: 0.53, cy: 0.5 }); // just right of the seam in camera space
  const wrist = hand.landmarks[0];
  // Player II's body is on the camera's left, but their arm reaches across to this wrist.
  const bodies = new BodyRoster();
  bodies.update([makeBody({ id: 1, cx: 0.75, z: 0.8 }), makeBody({ id: 2, cx: 0.3, z: 0.8, wrists: { r: { ...wrist } } })]);
  const hands = new HandRoster();
  const { slots } = hands.update([hand], 0, bodies);
  assert.equal(slots[1].length, 1, 'follows the wrist, not the half');
  assert.equal(slots[0].length, 0);
});
