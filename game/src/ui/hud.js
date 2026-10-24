// Duel HUD: framed nameplates (segmented HP crystals, mana, spell icons with cooldown sweeps,
// body-move chips, round pips), the center medallion (round + timer). DOM writes only on change.

import { PLAYER, ROUND } from '../game/balance.js';
import { boltCooldown, canRaiseWard, dodgeCooldown, isUltimateReady, ultimateCooldown } from '../game/rules.js';
import { PLAYER_THEME } from '../theme.js';
import { bodyArt } from './body-art.js';
import { glyphSvg } from './glyph-svg.js';

const SPELLS = ['ward', 'gather', 'aim', 'ultimate'];
const MOVES = ['focus', 'brace', 'dodge'];
const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];
const LOW_HP = 30;

const roman = (n) => ROMAN[n] ?? String(n);

function plateMarkup(slot) {
  const p = PLAYER_THEME[slot];
  const crystals = Array.from({ length: PLAYER.HP_SEGMENTS }, () => '<i class="crystal"><i></i></i>').join('');
  const pips = Array.from({ length: ROUND.WINS_NEEDED }, () => '<i class="pip"></i>').join('');
  const spells = SPELLS.map((s) => `<li class="spell" data-spell="${s}">${glyphSvg(s)}<span class="spell__sweep"></span></li>`).join('');
  const moves = MOVES.map((m) => `<li class="spell spell--body" data-spell="${m}" title="${m}">${bodyArt(m)}<span class="spell__sweep"></span></li>`).join('');
  return `
    <header class="plate__head">
      <span class="plate__numeral">${p.numeral}</span>
      <div class="plate__names"><h2>${p.name}</h2><p>${p.house}</p></div>
      <div class="plate__pips" aria-label="rounds won">${pips}</div>
    </header>
    <div class="plate__crystals">${crystals}</div>
    <div class="plate__mana"><span class="plate__mana-fill"></span></div>
    <ul class="plate__spells">${spells}<li class="plate__divider" aria-hidden="true"></li>${moves}</ul>`;
}

export class Hud {
  constructor(root) {
    this.root = root;
    root.innerHTML = `
      <section class="plate plate--p0">${plateMarkup(0)}</section>
      <div class="medallion"><span class="medallion__round"></span><span class="medallion__time"></span></div>
      <section class="plate plate--p1">${plateMarkup(1)}</section>`;
    this.plates = [0, 1].map((slot) => {
      const el = root.querySelector(`.plate--p${slot}`);
      return {
        el,
        crystals: [...el.querySelectorAll('.crystal')],
        pips: [...el.querySelectorAll('.pip')],
        mana: el.querySelector('.plate__mana-fill'),
        spells: Object.fromEntries([...el.querySelectorAll('.spell')].map((s) => [s.dataset.spell, s])),
        cache: {},
      };
    });
    this.round = root.querySelector('.medallion__round');
    this.time = root.querySelector('.medallion__time');
    this.cache = {};
  }

  setVisible(isVisible) {
    this.root.classList.toggle('is-shown', isVisible);
  }

  update({ combat, flow, view }) {
    const roundText = `Round ${roman(flow.round)}`;
    if (this.cache.round !== roundText) this.round.textContent = this.cache.round = roundText;
    const secs = Math.ceil(flow.timeLeftMs / 1000);
    const timeText = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`;
    if (this.cache.time !== timeText) this.time.textContent = this.cache.time = timeText;
    this.plates.forEach((plate, slot) => this.#plate(plate, combat.players[slot], flow.wins[slot], combat.clockMs, view.casters[slot]));
  }

  #set(plate, key, value, apply) {
    if (plate.cache[key] === value) return;
    plate.cache[key] = value;
    apply(value);
  }

  #plate(plate, player, wins, now, caster) {
    const perCrystal = PLAYER.MAX_HP / PLAYER.HP_SEGMENTS;
    plate.crystals.forEach((c, i) => {
      const fill = Math.max(0, Math.min(1, (player.hp - i * perCrystal) / perCrystal));
      this.#set(plate, `c${i}`, fill.toFixed(2), (v) => c.style.setProperty('--fill', v));
    });
    this.#set(plate, 'low', player.hp <= LOW_HP, (v) => plate.el.classList.toggle('is-low', v));
    plate.pips.forEach((pip, i) => this.#set(plate, `p${i}`, i < wins, (v) => pip.classList.toggle('is-won', v)));
    this.#set(plate, 'mana', (player.mana / PLAYER.MAX_MANA).toFixed(3), (v) => plate.mana.style.setProperty('--fill', v));
    const spells = {
      ward: { level: canRaiseWard(player, now) ? 1 : 0, on: player.isWarding },
      gather: { level: player.charge, on: player.isGathering || player.charge >= 1 },
      aim: { level: 1 - boltCooldown(player, now), on: Boolean(caster && [...caster.handStates.values()].some((s) => s.phase === 'ready')) },
      ultimate: { level: ultimateCooldown(player, now) > 0 ? 1 - ultimateCooldown(player, now) : player.charge, on: isUltimateReady(player, now) },
      focus: { level: 1, on: player.stance === 'leanIn' },
      brace: { level: 1, on: player.stance === 'leanBack' },
      dodge: { level: 1 - dodgeCooldown(player, now), on: now < player.evadeUntil },
    };
    for (const [name, { level, on }] of Object.entries(spells)) {
      const el = plate.spells[name];
      this.#set(plate, `s${name}`, level.toFixed(2), (v) => el.style.setProperty('--level', v));
      this.#set(plate, `o${name}`, on, (v) => el.classList.toggle('is-on', v));
    }
  }
}
