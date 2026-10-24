import assert from 'node:assert/strict';
import { test } from 'node:test';

import { PHASE } from '../../src/game/rounds.js';
import { Match } from '../../src/game/match.js';
import { DemoBot, botToInputs } from '../../src/sources/demo-bot.js';

const FRAME_W = 960;
const FRAME_H = 600;
const TICK_MS = 33;
const MAX_MATCH_MS = 8 * 60 * 1000;

// Runs the scripted demo through the real roster/caster/rules/rounds until the match ends.
function runDemoMatch() {
  const match = new Match();
  const bots = [new DemoBot(0, 7), new DemoBot(1, 19)];
  const events = [];
  const phases = new Set();
  let t = 0;
  for (; t < MAX_MATCH_MS; t += TICK_MS) {
    const context = { phase: match.flow.phase, phaseMs: match.flow.phaseMs, combat: match.combat };
    const inputs = bots.map((b, slot) => botToInputs(slot, b.update(t, context), FRAME_W, FRAME_H));
    events.push(...match.ingestBodies(inputs.map((i) => i.body), t));
    events.push(...match.ingest(inputs.flatMap((i) => i.observations), t), ...match.step(TICK_MS));
    phases.add(match.flow.phase);
    if (events.some((e) => e.kind === 'matchOver')) break;
  }
  return { match, events, phases, t };
}

test('demo_bots_should_play_a_full_best_of_three_match', () => {
  const { match, events, phases, t } = runDemoMatch();
  const kinds = (k) => events.filter((e) => e.kind === k);
  assert.equal(kinds('joined').length, 2, 'both players join');
  assert.ok(kinds('tick').length >= 6, 'countdowns run');
  assert.ok(kinds('cast').some((e) => e.projectile.kind === 'bolt'), 'bolts are cast');
  assert.ok(kinds('cast').some((e) => e.projectile.empowered), 'gather empowers a bolt');
  assert.ok(kinds('hit').some((e) => e.blocked > 0), 'wards block');
  assert.ok(kinds('evade').length > 0, 'dodges evade bolts');
  assert.ok(kinds('stance').some((e) => e.stance === 'leanIn'), 'players lean in to focus');
  assert.ok(kinds('stance').some((e) => e.stance === 'leanBack'), 'players lean back to brace');
  assert.ok(kinds('ko').length >= 2, 'rounds end by knockout');
  assert.equal(kinds('matchOver').length, 1);
  assert.ok([PHASE.ATTRACT, PHASE.COUNTDOWN, PHASE.FIGHT, PHASE.KO, PHASE.ROUND_END, PHASE.RESULTS].every((p) => phases.has(p)));
  assert.equal(Math.max(...match.flow.wins), 2);
  const rounds = kinds('roundOver').length;
  const avgRoundS = t / 1000 / rounds;
  assert.ok(avgRoundS > 25 && avgRoundS < 120, `average round ${avgRoundS.toFixed(1)} s`);
});

test('incantation_hook_should_cast_only_during_fight', () => {
  const match = new Match();
  assert.deepEqual(match.castIncantation(0, 'bolt', 1), []);
  match.flow.phase = PHASE.FIGHT;
  assert.equal(match.castIncantation(0, 'bolt', 1)[0].kind, 'cast');
  assert.deepEqual(match.castIncantation(0, 'fireworks', 1), []);
});
