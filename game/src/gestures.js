// Turns a stream of skeletons for ONE player into discrete gesture events.
// Pure logic (no DOM), so it runs the same for the ZED X and the webcam fallback.
//
// Events:
//   { type: 'stance', stance: 'forward' | 'neutral' | 'back' }   step toward / away from the camera
//   { type: 'push', hand: 'l' | 'r', power }                     fast hand thrust toward the camera (power in m/s)
//   { type: 'handsUp' }                                          both wrists above the head long enough

const DEFAULTS = {
  stepThreshold: 0.35, // meters from the player's resting depth
  stepHysteresis: 0.1,
  baselineRate: 0.02, // how fast the resting depth adapts while neutral
  pushSpeed: 1.2, // m/s of the wrist moving ahead of the shoulder
  pushFrames: 2,
  pushCooldownMs: 350,
  handsUpMs: 500,
};

export class GestureDetector {
  constructor(options = {}) {
    this.opts = { ...DEFAULTS, ...options };
    this.reset();
  }

  reset() {
    this.baseline = null;
    this.stance = 'neutral';
    this.hands = { l: newHandState(), r: newHandState() };
    this.handsUpSince = null;
    this.handsUpFired = false;
    this.lastT = null;
  }

  update(kp, tMs) {
    const events = [];
    const dt = this.lastT === null ? 0 : (tMs - this.lastT) / 1000;
    this.lastT = tMs;
    this.#updateStance(kp, events);
    if (dt > 0 && dt < 0.25) {
      this.#updatePush('l', kp.l_wrist, kp.l_shoulder, dt, tMs, events);
      this.#updatePush('r', kp.r_wrist, kp.r_shoulder, dt, tMs, events);
    }
    this.#updateHandsUp(kp, tMs, events);
    return events;
  }

  #updateStance(kp, events) {
    const torso = kp.pelvis ?? kp.neck;
    if (!torso) return;
    const { stepThreshold, stepHysteresis, baselineRate } = this.opts;
    if (this.baseline === null) this.baseline = torso.z;
    const offset = torso.z - this.baseline; // negative = closer to the camera

    let next = this.stance;
    if (this.stance === 'neutral') {
      if (offset < -stepThreshold) next = 'forward';
      else if (offset > stepThreshold) next = 'back';
    } else if (Math.abs(offset) < stepThreshold - stepHysteresis) {
      next = 'neutral';
    }
    if (next === 'neutral') this.baseline += (torso.z - this.baseline) * baselineRate;
    if (next !== this.stance) {
      this.stance = next;
      events.push({ type: 'stance', stance: next });
    }
  }

  #updatePush(hand, wrist, shoulder, dt, tMs, events) {
    const state = this.hands[hand];
    if (!wrist || !shoulder) {
      state.prevReach = null;
      return;
    }
    const reach = shoulder.z - wrist.z; // positive = hand in front of the shoulder
    if (state.prevReach !== null) {
      const speed = (reach - state.prevReach) / dt;
      if (speed > this.opts.pushSpeed) {
        state.fastFrames += 1;
        state.peak = Math.max(state.peak, speed);
      } else {
        state.fastFrames = 0;
        state.peak = 0;
      }
      const ready = tMs - state.lastPushT > this.opts.pushCooldownMs;
      if (state.fastFrames >= this.opts.pushFrames && ready) {
        events.push({ type: 'push', hand, power: state.peak, x: wrist.x, y: wrist.y });
        state.lastPushT = tMs;
        state.fastFrames = 0;
        state.peak = 0;
      }
    }
    state.prevReach = reach;
  }

  #updateHandsUp(kp, tMs, events) {
    const { head, l_wrist: lw, r_wrist: rw } = kp;
    const isUp = head && lw && rw && lw.y < head.y && rw.y < head.y;
    if (!isUp) {
      this.handsUpSince = null;
      this.handsUpFired = false;
      return;
    }
    this.handsUpSince ??= tMs;
    if (!this.handsUpFired && tMs - this.handsUpSince >= this.opts.handsUpMs) {
      this.handsUpFired = true;
      events.push({ type: 'handsUp' });
    }
  }
}

function newHandState() {
  return { prevReach: null, fastFrames: 0, peak: 0, lastPushT: -Infinity };
}
