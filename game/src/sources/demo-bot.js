// A scripted "player" for the demo source: performs real hand signs (synthetic landmarks) and
// body moves (synthetic torso) in reaction to the match flow, so the whole loop can be watched
// without a human. The bot never touches game state; it only moves its hands and body.

import { PHASE as FLOW } from '../game/rounds.js';
import { makeBody } from '../vision/synthetic-body.js';
import { POSES, makeHand, makeTrianglePair, placeHand, seededRandom } from '../vision/synthetic-hand.js';
import { vec } from '../vision/vec.js';

const REST_DEPTH = 0.75;
const THRUST_DEPTH = 0.5;
const THRUST_MS = 170;
const TORSO_Z = 0.9;
const LEAN_IN_Z = -0.2;
const LEAN_BACK_Z = 0.16;
const DODGE_SHIFT = 0.12; // view units (about 0.6 shoulder widths at the seat distance)
const SEAT_X = [0.25, 0.75]; // view space
const JOIN_DELAY_MS = [900, 1900];
const REMATCH_DELAY_MS = 5500;
const DEFENSE = [['ward', 0.45], ['dodge', 0.3], ['brace', 0.15]]; // the rest: take the hit
const HAND_SCORE = 0.97;
const FOCAL = 0.45; // ZED X-like wide lens
const TRIANGLE_ANCHOR = vec(0, -0.06, 0); // where the touching tips sit relative to the spec position

const ROUTINES = [
  { weight: 3, steps: [['rest', 500], ['sword', 650], ['thrust', THRUST_MS], ['sword', 250], ['rest', 900]] },
  { weight: 3, steps: [['rest', 300], ['fist', 900], ['sword', 600], ['thrust', THRUST_MS], ['sword', 250], ['rest', 1000]] },
  { weight: 1, steps: [['rest', 300], ['fist', 900], ['triangle', 1600], ['rest', 1200]] },
];

export class DemoBot {
  constructor(slot, seed) {
    this.slot = slot;
    this.random = seededRandom(seed);
    this.queue = [];
    this.stepStart = 0;
    this.defense = { kind: null, from: 0, until: 0 };
    this.seenProjectiles = new Set();
    this.lean = 0;
    this.shift = 0;
  }

  // Returns { hands: [hand spec], body: { x, z } } in view space.
  update(tMs, { phase, phaseMs, combat }) {
    const seat = SEAT_X[this.slot];
    const inward = this.slot === 0 ? 1 : -1; // toward the seam
    if (phase !== FLOW.FIGHT) this.queue = [];
    const hands = this.#hands(tMs, { phase, phaseMs, combat, seat, inward });
    const step = this.queue[0]?.[0];
    this.lean += (this.#targetLean(step, tMs) - this.lean) * 0.35;
    const isDodging = this.defense.kind === 'dodge' && tMs >= this.defense.from && tMs < this.defense.until;
    const targetShift = isDodging ? DODGE_SHIFT * -inward : 0;
    this.shift += (targetShift - this.shift) * (targetShift ? 0.6 : 0.08);
    const body = { x: seat + this.shift, z: TORSO_Z + this.lean };
    return { hands: hands.map((h) => ({ ...h, x: h.x + this.shift })), body };
  }

  #targetLean(step, tMs) {
    if (step === 'fist') return LEAN_IN_Z;
    if (this.defense.kind === 'brace' && tMs < this.defense.until) return LEAN_BACK_Z;
    return 0;
  }

