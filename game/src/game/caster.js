// Cast state machine for one player: turns smoothed hand signs + hand depth into deliberate
// actions. Nothing fires from casual movement: every cast needs a recognized sign held for its
// confirm window, then an explicit trigger (a thrust toward the camera, a sideways jab toward the
// opponent, or the ultimate hold).
//
// Per-hand phases (for the on-hand indicator):
//   idle -> detected (confirm fill) -> warding | charging | ready -> cast -> cooldown

import { SIGNS } from '../vision/signs.js';
import { JAB, THRUST } from '../vision/tuning.js';
import { BOLT, CONFIRM_MS } from './balance.js';
import { boltCooldown, canRaiseWard, isUltimateReady, ultimateCooldown } from './rules.js';

export const PHASE = Object.freeze({
  IDLE: 'idle',
  DETECTED: 'detected',
  WARDING: 'warding',
  CHARGING: 'charging',
  READY: 'ready',
  CAST: 'cast',
  COOLDOWN: 'cooldown',
  BLOCKED: 'blocked', // sign confirmed but the resource is missing (broken ward, no charge)
});

const CAST_FLASH_MS = 220;
const RECOCK_SPEED_RATIO = 0.35; // the hand must slow below this share of MIN_SPEED before re-firing

const NO_THRUST = Object.freeze({ speed: 0, travel: 0 });

// Approach speed (m/s, positive = toward the camera) and travel (m) over the thrust window.
// sinceMs: ignore samples before this (travel made before the aim sign was armed).
export function measureThrust(history, tMs, sinceMs = -Infinity) {
  const samples = history.filter((s) => s.z !== null && tMs - s.t <= THRUST.WINDOW_MS && s.t >= sinceMs);
  if (samples.length < 2) return { speed: 0, travel: 0 };
  const first = samples[0];
  const last = samples[samples.length - 1];
  const dt = (last.t - first.t) / 1000;
  const travel = first.z - last.z;
  return { speed: dt > 0 ? travel / dt : 0, travel };
}

export const isThrust = ({ speed, travel }) => speed >= THRUST.MIN_SPEED && travel >= THRUST.MIN_TRAVEL;

// Speed (view widths/s) and travel (widths) toward the opponent over the thrust window.
// toward: +1 when the opponent is to the right in view space (slot 0), -1 otherwise.
export function measureJab(history, tMs, toward, sinceMs = -Infinity) {
  const samples = history.filter((s) => s.x !== undefined && tMs - s.t <= THRUST.WINDOW_MS && s.t >= sinceMs);
  if (samples.length < 2) return NO_THRUST;
  const first = samples[0];
  const last = samples[samples.length - 1];
  const dt = (last.t - first.t) / 1000;
  const travel = (last.x - first.x) * toward;
  return { speed: dt > 0 ? travel / dt : 0, travel };
}

export const isJab = ({ speed, travel }) => speed >= JAB.MIN_SPEED && travel >= JAB.MIN_TRAVEL;

const power = (speed, min, full) => Math.max(0, Math.min(1, (speed - min) / (full - min)));

export class PlayerCaster {
  constructor() {
    this.reset();
  }

  reset() {
    this.hands = new Map(); // track id -> state
    this.ultimate = { since: null, latched: false };
  }

  // hands: roster tracks of this player; triangle: { active }; player: rules player; now: combat clock.
  update({ hands, triangle, tMs, player, now }) {
    const out = { intent: { gathering: false, warding: false }, casts: [], handStates: new Map(), ultimate: null, wardHand: null };
    const seen = new Set(hands.map((h) => h.id));
    for (const id of this.hands.keys()) if (!seen.has(id)) this.hands.delete(id);
    if (triangle.active && hands.length === 2) {
      this.#updateUltimate(hands, tMs, player, now, out);
      hands.forEach((h) => out.handStates.set(h.id, { phase: out.ultimate.phase, sign: SIGNS.ULTIMATE, progress: out.ultimate.progress }));
      return out;
    }
    this.ultimate = { since: null, latched: false };
    for (const hand of hands) out.handStates.set(hand.id, this.#updateHand(hand, tMs, player, now, out));
    return out;
  }

  #state(hand) {
    if (!this.hands.has(hand.id)) this.hands.set(hand.id, { sign: SIGNS.NONE, since: 0, armedAt: null, armedUntil: -Infinity, recocked: true, flashUntil: -Infinity });
    return this.hands.get(hand.id);
  }

