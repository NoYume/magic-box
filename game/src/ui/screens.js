// Full-screen moments: menu, countdown, knockout + round banner, and results.
// Visibility and motion are CSS transitions keyed off classes; this module only sets state.

import { ROUND } from '../game/balance.js';
import { PHASE, SEAT, TUTORIAL_SIGNS, countdownValue } from '../game/rounds.js';
import { CHARACTERS, PLAYER_THEME } from '../theme.js';
import { signArt } from './hand-art.js';
import { SPELLBOOK } from './spellbook.js';

const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V'];
const STAT_ROWS = [['casts', 'Spells cast'], ['hits', 'Hits landed'], ['blocked', 'Damage warded'], ['evaded', 'Bolts dodged'], ['bestHit', 'Mightiest hit']];

const TUTORIAL = new Map(SPELLBOOK.map((spell) => [spell.sign, spell]));

function lessonDots() {
  return TUTORIAL_SIGNS.map((_, step) => `<i data-step="${step}" aria-hidden="true"></i>`).join('');
}

function joinCard(slot) {
  const p = PLAYER_THEME[slot];
  const first = TUTORIAL.get(TUTORIAL_SIGNS[0]);
  return `
    <div class="join join--p${slot}" data-status="waiting">
      <span class="join__number" aria-hidden="true">${p.numeral}</span>
      <div class="join__ring" style="--progress:0">${signArt(first.sign)}</div>
      <div class="join__copy" aria-live="polite">
        <p class="join__who">${p.name} <span>${p.house}</span></p>
        <p class="join__lesson">Sign 1 of ${TUTORIAL_SIGNS.length}</p>
        <p class="join__line">${first.name}</p>
        <p class="join__sub">${first.how}. Hold to continue.</p>
        <div class="join__steps">${lessonDots()}</div>
      </div>
    </div>`;
}

