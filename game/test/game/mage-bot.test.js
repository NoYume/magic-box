import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MageBot } from '../../src/game/mage-bot.js';
import { Match } from '../../src/game/match.js';
import { PHASE, SEAT, TUTORIAL_SIGNS } from '../../src/game/rounds.js';
import { createCombat, stepCombat } from '../../src/game/rules.js';

const STEP_MS = 100;

test('mage_bot_should_repeat_shoot_gather_ultimate_with_pauses', () => {
  const bot = new MageBot({ random: () => 0 });
  const combat = createCombat();
  const actions = [];
  for (let elapsed = 0; elapsed <= 9000; elapsed += STEP_MS) {
    for (const event of bot.update(combat)) {
      if (event.kind === 'botAction') actions.push({ action: event.action, at: combat.clockMs });
    }
    stepCombat(combat, STEP_MS);
  }

  assert.deepEqual(actions.slice(0, 4).map((entry) => entry.action), ['shoot', 'gather', 'ultimate', 'shoot']);
  assert.deepEqual(actions.slice(0, 4).map((entry) => entry.at), [2000, 4000, 6000, 8000]);
});

test('bot_match_should_only_require_the_human_tutorial', () => {
  const match = new Match({ mode: 'bot', botRandom: () => 0 });
  assert.equal(match.flow.seats[1].status, SEAT.READY);
  assert.equal(match.flow.seats[1].tutorialStep, TUTORIAL_SIGNS.length);
  assert.equal(match.flow.seats[0].status, SEAT.WAITING);
});

test('bot_match_should_run_the_mage_cycle_during_a_fight', () => {
  const match = new Match({ mode: 'bot', botRandom: () => 0 });
  match.flow.phase = PHASE.FIGHT;
  const actions = [];
  for (let elapsed = 0; elapsed < 9000; elapsed += STEP_MS) {
    actions.push(...match.step(STEP_MS).filter((event) => event.kind === 'botAction'));
  }
  assert.deepEqual(actions.slice(0, 4).map((event) => event.action), ['shoot', 'gather', 'ultimate', 'shoot']);
});
