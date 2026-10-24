// Match flow. Pure state machine, no DOM.
//
//   attract (each side: waiting -> calibrating -> ready, by holding an open palm)
//     -> countdown -> fight -> ko (slow motion) -> roundEnd -> countdown ... (best of three)
//     -> results -> attract (after a while, or when both players show their palms)

import { ROUND } from './balance.js';

export const PHASE = Object.freeze({
  ATTRACT: 'attract',
  COUNTDOWN: 'countdown',
  FIGHT: 'fight',
  KO: 'ko',
  ROUND_END: 'roundEnd',
  RESULTS: 'results',
});

export const SEAT = Object.freeze({ WAITING: 'waiting', CALIBRATING: 'calibrating', READY: 'ready' });

const newSeat = () => ({ status: SEAT.WAITING, progress: 0 });

export function createFlow() {
  return {
    phase: PHASE.ATTRACT,
    phaseMs: 0,
    round: 1,
    wins: [0, 0],
    roundWinner: null,
    matchWinner: null,
    timeLeftMs: ROUND.TIME_LIMIT_S * 1000,
    seats: [newSeat(), newSeat()],
    idleMs: 0,
    rematchMs: 0,
    lastTick: null,
  };
}

export const isCombatLive = (flow) => flow.phase === PHASE.FIGHT;
export const timeScale = (flow) => (flow.phase === PHASE.KO ? ROUND.KO_TIME_SCALE : 1);
export const countdownValue = (flow) => Math.max(1, Math.ceil((ROUND.COUNTDOWN_MS - flow.phaseMs) / 1000));

function enter(flow, phase, events) {
  flow.phase = phase;
  flow.phaseMs = 0;
  flow.lastTick = null;
  events.push({ kind: 'phase', phase });
}

function backToAttract(flow, events) {
  Object.assign(flow, createFlow());
  events.push({ kind: 'phase', phase: PHASE.ATTRACT });
}

// input: { palms: [bool, bool], present: [bool, bool], hp: [n, n] }
export function updateFlow(flow, dtMs, input) {
  const events = [];
  flow.phaseMs += dtMs;
  const anyone = input.present[0] || input.present[1];
  flow.idleMs = anyone ? 0 : flow.idleMs + dtMs;
  const handler = HANDLERS[flow.phase];
  handler(flow, dtMs, input, events);
  return events;
}

const HANDLERS = {
  [PHASE.ATTRACT]: updateAttract,
  [PHASE.COUNTDOWN]: updateCountdown,
  [PHASE.FIGHT]: updateFight,
  [PHASE.KO]: (flow, dtMs, input, events) => {
    if (flow.phaseMs >= ROUND.KO_SLOWMO_MS) enter(flow, PHASE.ROUND_END, events);
  },
  [PHASE.ROUND_END]: updateRoundEnd,
  [PHASE.RESULTS]: updateResults,
};

function updateAttract(flow, dtMs, input, events) {
  if (flow.idleMs > ROUND.IDLE_RESET_MS && flow.seats.some((s) => s.status !== SEAT.WAITING)) {
    flow.seats = [newSeat(), newSeat()];
  }
  flow.seats.forEach((seat, slot) => {
    if (seat.status === SEAT.READY) return;
    const step = dtMs / ROUND.JOIN_HOLD_MS;
    seat.progress = input.palms[slot] ? seat.progress + step : Math.max(0, seat.progress - step * ROUND.JOIN_DECAY);
    seat.status = seat.progress > 0 ? SEAT.CALIBRATING : SEAT.WAITING;
    if (seat.progress >= 1) {
      Object.assign(seat, { status: SEAT.READY, progress: 1 });
      events.push({ kind: 'joined', slot });
    }
  });
  if (flow.seats.every((s) => s.status === SEAT.READY)) {
    events.push({ kind: 'matchStart' });
    enter(flow, PHASE.COUNTDOWN, events);
  }
}

function updateCountdown(flow, dtMs, input, events) {
  const value = countdownValue(flow);
  if (flow.phaseMs < ROUND.COUNTDOWN_MS && value !== flow.lastTick) {
    flow.lastTick = value;
    events.push({ kind: 'tick', value });
  }
  if (flow.phaseMs >= ROUND.COUNTDOWN_MS) {
    flow.timeLeftMs = ROUND.TIME_LIMIT_S * 1000;
    events.push({ kind: 'roundStart', round: flow.round });
    enter(flow, PHASE.FIGHT, events);
  }
}

function updateFight(flow, dtMs, input, events) {
  if (flow.idleMs > ROUND.IDLE_RESET_MS) return backToAttract(flow, events);
  flow.timeLeftMs = Math.max(0, flow.timeLeftMs - dtMs);
  if (flow.timeLeftMs > 0) return undefined;
  const [a, b] = input.hp;
  const winner = a === b ? null : a > b ? 0 : 1;
  return finishRound(flow, winner, events, PHASE.ROUND_END);
}

// Called when the rules report a knockout.
export function knockout(flow, winner) {
  const events = [];
  if (flow.phase === PHASE.FIGHT) finishRound(flow, winner, events, PHASE.KO);
  return events;
}

function finishRound(flow, winner, events, nextPhase) {
  flow.roundWinner = winner;
  if (winner !== null) flow.wins[winner] += 1;
  if (flow.wins.some((w) => w >= ROUND.WINS_NEEDED)) flow.matchWinner = flow.wins[0] > flow.wins[1] ? 0 : 1;
  events.push({ kind: 'roundOver', winner, wins: [...flow.wins] });
  enter(flow, nextPhase, events);
}

function updateRoundEnd(flow, dtMs, input, events) {
  if (flow.phaseMs < ROUND.ROUND_END_MS) return;
  if (flow.matchWinner !== null) {
    events.push({ kind: 'matchOver', winner: flow.matchWinner });
    enter(flow, PHASE.RESULTS, events);
    return;
  }
  if (flow.roundWinner !== null) flow.round += 1;
  events.push({ kind: 'nextRound', round: flow.round });
  enter(flow, PHASE.COUNTDOWN, events);
}

function updateResults(flow, dtMs, input, events) {
  flow.rematchMs = input.palms[0] && input.palms[1] ? flow.rematchMs + dtMs : 0;
  if (flow.phaseMs >= ROUND.RESULTS_MS || flow.rematchMs >= ROUND.REMATCH_HOLD_MS) backToAttract(flow, events);
}
