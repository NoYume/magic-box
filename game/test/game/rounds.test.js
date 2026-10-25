import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ROUND } from '../../src/game/balance.js';
import { PHASE, SEAT, TUTORIAL_SIGNS, createFlow, knockout, startMatch, timeScale, updateFlow } from '../../src/game/rounds.js';

const STEP_MS = 50;
const both = [true, true];
const none = [false, false];

function advance(flow, ms, input = {}) {
  const full = { signs: [[], []], palms: none, present: both, hp: [100, 100], ...input };
  const events = [];
  for (let t = 0; t < ms; t += STEP_MS) events.push(...updateFlow(flow, STEP_MS, full));
  return events;
}

function learn(flow, signsBySlot = [TUTORIAL_SIGNS, TUTORIAL_SIGNS]) {
  const events = [];
  for (let step = 0; step < TUTORIAL_SIGNS.length; step++) {
    const signs = signsBySlot.map((sequence) => (sequence[step] ? [sequence[step]] : []));
    events.push(...advance(flow, ROUND.TUTORIAL_HOLD_MS + STEP_MS, { signs }));
  }
  return events;
}

function toFight(flow) {
  learn(flow);
  advance(flow, ROUND.COUNTDOWN_MS + STEP_MS);
}

test('should_start_a_voice_match_without_the_hand_sign_tutorial', () => {
  const flow = createFlow();
  const events = startMatch(flow);
  assert.equal(flow.phase, PHASE.COUNTDOWN);
  assert.ok(flow.seats.every((seat) => seat.status === SEAT.READY));
  assert.deepEqual(events.map((event) => event.kind), ['matchStart', 'phase']);
});

test('should_start_after_both_players_learn_the_four_hand_signs', () => {
  const flow = createFlow();
  const events = learn(flow);
  assert.deepEqual(events.filter((e) => e.kind === 'tutorialStep').map((e) => e.sign), TUTORIAL_SIGNS.flatMap((sign) => [sign, sign]));
  assert.deepEqual(events.filter((e) => e.kind === 'joined').map((e) => e.slot), [0, 1]);
  assert.equal(flow.phase, PHASE.COUNTDOWN);
  events.push(...advance(flow, ROUND.COUNTDOWN_MS + STEP_MS));
  const ticks = events.filter((e) => e.kind === 'tick').map((e) => e.value);
  assert.deepEqual(ticks, [3, 2, 1]);
  assert.equal(flow.phase, PHASE.FIGHT);
});

test('should_let_each_player_finish_the_tutorial_independently', () => {
  const flow = createFlow();
  learn(flow, [TUTORIAL_SIGNS, []]);
  assert.equal(flow.phase, PHASE.ATTRACT);
  assert.equal(flow.seats[0].status, SEAT.READY);
  assert.equal(flow.seats[1].status, SEAT.WAITING);
});

test('should_lose_tutorial_progress_when_the_requested_sign_drops_early', () => {
  const flow = createFlow();
  advance(flow, ROUND.TUTORIAL_HOLD_MS / 2, { signs: [['ward'], []] });
  advance(flow, ROUND.TUTORIAL_HOLD_MS);
  assert.equal(flow.seats[0].status, SEAT.WAITING);
  assert.equal(flow.seats[0].tutorialStep, 0);
});

test('should_not_advance_for_a_body_move_or_the_wrong_hand_sign', () => {
  const flow = createFlow();
  advance(flow, ROUND.TUTORIAL_HOLD_MS * 2, { signs: [['gather'], []], bodyMoves: [['focus'], []] });
  assert.equal(flow.seats[0].tutorialStep, 0);
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
