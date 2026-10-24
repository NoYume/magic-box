// Bolt and ultimate visuals: a bright core, a soft halo, a ribbon trail (MeshRope) and shed motes.

import { Container, MeshRope, Point, RopeGeometry, Sprite } from 'pixi.js';

import { COLOR, PLAYER_THEME } from '../theme.js';

const TRAIL_POINTS = 18;
const BOLT_SIZE = 0.045; // core diameter as a fraction of the shown frame height
const EMPOWERED_SCALE = 1.45;
const ULTIMATE_SCALE = 2.2;
const SHED_PER_SECOND = 70;
const TRAIL_WIDTH = 1.3; // ribbon width relative to the core

function scaleFor(proj) {
  if (proj.kind === 'ultimate') return ULTIMATE_SCALE;
  return proj.empowered ? EMPOWERED_SCALE : 1;
}

export function projectileColors(proj) {
  if (proj.kind === 'ultimate') return { element: COLOR.violet, core: COLOR.violetCore };
  return { element: PLAYER_THEME[proj.from].element, core: PLAYER_THEME[proj.from].core };
}

export class ProjectileLayer {
  constructor(stage, particles) {
    this.stage = stage;
    this.particles = particles;
    this.container = new Container();
    this.container.blendMode = 'add';
    stage.layers.fx.addChild(this.container);
    this.visuals = new Map();
  }

  sync(projectiles, dt) {
    const alive = new Set();
    for (const proj of projectiles) {
      alive.add(proj.id);
      const visual = this.visuals.get(proj.id) ?? this.#create(proj);
      this.#update(visual, proj, dt);
    }
    for (const [id, visual] of this.visuals) {
      if (alive.has(id)) continue;
      visual.root.destroy({ children: true });
      this.visuals.delete(id);
    }
  }

  #create(proj) {
    const { textures } = this.stage;
    const { element, core } = projectileColors(proj);
    const start = this.stage.transform.viewToScreen(proj.x, proj.y);
    const points = Array.from({ length: TRAIL_POINTS }, (_, i) => new Point(start.x - (TRAIL_POINTS - i) * 0.5, start.y));
    const rope = new MeshRope({ texture: textures.trail, points });
    // MeshRope sizes its ribbon from the texture height; swap in a geometry with our width
    // (RopeGeometry.width is read-only after construction). autoUpdate keeps following the points.
    const width = this.stage.transform.viewLength(BOLT_SIZE) * scaleFor(proj) * TRAIL_WIDTH;
    rope.geometry = new RopeGeometry({ width, points, textureScale: 0 });
    rope.tint = element;
    const halo = new Sprite(textures.glow);
    const body = new Sprite(textures.core);
    const ring = new Sprite(textures.ring);
    [halo, body, ring].forEach((s) => s.anchor.set(0.5));
    halo.tint = element;
    body.tint = core;
    ring.tint = element;
    ring.visible = proj.kind === 'ultimate';
    const root = new Container();
    root.addChild(rope, halo, ring, body);
    this.container.addChild(root);
    const visual = { root, rope, points, halo, body, ring, element, shed: 0 };
    this.visuals.set(proj.id, visual);
    return visual;
  }

  #update(v, proj, dt) {
    const t = this.stage.transform;
    const p = t.viewToScreen(proj.x, proj.y);
    const sizeScale = scaleFor(proj);
    const size = t.viewLength(BOLT_SIZE) * sizeScale;
    const pulse = 1 + Math.sin(proj.age / 45) * 0.08;
    v.body.position.set(p.x, p.y);
    v.body.width = v.body.height = size * pulse;
    v.halo.position.set(p.x, p.y);
    v.halo.width = v.halo.height = size * 4.2;
    v.halo.alpha = 0.85;
    v.ring.position.set(p.x, p.y);
    v.ring.width = v.ring.height = size * 2.6;
    v.ring.rotation += dt * 3;
    // Shift the trail: the last point is the head.
    for (let i = 0; i < v.points.length - 1; i++) v.points[i].copyFrom(v.points[i + 1]);
    v.points[v.points.length - 1].set(p.x, p.y);
    v.shed += dt * SHED_PER_SECOND * sizeScale;
    while (v.shed >= 1) {
      v.shed -= 1;
      this.particles.spawn({
        texture: this.stage.textures.mote,
        tint: Math.random() < 0.3 ? 0xffffff : v.element,
        x: p.x + (Math.random() - 0.5) * size * 0.6,
        y: p.y + (Math.random() - 0.5) * size * 0.6,
        vx: (Math.random() - 0.5) * 40,
        vy: (Math.random() - 0.5) * 40,
        life: 0.45,
        scale: 0.35 * sizeScale,
        endScale: 0,
        drag: 3,
      });
    }
  }
}
