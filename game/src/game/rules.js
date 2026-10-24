// Combat rules. Pure state + logic, no rendering. Positions are view-normalized (mirrored frame).
//
// Each frame the caller provides per-player intent (from the caster) and anchors (where the
// player's body and ward are on screen); rules return fx events for the renderer and audio.

import { BOLT, GATHER, HIT_RADIUS, PLAYER, SEATS, ULTIMATE, WARD } from './balance.js';

export function createCombat() {
  return { players: [newPlayer(0), newPlayer(1)], projectiles: [], nextId: 1, clockMs: 0, isDecided: false };
}

function newPlayer(slot) {
  return {
    slot,
    hp: PLAYER.MAX_HP,
    mana: PLAYER.MAX_MANA,
    charge: 0,
    chargeKeptUntil: 0,
    isGathering: false,
    isWarding: false,
    wardBrokenUntil: 0,
    lastWardMs: -Infinity,
    boltReadyAt: 0,
    ultimateReadyAt: 0,
    core: { ...SEATS[slot] },
    wardAt: null,
    stats: { casts: 0, hits: 0, blocked: 0, damageDealt: 0, bestHit: 0 },
  };
}

export function resetCombat(combat) {
  combat.players = [newPlayer(0), newPlayer(1)];
  combat.projectiles = [];
  combat.clockMs = 0;
  combat.isDecided = false;
}

export const canRaiseWard = (p, now) => now >= p.wardBrokenUntil && p.mana >= WARD.MIN_MANA_TO_RAISE;
export const boltCooldown = (p, now) => Math.max(0, p.boltReadyAt - now) / BOLT.COOLDOWN_MS;
export const ultimateCooldown = (p, now) => Math.max(0, p.ultimateReadyAt - now) / ULTIMATE.COOLDOWN_MS;
export const isUltimateReady = (p, now) => now >= p.ultimateReadyAt && p.charge >= 1;

// anchors: { core: {x, y}, wardAt: {x, y} | null }
export function setAnchors(combat, slot, { core, wardAt }) {
  const p = combat.players[slot];
  if (core) p.core = core;
  p.wardAt = wardAt ?? null;
}

// intent: { gathering: bool, warding: bool }
export function applyIntent(combat, slot, intent) {
  const p = combat.players[slot];
  const now = combat.clockMs;
  p.isGathering = intent.gathering;
  const wantsWard = intent.warding && canRaiseWard(p, now);
  const fx = [];
  if (wantsWard && !p.isWarding) fx.push({ kind: 'wardUp', slot });
  if (!wantsWard && p.isWarding) fx.push({ kind: 'wardDown', slot });
  p.isWarding = wantsWard;
  return fx;
}

// Fires a bolt. power: { thrust: 0..1 } from the caster. origin: view position of the casting hand.
export function castBolt(combat, slot, { thrust = 0, origin } = {}) {
  const p = combat.players[slot];
  const now = combat.clockMs;
  if (now < p.boltReadyAt) return [];
  const charge = p.charge;
  const empowered = charge >= BOLT.EMPOWERED_AT;
  const damage = Math.round(BOLT.BASE_DAMAGE + charge * BOLT.CHARGE_DAMAGE + thrust * BOLT.THRUST_DAMAGE);
  p.charge = 0;
  p.boltReadyAt = now + BOLT.COOLDOWN_MS;
  p.stats.casts += 1;
  const speed = empowered ? BOLT.EMPOWERED_SPEED : BOLT.SPEED;
  return [launch(combat, slot, { kind: 'bolt', damage, speed, empowered, power: charge, origin })];
}

export function castUltimate(combat, slot, { origin } = {}) {
  const p = combat.players[slot];
  const now = combat.clockMs;
  if (!isUltimateReady(p, now)) return [];
  p.charge = 0;
  p.ultimateReadyAt = now + ULTIMATE.COOLDOWN_MS;
  p.stats.casts += 1;
  return [launch(combat, slot, { kind: 'ultimate', damage: ULTIMATE.DAMAGE, speed: ULTIMATE.SPEED, empowered: true, power: 1, origin })];
}

