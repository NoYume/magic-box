// Full-screen moments: attract / join, countdown, knockout + round banner, and results.
// Visibility and motion are CSS transitions keyed off classes; this module only sets state.

import { PHASE, SEAT, countdownValue } from '../game/rounds.js';
import { ROUND } from '../game/balance.js';
import { PLAYER_THEME } from '../theme.js';
import { signArt } from './hand-art.js';

const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V'];
const STAT_ROWS = [['casts', 'Spells cast'], ['hits', 'Hits landed'], ['blocked', 'Damage warded'], ['evaded', 'Bolts dodged'], ['bestHit', 'Mightiest hit']];

const SEAT_TEXT = {
  [SEAT.WAITING]: ['Palm up. You’re in.', 'Face the camera. Hold for one second.'],
  [SEAT.CALIBRATING]: ['Hold that pose.', 'Finding your hand and neutral posture.'],
  [SEAT.READY]: ['Locked in.', 'Waiting for the other player.'],
};

function joinCard(slot) {
  const p = PLAYER_THEME[slot];
  return `
    <div class="join join--p${slot}" data-status="waiting">
      <span class="join__number" aria-hidden="true">${p.numeral}</span>
      <div class="join__ring" style="--progress:0">${signArt('ward')}</div>
      <div class="join__copy">
        <p class="join__who">${p.name} <span>${p.house}</span></p>
        <p class="join__line"></p><p class="join__sub"></p>
      </div>
    </div>`;
}

export class Screens {
  constructor(root) {
    this.root = root;
    root.innerHTML = `
      <section class="screen screen--attract">
        <div class="title">
          <p class="title__kicker"><span class="live-dot" aria-hidden="true"></span> No controllers. Just you.</p>
          <h1 class="title__name">Arena<svg class="title__mark" viewBox="0 0 100 100" aria-hidden="true"><path d="M8 26 34 50 8 74M92 26 66 50 92 74M50 35 60 50 50 65 40 50Z" fill="none" stroke="currentColor" stroke-width="8" /></svg></h1>
          <div class="title__aside"><p class="title__sub">Make a sign.<br>Pick a fight.</p><p class="title__format">2 players / Best of 3</p></div>
        </div>
        ${joinCard(0)}${joinCard(1)}
      </section>
      <section class="screen screen--countdown"><p class="count__round"></p><p class="count__value"></p></section>
      <section class="screen screen--banner"><p class="banner__kicker"></p><p class="banner__title"></p></section>
      <section class="screen screen--results">
        <p class="results__kicker">Match complete / Final score</p>
        <h2 class="results__title"></h2>
        <table class="results__table"><thead><tr><th></th><th>${PLAYER_THEME[0].name}</th><th>${PLAYER_THEME[1].name}</th></tr></thead><tbody></tbody></table>
        <p class="results__foot"></p>
      </section>
      <p class="duel-flash" aria-hidden="true">Go.</p>
      <p class="toast" hidden></p>`;
    this.el = (sel) => root.querySelector(sel);
    this.joins = [0, 1].map((slot) => this.el(`.join--p${slot}`));
    this.cache = {};
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
      this.#once(`seat${slot}`, seat.status, (status) => {
        card.dataset.status = status;
        const [line, sub] = SEAT_TEXT[status];
        card.querySelector('.join__line').textContent = line;
        card.querySelector('.join__sub').textContent = sub;
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
