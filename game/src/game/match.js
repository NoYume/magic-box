// Orchestrates one cabinet session: hand roster -> per-player casters -> combat rules, inside the
// round flow. Pure (no DOM), so the full loop runs headless in tests with the demo bots.

import { calibrationScale } from '../vision/depth.js';
import { HandRoster } from '../vision/roster.js';
import { SIGNS } from '../vision/signs.js';
import { ROUND, SEATS } from './balance.js';
import { PlayerCaster } from './caster.js';
import { PHASE, createFlow, isCombatLive, knockout, timeScale, updateFlow } from './rounds.js';
import { applyIntent, castBolt, castUltimate, createCombat, resetCombat, setAnchors, stepCombat } from './rules.js';

const INCANTATION_WARD_MS = 1500;
const INCANTATION_GATHER = 0.5;
const SPELLS = ['bolt', 'ward', 'gather', 'ultimate'];

const emptyStats = () => ({ casts: 0, hits: 0, blocked: 0, damageDealt: 0, bestHit: 0 });

export class Match {
  constructor({ mirror = true } = {}) {
    this.roster = new HandRoster({ mirror });
    this.casters = [new PlayerCaster(), new PlayerCaster()];
    this.combat = createCombat();
    this.flow = createFlow();
    this.view = { slots: [[], []], triangles: [{ active: false }, { active: false }], rejected: [], casters: [null, null] };
    this.matchStats = [emptyStats(), emptyStats()];
    this.hitStopMs = 0;
    this.incantationWardUntil = [0, 0];
  }

  // New hand observations from the source. Returns fx events (casts, ward up/down).
  ingest(observations, tMs) {
    const { slots, triangles, rejected } = this.roster.update(observations, tMs);
    Object.assign(this.view, { slots, triangles, rejected });
    const fx = [];
    const live = isCombatLive(this.flow);
    for (const slot of [0, 1]) {
      const player = this.combat.players[slot];
      const out = this.casters[slot].update({ hands: slots[slot], triangle: triangles[slot], tMs, player, now: this.combat.clockMs });
      this.view.casters[slot] = out;
      this.#anchor(slot, slots[slot], out.wardHand);
      if (!live) continue;
      const warding = out.intent.warding || this.combat.clockMs < this.incantationWardUntil[slot];
      fx.push(...applyIntent(this.combat, slot, { ...out.intent, warding }));
      for (const cast of out.casts) fx.push(...this.#cast(slot, cast));
    }
    return fx;
  }

  // Advances real time. Returns fx events (hits, KO, flow changes, countdown ticks).
  step(dtMs) {
    const fx = [];
    const palms = [0, 1].map((slot) => this.view.slots[slot].some((h) => h.sign === SIGNS.WARD));
    const present = [0, 1].map((slot) => this.view.slots[slot].length > 0);
    const hp = this.combat.players.map((p) => p.hp);
    for (const ev of updateFlow(this.flow, dtMs, { palms, present, hp })) fx.push(...this.#onFlow(ev));
    const scaled = dtMs * timeScale(this.flow);
    const combatDt = this.hitStopMs > 0 ? 0 : scaled;
    this.hitStopMs = Math.max(0, this.hitStopMs - dtMs);
    if (this.#combatRuns()) {
      for (const ev of stepCombat(this.combat, combatDt)) fx.push(...this.#onCombat(ev));
    }
    return fx;
  }

  // Voice / AI hook: castIncantation(slot, 'bolt' | 'ward' | 'gather' | 'ultimate', intensity 0..1).
  castIncantation(slot, spellName, intensity = 1) {
    if (!isCombatLive(this.flow) || !SPELLS.includes(spellName) || ![0, 1].includes(slot)) return [];
    const power = Math.min(1, Math.max(0, intensity));
    const player = this.combat.players[slot];
    if (spellName === 'bolt') return castBolt(this.combat, slot, { thrust: power, origin: this.#castOrigin(slot) });
    if (spellName === 'ultimate') return castUltimate(this.combat, slot, { origin: this.#castOrigin(slot) });
    if (spellName === 'gather') player.charge = Math.min(1, player.charge + INCANTATION_GATHER * power);
    if (spellName === 'ward') this.incantationWardUntil[slot] = this.combat.clockMs + INCANTATION_WARD_MS * power;
    return [];
  }

  #combatRuns() {
    return [PHASE.FIGHT, PHASE.KO, PHASE.ROUND_END].includes(this.flow.phase);
  }

  #cast(slot, cast) {
    if (cast.type === 'bolt') return castBolt(this.combat, slot, { thrust: cast.thrust, origin: cast.origin });
    return castUltimate(this.combat, slot, { origin: cast.origin });
  }

  #castOrigin(slot) {
    const hands = this.view.slots[slot];
    return hands.length ? hands[0].view : this.combat.players[slot].core;
  }

  #anchor(slot, hands, wardHand) {
    if (!hands.length) return setAnchors(this.combat, slot, { core: { ...SEATS[slot] }, wardAt: null });
    const core = { x: hands.reduce((s, h) => s + h.view.x, 0) / hands.length, y: hands.reduce((s, h) => s + h.view.y, 0) / hands.length };
    return setAnchors(this.combat, slot, { core, wardAt: wardHand?.view ?? null });
  }

  #onFlow(ev) {
    if (ev.kind === 'joined') this.#calibrate(ev.slot);
    if (ev.kind === 'matchStart') this.matchStats = [emptyStats(), emptyStats()];
    if (ev.kind === 'roundStart' || (ev.kind === 'phase' && ev.phase === PHASE.ATTRACT)) {
      resetCombat(this.combat);
      this.casters.forEach((c) => c.reset());
    }
    if (ev.kind === 'roundOver') this.#tallyRound();
    return [ev];
  }

  #onCombat(ev) {
    if (ev.kind === 'hit') this.hitStopMs = ev.projectile.empowered ? ROUND.HEAVY_HIT_STOP_MS : ROUND.HIT_STOP_MS;
    if (ev.kind === 'ko') return [ev, ...knockout(this.flow, ev.winner).flatMap((e) => this.#onFlow(e))];
    return [ev];
  }

  // Webcam depth: learn this player's palm-size scale while they hold the joining palm.
  #calibrate(slot) {
    const palm = this.view.slots[slot].find((h) => h.sign === SIGNS.WARD);
    if (palm?.rawDepth) this.roster.setDepthScale(slot, calibrationScale(palm.rawDepth));
  }

  #tallyRound() {
    this.combat.players.forEach((p, slot) => {
      const total = this.matchStats[slot];
      for (const key of ['casts', 'hits', 'blocked', 'damageDealt']) total[key] += p.stats[key];
      total.bestHit = Math.max(total.bestHit, p.stats.bestHit);
    });
  }
}
