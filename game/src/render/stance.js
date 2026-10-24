// Body-move visuals at each player's torso: Focus (lean in) draws embers up through the chest,
// Brace (lean back) raises a gold crescent toward the foe, Dodge leaves an afterimage streak.
// Sized from the tracked shoulder width so they scale with the player's distance.

import { Container, Graphics, Sprite } from 'pixi.js';

import { COLOR, PLAYER_THEME } from '../theme.js';

const SHOW_RATE = 7; // fade in / out per second
const FOCUS_MOTES_PER_S = 40;
const BRACE_ARC = 1.1; // radians each side of the facing direction
const BRACE_RADIUS_SHOULDERS = 0.6;
const DODGE_GHOSTS = 4;
const FALLBACK_SHOULDER = 0.16; // view units, when no body is tracked (keyboard / voice play)

export class StanceLayer {
  constructor(stage, particles) {
    this.stage = stage;
    this.particles = particles;
    this.container = new Container();
    this.container.blendMode = 'add';
    stage.layers.fx.addChild(this.container);
    this.slots = [0, 1].map((slot) => this.#create(slot));
    this.time = 0;
  }

  #create(slot) {
    const glow = new Sprite(this.stage.textures.glow);
    glow.anchor.set(0.5);
    glow.tint = PLAYER_THEME[slot].element;
    const brace = new Graphics();
    this.container.addChild(glow, brace);
    return { glow, brace, focus: 0, braced: 0, mote: 0 };
  }

  // Afterimage for a dodge: a few faint ghosts strung out behind the player, plus speed lines.
  dodge({ slot, dir, at }) {
    const t = this.stage.transform;
    const p = t.viewToScreen(at.x, at.y);
    const u = t.drawnH;
    const tint = PLAYER_THEME[slot].element;
    for (let i = 0; i < DODGE_GHOSTS; i++) {
      const x = p.x - dir * u * 0.035 * i;
      this.particles.spawn({ x, y: p.y + u * 0.06, vx: -dir * u * 0.2, vy: 0, texture: this.stage.textures.wisp, tint, life: 0.35 + i * 0.05, scale: 1.1, endScale: 1.4, alpha: 0.22 - i * 0.04, drag: 3 });
    }
    this.particles.burst({ ...p, count: 14, speed: u * 0.9, texture: this.stage.textures.spark, tint: COLOR.parchment, dir: { x: -dir, y: 0 }, spread: 0.25, life: 0.25, scale: 0.35, alpha: 0.6, alignToVelocity: true, stretch: 0.005, drag: 6 });
  }

  update(dt, { combat, view }) {
    this.time += dt;
    const t = this.stage.transform;
    combat.players.forEach((player, slot) => {
      const s = this.slots[slot];
      const body = view.bodies?.[slot];
      const at = body?.view ?? player.core;
      const shoulder = (body?.torso.width ?? FALLBACK_SHOULDER) * t.drawnW;
      const p = t.viewToScreen(at.x, at.y);
      const step = (v, on) => Math.max(0, Math.min(1, v + (on ? 1 : -1) * dt * SHOW_RATE));
      s.focus = step(s.focus, player.stance === 'leanIn');
      s.braced = step(s.braced, player.stance === 'leanBack');
      this.#focus(s, p, shoulder, slot, dt);
      this.#brace(s, p, shoulder, slot);
    });
  }

  #focus(s, p, shoulder, slot, dt) {
    s.glow.visible = s.focus > 0;
    if (!s.glow.visible) return;
    s.glow.position.set(p.x, p.y + shoulder * 0.5);
    s.glow.width = s.glow.height = shoulder * (1.6 + 0.08 * Math.sin(this.time * 6));
    s.glow.alpha = 0.35 * s.focus;
    s.mote += dt * FOCUS_MOTES_PER_S * s.focus;
    for (; s.mote >= 1; s.mote -= 1) {
      const x = p.x + (Math.random() - 0.5) * shoulder * 1.2;
      const y = p.y + shoulder * (0.6 + Math.random() * 0.6);
      this.particles.spawn({ x, y, vx: 0, vy: -shoulder * (1 + Math.random()), texture: this.stage.textures.mote, tint: PLAYER_THEME[slot].element, life: 0.7, scale: 0.35, endScale: 0, drag: 0.5 });
    }
  }

  #brace(s, p, shoulder, slot) {
    s.brace.clear();
    if (s.braced <= 0) return;
    const facing = slot === 0 ? 0 : Math.PI; // toward the seam
    const r = shoulder * BRACE_RADIUS_SHOULDERS * (0.85 + 0.15 * s.braced);
    const cy = p.y + shoulder * 0.35;
    const arc = (radius, width, alpha) => s.brace
      .arc(p.x, cy, radius, facing - BRACE_ARC * s.braced, facing + BRACE_ARC * s.braced)
      .stroke({ width, color: COLOR.gold, alpha, cap: 'round' });
    arc(r, shoulder * 0.022, 0.5 * s.braced);
    arc(r * 1.1, shoulder * 0.008, 0.3 * s.braced);
  }
}
