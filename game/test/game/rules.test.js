import assert from 'node:assert/strict';
import { test } from 'node:test';

import { BODY_MOVES, BOLT, PLAYER, ULTIMATE, WARD } from '../../src/game/balance.js';
import { applyIntent, castBolt, castUltimate, createCombat, dodge, setStance, stepCombat } from '../../src/game/rules.js';

const STEP_MS = 16;

function runUntilLanded(combat, maxMs = 4000) {
  const fx = [];
  for (let t = 0; t < maxMs && combat.projectiles.length; t += STEP_MS) fx.push(...stepCombat(combat, STEP_MS));
  return fx;
}

test('should_damage_opponent_when_bolt_lands', () => {
  const combat = createCombat();
  castBolt(combat, 0);
  const fx = runUntilLanded(combat);
  assert.equal(combat.players[1].hp, PLAYER.MAX_HP - BOLT.BASE_DAMAGE);
  assert.ok(fx.some((e) => e.kind === 'hit' && e.damage === BOLT.BASE_DAMAGE));
});

test('should_empower_bolt_with_gathered_charge_and_consume_it', () => {
  const combat = createCombat();
  applyIntent(combat, 0, { gathering: true, warding: false });
  stepCombat(combat, 1000);
  assert.equal(combat.players[0].charge, 1);
  const [cast] = castBolt(combat, 0, { thrust: 1 });
  assert.equal(cast.projectile.empowered, true);
  assert.equal(cast.projectile.damage, BOLT.BASE_DAMAGE + BOLT.CHARGE_DAMAGE + BOLT.THRUST_DAMAGE);
  assert.equal(combat.players[0].charge, 0);
});

test('should_block_bolt_with_ward_and_spend_mana', () => {
  const combat = createCombat();
  applyIntent(combat, 1, { gathering: false, warding: true });
  castBolt(combat, 0);
  runUntilLanded(combat);
  assert.equal(combat.players[1].hp, PLAYER.MAX_HP);
  assert.ok(combat.players[1].mana < PLAYER.MAX_MANA - BOLT.BASE_DAMAGE * WARD.MANA_PER_DAMAGE + 1);
});

test('should_shatter_ward_when_overloaded_and_pass_overflow_damage', () => {
  const combat = createCombat();
  applyIntent(combat, 1, { gathering: false, warding: true });
  combat.players[1].mana = 12; // absorbs under 5 damage, minus what the ward drains in flight
  castBolt(combat, 0);
  const fx = runUntilLanded(combat);
  assert.ok(fx.some((e) => e.kind === 'wardShatter'));
  const taken = PLAYER.MAX_HP - combat.players[1].hp;
  assert.ok(taken > 0 && taken < BOLT.BASE_DAMAGE, `took ${taken}`);
  assert.equal(combat.players[1].isWarding, false);
  assert.deepEqual(applyIntent(combat, 1, { gathering: false, warding: true }), [], 'cannot re-raise while broken');
});

test('should_enforce_bolt_cooldown', () => {
  const combat = createCombat();
  assert.equal(castBolt(combat, 0).length, 1);
  assert.equal(castBolt(combat, 0).length, 0);
  stepCombat(combat, BOLT.COOLDOWN_MS);
  assert.equal(castBolt(combat, 0).length, 1);
});

test('should_require_full_charge_for_ultimate_and_apply_long_cooldown', () => {
  const combat = createCombat();
  assert.equal(castUltimate(combat, 0).length, 0);
  combat.players[0].charge = 1;
  assert.equal(castUltimate(combat, 0).length, 1);
  combat.players[0].charge = 1;
  assert.equal(castUltimate(combat, 0).length, 0, 'still cooling down');
  runUntilLanded(combat);
  assert.equal(combat.players[1].hp, PLAYER.MAX_HP - ULTIMATE.DAMAGE);
});

