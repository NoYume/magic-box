// Scale- and rotation-invariant measurements of one hand.
//   world:   21 metric points (MediaPipe worldLandmarks, or synthetic) for finger shape
//   image3d: 21 camera-aligned isotropic points (pixels) for orientation relative to the camera

import { FINGERS, INDEX, MIDDLE, PINKY, THUMB, WRIST } from './landmarks.js';
import { SIGN } from './tuning.js';
import { angleBetween, cross, dist, dot, length, normalize, smoothstep, sub } from './vec.js';

export const palmSize = (points) => dist(points[WRIST], points[MIDDLE[0]]);

// 0 = fully curled, 1 = fully straight.
export function fingerExtension(world, [mcp, pip, dip, tip]) {
  const proximal = sub(world[pip], world[mcp]);
  const middle = sub(world[dip], world[pip]);
  const distal = sub(world[tip], world[dip]);
  const bend = angleBetween(proximal, middle) + angleBetween(middle, distal);
  const arc = length(proximal) + length(middle) + length(distal);
  const chord = dist(world[mcp], world[tip]) / Math.max(arc, 1e-9);
  const byBend = smoothstep(SIGN.BEND_CURLED, SIGN.BEND_OPEN, bend);
  const byChord = smoothstep(SIGN.CHORD_CURLED, SIGN.CHORD_OPEN, chord);
  return Math.min(byBend, byChord);
}

export function fingerExtensions(world) {
  const out = {};
  for (const [name, chain] of Object.entries(FINGERS)) out[name] = fingerExtension(world, chain);
  return out;
}

// 1 when the palm plane faces the camera (front or back), 0 when edge-on.
export function palmFacing(image3d) {
  const across = sub(image3d[PINKY[0]], image3d[INDEX[0]]);
  const up = sub(image3d[MIDDLE[0]], image3d[WRIST]);
  const normal = normalize(cross(across, up));
  return Math.abs(normal.z);
}

// Index-middle tip gap relative to palm size (small = fingers held together).
export const swordGap = (world) => dist(world[INDEX[3]], world[MIDDLE[3]]) / palmSize(world);

// How far the thumb tip rises past the knuckle line along the palm's up axis, relative to palm
// size (<= 0 when the thumb is wrapped over a fist, large for a thumbs-up).
export function thumbRise(world) {
  const up = normalize(sub(world[MIDDLE[0]], world[WRIST]));
  return dot(sub(world[THUMB[3]], world[MIDDLE[0]]), up) / palmSize(world);
}

// Rejects landmark sets that are not hand-shaped (bad detections): palm proportions and finger
// lengths relative to the palm must be anatomically plausible.
export function isPlausibleHand(world) {
  const palm = palmSize(world);
  if (!(palm > 0)) return false;
  const width = dist(world[INDEX[0]], world[PINKY[0]]) / palm;
  if (width < SIGN.PALM_WIDTH_RATIO[0] || width > SIGN.PALM_WIDTH_RATIO[1]) return false;
  return Object.values(FINGERS).every(([mcp, pip, dip, tip]) => {
    const arc = (dist(world[mcp], world[pip]) + dist(world[pip], world[dip]) + dist(world[dip], world[tip])) / palm;
    return arc >= SIGN.FINGER_LENGTH_RATIO[0] && arc <= SIGN.FINGER_LENGTH_RATIO[1];
  });
}

export function describeHand({ world, image3d }) {
  return {
    ext: fingerExtensions(world),
    facing: palmFacing(image3d),
    swordGap: swordGap(world),
    thumbRise: thumbRise(world),
  };
}