export class Screens {
  constructor(root, { onStartLocal, onStartBot } = {}) {
    this.root = root;
    this.route = 'menu';
    this.characterChoices = CHARACTERS.map((character) => character.id);
    root.innerHTML = `
      <section class="screen screen--menu is-shown">
        <div class="menu__eyebrow">Magic Box / Arena</div>
        <h1 class="menu__title">Choose<br>your duel.</h1>
        <div class="menu__actions">
          <button class="menu-choice menu-choice--local" type="button">
            <span class="menu-choice__number">01</span><b>Local duel</b><small>Choose two mages, then cast abilities by voice.</small>
          </button>
          <button class="menu-choice menu-choice--bot" type="button">
            <span class="menu-choice__number">02</span><b>Challenge the Mage Bot</b><small>Speak your abilities against an arcane rival.</small>
          </button>
        </div>
        <p class="menu__foot">Voice-cast abilities / Best of three</p>
      </section>
      <section class="screen screen--characters">
        <button class="characters__back" type="button">← Main menu</button>
        <p class="characters__kicker">Local duel / Character selection</p>
        <h2 class="characters__title">Choose your mages.</h2>
        <div class="characters__players">${[0, 1]
          .map(
            (slot) => `<section class="character-player character-player--${slot}">
              <p>Player ${String(slot + 1).padStart(2, '0')}</p>
              <div class="character-options">${CHARACTERS.map(
                (character) => `<button type="button" data-character="${character.id}" data-slot="${slot}">
                  <i style="--character-color:#${character.element.toString(16).padStart(6, '0')}"></i>
                  <b>${character.name}</b><span>${character.house}</span>
                </button>`,
              ).join('')}</div>
            </section>`,
          )
          .join('')}</div>
        <button class="characters__start" type="button">Begin duel</button>
      </section>
      <section class="screen screen--attract">
        <div class="title">
          <p class="title__kicker"><span class="live-dot" aria-hidden="true"></span> Two houses. One circle.</p>
          <h1 class="title__name">Arena<svg class="title__mark" viewBox="0 0 100 100" aria-hidden="true"><path d="M8 26 34 50 8 74M92 26 66 50 92 74M50 35 60 50 50 65 40 50Z" fill="none" stroke="currentColor" stroke-width="8" /></svg></h1>
          <div class="title__aside"><p class="title__sub">Learn four signs.<br>Enter the circle.</p><p class="title__format">Each player advances separately</p></div>
        </div>
        ${joinCard(0)}${joinCard(1)}
      </section>
      <section class="screen screen--countdown"><p class="count__round"></p><p class="count__value"></p></section>
      <section class="screen screen--banner"><p class="banner__kicker"></p><p class="banner__title"></p></section>
      <section class="screen screen--results">
        <p class="results__kicker">Match complete / Final score</p>
        <h2 class="results__title"></h2>
        <table class="results__table"><thead><tr><th></th><th class="results__p0">${PLAYER_THEME[0].name}</th><th class="results__p1">${PLAYER_THEME[1].name}</th></tr></thead><tbody></tbody></table>
        <p class="results__foot"></p>
      </section>
      <p class="duel-flash" aria-hidden="true">Go.</p>
      <p class="toast" hidden></p>`;
    this.el = (sel) => root.querySelector(sel);
    this.joins = [0, 1].map((slot) => this.el(`.join--p${slot}`));
    this.cache = {};
    this.el('.menu-choice--local').addEventListener('click', () => this.#route('characters'));
    this.el('.menu-choice--bot').addEventListener('click', () => onStartBot?.());
    this.el('.characters__back').addEventListener('click', () => this.#route('menu'));
    this.el('.characters__start').addEventListener('click', () => onStartLocal?.([...this.characterChoices]));
    root.querySelectorAll('[data-character]').forEach((button) => {
      button.addEventListener('click', () => this.#chooseCharacter(Number(button.dataset.slot), button.dataset.character));
    });
    this.#paintCharacterChoices();
  }

  #route(route) {
    this.route = route;
    this.root.querySelectorAll('.screen').forEach((screen) => screen.classList.remove('is-shown'));
    this.el(`.screen--${route}`).classList.add('is-shown');
  }

  #chooseCharacter(slot, character) {
    this.characterChoices[slot] = character;
    const other = 1 - slot;
    if (this.characterChoices[other] === character) {
      this.characterChoices[other] = CHARACTERS.find((candidate) => candidate.id !== character).id;
    }
    this.#paintCharacterChoices();
  }

  #paintCharacterChoices() {
    this.root.querySelectorAll('[data-character]').forEach((button) => {
      button.classList.toggle('is-selected', this.characterChoices[Number(button.dataset.slot)] === button.dataset.character);
    });
  }

  showGame() {
    this.route = 'game';
    delete this.cache.phase;
    this.root.querySelectorAll('.screen').forEach((screen) => screen.classList.remove('is-shown'));
  }

  showMenu() {
    this.#route('menu');
  }

  setPlayers() {
    this.joins.forEach((card, slot) => {
      card.querySelector('.join__who').childNodes[0].textContent = `${PLAYER_THEME[slot].name} `;
      card.querySelector('.join__who span').textContent = PLAYER_THEME[slot].house;
    });
    this.el('.results__p0').textContent = PLAYER_THEME[0].name;
    this.el('.results__p1').textContent = PLAYER_THEME[1].name;
  }