  #hands(tMs, { phase, phaseMs, combat, seat, inward }) {
    const rest = { pose: 'relaxed', x: seat + inward * 0.06, y: 0.84, depth: REST_DEPTH, roll: 0.2 * inward };
    const offHand = { pose: 'relaxed', x: seat - inward * 0.07, y: 0.85, depth: REST_DEPTH, roll: -0.2 * inward, handedness: 'Left' };
    if (phase === FLOW.ATTRACT || phase === FLOW.RESULTS) {
      const delay = phase === FLOW.ATTRACT ? JOIN_DELAY_MS[this.slot] : REMATCH_DELAY_MS;
      const palm = { pose: 'open', x: seat + inward * 0.04, y: 0.55, depth: REST_DEPTH, roll: 0.1 * inward };
      return [phaseMs > delay ? palm : rest, offHand];
    }
    if (phase !== FLOW.FIGHT) return [rest, offHand];
    this.#react(tMs, combat);
    const cast = this.#castHand(tMs, seat, inward, rest);
    if (cast.triangle) return [cast];
    const isWarding = this.defense.kind === 'ward' && tMs >= this.defense.from && tMs < this.defense.until;
    const ward = { pose: 'open', x: seat - inward * 0.02, y: 0.6, depth: REST_DEPTH - 0.05, roll: -0.15 * inward, handedness: 'Left' };
    return [cast, isWarding ? ward : offHand];
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
    const hand = { x: seat + inward * 0.08, y: 0.62, depth: REST_DEPTH, roll: 0.25 * inward };
    if (name === 'rest') return rest;
    if (name === 'thrust') return { ...hand, pose: 'sword', depth: REST_DEPTH - (REST_DEPTH - THRUST_DEPTH) * t };
    if (name === 'triangle') return { triangle: true, x: seat + inward * 0.03, y: 0.6, depth: REST_DEPTH };
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

  // Chooses a defense for each new incoming projectile: ward, dodge (timed to the impact), brace.
  #react(tMs, combat) {
    for (const proj of combat.projectiles) {
      if (proj.from === this.slot || this.seenProjectiles.has(proj.id)) continue;
      this.seenProjectiles.add(proj.id);
      let roll = this.random();
      const choice = DEFENSE.find(([, p]) => (roll -= p) < 0)?.[0] ?? null;
      if (choice === 'ward') this.defense = { kind: 'ward', from: tMs, until: tMs + 1100 };
      if (choice === 'dodge' && proj.kind === 'bolt') this.defense = { kind: 'dodge', from: tMs + 150, until: tMs + 900 };
      if (choice === 'brace') this.defense = { kind: 'brace', from: tMs, until: tMs + 1300 };
    }
  }
}

export function specToObservations(spec, frameW, frameH) {
  const base = { cx: 1 - spec.x, cy: spec.y, depth: spec.depth, frameW, frameH, focal: FOCAL };
  const observe = (world, handedness, anchor) => ({
    landmarks: placeHand(world, { ...base, anchor }).landmarks,
    world,
    handedness,
    handScore: HAND_SCORE,
    frameW,
    frameH,
    depth: spec.depth,
    depthSource: 'stereo', // scripted metric depth, like the ZED map
  });
  if (spec.triangle) {
    const { left, right } = makeTrianglePair();
    return [observe(left, 'Left', TRIANGLE_ANCHOR), observe(right, 'Right', TRIANGLE_ANCHOR)];
  }
  const handedness = spec.handedness ?? 'Right';
  return [observe(makeHand(POSES[spec.pose], { roll: spec.roll ?? 0, handedness }), handedness)];
}

// Converts a bot frame (view space) into hand observations and a body skeleton (camera space).
// The skeleton's wrists sit on the hands, as the ZED's would.
export function botToInputs(slot, { hands, body }, frameW, frameH) {
  const observations = hands.flatMap((spec) => specToObservations(spec, frameW, frameH));
  // The person's left wrist is the one on the camera's right (larger camera x).
  const wrists = observations.map((o) => ({ ...o.landmarks[0], z: o.depth })).sort((a, b) => b.x - a.x);
  const pair = wrists.length === 1 && wrists[0].x < 1 - body.x ? [null, wrists[0]] : wrists;
  const skeleton = makeBody({ id: slot + 1, cx: 1 - body.x, z: body.z, frameW, frameH, focal: FOCAL, wrists: { l: pair[0] ?? null, r: pair[1] ?? null } });
  return { observations, body: skeleton };
}
