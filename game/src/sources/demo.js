// Scripted demo source (?src=demo): two DemoBots perform real signs as synthetic 21-point hands.
// Observations go through the same roster / classifier / caster path as camera input; only the
// detector is replaced. The frame shows a painted room with the hands drawn at their exact
// landmark pixels, so the debug overlay (D) doubles as an alignment check.

import { HAND_BONES, PALM_POINTS } from '../vision/landmarks.js';
import { DemoBot, specToObservations } from './demo-bot.js';

const FRAME_W = 960;
const FRAME_H = 600; // ZED X aspect
const TICK_MS = 33;
const BOT_SEEDS = [7, 19];
const SKIN = '#c4977d';
const SKIN_SHADE = '#9c7260';
const PALM_STROKE_RATIO = 0.22; // finger stroke width relative to palm length

function paintRoom() {
  const room = document.createElement('canvas');
  [room.width, room.height] = [FRAME_W, FRAME_H];
  const ctx = room.getContext('2d');
  const wall = ctx.createLinearGradient(0, 0, 0, FRAME_H);
  wall.addColorStop(0, '#3a3140');
  wall.addColorStop(0.7, '#241d2a');
  wall.addColorStop(1, '#1a1418');
  ctx.fillStyle = wall;
  ctx.fillRect(0, 0, FRAME_W, FRAME_H);
  const lamp = ctx.createRadialGradient(FRAME_W * 0.5, FRAME_H * 0.1, 10, FRAME_W * 0.5, FRAME_H * 0.1, FRAME_W * 0.6);
  lamp.addColorStop(0, 'rgba(255, 214, 160, 0.22)');
  lamp.addColorStop(1, 'rgba(255, 214, 160, 0)');
  ctx.fillStyle = lamp;
  ctx.fillRect(0, 0, FRAME_W, FRAME_H);
  ctx.filter = 'blur(10px)';
  for (const u of [0.25, 0.75]) {
    ctx.fillStyle = '#4a3f4c';
    ctx.beginPath();
    ctx.ellipse(u * FRAME_W, 0.3 * FRAME_H, 0.075 * FRAME_W, 0.15 * FRAME_H, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#3b3140';
    ctx.beginPath();
    ctx.ellipse(u * FRAME_W, 0.86 * FRAME_H, 0.19 * FRAME_W, 0.36 * FRAME_H, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.filter = 'none';
  ctx.fillStyle = '#2b211d';
  ctx.fillRect(0, FRAME_H * 0.9, FRAME_W, FRAME_H * 0.1);
  return room;
}

function paintHand(ctx, landmarks) {
  const px = landmarks.map((p) => ({ x: p.x * FRAME_W, y: p.y * FRAME_H }));
  const palm = Math.hypot(px[0].x - px[9].x, px[0].y - px[9].y);
  ctx.fillStyle = SKIN_SHADE;
  ctx.beginPath();
  PALM_POINTS.concat([1]).forEach((i, n) => (n ? ctx.lineTo(px[i].x, px[i].y) : ctx.moveTo(px[i].x, px[i].y)));
  ctx.fill();
  ctx.strokeStyle = SKIN;
  ctx.lineCap = 'round';
  ctx.lineWidth = palm * PALM_STROKE_RATIO;
  for (const [a, b] of HAND_BONES) {
    ctx.beginPath();
    ctx.moveTo(px[a].x, px[a].y);
    ctx.lineTo(px[b].x, px[b].y);
    ctx.stroke();
  }
}

export function createDemoSource() {
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = [FRAME_W, FRAME_H];
  const ctx = canvas.getContext('2d');
  const room = paintRoom();
  const bots = BOT_SEEDS.map((seed, slot) => new DemoBot(slot, seed));
  const stats = { kind: 'demo', hands: { delegate: 'scripted', fps: 1000 / TICK_MS, inferMs: 0 } };
  let lastTick = -Infinity;

  // context: { phase, phaseMs, combat }
  function poll(tMs, context) {
    if (tMs - lastTick < TICK_MS) return null;
    lastTick = tMs;
    const observations = bots.flatMap((bot) => bot.update(tMs, context)).flatMap((spec) => specToObservations(spec, FRAME_W, FRAME_H));
    ctx.drawImage(room, 0, 0);
    for (const obs of observations) paintHand(ctx, obs.landmarks);
    return observations;
  }

  return { kind: 'demo', canvas, mirror: true, poll, stats, getDepthMap: () => null };
}
