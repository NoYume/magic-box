// Pooled additive particles. A fixed budget of Sprites is allocated once; spawning past the
// budget recycles the oldest particle instead of allocating.

import { Container, Sprite } from 'pixi.js';

const DEFAULT_BUDGET = 900;

const easeOutQuad = (t) => 1 - (1 - t) * (1 - t);

export class ParticlePool {
  constructor(budget = DEFAULT_BUDGET) {
    this.container = new Container();
    this.container.blendMode = 'add';
    this.items = Array.from({ length: budget }, () => {
      const sprite = new Sprite();
      sprite.anchor.set(0.5);
      sprite.visible = false;
      this.container.addChild(sprite);
      return { sprite, life: 0, maxLife: 1 };
    });
    this.cursor = 0;
  }

  // opts: { texture, x, y, vx, vy, life (s), scale, endScale, alpha, tint, drag, gravity,
  //         rotation, spin, alignToVelocity, stretch }
  spawn(opts) {
    const p = this.items[this.cursor];
    this.cursor = (this.cursor + 1) % this.items.length;
    const s = p.sprite;
    s.texture = opts.texture;
    s.tint = opts.tint ?? 0xffffff;
    s.visible = true;
    s.position.set(opts.x, opts.y);
    s.rotation = opts.rotation ?? 0;
    Object.assign(p, {
      vx: opts.vx ?? 0,
      vy: opts.vy ?? 0,
      life: opts.life ?? 0.6,
      maxLife: opts.life ?? 0.6,
      scale: opts.scale ?? 1,
      endScale: opts.endScale ?? 0,
      alpha: opts.alpha ?? 1,
      drag: opts.drag ?? 2,
      gravity: opts.gravity ?? 0,
      spin: opts.spin ?? 0,
      align: opts.alignToVelocity ?? false,
      stretch: opts.stretch ?? 0,
    });
    this.#apply(p, 0);
  }

  // Ring of particles fanning out from a point. dir (optional) biases them into a cone.
  burst({ x, y, count, speed, texture, tint, life = 0.6, scale = 0.5, dir = null, spread = Math.PI, ...rest }) {
    const base = dir ? Math.atan2(dir.y, dir.x) : 0;
    for (let i = 0; i < count; i++) {
      const a = dir ? base + (Math.random() - 0.5) * spread : Math.random() * Math.PI * 2;
      const v = speed * (0.35 + Math.random() * 0.9);
      this.spawn({ texture, tint, x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: life * (0.6 + Math.random() * 0.6), scale: scale * (0.6 + Math.random() * 0.8), ...rest });
    }
  }

  update(dt) {
    for (const p of this.items) {
      if (!p.sprite.visible) continue;
      p.life -= dt;
      if (p.life <= 0) {
        p.sprite.visible = false;
        continue;
      }
      const damping = Math.exp(-p.drag * dt);
      p.vx *= damping;
      p.vy = p.vy * damping + p.gravity * dt;
      p.sprite.x += p.vx * dt;
      p.sprite.y += p.vy * dt;
      p.sprite.rotation += p.spin * dt;
      this.#apply(p, 1 - p.life / p.maxLife);
    }
  }

  #apply(p, t) {
    const s = p.sprite;
    const size = p.scale + (p.endScale - p.scale) * easeOutQuad(t);
    if (p.align) {
      s.rotation = Math.atan2(p.vy, p.vx);
      const speed = Math.hypot(p.vx, p.vy);
      s.scale.set(size * (1 + speed * p.stretch), size);
    } else {
      s.scale.set(size);
    }
    s.alpha = p.alpha * (t < 0.1 ? t / 0.1 : 1 - (t - 0.1) / 0.9);
  }

  clear() {
    for (const p of this.items) p.sprite.visible = false;
  }
}