  #once(key, value, apply) {
    if (this.cache[key] === value) return;
    this.cache[key] = value;
    apply(value);
  }

  setStatus(message) {
    const toast = this.el('.toast');
    toast.hidden = !message;
    toast.textContent = message ?? '';
  }

  update({ flow, matchStats }) {
    if (this.route !== 'game') return;
    const phase = flow.phase;
    this.#once('phase', phase, () => {
      this.root.dataset.phase = phase;
      for (const name of ['attract', 'countdown', 'banner', 'results']) this.el(`.screen--${name}`).classList.remove('is-shown');
      const shown = { [PHASE.ATTRACT]: 'attract', [PHASE.COUNTDOWN]: 'countdown', [PHASE.KO]: 'banner', [PHASE.ROUND_END]: 'banner', [PHASE.RESULTS]: 'results' }[phase];
      if (shown) this.el(`.screen--${shown}`).classList.add('is-shown');
    });
    if (phase === PHASE.ATTRACT) this.#attract(flow);
    if (phase === PHASE.COUNTDOWN) this.#countdown(flow);
    if (phase === PHASE.KO || phase === PHASE.ROUND_END) this.#banner(flow);
    if (phase === PHASE.RESULTS) this.#results(flow, matchStats);
    this.#once('fight', phase === PHASE.FIGHT && flow.phaseMs < ROUND.FIGHT_BANNER_MS, (v) => this.root.classList.toggle('is-duel-start', v));
  }

  #attract(flow) {
    flow.seats.forEach((seat, slot) => {
      const card = this.joins[slot];
      this.#once(`lesson${slot}`, `${seat.tutorialStep}|${seat.status}`, () => {
        card.dataset.status = seat.status;
        const complete = seat.status === SEAT.READY;
        const step = Math.min(seat.tutorialStep, TUTORIAL_SIGNS.length - 1);
        const spell = TUTORIAL.get(TUTORIAL_SIGNS[step]);
        card.querySelector('.join__ring').innerHTML = complete ? '<span class="join__check">✓</span>' : signArt(spell.sign);
        card.querySelector('.join__lesson').textContent = complete ? 'Tutorial complete' : `Sign ${step + 1} of ${TUTORIAL_SIGNS.length}`;
        card.querySelector('.join__line').textContent = complete ? 'Ready' : spell.name;
        card.querySelector('.join__sub').textContent = complete ? 'Waiting for your rival.' : `${spell.how}. Hold to continue.`;
        card.querySelectorAll('.join__steps i').forEach((dot, index) => dot.classList.toggle('is-done', index < seat.tutorialStep));
      });
      this.#once(`prog${slot}`, seat.progress.toFixed(2), (v) => card.querySelector('.join__ring').style.setProperty('--progress', v));
    });
  }

  #countdown(flow) {
    this.#once('countRound', flow.round, (r) => (this.el('.count__round').textContent = `Round ${ROMAN[r] ?? r}`));
    this.#once('count', countdownValue(flow), (v) => {
      const el = this.el('.count__value');
      el.textContent = String(v);
      el.classList.remove('is-ticking');
      void el.offsetWidth; // restart the CSS animation for every number
      el.classList.add('is-ticking');
    });
  }

  #banner(flow) {
    const isKo = flow.phase === PHASE.KO;
    const winner = flow.roundWinner;
    const kicker = isKo ? `Round ${ROMAN[flow.round] ?? flow.round}` : winner === null ? 'Time' : `${PLAYER_THEME[winner].house}`;
    const title = isKo ? 'Knockout' : winner === null ? 'A draw' : `${PLAYER_THEME[winner].name} takes the round`;
    this.#once('banner', `${kicker}|${title}`, () => {
      this.el('.banner__kicker').textContent = kicker;
      this.el('.banner__title').textContent = title;
      this.el('.screen--banner').dataset.winner = winner ?? 'none';
    });
  }

  #results(flow, matchStats) {
    const w = flow.matchWinner ?? 0;
    this.#once('resultTitle', w, () => {
      this.el('.results__title').textContent = `${PLAYER_THEME[w].name} wins.`;
      this.el('.screen--results').dataset.winner = w;
      this.el('.results__table tbody').innerHTML = STAT_ROWS.map(
        ([key, label]) => `<tr><th>${label}</th><td>${matchStats[0][key]}</td><td>${matchStats[1][key]}</td></tr>`,
      ).join('');
    });
    const left = Math.max(0, Math.ceil((ROUND.RESULTS_MS - flow.phaseMs) / 1000));
    this.#once('resultFoot', left, (s) => (this.el('.results__foot').textContent = `Next match in ${s}s. Both raise a palm to play again.`));
  }
}
