// Battle rules. Pure state + logic, no rendering. All positions are screen-normalized (0-1, mirrored).
//
// Brawler/Mage mechanics:
//   - Step forward  -> charge builds; the next push is a heavy blast.
//   - Step back     -> shield up; incoming damage is reduced.
//   - Push          -> fire a bolt at the opponent; push speed sets bolt speed + damage.
//   - Hands up      -> heal (cooldown).
//   - Voice spells  -> castSpell() (wired to Muse Voice Transcribe later).

export const MAX_HP = 100;
const CHARGE_PER_SEC = 0.8;
const SHIELD_FACTOR = 0.3;
const HEAL_AMOUNT = 15;
const HEAL_COOLDOWN_MS = 6000;
const BOLT_BASE_DAMAGE = 6;
const BOLT_SPEED_SCALE = 0.35; // screen widths per second per m/s of push
const HEAVY_MULTIPLIER = 3;

export const SPELLS = {
  fireball: { damage: 18, speed: 0.9, radius: 0.05, color: 0xff6a00 },
  lightning: { damage: 12, speed: 2.2, radius: 0.03, color: 0x7fd4ff },
  frost: { damage: 10, speed: 0.6, radius: 0.06, color: 0xbff4ff },
};

export function createGame() {
  return { players: [newPlayer(0), newPlayer(1)], bolts: [], winner: null };
}

function newPlayer(slot) {
  return { slot, hp: MAX_HP, present: false, x: slot === 0 ? 0.25 : 0.75, y: 0.5, stance: 'neutral', charge: 0, lastHealT: -Infinity };
}

// Returns a list of fx events for the renderer: { kind: 'cast' | 'heal' | 'shield', ... }
export function handleGesture(game, slot, ev, now) {
  const p = game.players[slot];
  if (game.winner !== null || !p.present) return [];
  if (ev.type === 'stance') {
    p.stance = ev.stance;
    return ev.stance === 'back' ? [{ kind: 'shield', slot }] : [];
  }
  if (ev.type === 'push') {
    const heavy = p.charge >= 1;
    const damage = BOLT_BASE_DAMAGE * Math.min(ev.power, 3) * (heavy ? HEAVY_MULTIPLIER : 1);
    const speed = Math.max(0.5, ev.power * BOLT_SPEED_SCALE);
    if (heavy) p.charge = 0;
    return [fireBolt(game, slot, { damage, speed, radius: heavy ? 0.07 : 0.035, color: heavy ? 0xff2bd6 : 0xffd84a, heavy, origin: ev })];
  }
  if (ev.type === 'handsUp' && now - p.lastHealT > HEAL_COOLDOWN_MS) {
    p.lastHealT = now;
    p.hp = Math.min(MAX_HP, p.hp + HEAL_AMOUNT);
    return [{ kind: 'heal', slot }];
  }
  return [];
}

export function castSpell(game, slot, name) {
  const spell = SPELLS[name];
  const p = game.players[slot];
  if (!spell || game.winner !== null || !p.present) return [];
  return [fireBolt(game, slot, { ...spell, heavy: false, spell: name })];
}

function fireBolt(game, slot, { damage, speed, radius, color, heavy, origin, spell }) {
  const p = game.players[slot];
  const dir = slot === 0 ? 1 : -1;
  const bolt = { from: slot, x: origin?.sx ?? p.x, y: origin?.sy ?? p.y, vx: dir * speed, damage, radius, color, heavy, spell };
  game.bolts.push(bolt);
  return { kind: 'cast', slot, bolt };
}

// Advances bolts and charge. Returns fx events: { kind: 'hit', slot, damage, shielded, x, y } and 'ko'.
export function step(game, dt) {
  const fx = [];
  for (const p of game.players) {
    if (p.stance === 'forward') p.charge = Math.min(1, p.charge + CHARGE_PER_SEC * dt);
  }
  game.bolts = game.bolts.filter((bolt) => {
    bolt.x += bolt.vx * dt;
    const target = game.players[1 - bolt.from];
    const reached = bolt.vx > 0 ? bolt.x >= target.x : bolt.x <= target.x;
    if (reached && target.present && game.winner === null) {
      const shielded = target.stance === 'back';
      const damage = Math.round(bolt.damage * (shielded ? SHIELD_FACTOR : 1));
      target.hp = Math.max(0, target.hp - damage);
      fx.push({ kind: 'hit', slot: target.slot, damage, shielded, x: target.x, y: bolt.y, color: bolt.color, heavy: bolt.heavy });
      if (target.hp === 0) {
        game.winner = bolt.from;
        fx.push({ kind: 'ko', slot: target.slot, winner: bolt.from });
      }
      return false;
    }
    return bolt.x > -0.1 && bolt.x < 1.1;
  });
  return fx;
}

export function resetGame(game) {
  for (const p of game.players) Object.assign(p, newPlayer(p.slot), { present: p.present, x: p.x, y: p.y });
  game.bolts = [];
  game.winner = null;
}
