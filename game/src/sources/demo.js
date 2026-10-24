// Scripted demo source (?src=demo): two DemoBots perform real hand signs (synthetic 21-point
// hands) and body moves (synthetic torsos). Everything goes through the same body roster,
// posture, hand roster, classifier and caster path as camera input; only the detectors are
// replaced. The painted frame draws bodies and hands at their exact pixels, so the debug
// overlay (D) doubles as an alignment check.

import { HAND_BONES, PALM_POINTS } from '../vision/landmarks.js';
import { DemoBot, botToInputs } from './demo-bot.js';

const FRAME_W = 960;
const FRAME_H = 600; // ZED X aspect
const TICK_MS = 33;
const BOT_SEEDS = [7, 19];
const SKIN = '#c4977d';
const SKIN_SHADE = '#9c7260';
const CLOTH = ['#4a3c48', '#3c4150'];
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
  return room;
}

function paintBody(ctx, kp, color) {
  const px = (p) => ({ x: p.x * FRAME_W, y: p.y * FRAME_H });
  const l = px(kp.l_shoulder);
  const r = px(kp.r_shoulder);
  const head = px(kp.head);
  const half = Math.abs(l.x - r.x) / 2;
  const cx = (l.x + r.x) / 2;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.ellipse(cx, l.y + half * 1.6, half * 1.25, half * 2, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(head.x, head.y, half * 0.42, half * 0.55, 0, 0, Math.PI * 2);
  ctx.fill();
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

  // context: { phase, phaseMs, combat }. Returns { observations, bodies } or null between ticks.
  function poll(tMs, context) {
    if (tMs - lastTick < TICK_MS) return null;
    lastTick = tMs;
    const inputs = bots.map((bot, slot) => botToInputs(slot, bot.update(tMs, context), FRAME_W, FRAME_H));
    ctx.drawImage(room, 0, 0);
    inputs.forEach(({ body }, slot) => paintBody(ctx, body.kp, CLOTH[slot]));
    for (const { observations } of inputs) for (const obs of observations) paintHand(ctx, obs.landmarks);
    return { observations: inputs.flatMap((i) => i.observations), bodies: inputs.map((i) => i.body) };
  }

  return { kind: 'demo', canvas, mirror: true, poll, stats, getDepthMap: () => null };
}
