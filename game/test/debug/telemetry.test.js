import assert from 'node:assert/strict';
import { test } from 'node:test';

import { Telemetry, buildRecord } from '../../src/debug/telemetry.js';

const landmarks = Array.from({ length: 21 }, (_, i) => ({ x: 0.123456 + i / 100, y: 0.5, z: -0.01 }));

function fixtureView() {
  const hand = {
    id: 3,
    handedness: 'Right',
    handScore: 0.9876,
    sign: 'ward',
    frameSign: 'ward',
    frameScore: 0.81234,
    agreement: 0.6667,
    scores: { ward: 0.81234, gather: 0.01, aim: 0.2 },
    features: { ext: { index: 0.9, middle: 0.95, ring: 0.88, pinky: 0.7 }, facing: 0.6234, thumbRise: 0.4 },
    depth: 0.54321,
    depthSource: 'stereo',
    bodySlot: 0,
    landmarks,
  };
  const body = { id: 7, torso: { x: 0.3, y: 0.4, z: 0.87654, width: 0.2 }, kp: {} };
  return {
    slots: [[hand], []],
    rejected: [{ reason: 'out of play range', handedness: 'Left', handScore: 0.7, depth: null, landmarks }],
    triangles: [{ active: false, score: 0.1234 }, { active: false }],
    casters: [{ handStates: new Map([[3, { phase: 'detected' }]]) }, null],
    bodies: [body, null],
    postures: [{ stance: 'neutral', leanOffset: -0.01234, lateral: 0.0567 }, null],
    rejectedBodies: [{ id: 9, kp: {} }],
  };
}

test('should_build_a_compact_record_of_what_the_vision_pipeline_saw', () => {
  const record = buildRecord({ seq: 42, tMs: 1234.56, view: fixtureView(), flow: { phase: 'attract' }, stats: { render: 59.7, hands: 28.44 }, mirror: true });
  assert.equal(record.type, 'debug');
  assert.equal(record.seq, 42);
  assert.equal(record.mirror, true);
  assert.equal(record.t, 1235);
  assert.equal(record.phase, 'attract');
  assert.deepEqual(record.stats, { render: 59.7, hands: 28.4 });
  const [hand] = record.hands;
  assert.equal(hand.slot, 0);
  assert.equal(hand.phase, 'detected');
  assert.equal(hand.frameScore, 0.81);
  assert.deepEqual(hand.scores, { ward: 0.81, gather: 0.01, aim: 0.2 });
  assert.deepEqual(hand.ext, { index: 0.9, middle: 0.95, ring: 0.88, pinky: 0.7 });
  assert.equal(hand.facing, 0.62);
  assert.equal(hand.depth, 0.543);
  assert.equal(hand.lm.length, 21);
  assert.deepEqual(hand.lm[0], [0.123, 0.5]);
  assert.deepEqual(record.rejected[0].reason, 'out of play range');
  assert.equal(record.rejected[0].depth, null);
  assert.deepEqual(record.triangles, [0.12, null]);
  assert.deepEqual(record.bodies, [{ id: 7, z: 0.877, stance: 'neutral', lean: -0.012, side: 0.06 }, null]);
  assert.deepEqual(record.rejectedBodies, [9]);
  assert.doesNotThrow(() => JSON.stringify(record));
});

test('should_send_records_only_while_enabled_and_marks_any_time', () => {
  const sent = [];
  const telemetry = new Telemetry((message) => sent.push(message) > 0);
  const args = { seq: 1, tMs: 0, view: fixtureView(), flow: { phase: 'fight' }, stats: {} };
  telemetry.record(args);
  assert.equal(sent.length, 0);
  telemetry.toggle();
  telemetry.record(args);
  assert.equal(sent.length, 1);
  telemetry.mark(5, 100);
  assert.deepEqual(sent[1], { type: 'mark', seq: 5, t: 100 });
  assert.equal(telemetry.marks, 1);
});

test('should_stay_off_without_a_transport', () => {
  const telemetry = new Telemetry(undefined, { enabled: true });
  assert.equal(telemetry.enabled, false);
  telemetry.toggle();
  assert.equal(telemetry.enabled, false);
  assert.doesNotThrow(() => telemetry.mark(1, 1));
});
