import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ROUND } from '../../src/game/balance.js';
import { PHASE, SEAT, createFlow, knockout, timeScale, updateFlow } from '../../src/game/rounds.js';

const STEP_MS = 50;
const both = [true, true];
const none = [false, false];

function advance(flow, ms, input = {}) {
  const full = { palms: none, present: both, hp: [100, 100], ...input };
  const events = [];
  for (let t = 0; t < ms; t += STEP_MS) events.push(...updateFlow(flow, STEP_MS, full));
  return events;
}

function toFight(flow) {
  advance(flow, ROUND.JOIN_HOLD_MS + STEP_MS, { palms: both });
  advance(flow, ROUND.COUNTDOWN_MS + STEP_MS);
}

test('should_join_both_players_after_palm_hold_then_count_down', () => {
  const flow = createFlow();
  const events = advance(flow, ROUND.JOIN_HOLD_MS + STEP_MS, { palms: both });
  assert.deepEqual(events.filter((e) => e.kind === 'joined').map((e) => e.slot), [0, 1]);
  assert.equal(flow.phase, PHASE.COUNTDOWN);
  events.push(...advance(flow, ROUND.COUNTDOWN_MS + STEP_MS));
  const ticks = events.filter((e) => e.kind === 'tick').map((e) => e.value);
  assert.deepEqual(ticks, [3, 2, 1]);
  assert.equal(flow.phase, PHASE.FIGHT);
});

test('should_wait_in_attract_when_only_one_player_joins', () => {
  const flow = createFlow();
  advance(flow, 3000, { palms: [true, false] });
  assert.equal(flow.phase, PHASE.ATTRACT);
  assert.equal(flow.seats[0].status, SEAT.READY);
  assert.equal(flow.seats[1].status, SEAT.WAITING);
});

test('should_lose_join_progress_when_palm_drops_early', () => {
  const flow = createFlow();
  advance(flow, ROUND.JOIN_HOLD_MS / 2, { palms: [true, false] });
  advance(flow, ROUND.JOIN_HOLD_MS);
  assert.equal(flow.seats[0].status, SEAT.WAITING);
});

test('should_slow_time_on_ko_then_show_round_end', () => {
  const flow = createFlow();
  toFight(flow);
  knockout(flow, 0);
  assert.equal(flow.phase, PHASE.KO);
  assert.equal(timeScale(flow), ROUND.KO_TIME_SCALE);
  advance(flow, ROUND.KO_SLOWMO_MS + STEP_MS);
  assert.equal(flow.phase, PHASE.ROUND_END);
  assert.deepEqual(flow.wins, [1, 0]);
});

test('should_finish_best_of_three_and_return_to_attract', () => {
  const flow = createFlow();
  toFight(flow);
  for (const winner of [1, 0, 1]) {
    knockout(flow, winner);
    advance(flow, ROUND.KO_SLOWMO_MS + ROUND.ROUND_END_MS + 2 * STEP_MS);
    if (flow.phase === PHASE.COUNTDOWN) advance(flow, ROUND.COUNTDOWN_MS + STEP_MS);
  }
  assert.equal(flow.phase, PHASE.RESULTS);
  assert.equal(flow.matchWinner, 1);
  advance(flow, ROUND.RESULTS_MS + STEP_MS);
  assert.equal(flow.phase, PHASE.ATTRACT);
  assert.deepEqual(flow.wins, [0, 0]);
});

test('should_return_to_attract_early_when_both_show_palms_on_results', () => {
  const flow = createFlow();
  toFight(flow);
  for (const winner of [0, 0]) {
    knockout(flow, winner);
    advance(flow, ROUND.KO_SLOWMO_MS + ROUND.ROUND_END_MS + 2 * STEP_MS);
    if (flow.phase === PHASE.COUNTDOWN) advance(flow, ROUND.COUNTDOWN_MS + STEP_MS);
  }
  assert.equal(flow.phase, PHASE.RESULTS);
  advance(flow, ROUND.REMATCH_HOLD_MS + STEP_MS, { palms: both });
  assert.equal(flow.phase, PHASE.ATTRACT);
});

test('should_award_timeout_round_to_higher_hp', () => {
  const flow = createFlow();
  toFight(flow);
  advance(flow, ROUND.TIME_LIMIT_S * 1000 + STEP_MS, { hp: [40, 70] });
  assert.deepEqual(flow.wins, [0, 1]);
});

test('should_reset_to_attract_when_fight_is_abandoned', () => {
  const flow = createFlow();
  toFight(flow);
  advance(flow, ROUND.IDLE_RESET_MS + STEP_MS, { present: none });
  assert.equal(flow.phase, PHASE.ATTRACT);
});

test('should_ignore_knockout_outside_fight', () => {
  const flow = createFlow();
  assert.deepEqual(knockout(flow, 0), []);
  assert.equal(flow.phase, PHASE.ATTRACT);
});
