// Wards (a hand-sized rune sigil anchored at the warding palm) and gather auras (energy
// condensing at the fist). Both live in the bloomed fx layer.

import { Container, Sprite } from 'pixi.js';

import { PHASE } from '../game/caster.js';
import { COLOR, PLAYER_THEME } from '../theme.js';

const WARD_RADIUS_PALMS = 1.25; // ward radius in palm lengths
const WARD_RAISE_RATE = 9; // spring rate of the raise / lower animation
const CHARGE_RADIUS_PALMS = 0.9;
const MOTES_PER_SECOND = 55;
const LOW_MANA = 25;

const lerp = (a, b, t) => a + (b - a) * t;

function sprite(texture, tint) {
  const s = new Sprite(texture);
  s.anchor.set(0.5);
  s.tint = tint;
  return s;
}

export class AuraLayer {
  constructor(stage, particles) {
    this.stage = stage;
    this.particles = particles;
    this.container = new Container();
    this.container.blendMode = 'add';
    stage.layers.fx.addChild(this.container);
    this.wards = [0, 1].map(() => this.#createWard());
    this.charges = [0, 1].map((slot) => this.#createCharge(slot));
    this.time = 0;
  }

  #createWard() {
    const { textures } = this.stage;
    const root = new Container();
    const glow = sprite(textures.glow, COLOR.verdant);
    const outer = sprite(textures.sigil, COLOR.verdant);
    const inner = sprite(textures.sigil, COLOR.verdantCore);
    const ripple = sprite(textures.ring, COLOR.verdantCore);
    root.addChild(glow, outer, inner, ripple);
    root.visible = false;
    this.container.addChild(root);
    return { root, glow, outer, inner, ripple, open: 0, radius: 0, pulse: 0, rippleT: 1, x: 0, y: 0 };
  }

  #createCharge(slot) {
    const { textures } = this.stage;
    const element = PLAYER_THEME[slot].element;
    const root = new Container();
    const glow = sprite(textures.glow, element);
    const core = sprite(textures.core, PLAYER_THEME[slot].core);
    const ring = sprite(textures.ring, element);
    root.addChild(glow, ring, core);
    root.visible = false;
    this.container.addChild(root);
    return { root, glow, core, ring, element, shown: 0, mote: 0 };
  }

  // A blocked hit makes the ward flare and ripple.
  pulseWard(slot) {
    const ward = this.wards[slot];
    ward.pulse = 1;
    ward.rippleT = 0;
  }

  update(dt, { combat, view }) {
    this.time += dt;
    for (const slot of [0, 1]) {
      const player = combat.players[slot];
      const caster = view.casters[slot];
      this.#updateWard(this.wards[slot], player, caster?.wardHand, dt);
      const fist = view.slots[slot].find((h) => caster?.handStates.get(h.id)?.phase === PHASE.CHARGING);
      this.#updateCharge(this.charges[slot], player.charge, fist, dt);
    }
  }

  #updateWard(w, player, hand, dt) {
    const t = this.stage.transform;
    const isUp = player.isWarding && hand;
    w.open += ((isUp ? 1 : 0) - w.open) * Math.min(1, WARD_RAISE_RATE * dt);
    w.root.visible = w.open > 0.02;
    if (!w.root.visible) return;
    if (hand) {
      const p = t.viewToScreen(hand.view.x, hand.view.y);
      w.x = lerp(w.x || p.x, p.x, Math.min(1, 25 * dt));
      w.y = lerp(w.y || p.y, p.y, Math.min(1, 25 * dt));
      w.radius = hand.palmSpan * t.drawnH * WARD_RADIUS_PALMS;
    }
    w.pulse = Math.max(0, w.pulse - dt * 3);
    w.rippleT = Math.min(1, w.rippleT + dt * 2.2);
    const lowMana = player.mana < LOW_MANA;
    const flicker = lowMana ? 0.55 + 0.45 * Math.abs(Math.sin(this.time * 18)) : 1;
    const shimmer = 0.85 + 0.15 * Math.sin(this.time * 5);
    const size = w.radius * 2 * (0.6 + 0.4 * w.open) * (1 + w.pulse * 0.12);
    w.root.position.set(w.x, w.y);
    w.outer.width = w.outer.height = size;
    w.outer.rotation += dt * 0.5;
    w.outer.alpha = w.open * shimmer * flicker * (0.75 + w.pulse * 0.25);
    w.inner.width = w.inner.height = size * 0.62;
    w.inner.rotation -= dt * 0.9;
    w.inner.alpha = w.open * 0.45 * flicker;
    w.glow.width = w.glow.height = size * 1.9;
    w.glow.alpha = w.open * (0.22 + w.pulse * 0.35) * flicker;
    w.ripple.width = w.ripple.height = size * (1 + w.rippleT * 0.8);
    w.ripple.alpha = (1 - w.rippleT) * 0.9;
  }

  #updateCharge(c, charge, fist, dt) {
    const t = this.stage.transform;
    c.shown += ((fist ? 1 : 0) - c.shown) * Math.min(1, 10 * dt);
    c.root.visible = c.shown > 0.02 && charge > 0.01;
    if (!c.root.visible || !fist) return;
    const p = t.viewToScreen(fist.view.x, fist.view.y);
    const radius = fist.palmSpan * t.drawnH * CHARGE_RADIUS_PALMS;
    const full = charge >= 1;
    const beat = full ? 1 + 0.12 * Math.sin(this.time * 14) : 1;
    c.root.position.set(p.x, p.y);
    c.core.width = c.core.height = radius * (0.35 + 0.5 * charge) * beat;
    c.glow.width = c.glow.height = radius * (1.4 + 2 * charge) * beat;
    c.glow.alpha = c.shown * (0.4 + 0.5 * charge);
    c.ring.visible = full;
    c.ring.width = c.ring.height = radius * 2.4 * beat;
    c.ring.rotation += dt * 2;
    c.mote += dt * MOTES_PER_SECOND * (0.3 + charge);
    while (c.mote >= 1) {
      c.mote -= 1;
      const a = Math.random() * Math.PI * 2;
      const r = radius * (1.6 + Math.random());
      const speed = r * 2.8;
      this.particles.spawn({
        texture: this.stage.textures.spark,
        tint: Math.random() < 0.25 ? 0xffffff : c.element,
        x: p.x + Math.cos(a) * r,
        y: p.y + Math.sin(a) * r,
        vx: -Math.cos(a) * speed,
        vy: -Math.sin(a) * speed,
        life: 0.34,
        scale: 0.3,
        endScale: 0.05,
        drag: 0,
        alignToVelocity: true,
        stretch: 0.004,
      });
    }
  }
}
