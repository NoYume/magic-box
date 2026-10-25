// Orchestrates one cabinet session: body roster + posture (body moves) and hand roster -> per-player
// casters (hand signs) -> combat rules, inside the round flow. Pure (no DOM), so the full loop runs headless in tests with the demo bots.

import { BodyRoster } from '../vision/bodies.js';
import { calibrationScale } from '../vision/depth.js';
import { PostureDetector, STANCE } from '../vision/posture.js';
import { HandRoster } from '../vision/roster.js';
import { SIGNS } from '../vision/signs.js';
import { GATHER, ROUND, SEATS, WARD } from './balance.js';
import { PlayerCaster } from './caster.js';
import { MageBot } from './mage-bot.js';
import { PHASE, SEAT, TUTORIAL_SIGNS, createFlow, isCombatLive, knockout, startMatch, timeScale, updateFlow } from './rounds.js';
import { applyIntent, castBolt, castUltimate, createCombat, dodge, resetCombat, setAnchors, setStance, stepCombat } from './rules.js';

const INCANTATION_WARD_MS = 1500;
const INCANTATION_GATHER = 0.5;
const SPELLS = ['bolt', 'ward', 'gather', 'ultimate'];
const BODY_STALE_MS = 500; // body slots are trusted for hand attachment while this fresh
const INPUT_STALE_MS = 400; // no hand / body input for this long (camera stall): forget it all

const emptyStats = () => ({ casts: 0, hits: 0, blocked: 0, damageDealt: 0, bestHit: 0, evaded: 0 });

export class Match {
  constructor({ mirror = true, mode = 'local', botRandom = Math.random } = {}) {
    this.mirror = mirror;
    this.mode = mode;
    this.bot = mode === 'bot' ? new MageBot({ slot: 1, random: botRandom }) : null;
    this.roster = new HandRoster({ mirror });
    this.bodyRoster = new BodyRoster({ mirror });
    this.postures = [new PostureDetector(), new PostureDetector()];
    this.lastBodiesMs = -Infinity;
    // Monotonic match clock (sum of step dt), independent of the source's timestamps.
    this.clockMs = 0;
    this.seenAt = { hands: -Infinity, bodies: -Infinity };
    this.casters = [new PlayerCaster(), new PlayerCaster()];
    this.combat = createCombat();
    this.flow = createFlow();
    if (this.bot) {
      this.flow.seats[1] = {
        status: SEAT.READY,
        progress: 1,
        tutorialStep: TUTORIAL_SIGNS.length,
      };
    }
    this.view = {
      botSlot: this.bot?.slot ?? null,
      slots: [[], []],
      triangles: [{ active: false }, { active: false }],
      rejected: [],
      casters: [null, null],
      bodies: [null, null],
      postures: [null, null],
      rejectedBodies: [],
    };
    this.matchStats = [emptyStats(), emptyStats()];
    this.hitStopMs = 0;
    this.incantationWardUntil = [0, 0];
    this.voiceControlled = false;
  }

  // New body skeletons (camera coords, docs/protocol.md). Returns fx events (stance, dodge).
  ingestBodies(bodies, tMs) {
    const previous = this.bodyRoster.slots.map((b) => b?.id);
    const { slots, rejected } = this.bodyRoster.update(bodies);
    this.lastBodiesMs = tMs;
    this.seenAt.bodies = this.clockMs;
    this.view.bodies = slots;
    this.view.rejectedBodies = rejected;
    const fx = [];
    const live = isCombatLive(this.flow);
    slots.forEach((body, slot) => {
      if (this.bot && slot === this.bot.slot) return;
      if (body && body.id !== previous[slot]) this.postures[slot].reset();
      const posture = body ? this.postures[slot].update(body.kp, tMs) : null;
      this.view.postures[slot] = posture;
      if (!live) return;
      fx.push(...setStance(this.combat, slot, posture?.stance ?? STANCE.NEUTRAL));
      if (posture?.dodge) fx.push(...dodge(this.combat, slot, this.mirror ? -posture.dodge : posture.dodge));
    });
    return fx;
  }

