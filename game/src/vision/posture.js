// Desk-scale body moves for one player, from a torso skeleton. Pure (no DOM).
//
//   lean in   torso closer than the player's neutral   -> stance 'leanIn'  (held, with hysteresis)
//   lean back torso farther than neutral               -> stance 'leanBack'
//   dodge     a quick sideways shift of the shoulders  -> one 'dodge' per move, re-armed on return
//
// Neutral is captured per player during the joining palm (calibrate) and drifts slowly while
// upright, so posture changes over a session don't read as leans.

import { BODY } from './tuning.js';

export const STANCE = Object.freeze({ NEUTRAL: 'neutral', LEAN_IN: 'leanIn', LEAN_BACK: 'leanBack' });

// Torso center (camera coords), depth (m) and shoulder width (normalized x) from a body, or null.
export function torsoOf(kp) {
  const l = kp?.l_shoulder;
  const r = kp?.r_shoulder;
  if (!l || !r) return null;
  const width = Math.abs(l.x - r.x);
  if (!(width > 0)) return null;
  return { x: (l.x + r.x) / 2, y: (l.y + r.y) / 2, z: (l.z + r.z) / 2, width };
}

export class PostureDetector {
  constructor() {
    this.reset();
  }

  reset() {
    this.torso = null; // smoothed
    this.neutral = null;
    this.stance = STANCE.NEUTRAL;
    this.pending = { stance: STANCE.NEUTRAL, since: 0 };
    this.history = [];
    this.isDodgeArmed = true;
    this.lastMs = null;
  }

  // Locks the current smoothed posture as this player's neutral.
  calibrate() {
    if (this.torso) this.neutral = { ...this.torso };
  }

  // Returns { stance, leanOffset (m), lateral (shoulder widths, camera x), dodge: -1 | 0 | 1 }.
  update(kp, tMs) {
    const raw = torsoOf(kp);
    if (!raw) return { stance: this.stance, leanOffset: 0, lateral: 0, dodge: 0, isTracked: false };
    const dtMs = this.lastMs === null ? 0 : Math.max(0, tMs - this.lastMs);
    this.lastMs = tMs;
    this.torso = this.torso ? blend(this.torso, raw, emaFactor(dtMs, BODY.SMOOTHING_TAU_MS)) : { ...raw };
    this.neutral ??= { ...this.torso };
    const leanOffset = this.torso.z - this.neutral.z; // negative = closer
    // Dodge reads the raw shoulders: smoothing would eat the quick shift it looks for.
    const lateral = (raw.x - this.neutral.x) / raw.width;
    this.#updateStance(leanOffset, tMs);
    const dodge = this.#updateDodge(lateral, tMs);
    if (this.stance === STANCE.NEUTRAL && !dodge && Math.abs(lateral) < BODY.DODGE_REARM) {
      this.neutral = blend(this.neutral, this.torso, emaFactor(dtMs, BODY.DRIFT_TAU_MS));
    }
    return { stance: this.stance, leanOffset, lateral, dodge, isTracked: true };
  }

  #updateStance(offset, tMs) {
    let wanted = this.stance;
    // Thresholds scale with the player's distance, so a lean feels the same near or far.
    const leanIn = BODY.LEAN_IN_FRAC * this.neutral.z;
    const leanBack = BODY.LEAN_BACK_FRAC * this.neutral.z;
    const hysteresis = BODY.LEAN_HYSTERESIS_FRAC * this.neutral.z;
    if (this.stance === STANCE.LEAN_IN && offset > -(leanIn - hysteresis)) wanted = STANCE.NEUTRAL;
    if (this.stance === STANCE.LEAN_BACK && offset < leanBack - hysteresis) wanted = STANCE.NEUTRAL;
    if (wanted === STANCE.NEUTRAL || this.stance === STANCE.NEUTRAL) {
      if (offset < -leanIn) wanted = STANCE.LEAN_IN;
      else if (offset > leanBack) wanted = STANCE.LEAN_BACK;
    }
    if (wanted !== this.pending.stance) this.pending = { stance: wanted, since: tMs };
    if (wanted !== this.stance && tMs - this.pending.since >= BODY.STANCE_HOLD_MS) this.stance = wanted;
  }

  #updateDodge(lateral, tMs) {
    this.history.push({ t: tMs, lateral });
    while (this.history.length && tMs - this.history[0].t > BODY.DODGE_WINDOW_MS) this.history.shift();
    if (!this.isDodgeArmed) {
      if (Math.abs(lateral) < BODY.DODGE_REARM) this.isDodgeArmed = true;
      return 0;
    }
    const shift = lateral - this.history[0].lateral;
    if (Math.abs(lateral) >= BODY.DODGE_SHIFT && Math.abs(shift) >= BODY.DODGE_SHIFT && Math.sign(shift) === Math.sign(lateral)) {
      this.isDodgeArmed = false;
      return Math.sign(lateral);
    }
    return 0;
  }
}

// Per-update EMA factor for a time constant, so the response doesn't depend on frame rate.
function emaFactor(dtMs, tauMs) {
  return 1 - Math.exp(-dtMs / tauMs);
}

function blend(a, b, t) {
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, z: a.z + (b.z - a.z) * t, width: a.width + (b.width - a.width) * t };
}