function launch(combat, slot, { kind, damage, speed, empowered, power, origin }) {
  const p = combat.players[slot];
  const start = origin ?? p.core;
  const projectile = { id: combat.nextId++, from: slot, kind, damage, speed, empowered, power, x: start.x, y: start.y, age: 0 };
  combat.projectiles.push(projectile);
  return { kind: 'cast', slot, projectile };
}

// Where a projectile is heading: the ward if the target is warding, else their body.
const aimPoint = (target) => (target.isWarding && target.wardAt ? target.wardAt : target.core);

// Advances time. Returns fx events: hit, wardShatter, ko.
export function stepCombat(combat, dtMs) {
  combat.clockMs += dtMs;
  const fx = [];
  for (const p of combat.players) updateResources(p, combat.clockMs, dtMs / 1000);
  combat.projectiles = combat.projectiles.filter((proj) => {
    proj.age += dtMs;
    const target = combat.players[1 - proj.from];
    const goal = aimPoint(target);
    const dx = goal.x - proj.x;
    const dy = goal.y - proj.y;
    const distance = Math.hypot(dx, dy);
    const travel = proj.speed * (dtMs / 1000);
    if (distance <= Math.max(HIT_RADIUS, travel)) {
      // Once a KO has landed, stragglers fizzle so a round can't end in a double knockout.
      if (combat.isDecided) fx.push({ kind: 'fizzle', projectile: proj, at: { x: proj.x, y: proj.y } });
      else fx.push(...resolveHit(combat, proj, target, { x: dx / (distance || 1), y: dy / (distance || 1) }));
      return false;
    }
    proj.x += (dx / distance) * travel;
    proj.y += (dy / distance) * travel;
    return true;
  });
  return fx;
}

function updateResources(p, now, dt) {
  if (p.isGathering) {
    p.charge = Math.min(1, p.charge + GATHER.RATE_PER_S * dt);
    p.chargeKeptUntil = now + GATHER.HOLD_MS;
  } else if (now > p.chargeKeptUntil) {
    p.charge = Math.max(0, p.charge - GATHER.DECAY_PER_S * dt);
  }
  if (p.isWarding) {
    p.mana = Math.max(0, p.mana - WARD.DRAIN_PER_S * dt);
    p.lastWardMs = now;
  } else if (now - p.lastWardMs > WARD.REGEN_DELAY_MS) {
    p.mana = Math.min(PLAYER.MAX_MANA, p.mana + WARD.REGEN_PER_S * dt);
  }
}

function resolveHit(combat, proj, target, dir) {
  const attacker = combat.players[proj.from];
  const at = { x: proj.x, y: proj.y };
  const fx = [];
  let damage = proj.damage;
  let blocked = 0;
  if (target.isWarding) {
    const shielded = proj.kind === 'ultimate' ? damage * (1 - ULTIMATE.WARD_PASS_THROUGH) : damage;
    const absorbable = target.mana / WARD.MANA_PER_DAMAGE;
    blocked = Math.min(shielded, absorbable);
    target.mana = Math.max(0, target.mana - blocked * WARD.MANA_PER_DAMAGE);
    damage = Math.round(damage - blocked);
    if (blocked < shielded) {
      target.isWarding = false;
      target.wardBrokenUntil = combat.clockMs + WARD.BROKEN_MS;
      fx.push({ kind: 'wardShatter', slot: target.slot, at });
    }
    target.stats.blocked += Math.round(blocked);
  }
  target.hp = Math.max(0, target.hp - damage);
  attacker.stats.damageDealt += damage;
  if (damage > 0) attacker.stats.hits += 1;
  attacker.stats.bestHit = Math.max(attacker.stats.bestHit, damage);
  fx.push({ kind: 'hit', slot: target.slot, from: proj.from, damage, blocked: Math.round(blocked), projectile: proj, at, dir });
  if (target.hp === 0) {
    combat.isDecided = true;
    fx.push({ kind: 'ko', slot: target.slot, winner: proj.from, at });
  }
  return fx;
}
