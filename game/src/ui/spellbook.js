// Per-player spellbook card: the four hand signs and three body moves as line illustrations,
// learnable in ten seconds. Expanded on the attract screen, compact during the duel with the
// active sign and stance highlighted.

import { PHASE as CAST } from '../game/caster.js';
import { bodyArt } from './body-art.js';
import { signArt } from './hand-art.js';

export const SPELLBOOK = [
  { sign: 'ward', name: 'Ward', how: 'Open palm to the screen', note: 'Blocks while held. Costs mana.' },
  { sign: 'gather', name: 'Gather', how: 'Make a fist and hold', note: 'Charges your next spell.' },
  { sign: 'aim', name: 'Bolt', how: 'Two fingers, then thrust', note: 'Push toward the screen to fire.' },
  { sign: 'ultimate', name: 'Ultimate', how: 'Diamond with both hands', note: 'Full charge, hold one second.' },
];

// Body moves change how spells land; they never cast on their own.
export const BODY_BOOK = [
  { move: 'focus', name: 'Focus', how: 'Lean in toward the screen', note: 'Gather charges twice as fast.' },
  { move: 'brace', name: 'Brace', how: 'Lean back and hold', note: 'Take less damage from hits.' },
  { move: 'dodge', name: 'Dodge', how: 'Sway sideways, quickly', note: 'Bolts miss. Ultimates do not.' },
];
const STANCE_MOVE = { leanIn: 'focus', leanBack: 'brace' };

const card = (key, art, { name, how, note }) => `<li class="spell-card" data-sign="${key}">${art}<div class="spell-card__text"><b>${name}</b><span class="how">${how}</span><span class="note">${note}</span></div></li>`;

const ACTIVE_PHASES = new Set([CAST.DETECTED, CAST.WARDING, CAST.CHARGING, CAST.READY, CAST.CAST]);

export class Spellbook {
  constructor(root, slot) {
    this.root = root;
    this.slot = slot;
    root.className = `spellbook spellbook--p${slot}`;
    root.innerHTML = `
      <h3 class="spellbook__title">Spellbook</h3>
      <ol class="spellbook__list">${SPELLBOOK.map((s) => card(s.sign, signArt(s.sign), s)).join('')}</ol>
      <h4 class="spellbook__sub">Body</h4>
      <ol class="spellbook__list spellbook__list--body">${BODY_BOOK.map((m) => card(m.move, bodyArt(m.move), m)).join('')}</ol>`;
    this.cards = new Map([...root.querySelectorAll('.spell-card')].map((el) => [el.dataset.sign, el]));
    this.active = null;
    this.activeMove = null;
    this.mode = null;
  }

  setMode(mode) {
    if (mode === this.mode) return;
    this.mode = mode;
    this.root.dataset.mode = mode; // 'open' | 'compact' | 'hidden'
  }

  // Highlights the body move in effect: the held stance, or a dodge inside its evade window.
  setBody(player, now) {
    const isDodging = now < player.evadeUntil;
    const move = isDodging ? 'dodge' : STANCE_MOVE[player.stance] ?? null;
    if (move === this.activeMove) return;
    this.cards.get(this.activeMove)?.classList.remove('is-active');
    this.cards.get(move)?.classList.add('is-active');
    this.activeMove = move;
  }

  // Highlights the sign this player is currently forming.
  setCaster(caster) {
    let active = null;
    if (caster?.ultimate) active = 'ultimate';
    else if (caster) {
      for (const state of caster.handStates.values()) if (ACTIVE_PHASES.has(state.phase)) active = state.sign;
    }
    if (active === this.active) return;
    this.cards.get(this.active)?.classList.remove('is-active');
    this.cards.get(active)?.classList.add('is-active');
    this.active = active;
  }
}
