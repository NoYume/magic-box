// Minimal fight HUD: health, mana, and a central round clock.
// The spellbook and in-world effects carry the rest of the combat information.

import { PLAYER, ROUND } from '../game/balance.js';
import { PLAYER_THEME } from '../theme.js';
const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];
const LOW_HP = 30;

const roman = (n) => ROMAN[n] ?? String(n);

function plateMarkup(slot) {
  const p = PLAYER_THEME[slot];
  const crystals = Array.from({ length: PLAYER.HP_SEGMENTS }, () => '<i class="crystal"><i class="crystal__fill"></i></i>').join('');
  return `
    <span class="plate__label">Health</span>
    <div class="plate__crystals" role="meter" aria-label="${p.name} health" aria-valuemin="0" aria-valuemax="${PLAYER.MAX_HP}">${crystals}</div>
    <span class="plate__label">Mana</span>
    <div class="plate__mana" role="meter" aria-label="${p.name} mana" aria-valuemin="0" aria-valuemax="${PLAYER.MAX_MANA}"><span class="plate__mana-fill"></span></div>`;
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
        healthMeter: el.querySelector('.plate__crystals'),
        manaMeter: el.querySelector('.plate__mana'),
        mana: el.querySelector('.plate__mana-fill'),
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

  setPlayers() {
    this.plates.forEach((plate, slot) => {
      plate.el.setAttribute('aria-label', PLAYER_THEME[slot].name);
      plate.healthMeter.setAttribute('aria-label', `${PLAYER_THEME[slot].name} health`);
      plate.manaMeter.setAttribute('aria-label', `${PLAYER_THEME[slot].name} mana`);
    });
  }

  update({ combat, flow }) {
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
    this.plates.forEach((plate, slot) => this.#plate(plate, combat.players[slot]));
  }

  #set(plate, key, value, apply) {
    if (plate.cache[key] === value) return;
    plate.cache[key] = value;
    apply(value);
  }

  #plate(plate, player) {
    const perCrystal = PLAYER.MAX_HP / PLAYER.HP_SEGMENTS;
    plate.crystals.forEach((crystal, i) => {
      const fill = Math.max(0, Math.min(1, (player.hp - i * perCrystal) / perCrystal));
      this.#set(plate, `c${i}`, fill.toFixed(2), (value) => crystal.style.setProperty('--fill', value));
    });
    const hp = Math.max(0, Math.round(player.hp));
    this.#set(plate, 'hp', hp, (value) => plate.healthMeter.setAttribute('aria-valuenow', value));
    this.#set(plate, 'low', player.hp <= LOW_HP, (value) => plate.el.classList.toggle('is-low', value));
    this.#set(plate, 'mana', (player.mana / PLAYER.MAX_MANA).toFixed(3), (value) => {
      plate.mana.style.setProperty('--fill', value);
      plate.manaMeter.setAttribute('aria-valuenow', Math.round(Number(value) * PLAYER.MAX_MANA));
    });
  }
}
