// Rule-based hand-sign classifier + temporal smoothing. Pure: no DOM, no MediaPipe.
//
// One hand:  WARD (open palm facing the camera), GATHER (fist), AIM (index + middle together).
// Two hands: ULTIMATE (index tips and thumb tips touching in a diamond).

import { describeHand, isPlausibleHand, palmSize } from './hand-geometry.js';
import { INDEX, THUMB } from './landmarks.js';
import { SIGN, SMOOTHING } from './tuning.js';
import { dist, mid, smoothstep } from './vec.js';

export const SIGNS = Object.freeze({ NONE: 'none', WARD: 'ward', GATHER: 'gather', AIM: 'aim', ULTIMATE: 'ultimate' });

const SINGLE_HAND_SIGNS = [SIGNS.WARD, SIGNS.GATHER, SIGNS.AIM];

export function scoreSigns(features) {
  const { ext, facing, swordGap, thumbRise } = features;
  const open = [ext.index, ext.middle, ext.ring, ext.pinky];
  const curled = open.map((e) => 1 - e);
  return {
    [SIGNS.WARD]: Math.min(...open, smoothstep(SIGN.FACING_MIN, SIGN.FACING_FULL, facing)),
    [SIGNS.GATHER]: Math.min(...curled, smoothstep(SIGN.FIST_THUMB_RISE_MAX, SIGN.FIST_THUMB_RISE_FULL, thumbRise)),
    [SIGNS.AIM]: Math.min(ext.index, ext.middle, 1 - ext.ring, 1 - ext.pinky, smoothstep(SIGN.SWORD_GAP_MAX, SIGN.SWORD_GAP_FULL, swordGap)),
  };
}

// Classifies one frame of one hand. Returns { sign, score, scores, features }.
export function classifyHand(hand) {
  if (!isPlausibleHand(hand.world)) return { sign: SIGNS.NONE, score: 1, scores: {}, features: null };
  const features = describeHand(hand);
  const scores = scoreSigns(features);
  let best = { sign: SIGNS.NONE, score: 0 };
  for (const sign of SINGLE_HAND_SIGNS) {
    if (scores[sign] > best.score) best = { sign, score: scores[sign] };
  }
  if (best.score < SIGN.MIN_SCORE) best = { sign: SIGNS.NONE, score: 1 - best.score };
  return { ...best, scores, features };
}

// Two hands of the same player, in shared image space. Returns a 0..1 triangle score.
export function scoreTriangle(a, b) {
  const palm = (palmSize(a.image3d) + palmSize(b.image3d)) / 2;
  if (!(palm > 0)) return 0;
  const indexGap = dist(a.image3d[INDEX[3]], b.image3d[INDEX[3]]) / palm;
  const thumbGap = dist(a.image3d[THUMB[3]], b.image3d[THUMB[3]]) / palm;
  const indexTop = mid(a.image3d[INDEX[3]], b.image3d[INDEX[3]]);
  const thumbBottom = mid(a.image3d[THUMB[3]], b.image3d[THUMB[3]]);
  const height = (thumbBottom.y - indexTop.y) / palm; // image y grows downward
  const ext = Math.min(describeHand(a).ext.index, describeHand(b).ext.index);
  return Math.min(
    smoothstep(SIGN.TOUCH_MAX, SIGN.TOUCH_FULL, indexGap),
    smoothstep(SIGN.TOUCH_MAX, SIGN.TOUCH_FULL, thumbGap),
    smoothstep(SIGN.DIAMOND_MIN_HEIGHT * 0.5, SIGN.DIAMOND_MIN_HEIGHT, height),
    ext,
  );
}

export const isTriangle = (a, b) => scoreTriangle(a, b) >= SIGN.MIN_SCORE;

// Majority vote over the last few frames with hysteresis: a new sign needs ENTER_VOTES to take
// over, the current sign keeps the lead while it still has STAY_VOTES.
export class SignSmoother {
  constructor({ window = SMOOTHING.WINDOW, enter = SMOOTHING.ENTER_VOTES, stay = SMOOTHING.STAY_VOTES } = {}) {
    Object.assign(this, { window, enter, stay });
    this.reset();
  }

  reset() {
    this.history = [];
    this.current = SIGNS.NONE;
  }

  push(sign) {
    this.history.push(sign);
    if (this.history.length > this.window) this.history.shift();
    const counts = new Map();
    for (const s of this.history) counts.set(s, (counts.get(s) ?? 0) + 1);
    if ((counts.get(this.current) ?? 0) >= this.stay && this.current !== SIGNS.NONE) return this.current;
    let leader = SIGNS.NONE;
    for (const [s, n] of counts) if (n >= this.enter && n > (counts.get(leader) ?? 0)) leader = s;
    this.current = leader;
    return this.current;
  }

  // Share of the window that agrees with the current sign (for the debug readout).
  get agreement() {
    if (!this.history.length) return 0;
    return this.history.filter((s) => s === this.current).length / this.history.length;
  }
}
