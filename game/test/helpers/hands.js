// Test helpers: canonical sign fixtures built on the shared synthetic hand generator.

import { POSES, addNoise, makeHand, placeHand, seededRandom } from '../../src/vision/synthetic-hand.js';

export const FRAME = { frameW: 1280, frameH: 720 };

// A classifier input ({ world, image3d }) for a named pose with optional rotation/noise.
export function handFixture(poseName, { noise = 0, seed = 1, cx = 0.3, cy = 0.5, depth = 0.7, ...orientation } = {}) {
  let world = makeHand(POSES[poseName], orientation);
  if (noise > 0) world = addNoise(world, noise, seededRandom(seed));
  const { image3d, landmarks } = placeHand(world, { cx, cy, depth, ...FRAME });
  return { world, image3d, landmarks };
}

// Orientation variations a real player produces while holding a sign toward the camera.
export const VARIATIONS = [
  {},
  { roll: 0.5 },
  { roll: -0.5 },
  { yaw: 0.35 },
  { pitch: 0.3 },
  { handedness: 'Left' },
  { handedness: 'Left', roll: 0.4, yaw: -0.3 },
  { size: 0.85 },
  { size: 1.15, roll: -0.3 },
];

export const NOISE_M = 0.003; // 3 mm landmark jitter
export const NOISE_SEEDS = [1, 2, 3, 4, 5];

// A roster observation (what a source + MediaPipe produce for one hand) with ZED-style depth.
export function observation(poseName, { cx = 0.7, cy = 0.5, depth = 0.7, handScore = 0.95, ...rest } = {}) {
  const { world, landmarks } = handFixture(poseName, { cx, cy, depth, ...rest });
  return { landmarks, world, handedness: rest.handedness ?? 'Right', handScore, ...FRAME, depth };
}

export const FRAME_MS = 33;
