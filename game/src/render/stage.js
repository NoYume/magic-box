// Pixi application, layer stack, camera feed, post effects and screen shake.
// The feed sprite and every overlay share one camera -> screen transform (vision/transform.js).

import { AdvancedBloomFilter } from 'pixi-filters';
import { Application, ColorMatrixFilter, Container, Sprite, Texture } from 'pixi.js';

import { COLOR } from '../theme.js';
import { createViewTransform } from '../vision/transform.js';
import { createTextures } from './textures.js';

const FEED_TINT = 0xe5e8dd; // neutral, slightly desaturated camera under the cabinet graphics
const FEED_SATURATION = -0.15;
const SHAKE_FREQUENCY = 38; // Hz of the damped shake oscillation
const SHAKE_DECAY = 9;
const FLASH_DECAY = 6;
const BLOOM = { threshold: 0.45, bloomScale: 0.9, brightness: 1, blur: 7, quality: 5 };

export async function createStage(feedCanvas, { mirror }) {
  const app = new Application();
  await app.init({ resizeTo: window, background: COLOR.inkDeep, antialias: true, autoDensity: true, resolution: Math.min(window.devicePixelRatio, 2) });
  app.canvas.classList.add('stage');
  document.getElementById('app').prepend(app.canvas);
  const textures = createTextures(app.renderer);

  const world = new Container();
  const feedTexture = Texture.from(feedCanvas);
  const feed = new Sprite(feedTexture);
  feed.tint = FEED_TINT;
  const grade = new ColorMatrixFilter();
  grade.saturate(FEED_SATURATION, false);
  feed.filters = [grade];
  const vignette = new Sprite(textures.vignette);
  const fx = new Container(); // additive magic, bloomed
  fx.filters = [new AdvancedBloomFilter(BLOOM)];
  const marks = new Container(); // on-hand indicators, crisp
  const debug = new Container();
  world.addChild(feed, vignette, fx, marks, debug);
  const flash = new Sprite(Texture.WHITE);
  flash.alpha = 0;
  flash.blendMode = 'add';
  app.stage.addChild(world, flash);

  let transform = null;
  const shake = { amp: 0, dirX: 0, dirY: 0, t: 0 };

  function layout() {
    const { width, height } = app.screen;
    transform = createViewTransform({ srcW: feedCanvas.width, srcH: feedCanvas.height, dstW: width, dstH: height, mirror });
    const place = transform.feedPlacement();
    feed.position.set(place.x, place.y);
    feed.scale.set(place.scaleX, place.scaleY);
    vignette.width = width;
    vignette.height = height;
    flash.width = width;
    flash.height = height;
    fx.filterArea = app.screen;
  }

  let lastSize = '';
  function frame(dt) {
    feedTexture.source.update();
    const size = `${app.screen.width}x${app.screen.height}x${feedCanvas.width}x${feedCanvas.height}`;
    if (size !== lastSize) {
      lastSize = size;
      layout();
    }
    shake.t += dt;
    shake.amp *= Math.exp(-SHAKE_DECAY * dt);
    const wave = Math.sin(shake.t * SHAKE_FREQUENCY * Math.PI * 2) * shake.amp;
    const jitter = (Math.random() - 0.5) * shake.amp * 0.3;
    world.position.set(shake.dirX * wave + jitter, shake.dirY * wave + jitter);
    flash.alpha *= Math.exp(-FLASH_DECAY * dt);
  }

  return {
    app,
    textures,
    layers: { fx, marks, debug },
    get transform() {
      return transform;
    },
    frame,
    // Directional shake: dir is the impact direction (screen space), amp in pixels.
    kick(dir, amp) {
      const len = Math.hypot(dir.x, dir.y) || 1;
      Object.assign(shake, { amp: Math.max(shake.amp, amp), dirX: dir.x / len, dirY: dir.y / len, t: 0 });
    },
    flash(color, alpha) {
      flash.tint = color;
      flash.alpha = Math.max(flash.alpha, alpha);
    },
  };
}
