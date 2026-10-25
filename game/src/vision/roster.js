// Turns raw hand detections into stable per-player hand tracks. Pure (no DOM).
//
//  - Player slot = the body whose wrist the hand is attached to (when body tracking is available),
//    else which half of the shown (mirrored) frame the palm is in, split at the center seam.
//  - Detections are dropped if low-confidence, partially out of frame, or outside the play depth
//    range (bystanders behind the players).
//  - Each slot keeps at most two tracks (the nearest hands), matched frame to frame by position,
//    each with its own sign smoother and depth history. A detection only continues a track if it
//    is the same hand: same handedness, same body, and no impossible depth jump. Anything else
//    starts a fresh track, so a replacement hand never inherits a sign or a thrust history.
//  - Depth comes from the stereo map (ZED) or palm size (webcam), per observation.depthSource.
//    A stereo dropout is "depth unknown" for that frame (no thrust), never a palm-size guess.

import { depthFromPalmSize, isInPlayRange } from './depth.js';
import { MIDDLE, PALM_POINTS, WRIST } from './landmarks.js';
import { SIGNS, SignSmoother, classifyHand, scoreTriangle } from './signs.js';
import { HANDS, SIGN, THRUST } from './tuning.js';
import { dist, vec } from './vec.js';

const MAX_HANDS_PER_SLOT = 2;
const DEPTH_HISTORY_MS = THRUST.WINDOW_MS * 3;