  // New hand observations from the source. Returns fx events (casts, ward up/down).
  ingest(observations, tMs) {
    const bodies = tMs - this.lastBodiesMs <= BODY_STALE_MS ? this.bodyRoster : null;
    const { slots, triangles, rejected } = this.roster.update(observations, tMs, bodies);
    this.seenAt.hands = this.clockMs;
    Object.assign(this.view, { slots, triangles, rejected });
    const fx = [];
    const live = isCombatLive(this.flow);
    for (const slot of [0, 1]) {
      if (this.bot && slot === this.bot.slot) {
        this.view.casters[slot] = null;
        setAnchors(this.combat, slot, { core: SEATS[slot], wardAt: null });
        continue;
      }
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
    this.clockMs += dtMs;
    const fx = [...this.#expireStaleInput()];
    const palms = [0, 1].map((slot) => this.view.slots[slot].some((h) => h.sign === SIGNS.WARD));
    const signs = [0, 1].map((slot) => {
      const visible = this.view.slots[slot].map((hand) => hand.sign);
      if (this.view.triangles[slot].active) visible.push(SIGNS.ULTIMATE);
      return visible;
    });
    const present = [0, 1].map((slot) => Boolean(this.bot && slot === this.bot.slot) || this.view.slots[slot].length > 0 || Boolean(this.view.bodies[slot]));
    const hp = this.combat.players.map((p) => p.hp);
    for (const ev of updateFlow(this.flow, dtMs, { signs, palms, present, hp })) fx.push(...this.#onFlow(ev));
    if (this.voiceControlled && this.flow.phase === PHASE.ATTRACT) fx.push(...this.start());
    if (this.bot && isCombatLive(this.flow)) fx.push(...this.bot.update(this.combat));
    const scaled = dtMs * timeScale(this.flow);
    const combatDt = this.hitStopMs > 0 ? 0 : scaled;
    this.hitStopMs = Math.max(0, this.hitStopMs - dtMs);
    if (this.#combatRuns()) {
      for (const ev of stepCombat(this.combat, combatDt)) fx.push(...this.#onCombat(ev));
    }
    return fx;
  }

  // Skip the legacy hand-sign tutorial when a player starts a voice-controlled duel.
  start() {
    this.voiceControlled = true;
    return startMatch(this.flow).flatMap((event) => this.#onFlow(event));
  }

  incantationAvailability(slot, spellName) {
    if (![0, 1].includes(slot)) return { available: false, reason: 'invalidPlayer' };
    if (!SPELLS.includes(spellName)) return { available: false, reason: 'unknownAbility' };
    if (!isCombatLive(this.flow)) return { available: false, reason: 'duelNotLive' };
    const player = this.combat.players[slot];
    const now = this.combat.clockMs;
    if (spellName === 'bolt' && now < player.boltReadyAt) {
      return { available: false, reason: 'cooldown', remainingMs: player.boltReadyAt - now };
    }
    if (spellName === 'ultimate' && now < player.ultimateReadyAt) {
      return { available: false, reason: 'cooldown', remainingMs: player.ultimateReadyAt - now };
    }
    if (spellName === 'ultimate' && player.charge < 1) {
      return { available: false, reason: 'chargeRequired', charge: player.charge };
    }
    if (spellName === 'ward' && now < player.wardBrokenUntil) {
      return { available: false, reason: 'wardBroken', remainingMs: player.wardBrokenUntil - now };
    }
    if (spellName === 'ward' && player.mana < WARD.MIN_MANA_TO_RAISE) {
      return { available: false, reason: 'manaRequired', mana: player.mana };
    }
    if (spellName === 'gather' && player.charge >= 1) {
      return { available: false, reason: 'chargeFull' };
    }
    return { available: true };
  }

  // Voice / AI hook: castIncantation(slot, 'bolt' | 'ward' | 'gather' | 'ultimate', intensity 0..1).
  castIncantation(slot, spellName, intensity = 1) {
    if (!this.incantationAvailability(slot, spellName).available) return [];
    const power = Math.min(1, Math.max(0, intensity));
    const player = this.combat.players[slot];
    if (spellName === 'bolt') return castBolt(this.combat, slot, { thrust: power, origin: this.#castOrigin(slot) });
    if (spellName === 'ultimate') return castUltimate(this.combat, slot, { origin: this.#castOrigin(slot) });
    if (spellName === 'gather') {
      player.charge = Math.min(1, player.charge + INCANTATION_GATHER * power);
      player.chargeKeptUntil = this.combat.clockMs + GATHER.HOLD_MS;
    }
    if (spellName === 'ward') {
      this.incantationWardUntil[slot] = this.combat.clockMs + INCANTATION_WARD_MS * power;
      return applyIntent(this.combat, slot, { gathering: false, warding: true });
    }
    return [];
  }

  // A stalled camera must not keep the last frame alive (gathering, warding, stance, presence).
  #expireStaleInput() {
    const fx = [];
    const isStale = (kind) => this.clockMs - this.seenAt[kind] > INPUT_STALE_MS;
    const hasHands = this.view.slots.some((hands) => hands.length) || this.combat.players.some((p) => p.isGathering || p.isWarding);
    if (isStale('hands') && hasHands) {
      this.roster.reset();
      Object.assign(this.view, { slots: [[], []], triangles: [{ active: false }, { active: false }], rejected: [] });
      this.casters.forEach((caster, slot) => {
        caster.reset();
        const player = this.combat.players[slot];
        this.view.casters[slot] = caster.update({ hands: [], triangle: { active: false }, tMs: 0, player, now: this.combat.clockMs });
        fx.push(...applyIntent(this.combat, slot, { gathering: false, warding: this.combat.clockMs < this.incantationWardUntil[slot] }));
      });
    }
    const hasBodies = this.view.bodies.some(Boolean) || this.combat.players.some((p) => p.stance !== STANCE.NEUTRAL);
    if (isStale('bodies') && hasBodies) {
      this.bodyRoster.reset();
      this.postures.forEach((posture) => posture.reset());
      Object.assign(this.view, { bodies: [null, null], postures: [null, null], rejectedBodies: [] });
      [0, 1].forEach((slot) => fx.push(...setStance(this.combat, slot, STANCE.NEUTRAL)));
    }
    return fx;
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

  // Where this player can be hit: their torso when tracked, else between their hands, else the seat.
  #anchor(slot, hands, wardHand) {
    const body = this.view.bodies[slot];
    let core = { ...SEATS[slot] };
    if (body) core = { ...body.view };
    else if (hands.length) core = { x: hands.reduce((s, h) => s + h.view.x, 0) / hands.length, y: hands.reduce((s, h) => s + h.view.y, 0) / hands.length };
    return setAnchors(this.combat, slot, { core, wardAt: wardHand?.view ?? null });
  }

  #onFlow(ev) {
    if (ev.kind === 'tutorialStep' && ev.sign === SIGNS.WARD) this.#calibrate(ev.slot);
    if (ev.kind === 'matchStart') this.matchStats = [emptyStats(), emptyStats()];
    if (ev.kind === 'roundStart' || (ev.kind === 'phase' && ev.phase === PHASE.ATTRACT)) {
      resetCombat(this.combat);
      this.casters.forEach((c) => c.reset());
      this.bot?.reset(this.combat.clockMs);
      if (this.bot && ev.phase === PHASE.ATTRACT) {
        this.flow.seats[1] = {
          status: SEAT.READY,
          progress: 1,
          tutorialStep: TUTORIAL_SIGNS.length,
        };
      }
    }
    if (ev.kind === 'roundOver') this.#tallyRound();
    return [ev];
  }

  #onCombat(ev) {
    if (ev.kind === 'hit') this.hitStopMs = ev.projectile.empowered ? ROUND.HEAVY_HIT_STOP_MS : ROUND.HIT_STOP_MS;
    if (ev.kind === 'ko') return [ev, ...knockout(this.flow, ev.winner).flatMap((e) => this.#onFlow(e))];
    return [ev];
  }

  // Webcam depth: learn this player's palm-size scale during the ward tutorial step.
  #calibrate(slot) {
    this.postures[slot].calibrate();
    const palm = this.view.slots[slot].find((h) => h.sign === SIGNS.WARD);
    if (palm?.rawDepth) this.roster.setDepthScale(slot, calibrationScale(palm.rawDepth));
  }

  #tallyRound() {
    this.combat.players.forEach((p, slot) => {
      const total = this.matchStats[slot];
      for (const key of ['casts', 'hits', 'blocked', 'damageDealt', 'evaded']) total[key] += p.stats[key];
      total.bestHit = Math.max(total.bestHit, p.stats.bestHit);
    });
  }
}
