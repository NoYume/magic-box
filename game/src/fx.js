// PixiJS renderer: mirrored camera feed + skeleton glow + bolts + particles + HUD.

import { Application, Container, Graphics, Sprite, Text, Texture } from 'https://cdn.jsdelivr.net/npm/pixi.js@8.6.6/dist/pixi.min.mjs';

import { MAX_HP } from './game.js';

const PLAYER_COLORS = [0x4ad7ff, 0xff4a8b];
const BONES = [
  ['head', 'neck'], ['neck', 'l_shoulder'], ['neck', 'r_shoulder'], ['l_shoulder', 'l_wrist'],
  ['r_shoulder', 'r_wrist'], ['neck', 'pelvis'],
];
const SHAKE_DECAY = 8;

export async function createRenderer(feedCanvas) {
  const app = new Application();
  await app.init({ resizeTo: window, background: '#05010d', antialias: true });
  document.body.appendChild(app.canvas);

  const world = new Container();
  app.stage.addChild(world);
  const feedTexture = Texture.from(feedCanvas);
  const feed = new Sprite(feedTexture);
  feed.alpha = 0.85;
  world.addChild(feed);

  const skeletons = new Graphics();
  const magic = new Graphics();
  magic.blendMode = 'add';
  skeletons.blendMode = 'add';
  world.addChild(skeletons, magic);

  const hud = new Graphics();
  const banner = new Text({ text: '', style: { fill: 0xffffff, fontSize: 72, fontWeight: '900', align: 'center', fontFamily: 'Georgia, serif', dropShadow: { color: 0x9b4dff, blur: 18, distance: 0 } } });
  banner.anchor.set(0.5);
  app.stage.addChild(hud, banner);

  const particles = [];
  const floaters = [];
  let shake = 0;

  const toPx = (sx, sy) => ({ x: sx * app.screen.width, y: sy * app.screen.height });

  function layoutFeed() {
    const scale = Math.max(app.screen.width / feedCanvas.width, app.screen.height / feedCanvas.height) || 1;
    feed.scale.set(-scale, scale); // mirror so it feels like a magic mirror
    feed.x = app.screen.width;
  }

  function burst(sx, sy, color, count, speed) {
    const { x, y } = toPx(sx, sy);
    for (let i = 0; i < count; i++) {
      const a = Math.random() * Math.PI * 2;
      const v = speed * (0.3 + Math.random());
      particles.push({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, color, r: 2 + Math.random() * 5 });
    }
  }

  function addFloater(sx, sy, text, color) {
    const label = new Text({ text, style: { fill: color, fontSize: 48, fontWeight: '900', stroke: { color: 0x000000, width: 6 } } });
    label.anchor.set(0.5);
    Object.assign(label.position, toPx(sx, sy));
    app.stage.addChild(label);
    floaters.push({ label, life: 1 });
  }

  function onFx(ev, game) {
    if (ev.kind === 'cast') burst(ev.bolt.x, ev.bolt.y, ev.bolt.color, ev.bolt.heavy ? 60 : 20, ev.bolt.heavy ? 9 : 5);
    if (ev.kind === 'hit') {
      burst(ev.x, ev.y, ev.shielded ? 0x9fe8ff : ev.color, ev.heavy ? 120 : 45, ev.heavy ? 14 : 8);
      addFloater(ev.x, ev.y - 0.08, ev.shielded ? `${ev.damage} 🛡` : `-${ev.damage}`, ev.shielded ? 0x9fe8ff : 0xffe14a);
      shake = Math.max(shake, ev.heavy ? 28 : 10);
    }
    if (ev.kind === 'heal') {
      const p = game.players[ev.slot];
      burst(p.x, p.y, 0x5dff8a, 70, 4);
      addFloater(p.x, p.y - 0.2, '+HEAL', 0x5dff8a);
    }
    if (ev.kind === 'ko') shake = 40;
  }

  function drawSkeletons(bodies, game) {
    skeletons.clear();
    for (const { slot, kp } of bodies) {
      const color = PLAYER_COLORS[slot] ?? 0xffffff;
      const p = game.players[slot];
      const width = p?.stance === 'forward' ? 10 : 5;
      for (const [a, b] of BONES) {
        if (!kp[a] || !kp[b]) continue;
        const pa = toPx(1 - kp[a].x, kp[a].y);
        const pb = toPx(1 - kp[b].x, kp[b].y);
        skeletons.moveTo(pa.x, pa.y).lineTo(pb.x, pb.y).stroke({ width: width * 3, color, alpha: 0.15 });
        skeletons.moveTo(pa.x, pa.y).lineTo(pb.x, pb.y).stroke({ width, color, alpha: 0.8 });
      }
      for (const name of ['l_wrist', 'r_wrist']) {
        if (!kp[name]) continue;
        const { x, y } = toPx(1 - kp[name].x, kp[name].y);
        const glow = 14 + (p?.charge ?? 0) * 30;
        skeletons.circle(x, y, glow).fill({ color: p?.charge >= 1 ? 0xff2bd6 : color, alpha: 0.35 });
      }
      if (p?.stance === 'back') {
        const c = toPx(p.x, p.y);
        skeletons.circle(c.x, c.y, app.screen.height * 0.28).stroke({ width: 8, color: 0x9fe8ff, alpha: 0.6 });
      }
    }
  }

  function drawMagic(game, dt) {
    magic.clear();
    for (const bolt of game.bolts) {
      const { x, y } = toPx(bolt.x, bolt.y);
      const r = bolt.radius * app.screen.height;
      magic.circle(x, y, r * 2).fill({ color: bolt.color, alpha: 0.2 });
      magic.circle(x, y, r).fill({ color: bolt.color, alpha: 0.9 });
      magic.circle(x, y, r * 0.45).fill({ color: 0xffffff, alpha: 0.9 });
      if (Math.random() < 0.6) particles.push({ x, y, vx: -bolt.vx * 60, vy: (Math.random() - 0.5) * 60, life: 0.6, color: bolt.color, r: r * 0.4 });
    }
    for (let i = particles.length - 1; i >= 0; i--) {
      const s = particles[i];
      s.x += s.vx * dt * 60;
      s.y += s.vy * dt * 60;
      s.vx *= 0.94;
      s.vy *= 0.94;
      s.life -= dt * 1.4;
      if (s.life <= 0) particles.splice(i, 1);
      else magic.circle(s.x, s.y, s.r * s.life).fill({ color: s.color, alpha: s.life });
    }
  }

  function drawHud(game) {
    hud.clear();
    const w = app.screen.width * 0.38;
    const h = 26;
    game.players.forEach((p, slot) => {
      const x = slot === 0 ? 30 : app.screen.width - 30 - w;
      const fill = (w * p.hp) / MAX_HP;
      hud.roundRect(x, 30, w, h, 10).fill({ color: 0x000000, alpha: 0.55 });
      hud.roundRect(slot === 0 ? x : x + w - fill, 30, fill, h, 10).fill({ color: PLAYER_COLORS[slot], alpha: p.present ? 1 : 0.3 });
      hud.roundRect(x, 62, w * p.charge, 8, 4).fill({ color: 0xff2bd6, alpha: 0.9 });
    });
  }

  function render(game, bodies, dt, bannerText) {
    feedTexture.source.update();
    layoutFeed();
    drawSkeletons(bodies, game);
    drawMagic(game, dt);
    drawHud(game);
    for (let i = floaters.length - 1; i >= 0; i--) {
      const f = floaters[i];
      f.life -= dt;
      f.label.y -= 60 * dt;
      f.label.alpha = Math.max(0, f.life);
      if (f.life <= 0) {
        f.label.destroy();
        floaters.splice(i, 1);
      }
    }
    shake = Math.max(0, shake - shake * SHAKE_DECAY * dt);
    world.position.set((Math.random() - 0.5) * shake, (Math.random() - 0.5) * shake);
    banner.text = bannerText;
    banner.position.set(app.screen.width / 2, app.screen.height / 2);
  }

  return { app, render, onFx };
}
