// Stable player slots from body skeletons. Pure (no DOM).
//
// A player is the nearest valid torso in a half of the shown (mirrored) frame: both shoulders in
// frame, torso within the play depth. Tracker ids keep a body in its slot until it clearly
// crosses the seam. Hands are then attached to the body whose wrist is nearest.

import { torsoOf } from './posture.js';
import { BODY, HANDS } from './tuning.js';

const isInside = (p) => p && p.x > BODY.EDGE_MARGIN && p.x < 1 - BODY.EDGE_MARGIN && p.y > BODY.EDGE_MARGIN && p.y < 1 - BODY.EDGE_MARGIN;

export class BodyRoster {
  constructor({ mirror = true } = {}) {
    this.mirror = mirror;
    this.slots = [null, null]; // { id, kp, torso, view }
  }

  // bodies: [{ id, kp }] in camera coords (docs/protocol.md). Returns { slots, rejected }.
  update(bodies) {
    const rejected = [];
    const valid = [];
    for (const body of bodies) {
      const torso = torsoOf(body.kp);
      const ok = torso && isInside(body.kp.l_shoulder) && isInside(body.kp.r_shoulder) && torso.z >= BODY.PLAY_NEAR_M && torso.z <= BODY.PLAY_FAR_M;
      if (!ok) {
        rejected.push(body);
        continue;
      }
      valid.push({ ...body, torso, view: { x: this.mirror ? 1 - torso.x : torso.x, y: torso.y } });
    }
    this.slots = [0, 1].map((slot) => this.#pick(slot, valid));
    return { slots: this.slots, rejected };
  }

  #pick(slot, valid) {
    const sideOf = (b) => {
      const previous = this.slots.findIndex((s) => s?.id === b.id);
      if (previous === -1) return b.view.x < 0.5 ? 0 : 1;
      const past = previous === 0 ? b.view.x - 0.5 : 0.5 - b.view.x;
      return past > HANDS.SEAM_HYSTERESIS ? 1 - previous : previous;
    };
    const mine = valid.filter((b) => sideOf(b) === slot).sort((a, b) => a.torso.z - b.torso.z);
    return mine[0] ?? null;
  }

  // Slot of the body whose wrist is nearest to a hand's wrist (camera coords), or null.
  slotForHand(wrist) {
    let best = null;
    this.slots.forEach((body, slot) => {
      if (!body) return;
      for (const w of [body.kp.l_wrist, body.kp.r_wrist]) {
        if (!w) continue;
        const d = Math.hypot(w.x - wrist.x, w.y - wrist.y);
        if (d <= BODY.WRIST_MATCH_RADIUS && (!best || d < best.d)) best = { slot, d };
      }
    });
    return best?.slot ?? null;
  }
}
