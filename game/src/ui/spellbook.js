// Per-player quick reference: a printed gesture guide in the lobby and a dark equipment rail
// during combat. Both retain visual hand/body cues and highlight active signs and stances.

import { PHASE as CAST } from '../game/caster.js';
import { bodyArt } from './body-art.js';
import { signArt } from './hand-art.js';

export const SPELLBOOK = [
  { sign: 'ward', name: 'Ward', cue: 'Open palm', how: 'Open palm to the screen', note: 'Blocks while held. Costs mana.' },
  { sign: 'gather', name: 'Gather', cue: 'Hold a fist', how: 'Make a fist and hold', note: 'Charges your next spell.' },
  { sign: 'aim', name: 'Bolt', cue: 'Two fingers, shoot', how: 'Two fingers, then jab', note: 'Jab at your rival or the screen.' },
  { sign: 'ultimate', name: 'Ultimate', cue: 'Diamond + hold', how: 'Diamond with both hands', note: 'Full charge, hold one second.' },
];

// Body moves change how spells land; they never cast on their own.
export const BODY_BOOK = [
  { move: 'focus', name: 'Focus', cue: 'Lean in', how: 'Lean in toward the screen', note: 'Gather charges twice as fast.' },
  { move: 'brace', name: 'Brace', cue: 'Lean back', how: 'Lean back and hold', note: 'Take less damage from hits.' },
  { move: 'dodge', name: 'Dodge', cue: 'Quick side step', how: 'Sway sideways, quickly', note: 'Bolts miss. Ultimates do not.' },
];
const STANCE_MOVE = { leanIn: 'focus', leanBack: 'brace' };

const card = (key, art, { name, cue, how, note }) => `
  <li class="spell-card" data-sign="${key}">
    <div class="spell-card__icon-frame">
      ${art}
      <span class="spell-card__ring" aria-hidden="true"></span>
    </div>
    <div class="spell-card__text">
      <b>${name}</b>
      <span class="cue">${cue}</span>
      <span class="how">${how}</span>
      <span class="note">${note}</span>
    </div>
  </li>`;

const ACTIVE_PHASES = new Set([CAST.DETECTED, CAST.WARDING, CAST.CHARGING, CAST.READY, CAST.CAST]);

export class Spellbook {
  constructor(root, slot) {
    this.root = root;
    this.slot = slot;
    root.className = `spellbook spellbook--p${slot}`;
    root.innerHTML = `
      <h3 class="spellbook__title"><span>01 — The hand signs</span><span>Cast</span></h3>
      <ol class="spellbook__list">${SPELLBOOK.map((s) => card(s.sign, signArt(s.sign), s)).join('')}</ol>
      <h4 class="spellbook__sub"><span>02 — Move your body</span><span>Defend + amplify</span></h4>
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
