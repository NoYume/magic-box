// Single-player opponent. The mage repeats bolt -> gather -> ultimate, pausing between actions.
// It drives the same combat rules as a human caster so projectiles, damage, audio and FX stay real.

import { applyIntent, castBolt, castUltimate } from './rules.js';

export const MAGE_BOT_ACTIONS = Object.freeze(['shoot', 'gather', 'ultimate']);
export const MAGE_BOT_WAIT_MIN_MS = 2000;
export const MAGE_BOT_WAIT_MAX_MS = 4000;
export const MAGE_BOT_GATHER_MS = 1000;

export class MageBot {
  constructor({ slot = 1, random = Math.random } = {}) {
    this.slot = slot;
    this.random = random;
    this.reset(0);
  }

  reset(now) {
    this.actionIndex = 0;
    this.gatherUntil = null;
    this.nextActionAt = now + this.#wait();
  }

  update(combat) {
    const now = combat.clockMs;
    if (this.gatherUntil !== null) {
      if (now < this.gatherUntil) {
        applyIntent(combat, this.slot, { gathering: true, warding: false });
        return [];
      }
      applyIntent(combat, this.slot, { gathering: false, warding: false });
      this.gatherUntil = null;
    }
    if (now < this.nextActionAt) return [];

    const action = MAGE_BOT_ACTIONS[this.actionIndex];
    const player = combat.players[this.slot];
    if (action === 'gather') {
      applyIntent(combat, this.slot, { gathering: true, warding: false });
      this.gatherUntil = now + MAGE_BOT_GATHER_MS;
      this.#advance(now);
      return [{ kind: 'botAction', slot: this.slot, action }];
    }

    let fx;
    if (action === 'shoot') {
      fx = castBolt(combat, this.slot, { thrust: 0.65, origin: player.core });
    } else {
      // The Mage Bot's signature loop intentionally overrides the normal long ultimate cooldown.
      player.charge = 1;
      player.ultimateReadyAt = now;
      fx = castUltimate(combat, this.slot, { origin: player.core });
    }
    this.#advance(now);
    return [{ kind: 'botAction', slot: this.slot, action }, ...fx];
  }

  #advance(now) {
    this.actionIndex = (this.actionIndex + 1) % MAGE_BOT_ACTIONS.length;
    this.nextActionAt = now + this.#wait();
  }

  #wait() {
    return MAGE_BOT_WAIT_MIN_MS + this.random() * (MAGE_BOT_WAIT_MAX_MS - MAGE_BOT_WAIT_MIN_MS);
  }
}
