import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MAX_HP, castSpell, createGame, handleGesture, step } from '../src/game.js';

function readyGame() {
  const game = createGame();
  game.players.forEach((p) => (p.present = true));
  return game;
}

function runUntilBoltsLand(game) {
  const fx = [];
  for (let i = 0; i < 300 && game.bolts.length; i++) fx.push(...step(game, 1 / 60));
  return fx;
}

test('should_damage_opponent_when_push_bolt_lands', () => {
  const game = readyGame();
  handleGesture(game, 0, { type: 'push', power: 2 }, 0);
  runUntilBoltsLand(game);
  assert.ok(game.players[1].hp < MAX_HP);
});

test('should_reduce_damage_when_target_is_shielding', () => {
  const open = readyGame();
  const shielded = readyGame();
  handleGesture(shielded, 1, { type: 'stance', stance: 'back' }, 0);
  for (const game of [open, shielded]) {
    castSpell(game, 0, 'fireball');
    runUntilBoltsLand(game);
  }
  assert.ok(MAX_HP - shielded.players[1].hp < MAX_HP - open.players[1].hp);
});

test('should_fire_heavy_bolt_after_full_charge', () => {
  const game = readyGame();
  handleGesture(game, 0, { type: 'stance', stance: 'forward' }, 0);
  step(game, 2);
  const [cast] = handleGesture(game, 0, { type: 'push', power: 2 }, 0);
  assert.equal(cast.bolt.heavy, true);
  assert.equal(game.players[0].charge, 0);
});

test('should_declare_winner_on_knockout', () => {
  const game = readyGame();
  game.players[1].hp = 1;
  castSpell(game, 0, 'lightning');
  const fx = runUntilBoltsLand(game);
  assert.equal(game.winner, 0);
  assert.ok(fx.some((e) => e.kind === 'ko'));
});

test('should_ignore_gestures_from_absent_player', () => {
  const game = createGame();
  assert.deepEqual(handleGesture(game, 0, { type: 'push', power: 2 }, 0), []);
});
