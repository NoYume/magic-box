// Turns gameplay fx events into visuals: cast anticipation, impacts, ward ripples and shatters,
// body moves (focus, brace, dodge, evade), knockout bursts and floating damage numbers. Owns the particle pool and the effect layers.

import { Container, Sprite, Text } from 'pixi.js';

import { COLOR, FONT, PLAYER_THEME } from '../theme.js';
import { AuraLayer } from './auras.js';
import { HandMarks } from './hand-marks.js';
import { ParticlePool } from './particles.js';
import { ProjectileLayer, projectileColors } from './projectiles.js';
import { StanceLayer } from './stance.js';

const RING_LIFE = 0.45;
const FLOATER_LIFE = 1.1;
const FLOATER_RISE = 70; // px per second
const SHAKE_PER_DAMAGE = 0.9;
const KO_SHAKE = 34;
const STANCE_LABELS = { leanIn: 'Focus', leanBack: 'Brace' };
const STANCE_LABEL_DROP = 0.16; // view units below the torso anchor

const easeOutCubic = (t) => 1 - (1 - t) ** 3;
const easeOutBack = (t) => 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2;

export class Effects {
  constructor(stage) {
    this.stage = stage;
    this.particles = new ParticlePool();
    this.projectiles = new ProjectileLayer(stage, this.particles);
    this.auras = new AuraLayer(stage, this.particles);
    this.stance = new StanceLayer(stage, this.particles);
    this.marks = new HandMarks(stage);
    this.rings = new Container();
    this.rings.blendMode = 'add';
    stage.layers.fx.addChild(this.rings, this.particles.container);
    this.floatLayer = new Container();
    stage.layers.marks.addChild(this.floatLayer);
    this.transient = []; // rings and floaters
  }

