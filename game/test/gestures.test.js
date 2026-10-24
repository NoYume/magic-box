import assert from 'node:assert/strict';
import { test } from 'node:test';

import { GestureDetector } from '../src/gestures.js';

const FRAME_MS = 33;

function pose({ z = 2, lWristZ = z, rWristZ = z, wristY = 0.5 } = {}) {
  return {
    head: { x: 0.5, y: 0.2, z },
    neck: { x: 0.5, y: 0.3, z },
    pelvis: { x: 0.5, y: 0.55, z },
    l_shoulder: { x: 0.45, y: 0.3, z },
    r_shoulder: { x: 0.55, y: 0.3, z },
    l_wrist: { x: 0.4, y: wristY, z: lWristZ },
    r_wrist: { x: 0.6, y: wristY, z: rWristZ },
  };
}

function run(detector, poses) {
  return poses.flatMap((kp, i) => detector.update(kp, i * FRAME_MS));
}

test('should_emit_forward_stance_when_player_steps_toward_camera', () => {
  const events = run(new GestureDetector(), [pose({ z: 2 }), pose({ z: 2 }), pose({ z: 1.5 })]);
  assert.deepEqual(events, [{ type: 'stance', stance: 'forward' }]);
});

test('should_emit_back_stance_then_neutral_when_player_returns', () => {
  const events = run(new GestureDetector(), [pose({ z: 2 }), pose({ z: 2.5 }), pose({ z: 2.05 })]);
  assert.deepEqual(events.map((e) => e.stance), ['back', 'neutral']);
});

test('should_ignore_depth_jitter_below_threshold', () => {
  const jitter = [2, 2.1, 1.9, 2.15, 1.85, 2].map((z) => pose({ z }));
  assert.deepEqual(run(new GestureDetector(), jitter), []);
});

test('should_emit_push_when_wrist_thrusts_toward_camera', () => {
  const thrust = [2, 2, 1.9, 1.8, 1.7].map((w) => pose({ rWristZ: w }));
  const pushes = run(new GestureDetector(), thrust).filter((e) => e.type === 'push');
  assert.equal(pushes.length, 1);
  assert.equal(pushes[0].hand, 'r');
  assert.ok(pushes[0].power > 2.5);
});

test('should_not_emit_push_for_slow_hand_movement', () => {
  const slow = [2, 1.99, 1.98, 1.97, 1.96].map((w) => pose({ lWristZ: w }));
  assert.equal(run(new GestureDetector(), slow).filter((e) => e.type === 'push').length, 0);
});

test('should_emit_hands_up_once_after_hold', () => {
  const held = Array.from({ length: 30 }, () => pose({ wristY: 0.1 }));
  assert.deepEqual(run(new GestureDetector(), held).filter((e) => e.type === 'handsUp'), [{ type: 'handsUp' }]);
});
