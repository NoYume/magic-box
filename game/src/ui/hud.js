// Broadcast scoreboard: player IDs, segmented health bars, mana, cooldown indicators,
// round wins and a central clock. DOM writes only on change.

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
  const crystals = Array.from({ length: PLAYER.HP_SEGMENTS }, () => '<i class="crystal"><i class="crystal__fill"></i></i>').join('');
  const pips = Array.from({ length: ROUND.WINS_NEEDED }, () => '<i class="pip"><span class="pip__glow"></span></i>').join('');
  const spells = SPELLS.map((s) => `<li class="spell" data-spell="${s}" title="${s}"><span class="spell__art">${glyphSvg(s)}</span><span class="spell__sweep"></span><span class="spell__label">${s}</span></li>`).join('');
  const moves = MOVES.map((m) => `<li class="spell spell--body" data-spell="${m}" title="${m}"><span class="spell__art">${bodyArt(m)}</span><span class="spell__sweep"></span><span class="spell__label">${m}</span></li>`).join('');
  return `
    <div class="plate__cyber-bevel" aria-hidden="true"></div>
    <header class="plate__head">
      <div class="plate__crest-block">
        <span class="plate__numeral">${p.numeral}</span>
      </div>
      <div class="plate__names">
        <div class="plate__headline">
          <h2>${p.name}</h2>
          <span class="plate__hp-readout"><b class="plate__hp-current">100</b><span class="plate__hp-denom">/100</span></span>
        </div>
        <p class="plate__subhead"><span>HOUSE OF</span> <strong>${p.house}</strong></p>
      </div>
      <div class="plate__pips" aria-label="rounds won">${pips}</div>
    </header>
    <div class="plate__vitals">
      <div class="plate__crystals-container">
        <div class="plate__crystals">${crystals}</div>
      </div>
      <div class="plate__mana-strip">
        <span class="plate__mana-caption">MANA</span>
        <div class="plate__mana"><span class="plate__mana-fill"></span></div>
      </div>
    </div>
    <div class="plate__tactical-row">
      <ul class="plate__spells">${spells}<li class="plate__divider" aria-hidden="true"></li>${moves}</ul>
      <div class="plate__stance-badge" data-stance="neutral">
        <span class="stance-badge__dot"></span>
        <span class="stance-badge__text">Neutral</span>
      </div>
    </div>
    <div class="plate__ult-beacon" aria-hidden="true">
      <span class="ult-beacon__flare">⚡</span>
      <span>ULTIMATE READY</span>
    </div>`;
}

export class Hud {
  constructor(root) {
    this.root = root;
    root.innerHTML = `
      <section class="plate plate--p0">${plateMarkup(0)}</section>
      <div class="medallion">
        <div class="medallion__frame">
          <span class="medallion__round"></span>
          <span class="medallion__time"></span>
        </div>
      </div>
      <section class="plate plate--p1">${plateMarkup(1)}</section>`;
    this.plates = [0, 1].map((slot) => {
      const el = root.querySelector(`.plate--p${slot}`);
      return {
        el,
        crystals: [...el.querySelectorAll('.crystal')],
        pips: [...el.querySelectorAll('.pip')],
        mana: el.querySelector('.plate__mana-fill'),
        spells: Object.fromEntries([...el.querySelectorAll('.spell')].map((s) => [s.dataset.spell, s])),
        hpText: el.querySelector('.plate__hp-current'),
        stanceBadge: el.querySelector('.plate__stance-badge'),
        stanceText: el.querySelector('.stance-badge__text'),
        cache: {},
      };
    });
    this.round = root.querySelector('.medallion__round');
    this.time = root.querySelector('.medallion__time');
    this.medallion = root.querySelector('.medallion');
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
    const isUrgent = secs <= 10 && secs > 0;
    if (this.cache.urgent !== isUrgent) {
      this.cache.urgent = isUrgent;
      this.medallion.classList.toggle('is-urgent', isUrgent);
    }
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
    const hpVal = Math.max(0, Math.round(player.hp));
    this.#set(plate, 'hp', hpVal, (v) => {
      if (plate.hpText) plate.hpText.textContent = String(v);
    });
    this.#set(plate, 'low', player.hp <= LOW_HP, (v) => plate.el.classList.toggle('is-low', v));
    plate.pips.forEach((pip, i) => this.#set(plate, `p${i}`, i < wins, (v) => pip.classList.toggle('is-won', v)));
    this.#set(plate, 'mana', (player.mana / PLAYER.MAX_MANA).toFixed(3), (v) => plate.mana.style.setProperty('--fill', v));
    const ultReady = isUltimateReady(player, now);
    this.#set(plate, 'hasUlt', ultReady, (v) => plate.el.classList.toggle('has-ult', v));

    const isDodging = now < player.evadeUntil;
    const stance = isDodging ? 'dodge' : player.stance === 'leanIn' ? 'focus' : player.stance === 'leanBack' ? 'brace' : 'neutral';
    const stanceLabel = isDodging ? 'Evading' : player.stance === 'leanIn' ? 'Focus 2×' : player.stance === 'leanBack' ? 'Brace -40%' : 'Neutral';
    this.#set(plate, 'st', stance, (v) => {
      if (plate.stanceBadge) plate.stanceBadge.dataset.stance = v;
      if (plate.stanceText) plate.stanceText.textContent = stanceLabel;
    });

    const spells = {
      ward: { level: canRaiseWard(player, now) ? 1 : 0, on: player.isWarding },
      gather: { level: player.charge, on: player.isGathering || player.charge >= 1 },
      aim: { level: 1 - boltCooldown(player, now), on: Boolean(caster && [...caster.handStates.values()].some((s) => s.phase === 'ready')) },
      ultimate: { level: ultimateCooldown(player, now) > 0 ? 1 - ultimateCooldown(player, now) : player.charge, on: ultReady },
      focus: { level: 1, on: player.stance === 'leanIn' },
      brace: { level: 1, on: player.stance === 'leanBack' },
      dodge: { level: 1 - dodgeCooldown(player, now), on: isDodging },
    };
    for (const [name, { level, on }] of Object.entries(spells)) {
      const el = plate.spells[name];
      this.#set(plate, `s${name}`, level.toFixed(2), (v) => el.style.setProperty('--level', v));
      this.#set(plate, `o${name}`, on, (v) => el.classList.toggle('is-on', v));
    }
  }
}
