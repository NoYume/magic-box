// Turns raw hand detections into stable per-player hand tracks. Pure (no DOM).
//
//  - Player slot = which half of the shown (mirrored) frame the palm is in, split at the center seam.
//  - Detections are dropped if low-confidence, partially out of frame, or outside the play depth
//    range (bystanders behind the players).
//  - Each slot keeps at most two tracks (the nearest hands), matched frame to frame by position,
//    each with its own sign smoother and depth history.

import { depthFromPalmSize, isInPlayRange } from './depth.js';
import { MIDDLE, PALM_POINTS, WRIST } from './landmarks.js';
import { SIGNS, SignSmoother, classifyHand, scoreTriangle } from './signs.js';
import { HANDS, SIGN, THRUST } from './tuning.js';
import { dist, vec } from './vec.js';

const MAX_HANDS_PER_SLOT = 2;
const DEPTH_HISTORY_MS = THRUST.WINDOW_MS * 3;

export const REJECT = Object.freeze({ CONFIDENCE: 'low confidence', EDGE: 'partly out of frame', RANGE: 'out of play range' });

function palmCenter(landmarks) {
  const sum = PALM_POINTS.reduce((acc, i) => ({ u: acc.u + landmarks[i].x, v: acc.v + landmarks[i].y }), { u: 0, v: 0 });
  return { u: sum.u / PALM_POINTS.length, v: sum.v / PALM_POINTS.length };
}

const isInsideFrame = (landmarks) =>
  PALM_POINTS.every((i) => {
    const { x, y } = landmarks[i];
    return x > HANDS.EDGE_MARGIN && x < 1 - HANDS.EDGE_MARGIN && y > HANDS.EDGE_MARGIN && y < 1 - HANDS.EDGE_MARGIN;
  });

export class HandRoster {
  constructor({ mirror = true } = {}) {
    this.mirror = mirror;
    this.tracks = [];
    this.nextId = 1;
    this.triangle = [new SignSmoother(), new SignSmoother()];
    this.depthScale = [1, 1]; // webcam calibration per slot
  }

  // obs: { landmarks, world, handedness, handScore, frameW, frameH, depth (m) | null }
  update(observations, tMs) {
    const rejected = [];
    const candidates = [];
    for (const obs of observations) {
      const hand = this.#measure(obs);
      const reason = this.#rejectReason(obs, hand);
      if (reason) rejected.push({ ...hand, reason });
      else candidates.push(hand);
    }
    this.#match(candidates, tMs);
    this.tracks = this.tracks.filter((t) => tMs - t.lastSeen <= HANDS.LOST_MS);
    return { slots: [this.handsIn(0), this.handsIn(1)], triangles: [this.#triangle(0), this.#triangle(1)], rejected };
  }

  handsIn(slot) {
    return this.tracks.filter((t) => t.slot === slot && t.fresh);
  }

  setDepthScale(slot, scale) {
    this.depthScale[slot] = scale;
  }

  reset() {
    this.tracks = [];
    this.triangle.forEach((s) => s.reset());
  }

  #measure(obs) {
    const { landmarks, frameW, frameH } = obs;
    const image3d = landmarks.map((p) => vec(p.x * frameW, p.y * frameH, p.z * frameW));
    const cam = palmCenter(landmarks);
    const view = { x: this.mirror ? 1 - cam.u : cam.u, y: cam.v };
    const slotGuess = view.x < 0.5 ? 0 : 1;
    const rawDepth = obs.depth ?? depthFromPalmSize(image3d, frameW);
    const depth = obs.depth ?? (rawDepth === null ? null : rawDepth * this.depthScale[slotGuess]);
    const palmSpan = dist(image3d[WRIST], image3d[MIDDLE[0]]) / frameH; // fraction of frame height
    return { ...obs, image3d, cam, view, slotGuess, depth, rawDepth, palmSpan };
  }

  #rejectReason(obs, hand) {
    if ((obs.handScore ?? 1) < HANDS.MIN_HANDEDNESS_SCORE) return REJECT.CONFIDENCE;
    if (!isInsideFrame(obs.landmarks)) return REJECT.EDGE;
    if (!isInPlayRange(hand.depth)) return REJECT.RANGE;
    return null;
  }

  #slotFor(hand, track) {
    if (!track) return hand.slotGuess;
    const past = track.slot === 0 ? hand.view.x - 0.5 : 0.5 - hand.view.x;
    return past > HANDS.SEAM_HYSTERESIS ? 1 - track.slot : track.slot;
  }

  #match(candidates, tMs) {
    this.tracks.forEach((t) => (t.fresh = false));
    // Greedy nearest-neighbour matching, closest pairs first.
    const pairs = [];
    candidates.forEach((hand, ci) => this.tracks.forEach((track, ti) => pairs.push({ ci, ti, d: Math.hypot(hand.view.x - track.view.x, hand.view.y - track.view.y) })));
    pairs.sort((a, b) => a.d - b.d);
    const usedC = new Set();
    const usedT = new Set();
    for (const { ci, ti, d } of pairs) {
      if (d > HANDS.MATCH_RADIUS || usedC.has(ci) || usedT.has(ti)) continue;
      usedC.add(ci);
      usedT.add(ti);
      this.#refresh(this.tracks[ti], candidates[ci], tMs);
    }
    candidates.forEach((hand, ci) => {
      if (usedC.has(ci)) return;
      const track = { id: this.nextId++, smoother: new SignSmoother(), depthHistory: [] };
      this.tracks.push(track);
      this.#refresh(track, hand, tMs);
    });
    this.#capPerSlot();
  }

  #refresh(track, hand, tMs) {
    const frame = classifyHand(hand);
    Object.assign(track, hand, { slot: this.#slotFor(hand, track.slot === undefined ? null : track), lastSeen: tMs, fresh: true });
    track.frameSign = frame.sign;
    track.frameScore = frame.score;
    track.scores = frame.scores;
    track.sign = track.smoother.push(frame.sign);
    track.agreement = track.smoother.agreement;
    track.depthHistory.push({ t: tMs, z: hand.depth });
    while (track.depthHistory.length && tMs - track.depthHistory[0].t > DEPTH_HISTORY_MS) track.depthHistory.shift();
  }

  // Bystanders reaching into a half: keep only the nearest hands per slot.
  #capPerSlot() {
    for (const slot of [0, 1]) {
      const fresh = this.handsIn(slot).sort((a, b) => a.depth - b.depth);
      fresh.slice(MAX_HANDS_PER_SLOT).forEach((t) => (t.fresh = false));
    }
  }

  #triangle(slot) {
    const hands = this.handsIn(slot);
    const score = hands.length === 2 ? scoreTriangle(hands[0], hands[1]) : 0;
    const sign = this.triangle[slot].push(score >= SIGN.MIN_SCORE ? SIGNS.ULTIMATE : SIGNS.NONE);
    return { active: sign === SIGNS.ULTIMATE, score };
  }
}
