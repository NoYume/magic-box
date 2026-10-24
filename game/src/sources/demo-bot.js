// A scripted "player" for the demo source: performs real signs (synthetic landmarks) in reaction
// to the match flow, so the whole loop (join, signs, charge, cast, ward, impact, KO, results) can
// be watched without a human. The bot never touches game state; it only moves its hands.

import { PHASE as FLOW } from '../game/rounds.js';
import { POSES, makeHand, makeTrianglePair, placeHand, seededRandom } from '../vision/synthetic-hand.js';
import { vec } from '../vision/vec.js';

const REST_DEPTH = 0.75;
const THRUST_DEPTH = 0.5;
const THRUST_MS = 170;
const SEAT_X = [0.25, 0.75]; // view space
const JOIN_DELAY_MS = [900, 1900];
const REMATCH_DELAY_MS = 5500;
const WARD_CHANCE = 0.6;
const HAND_SCORE = 0.97;
const TRIANGLE_ANCHOR = vec(0, -0.06, 0); // where the touching tips sit relative to the spec position

const ROUTINES = [
  { weight: 3, steps: [['rest', 500], ['sword', 650], ['thrust', THRUST_MS], ['sword', 250], ['rest', 900]] },
  { weight: 3, steps: [['rest', 300], ['fist', 1250], ['sword', 600], ['thrust', THRUST_MS], ['sword', 250], ['rest', 1000]] },
  { weight: 1, steps: [['rest', 300], ['fist', 1300], ['triangle', 1600], ['rest', 1200]] },
];

export class DemoBot {
  constructor(slot, seed) {
    this.slot = slot;
    this.random = seededRandom(seed);
    this.queue = [];
    this.stepStart = 0;
    this.wardUntil = 0;
    this.seenProjectiles = new Set();
  }

  // Returns hand specs in view space: [{ pose, x, y, depth, roll, handedness }] or a { triangle } spec.
  update(tMs, { phase, phaseMs, combat }) {
    const seat = SEAT_X[this.slot];
    const inward = this.slot === 0 ? 1 : -1; // toward the seam
    const rest = { pose: 'relaxed', x: seat + inward * 0.07, y: 0.82, depth: REST_DEPTH, roll: 0.2 * inward };
    const offHand = { pose: 'relaxed', x: seat - inward * 0.08, y: 0.84, depth: REST_DEPTH, roll: -0.2 * inward, handedness: 'Left' };
    if (phase === FLOW.ATTRACT || phase === FLOW.RESULTS) {
      const delay = phase === FLOW.ATTRACT ? JOIN_DELAY_MS[this.slot] : REMATCH_DELAY_MS;
      const palmUp = phaseMs > delay;
      return [palmUp ? { pose: 'open', x: seat + inward * 0.04, y: 0.42, depth: REST_DEPTH, roll: 0.1 * inward } : rest, offHand];
    }
    if (phase !== FLOW.FIGHT) {
      this.queue = [];
      return [rest, offHand];
    }
    const ward = this.#wardHand(tMs, combat, seat, inward);
    const cast = this.#castHand(tMs, seat, inward, rest);
    return cast.triangle ? [cast] : [cast, ward ?? offHand];
  }

  #castHand(tMs, seat, inward, rest) {
    if (!this.queue.length) this.#pickRoutine(tMs);
    let [name, duration] = this.queue[0];
    while (tMs - this.stepStart >= duration) {
      this.stepStart += duration;
      this.queue.shift();
      if (!this.queue.length) this.#pickRoutine(this.stepStart);
      [name, duration] = this.queue[0];
    }
    const t = (tMs - this.stepStart) / duration;
    const hand = { x: seat + inward * 0.09, y: 0.5, depth: REST_DEPTH, roll: 0.25 * inward };
    if (name === 'rest') return rest;
    if (name === 'thrust') return { ...hand, pose: 'sword', depth: REST_DEPTH - (REST_DEPTH - THRUST_DEPTH) * t };
    if (name === 'triangle') return { triangle: true, x: seat + inward * 0.03, y: 0.5, depth: REST_DEPTH };
    return { ...hand, pose: name };
  }

  #pickRoutine(tMs) {
    const total = ROUTINES.reduce((sum, r) => sum + r.weight, 0);
    let pick = this.random() * total;
    const routine = ROUTINES.find((r) => (pick -= r.weight) < 0) ?? ROUTINES[0];
    const jitter = () => 0.8 + this.random() * 0.5;
    this.queue = routine.steps.map(([name, ms]) => [name, name === 'thrust' ? ms : ms * jitter()]);
    this.stepStart = tMs;
  }

  // Raises an open palm with the off hand when an enemy projectile is incoming (not always).
  #wardHand(tMs, combat, seat, inward) {
    for (const proj of combat.projectiles) {
      if (proj.from === this.slot || this.seenProjectiles.has(proj.id)) continue;
      this.seenProjectiles.add(proj.id);
      if (this.random() < WARD_CHANCE) this.wardUntil = tMs + 1100;
    }
    if (tMs > this.wardUntil) return null;
    return { pose: 'open', x: seat - inward * 0.02, y: 0.46, depth: REST_DEPTH - 0.05, roll: -0.15 * inward, handedness: 'Left' };
  }
}

// Converts a bot hand spec (view space) into roster observations (camera space, mirrored view).
export function specToObservations(spec, frameW, frameH) {
  const base = { cx: 1 - spec.x, cy: spec.y, depth: spec.depth, frameW, frameH };
  const observe = (world, handedness, anchor) => ({
    landmarks: placeHand(world, { ...base, anchor }).landmarks,
    world,
    handedness,
    handScore: HAND_SCORE,
    frameW,
    frameH,
    depth: spec.depth,
  });
  if (spec.triangle) {
    const { left, right } = makeTrianglePair();
    return [observe(left, 'Left', TRIANGLE_ANCHOR), observe(right, 'Right', TRIANGLE_ANCHOR)];
  }
  const handedness = spec.handedness ?? 'Right';
  return [observe(makeHand(POSES[spec.pose], { roll: spec.roll ?? 0, handedness }), handedness)];
}