export const DEPTH_SOURCE = Object.freeze({ STEREO: 'stereo', PALM: 'palm' });

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

  // obs: { landmarks, world, handedness, handScore, frameW, frameH, depth (m) | null, depthSource }
  // bodies (optional): a BodyRoster that already saw this frame's skeletons.
  update(observations, tMs, bodies = null) {
    const rejected = [];
    const candidates = [];
    for (const obs of observations) {
      const hand = this.#measure(obs, bodies);
      const reason = this.#rejectReason(obs, hand);
      if (reason) rejected.push({ ...hand, reason });
      else candidates.push(hand);
    }
    // A stereo dropout may continue a known hand, but an unknown hand with no depth could be a
    // bystander beyond range (the map reads 0 there), so it never starts a track.
    for (const hand of this.#match(candidates, tMs)) rejected.push({ ...hand, reason: REJECT.RANGE });
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

  #measure(obs, bodies) {
    const { landmarks, frameW, frameH } = obs;
    const image3d = landmarks.map((p) => vec(p.x * frameW, p.y * frameH, p.z * frameW));
    const cam = palmCenter(landmarks);
    const view = { x: this.mirror ? 1 - cam.u : cam.u, y: cam.v };
    const bodySlot = bodies?.slotForHand(landmarks[WRIST]) ?? null;
    const slotGuess = bodySlot ?? (view.x < 0.5 ? 0 : 1);
    const depthSource = obs.depthSource ?? (obs.depth == null ? DEPTH_SOURCE.PALM : DEPTH_SOURCE.STEREO);
    const isStereo = depthSource === DEPTH_SOURCE.STEREO;
    const rawDepth = isStereo ? obs.depth ?? null : depthFromPalmSize(image3d, frameW);
    const depth = isStereo || rawDepth === null ? rawDepth : rawDepth * this.depthScale[slotGuess];
    const palmSpan = dist(image3d[WRIST], image3d[MIDDLE[0]]) / frameH; // fraction of frame height
    return { ...obs, image3d, cam, view, slotGuess, bodySlot, depth, depthSource, rawDepth, palmSpan };
  }

  #rejectReason(obs, hand) {
    if ((obs.handScore ?? 1) < HANDS.MIN_HANDEDNESS_SCORE) return REJECT.CONFIDENCE;
    if (!isInsideFrame(obs.landmarks)) return REJECT.EDGE;
    const isDropout = hand.depth === null && hand.depthSource === DEPTH_SOURCE.STEREO;
    if (!isDropout && !isInPlayRange(hand.depth)) return REJECT.RANGE;
    return null;
  }

  // Same physical hand? Handedness and body owner must agree and depth cannot teleport.
  #isSameHand(hand, track) {
    if (hand.handedness !== track.handedness) return false;
    if (hand.bodySlot !== null && track.bodySlot !== null && hand.bodySlot !== track.bodySlot) return false;
    if (hand.depth === null || track.lastDepth === null) return true;
    return Math.abs(hand.depth - track.lastDepth) <= HANDS.MAX_DEPTH_JUMP_M;
  }

  #slotFor(hand, track) {
    if (hand.bodySlot !== null) return hand.bodySlot; // attached to a tracked body: that body's player
    if (!track) return hand.slotGuess;
    const past = track.slot === 0 ? hand.view.x - 0.5 : 0.5 - hand.view.x;
    return past > HANDS.SEAM_HYSTERESIS ? 1 - track.slot : track.slot;
  }

  // Returns the candidates that could not be placed (unknown hands without depth).
  #match(candidates, tMs) {
    this.tracks.forEach((t) => (t.fresh = false));
    // Greedy nearest-neighbour matching, closest pairs first, same physical hand only.
    const pairs = [];
    candidates.forEach((hand, ci) =>
      this.tracks.forEach((track, ti) => {
        if (this.#isSameHand(hand, track)) pairs.push({ ci, ti, d: Math.hypot(hand.view.x - track.view.x, hand.view.y - track.view.y) });
      }),
    );
    pairs.sort((a, b) => a.d - b.d);
    const usedC = new Set();
    const usedT = new Set();
    for (const { ci, ti, d } of pairs) {
      if (d > HANDS.MATCH_RADIUS || usedC.has(ci) || usedT.has(ti)) continue;
      usedC.add(ci);
      usedT.add(ti);
      this.#refresh(this.tracks[ti], candidates[ci], tMs);
    }
    const unplaced = [];
    candidates.forEach((hand, ci) => {
      if (usedC.has(ci)) return;
      if (hand.depth === null) {
        unplaced.push(hand);
        return;
      }
      const track = { id: this.nextId++, smoother: new SignSmoother(), depthHistory: [], lastDepth: null };
      this.tracks.push(track);
      this.#refresh(track, hand, tMs);
    });
    this.#capPerSlot();
    return unplaced;
  }

  #refresh(track, hand, tMs) {
    const frame = classifyHand(hand);
    // Palm-size and stereo depth have different biases: never difference one against the other.
    if (track.depthSource !== undefined && track.depthSource !== hand.depthSource) track.depthHistory = [];
    if (hand.depth !== null) track.lastDepth = hand.depth;
    Object.assign(track, hand, { slot: this.#slotFor(hand, track.slot === undefined ? null : track), lastSeen: tMs, fresh: true });
    track.frameSign = frame.sign;
    track.frameScore = frame.score;
    track.scores = frame.scores;
    track.features = frame.features; // finger extension, palm facing, thumb rise (debug log)
    // An unreadable frame (failed the plausibility gate) says nothing about the sign: skip its
    // vote for a few frames in a row, so one-frame dropouts don't stall or break a sign.
    track.unreadable = frame.features ? 0 : (track.unreadable ?? 0) + 1;
    if (track.unreadable === 0 || track.unreadable > HANDS.UNREADABLE_GRACE_FRAMES) track.sign = track.smoother.push(frame.sign);
    else track.sign ??= track.smoother.current;
    track.agreement = track.smoother.agreement;
    track.depthHistory.push({ t: tMs, z: hand.depth, x: hand.view.x }); // x feeds the sideways jab
    while (track.depthHistory.length && tMs - track.depthHistory[0].t > DEPTH_HISTORY_MS) track.depthHistory.shift();
  }

  // Bystanders reaching into a half: keep only the nearest hands per slot.
  #capPerSlot() {
    for (const slot of [0, 1]) {
      const fresh = this.handsIn(slot).sort((a, b) => a.lastDepth - b.lastDepth);
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