  #updateHand(hand, tMs, player, now, out) {
    const s = this.#state(hand);
    if (hand.sign !== s.sign) Object.assign(s, { sign: hand.sign, since: tMs });
    const held = tMs - s.since;
    const confirm = CONFIRM_MS[s.sign] ?? Infinity;
    const isConfirmed = held >= confirm;
    if (s.sign === SIGNS.AIM && isConfirmed) {
      if (tMs >= s.armedUntil) s.armedAt = tMs; // newly armed: only travel from here on counts
      s.armedUntil = tMs + BOLT.ARM_GRACE_MS;
    }
    // No metric depth this frame (stereo dropout): the hand cannot trigger anything.
    const history = hand.depthHistory ?? [];
    const toward = hand.slot === 1 ? -1 : 1;
    const thrust = hand.depth === null ? NO_THRUST : measureThrust(history, tMs, s.armedAt ?? -Infinity);
    const jab = measureJab(history, tMs, toward, s.armedAt ?? -Infinity);
    // Re-cocking looks at the whole window, so one long push or jab cannot fire twice.
    const pushSpeed = hand.depth === null ? 0 : measureThrust(history, tMs).speed;
    const isStill = pushSpeed < THRUST.MIN_SPEED * RECOCK_SPEED_RATIO && measureJab(history, tMs, toward).speed < JAB.MIN_SPEED * RECOCK_SPEED_RATIO;
    if (!s.recocked && isStill) s.recocked = true;

    if (tMs < s.flashUntil) return { phase: PHASE.CAST, sign: SIGNS.AIM, progress: 1 };
    if (tMs < s.armedUntil) return this.#aim(hand, s, { tMs, thrust, jab, player, now, out });
    if (s.sign === SIGNS.NONE) return { phase: PHASE.IDLE, sign: SIGNS.NONE, progress: 0 };
    if (!isConfirmed) return { phase: PHASE.DETECTED, sign: s.sign, progress: held / confirm };
    if (s.sign === SIGNS.WARD) return this.#ward(hand, player, now, out);
    if (s.sign === SIGNS.GATHER) {
      out.intent.gathering = true;
      return { phase: PHASE.CHARGING, sign: SIGNS.GATHER, progress: player.charge };
    }
    return { phase: PHASE.IDLE, sign: s.sign, progress: 0 };
  }

  #ward(hand, player, now, out) {
    if (!player.isWarding && !canRaiseWard(player, now)) return { phase: PHASE.BLOCKED, sign: SIGNS.WARD, progress: 0 };
    if (!out.intent.warding) {
      out.intent.warding = true;
      out.wardHand = hand;
    }
    return { phase: PHASE.WARDING, sign: SIGNS.WARD, progress: 1 };
  }

  #aim(hand, s, { tMs, thrust, jab, player, now, out }) {
    const cooldown = boltCooldown(player, now);
    if (cooldown > 0) return { phase: PHASE.COOLDOWN, sign: SIGNS.AIM, progress: 1 - cooldown };
    const isPush = isThrust(thrust);
    if (s.recocked && (isPush || isJab(jab))) {
      const strength = isPush ? power(thrust.speed, THRUST.MIN_SPEED, THRUST.FULL_SPEED) : power(jab.speed, JAB.MIN_SPEED, JAB.FULL_SPEED);
      out.casts.push({ type: 'bolt', thrust: strength, origin: hand.view, handId: hand.id });
      Object.assign(s, { recocked: false, flashUntil: tMs + CAST_FLASH_MS, armedUntil: -Infinity });
      return { phase: PHASE.CAST, sign: SIGNS.AIM, progress: 1 };
    }
    return { phase: PHASE.READY, sign: SIGNS.AIM, progress: 1 };
  }

  #updateUltimate(hands, tMs, player, now, out) {
    const u = this.ultimate;
    u.since ??= tMs;
    const at = { x: (hands[0].view.x + hands[1].view.x) / 2, y: (hands[0].view.y + hands[1].view.y) / 2 };
    const progress = Math.min(1, (tMs - u.since) / CONFIRM_MS.ultimate);
    if (u.latched) {
      out.ultimate = { phase: PHASE.COOLDOWN, progress: 1 - ultimateCooldown(player, now), at };
    } else if (!isUltimateReady(player, now)) {
      u.since = tMs; // the hold only counts once the spell is available
      const cooling = ultimateCooldown(player, now) > 0;
      out.ultimate = { phase: cooling ? PHASE.COOLDOWN : PHASE.BLOCKED, progress: cooling ? 1 - ultimateCooldown(player, now) : player.charge, at };
    } else if (progress >= 1) {
      u.latched = true;
      out.casts.push({ type: 'ultimate', origin: at });
      out.ultimate = { phase: PHASE.CAST, progress: 1, at };
    } else {
      out.ultimate = { phase: PHASE.DETECTED, progress, at };
    }
  }
}
