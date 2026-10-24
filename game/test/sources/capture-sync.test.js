import assert from 'node:assert/strict';
import { test } from 'node:test';

import { CaptureSync } from '../../src/sources/capture-sync.js';

// Regression (review P1): JPEG decoding is async, so the depth map of a later capture used to be
// paired with an earlier frame's hands. Frame, depth and bodies now travel as one capture.
test('should_pair_a_decoded_frame_with_its_own_depth_and_bodies', () => {
  const sync = new CaptureSync();
  sync.addDepth(1, 'depth-1');
  sync.addBodies(1, ['body-1']);
  sync.addDepth(2, 'depth-2'); // arrives while frame 1 is still decoding
  sync.addBodies(2, ['body-2']);
  assert.deepEqual(sync.takeFrame(1), { depth: 'depth-1', bodies: ['body-1'] });
  assert.deepEqual(sync.takeFrame(2), { depth: 'depth-2', bodies: ['body-2'] });
});

test('should_drop_depth_and_bodies_of_skipped_frames', () => {
  const sync = new CaptureSync();
  for (const seq of [1, 2, 3]) {
    sync.addDepth(seq, `depth-${seq}`);
    sync.addBodies(seq, [`body-${seq}`]);
  }
  assert.deepEqual(sync.takeFrame(3), { depth: 'depth-3', bodies: ['body-3'] });
  assert.equal(sync.pendingCount, 0, 'captures 1 and 2 were dropped with their frames');
  assert.deepEqual(sync.takeFrame(2), { depth: null, bodies: null }, 'a late frame never gets newer data');
});

test('should_report_missing_depth_when_a_capture_has_none', () => {
  const sync = new CaptureSync();
  sync.addDepth(5, 'depth-5');
  assert.deepEqual(sync.takeFrame(4), { depth: null, bodies: null });
  assert.equal(sync.takeFrame(5).depth, 'depth-5');
});

test('should_bound_pending_captures', () => {
  const sync = new CaptureSync({ maxPending: 4 });
  for (let seq = 1; seq <= 20; seq++) sync.addDepth(seq, seq);
  assert.ok(sync.pendingCount <= 4);
});
