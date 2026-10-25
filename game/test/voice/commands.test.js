import assert from 'node:assert/strict';
import { test } from 'node:test';

import { normalizeTranscript, parseVoiceCommand } from '../../src/voice/commands.js';

test('normalizes Muse punctuation and spacing', () => {
  assert.equal(normalizeTranscript('  Player ONE,   cast BOLT. '), 'player one cast bolt');
});

test('parses solo and player-addressed ability commands', () => {
  assert.deepEqual(parseVoiceCommand('Cast ward.'), {
    slot: null,
    ability: 'ward',
    transcript: 'cast ward',
  });
  assert.deepEqual(parseVoiceCommand('Player two, cast ultimate!'), {
    slot: 1,
    ability: 'ultimate',
    transcript: 'player two cast ultimate',
  });
  assert.equal(parseVoiceCommand('P1 gather').slot, 0);
});

test('fails closed for surrounding speech and unknown actions', () => {
  assert.equal(parseVoiceCommand('please cast bolt now'), null);
  assert.equal(parseVoiceCommand('player one cast fireball'), null);
  assert.equal(parseVoiceCommand('bolt and ward'), null);
});