  #screen(at) {
    return this.stage.transform.viewToScreen(at.x, at.y);
  }

  #unit() {
    return this.stage.transform.drawnH;
  }

  #ring(at, tint, size, life = RING_LIFE) {
    const s = new Sprite(this.stage.textures.ring);
    s.anchor.set(0.5);
    s.tint = tint;
    s.position.copyFrom(this.#screen(at));
    this.rings.addChild(s);
    this.transient.push({ sprite: s, life, maxLife: life, kind: 'ring', size });
  }

  #floater(at, text, color, big, size = null) {
    const label = new Text({
      text,
      style: { fontFamily: FONT.display, fontWeight: '700', fontSize: size ?? (big ? 56 : 40), fill: color, stroke: { color: COLOR.inkDeep, width: 6, join: 'round' }, letterSpacing: 1 },
    });
    label.anchor.set(0.5);
    const p = this.#screen(at);
    label.position.set(p.x, p.y - this.#unit() * 0.06);
    this.floatLayer.addChild(label);
    this.transient.push({ sprite: label, life: FLOATER_LIFE, maxLife: FLOATER_LIFE, kind: 'floater' });
  }

  onFx(ev) {
    const handler = {
      cast: () => this.#cast(ev),
      hit: () => this.#hit(ev),
      wardShatter: () => this.#shatter(ev),
      ko: () => this.#ko(ev),
      stance: () => STANCE_LABELS[ev.stance] && this.#stanceLabel(ev),
      dodge: () => this.stance.dodge(ev),
      evade: () => this.#evade(ev),
      fizzle: () => this.particles.burst({ ...this.#screen(ev.at), count: 10, speed: 120, texture: this.stage.textures.mote, tint: COLOR.parchmentDim, life: 0.4, scale: 0.4 }),
    }[ev.kind];
    handler?.();
  }

  #cast({ projectile: proj, slot }) {
    const { element } = projectileColors(proj);
    const at = { x: proj.x, y: proj.y };
    const p = this.#screen(at);
    const towardFoe = slot === 0 ? 1 : -1;
    const big = proj.kind === 'ultimate';
    this.#ring(at, element, this.#unit() * (big ? 0.5 : 0.22), 0.3);
    this.particles.burst({ ...p, count: big ? 70 : 26, speed: this.#unit() * (big ? 0.9 : 0.6), texture: this.stage.textures.spark, tint: element, dir: { x: towardFoe, y: 0 }, spread: 1.4, life: 0.35, scale: 0.55, alignToVelocity: true, stretch: 0.004, drag: 5 });
    this.stage.flash(element, big ? 0.22 : 0.07);
  }

  #hit(ev) {
    const { element } = projectileColors(ev.projectile);
    const p = this.#screen(ev.at);
    const u = this.#unit();
    const heavy = ev.projectile.empowered;
    const isBlocked = ev.blocked > 0 && ev.damage === 0;
    if (ev.blocked > 0) this.auras.pulseWard(ev.slot);
    const tint = isBlocked ? COLOR.verdant : element;
    this.#ring(ev.at, tint, u * (heavy ? 0.42 : 0.28));
    this.particles.burst({ ...p, count: heavy ? 90 : 45, speed: u * (heavy ? 1.3 : 0.9), texture: this.stage.textures.spark, tint, dir: ev.dir, spread: isBlocked ? 2.6 : 1.5, life: 0.5, scale: 0.6, alignToVelocity: true, stretch: 0.003, drag: 4 });
    this.particles.burst({ ...p, count: heavy ? 8 : 4, speed: u * 0.15, texture: this.stage.textures.wisp, tint, life: 0.9, alpha: 0.5, scale: heavy ? 1.1 : 0.7, endScale: 1.6, drag: 2 });
    this.stage.kick(ev.dir, (heavy ? 10 : 5) + ev.damage * SHAKE_PER_DAMAGE);
    if (ev.damage > 0) {
      this.#floater(ev.at, `${ev.damage}`, heavy ? COLOR.goldBright : COLOR.parchment, heavy);
      this.stage.flash(element, heavy ? 0.16 : 0.08);
    } else {
      this.#floater(ev.at, 'Warded', COLOR.verdant, false);
    }
  }

  #core(slot) {
    return this.lastSnapshot?.combat.players[slot].core ?? { x: slot ? 0.75 : 0.25, y: 0.5 };
  }

  // Stance names sit below the chest so they never collide with damage numbers above it.
  #stanceLabel(ev) {
    const core = this.#core(ev.slot);
    this.#floater({ x: core.x, y: core.y + STANCE_LABEL_DROP }, STANCE_LABELS[ev.stance], COLOR.gold, false, 26);
  }

  #evade(ev) {
    const p = this.#screen(ev.at);
    this.particles.burst({ ...p, count: 16, speed: this.#unit() * 0.4, texture: this.stage.textures.mote, tint: COLOR.parchmentDim, life: 0.4, scale: 0.35 });
    this.#floater(ev.at, 'Evaded', COLOR.parchment, false);
  }

  #shatter(ev) {
    const p = this.#screen(ev.at);
    const u = this.#unit();
    this.#ring(ev.at, COLOR.verdantCore, u * 0.5, 0.6);
    this.particles.burst({ ...p, count: 60, speed: u * 0.9, texture: this.stage.textures.spark, tint: COLOR.verdant, life: 0.8, scale: 0.8, spin: 8, gravity: u * 1.4, drag: 1.5 });
    this.#floater(ev.at, 'Shattered', COLOR.verdant, true);
    this.stage.flash(COLOR.verdant, 0.14);
  }

  #ko(ev) {
    const p = this.#screen(ev.at);
    const winner = PLAYER_THEME[ev.winner].element;
    this.#ring(ev.at, COLOR.goldBright, this.#unit() * 1.2, 1.1);
    this.particles.burst({ ...p, count: 160, speed: this.#unit() * 1.6, texture: this.stage.textures.spark, tint: winner, life: 1.2, scale: 0.8, alignToVelocity: true, stretch: 0.003, drag: 2.5 });
    this.stage.kick({ x: 1, y: 0.3 }, KO_SHAKE);
    this.stage.flash(COLOR.parchment, 0.4);
  }

  update(dt, snapshot) {
    this.lastSnapshot = snapshot;
    this.projectiles.sync(snapshot.combat.projectiles, dt);
    this.stance.update(dt, snapshot);
    this.auras.update(dt, snapshot);
    this.marks.update(dt, snapshot);
    this.particles.update(dt);
    this.transient = this.transient.filter((item) => {
      item.life -= dt;
      const t = 1 - Math.max(0, item.life) / item.maxLife;
      if (item.kind === 'ring') {
        item.sprite.width = item.sprite.height = item.size * (0.3 + easeOutCubic(t) * 1.4);
        item.sprite.alpha = 1 - t;
      } else {
        item.sprite.scale.set(Math.min(1, easeOutBack(Math.min(1, t * 4))));
        item.sprite.y -= FLOATER_RISE * dt;
        item.sprite.alpha = t < 0.7 ? 1 : 1 - (t - 0.7) / 0.3;
      }
      if (item.life > 0) return true;
      item.sprite.destroy();
      return false;
    });
  }
}