test('should_let_half_of_ultimate_through_a_ward', () => {
  const combat = createCombat();
  applyIntent(combat, 1, { gathering: false, warding: true });
  combat.players[0].charge = 1;
  castUltimate(combat, 0);
  runUntilLanded(combat);
  assert.equal(combat.players[1].hp, PLAYER.MAX_HP - ULTIMATE.DAMAGE * ULTIMATE.WARD_PASS_THROUGH);
});

test('should_drain_mana_while_warding_and_regenerate_after', () => {
  const combat = createCombat();
  applyIntent(combat, 0, { gathering: false, warding: true });
  stepCombat(combat, 2000);
  const drained = combat.players[0].mana;
  assert.equal(drained, PLAYER.MAX_MANA - 2 * WARD.DRAIN_PER_S);
  applyIntent(combat, 0, { gathering: false, warding: false });
  for (let i = 0; i < 100; i++) stepCombat(combat, 20);
  assert.ok(combat.players[0].mana > drained);
});

test('should_knock_out_once_and_fizzle_later_projectiles', () => {
  const combat = createCombat();
  combat.players[1].hp = 1;
  combat.players[0].hp = 1;
  castBolt(combat, 0);
  castBolt(combat, 1);
  const fx = runUntilLanded(combat);
  assert.equal(fx.filter((e) => e.kind === 'ko').length, 1);
  assert.ok(fx.some((e) => e.kind === 'fizzle'));
});

test('should_decay_charge_after_hold_window', () => {
  const combat = createCombat();
  applyIntent(combat, 0, { gathering: true, warding: false });
  stepCombat(combat, 1000);
  applyIntent(combat, 0, { gathering: false, warding: false });
  stepCombat(combat, 2000);
  assert.equal(combat.players[0].charge, 1, 'kept during hold window');
  for (let i = 0; i < 100; i++) stepCombat(combat, 50);
  assert.equal(combat.players[0].charge, 0);
});

test('should_reduce_damage_while_braced', () => {
  const combat = createCombat();
  setStance(combat, 1, 'leanBack');
  castBolt(combat, 0);
  runUntilLanded(combat);
  assert.equal(combat.players[1].hp, PLAYER.MAX_HP - Math.round(BOLT.BASE_DAMAGE * (1 - BODY_MOVES.BRACE_REDUCTION)));
});

test('should_gather_faster_while_leaning_in', () => {
  const combat = createCombat();
  setStance(combat, 0, 'leanIn');
  applyIntent(combat, 0, { gathering: true, warding: false });
  stepCombat(combat, 250);
  assert.equal(combat.players[0].charge, 0.25 * BODY_MOVES.FOCUS_GATHER_MULT);
});

test('should_evade_bolt_when_dodge_window_covers_impact', () => {
  const combat = createCombat();
  castBolt(combat, 0);
  for (let t = 0; t < 300; t += STEP_MS) stepCombat(combat, STEP_MS);
  assert.equal(dodge(combat, 1, -1)[0].kind, 'dodge');
  const fx = runUntilLanded(combat);
  assert.ok(fx.some((e) => e.kind === 'evade'));
  assert.equal(combat.players[1].hp, PLAYER.MAX_HP);
});

test('should_not_evade_when_dodging_too_early_or_on_cooldown', () => {
  const combat = createCombat();
  dodge(combat, 1, 1);
  assert.deepEqual(dodge(combat, 1, 1), [], 'cooldown');
  stepCombat(combat, BODY_MOVES.EVADE_MS + 10);
  castBolt(combat, 0);
  runUntilLanded(combat);
  assert.ok(combat.players[1].hp < PLAYER.MAX_HP);
});

test('should_never_damage_from_body_moves_alone', () => {
  const combat = createCombat();
  for (const stance of ['leanIn', 'leanBack', 'neutral']) setStance(combat, 0, stance);
  dodge(combat, 0, 1);
  for (let i = 0; i < 100; i++) stepCombat(combat, 50);
  assert.deepEqual(combat.players.map((p) => p.hp), [PLAYER.MAX_HP, PLAYER.MAX_HP]);
});
