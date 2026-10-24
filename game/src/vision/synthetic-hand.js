// Generates plausible 21-point hand poses (MediaPipe layout) from a few parameters.
// Used by unit tests (sign fixtures + negatives), the scripted demo source, and the spellbook art,
// so the illustrations, the tests and the classifier all agree on what each sign looks like.
//
// Hand frame (meters): wrist at origin, fingers point up (-y), palm faces the camera (-z),
// x to the camera's right. A right hand has its thumb on +x.

import { add, normalize, rotate, scale, vec } from './vec.js';

const FINGER_LAYOUT = {
  index: { base: vec(0.026, -0.086, 0), segs: [0.04, 0.025, 0.021], lateral: 1 },
  middle: { base: vec(0.005, -0.091, 0), segs: [0.045, 0.028, 0.023], lateral: 0 },
  ring: { base: vec(-0.015, -0.086, 0), segs: [0.042, 0.026, 0.022], lateral: -1 },
  pinky: { base: vec(-0.032, -0.076, 0), segs: [0.032, 0.02, 0.018], lateral: -2 },
};
const FINGER_ORDER = ['index', 'middle', 'ring', 'pinky'];
const FLEX_PER_JOINT = [1.45, 1.75, 1.1]; // radians at full curl (MCP, PIP, DIP)
const THUMB_BASE = vec(0.022, -0.025, -0.012);
const THUMB_SEGS = [0.04, 0.032, 0.028];
const THUMB_OPEN_DIR = normalize(vec(0.75, -0.6, -0.25));
const THUMB_TUCK_DIR = normalize(vec(-0.75, -0.45, -0.5));
const DEFAULT_FOCAL = 0.9; // focal length as a fraction of image width

// Canonical poses. `spread` is the lateral fan between fingers (radians).
export const POSES = {
  open: { curls: [0, 0, 0, 0], thumb: 0.05, spread: 0.12 },
  fist: { curls: [1, 1, 1, 1], thumb: 0.95, spread: 0.02 },
  sword: { curls: [0, 0, 1, 1], thumb: 0.95, spread: 0.0 },
  point: { curls: [0, 1, 1, 1], thumb: 0.95, spread: 0.02 },
  peace: { curls: [0, 0, 1, 1], thumb: 0.95, spread: 0.32 },
  claw: { curls: [0.5, 0.5, 0.5, 0.5], thumb: 0.5, spread: 0.08 },
  relaxed: { curls: [0.3, 0.35, 0.4, 0.45], thumb: 0.3, spread: 0.06 },
  thumbsUp: { curls: [1, 1, 1, 1], thumb: 0, spread: 0.02, thumbOverride: vec(0.15, -1, -0.1) },
  rock: { curls: [0, 1, 1, 0], thumb: 0.95, spread: 0.1 },
};

// Deterministic PRNG so noisy fixtures are reproducible.
export function seededRandom(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function fingerChain(layout, curl, spread) {
  const points = [layout.base];
  let flex = 0;
  let p = layout.base;
  const lateral = layout.lateral * spread;
  layout.segs.forEach((len, j) => {
    flex += curl * FLEX_PER_JOINT[j];
    const dir = normalize(vec(Math.sin(lateral) * Math.cos(flex), -Math.cos(lateral) * Math.cos(flex), -Math.sin(flex)));
    p = add(p, scale(dir, len));
    points.push(p);
  });
  return points;
}

function thumbChain(curl, override) {
  const points = [THUMB_BASE];
  let p = THUMB_BASE;
  THUMB_SEGS.forEach((len, j) => {
    const t = Math.min(1, curl * (0.7 + 0.3 * j));
    const blended = add(scale(THUMB_OPEN_DIR, 1 - t), scale(THUMB_TUCK_DIR, t));
    const dir = override ? normalize(override) : normalize(blended);
    p = add(p, scale(dir, len));
    points.push(p);
  });
  return points;
}

// Builds a hand in its own frame, then rotates/scales it. Returns 21 points (meters).
export function makeHand(pose, { yaw = 0, pitch = 0, roll = 0, size = 1, handedness = 'Right' } = {}) {
  const points = [vec(), ...thumbChain(pose.thumb, pose.thumbOverride)];
  FINGER_ORDER.forEach((name, i) => points.push(...fingerChain(FINGER_LAYOUT[name], pose.curls[i], pose.spread)));
  const flip = handedness === 'Left' ? -1 : 1;
  return points.map((p) => rotate(scale(vec(p.x * flip, p.y, p.z), size), { yaw, pitch, roll }));
}

export function addNoise(points, amount, random) {
  const jitter = () => (random() * 2 - 1) * amount;
  return points.map((p) => vec(p.x + jitter(), p.y + jitter(), p.z + jitter()));
}

// Places a hand (meters, hand frame) into a camera image. (cx, cy): normalized image position of
// the palm center; depth: meters from the camera. Returns MediaPipe-like normalized landmarks and
// isotropic pixel-space points (x, y in pixels, z in the same pixel scale). `anchor` (hand-frame
// meters) overrides the palm center as the point placed at (cx, cy), to place hand pairs together.
export function placeHand(world, { cx, cy, depth, frameW, frameH, focal = DEFAULT_FOCAL, anchor }) {
  const pxPerMeter = (focal * frameW) / depth;
  const palm = anchor ?? scale(add(world[0], world[9]), 0.5);
  const image3d = world.map((p) => vec(cx * frameW + (p.x - palm.x) * pxPerMeter, cy * frameH + (p.y - palm.y) * pxPerMeter, (p.z - palm.z) * pxPerMeter));
  const landmarks = image3d.map((p) => vec(p.x / frameW, p.y / frameH, p.z / frameW));
  return { landmarks, image3d };
}

// Two hands forming a diamond with index tips touching above and thumb tips touching below.
// Rolls one hand until its index and thumb tips line up vertically, then mirrors it.
export function makeTrianglePair({ size = 1 } = {}) {
  const pose = { curls: [0, 0.6, 0.7, 0.8], thumb: 0, spread: 0.05 };
  let best = null;
  for (let deg = -90; deg <= 90; deg += 1) {
    const hand = makeHand(pose, { roll: (deg * Math.PI) / 180, size, handedness: 'Right' });
    const gap = Math.abs(hand[8].x - hand[4].x);
    const indexAbove = hand[8].y < hand[4].y;
    if (indexAbove && (!best || gap < best.gap)) best = { hand, gap };
  }
  const seamX = (best.hand[8].x + best.hand[4].x) / 2;
  const right = best.hand.map((p) => vec(p.x - seamX, p.y, p.z));
  const left = right.map((p) => vec(-p.x, p.y, p.z));
  return { left, right };
}
