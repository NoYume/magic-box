// Every texture is generated once at startup: soft gradients and noise on 2D canvases, rune
// glyphs and the ward sigil drawn as vector Graphics and baked into textures. All are white so
// they can be tinted per element.

import { Graphics, Texture } from 'pixi.js';

import { seededRandom } from '../vision/synthetic-hand.js';

const WHITE = 0xffffff;
const NOISE_SEED = 1337;

function canvasTexture(size, draw, height = size) {
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = [size, height];
  draw(canvas.getContext('2d'), size, height);
  return Texture.from(canvas);
}

function radial(stops) {
  return (ctx, w, h) => {
    const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    stops.forEach(([at, alpha]) => g.addColorStop(at, `rgba(255,255,255,${alpha})`));
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  };
}

// Soft blob broken up by value noise, for smoke and energy wisps.
function wisp(ctx, w) {
  radial([[0, 0.9], [0.4, 0.45], [1, 0]])(ctx, w, w);
  const random = seededRandom(NOISE_SEED);
  const image = ctx.getImageData(0, 0, w, w);
  for (let i = 0; i < image.data.length; i += 4) image.data[i + 3] *= 0.55 + random() * 0.45;
  ctx.putImageData(image, 0, 0);
}

function trail(ctx, w, h) {
  const along = ctx.createLinearGradient(0, 0, w, 0);
  along.addColorStop(0, 'rgba(255,255,255,0)');
  along.addColorStop(0.7, 'rgba(255,255,255,0.55)');
  along.addColorStop(1, 'rgba(255,255,255,1)');
  ctx.fillStyle = along;
  ctx.fillRect(0, 0, w, h);
  ctx.globalCompositeOperation = 'destination-in';
  const across = ctx.createLinearGradient(0, 0, 0, h);
  across.addColorStop(0, 'rgba(255,255,255,0)');
  across.addColorStop(0.5, 'rgba(255,255,255,1)');
  across.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = across;
  ctx.fillRect(0, 0, w, h);
}

function vignette(ctx, w, h) {
  const g = ctx.createRadialGradient(w / 2, h / 2, w * 0.25, w / 2, h / 2, w * 0.72);
  g.addColorStop(0, 'rgba(7,6,26,0)');
  g.addColorStop(0.6, 'rgba(7,6,26,0.35)');
  g.addColorStop(1, 'rgba(7,6,26,0.88)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
}

const polar = (r, a, c = 0) => [c + Math.cos(a) * r, c + Math.sin(a) * r];

function drawSigil(g, size) {
  const c = size / 2;
  const line = (width, alpha = 1) => ({ width, color: WHITE, alpha });
  g.circle(c, c, c * 0.94).stroke(line(6));
  g.circle(c, c, c * 0.87).stroke(line(2, 0.8));
  for (let i = 0; i < 24; i++) {
    const a = (i / 24) * Math.PI * 2;
    const inner = i % 6 === 0 ? 0.78 : 0.885;
    g.moveTo(...polar(c * inner, a, c)).lineTo(...polar(c * 0.925, a, c)).stroke(line(i % 6 === 0 ? 4 : 2));
  }
  for (const offset of [0, Math.PI]) {
    const pts = [0, 1, 2].flatMap((k) => polar(c * 0.7, offset - Math.PI / 2 + (k * Math.PI * 2) / 3, c));
    g.poly(pts, true).stroke(line(3, 0.9));
  }
  g.circle(c, c, c * 0.4).stroke(line(3));
  g.circle(c, c, c * 0.34).stroke(line(1.5, 0.6));
  for (let i = 0; i < 6; i++) g.circle(...polar(c * 0.7, -Math.PI / 2 + (i * Math.PI) / 3, c), c * 0.035).fill({ color: WHITE });
  g.poly([c, c * 0.82, c * 1.06, c, c, c * 1.18, c * 0.94, c], true).fill({ color: WHITE, alpha: 0.9 });
}

// Rune glyphs, one per sign, in a 128 px box.
const GLYPHS = {
  ward(g) {
    g.arc(64, 64, 30, 0.35, Math.PI - 0.35).stroke({ width: 6, color: WHITE, cap: 'round' });
    for (let i = 0; i < 5; i++) {
      const a = -Math.PI / 2 + (i - 2) * 0.42;
      g.moveTo(...polar(16, a, 64)).lineTo(...polar(50, a, 64)).stroke({ width: 6, color: WHITE, cap: 'round' });
    }
  },
  gather(g) {
    g.circle(64, 64, 44).stroke({ width: 4, color: WHITE, alpha: 0.7 });
    for (let i = 0; i < 3; i++) {
      const a = (i * Math.PI * 2) / 3;
      g.arc(64, 64, 30, a, a + 1.4).stroke({ width: 6, color: WHITE, cap: 'round' });
    }
    g.circle(64, 64, 10).fill({ color: WHITE });
  },
  aim(g) {
    g.moveTo(64, 14).lineTo(64, 96).stroke({ width: 6, color: WHITE, cap: 'round' });
    g.moveTo(50, 28).lineTo(64, 12).lineTo(78, 28).stroke({ width: 5, color: WHITE, cap: 'round', join: 'round' });
    g.moveTo(42, 80).lineTo(86, 80).stroke({ width: 6, color: WHITE, cap: 'round' });
    g.circle(64, 108, 7).fill({ color: WHITE });
  },
  ultimate(g) {
    g.poly([64, 16, 108, 64, 64, 112, 20, 64], true).stroke({ width: 6, color: WHITE, join: 'round' });
    g.poly([64, 42, 86, 64, 64, 86, 42, 64], true).fill({ color: WHITE, alpha: 0.85 });
    for (const [x, y] of [[64, 4], [120, 64], [64, 124], [8, 64]]) g.circle(x, y, 4).fill({ color: WHITE });
  },
};

function bake(renderer, draw, size) {
  const g = new Graphics();
  draw(g, size);
  // Fixed-size frame keeps every glyph centered on the same anchor.
  g.rect(0, 0, size, size).fill({ color: WHITE, alpha: 0.001 });
  const texture = renderer.generateTexture({ target: g, resolution: 2, antialias: true });
  g.destroy();
  return texture;
}

export function createTextures(renderer) {
  return {
    glow: canvasTexture(128, radial([[0, 1], [0.2, 0.7], [0.5, 0.18], [1, 0]])),
    core: canvasTexture(64, radial([[0, 1], [0.35, 1], [0.6, 0.35], [1, 0]])),
    mote: canvasTexture(32, radial([[0, 1], [0.3, 0.8], [1, 0]])),
    ring: canvasTexture(256, radial([[0, 0], [0.78, 0], [0.88, 1], [0.94, 0.4], [1, 0]])),
    spark: canvasTexture(64, (ctx, w, h) => {
      ctx.scale(1, h / w); // squash a round falloff into a streak
      radial([[0, 1], [0.25, 0.6], [1, 0]])(ctx, w, w);
    }, 12),
    wisp: canvasTexture(128, wisp),
    trail: canvasTexture(128, trail, 32),
    vignette: canvasTexture(512, vignette, 512),
    sigil: bake(renderer, drawSigil, 512),
    glyphs: Object.fromEntries(Object.keys(GLYPHS).map((name) => [name, bake(renderer, GLYPHS[name], 128)])),
  };
}
