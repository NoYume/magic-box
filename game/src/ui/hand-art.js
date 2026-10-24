// Line illustrations of the signs, drawn as SVG from the same synthetic hand model the classifier
// is tested against, seen in a slight three-quarter view so curled fingers read clearly.

import { FINGERS, THUMB, WRIST } from '../vision/landmarks.js';
import { POSES, makeHand, makeTrianglePair } from '../vision/synthetic-hand.js';
import { rotate } from '../vision/vec.js';

const VIEW = 100;
const PAD = 10;
const THREE_QUARTER = { yaw: 0.45, pitch: -0.3 };
const PALM_OUTLINE = [WRIST, THUMB[0], FINGERS.index[0], FINGERS.middle[0], FINGERS.ring[0], FINGERS.pinky[0]];

function fit(hands) {
  const all = hands.flat();
  const xs = all.map((p) => p.x);
  const ys = all.map((p) => p.y);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const scale = (VIEW - PAD * 2) / Math.max(maxX - minX, maxY - minY);
  const offX = (VIEW - (maxX - minX) * scale) / 2;
  const offY = (VIEW - (maxY - minY) * scale) / 2;
  return hands.map((pts) => pts.map((p) => ({ x: offX + (p.x - minX) * scale, y: offY + (p.y - minY) * scale, z: p.z })));
}

const polyline = (pts, idx) => idx.map((i) => `${pts[i].x.toFixed(1)},${pts[i].y.toFixed(1)}`).join(' ');

function handMarkup(pts) {
  const chains = [[WRIST, ...THUMB], ...Object.values(FINGERS)];
  const meanZ = (idx) => idx.reduce((s, i) => s + pts[i].z, 0) / idx.length;
  chains.sort((a, b) => meanZ(b) - meanZ(a)); // far first, near fingers drawn on top
  const palm = `<polygon class="art-palm" points="${polyline(pts, PALM_OUTLINE)}"/>`;
  const fingers = chains.map((c) => `<polyline class="art-edge" points="${polyline(pts, c)}"/><polyline class="art-line" points="${polyline(pts, c)}"/>`);
  return palm + fingers.join('');
}

// Small motion arcs that say "toward the screen".
function thrustMarks(pts) {
  const tip = pts[FINGERS.index[3]];
  return [0, 1, 2]
    .map((i) => `<circle class="art-thrust" cx="${tip.x.toFixed(1)}" cy="${(tip.y - 2).toFixed(1)}" r="${5 + i * 5}" style="--i:${i}"/>`)
    .join('');
}

export function signArt(sign) {
  let hands;
  if (sign === 'ultimate') {
    const { left, right } = makeTrianglePair();
    hands = fit([left, right].map((h) => h.map((p) => rotate(p, { pitch: -0.15 }))));
  } else {
    const pose = { ward: 'open', gather: 'fist', aim: 'sword' }[sign];
    hands = fit([makeHand(POSES[pose]).map((p) => rotate(p, THREE_QUARTER))]);
  }
  const extra = sign === 'aim' ? thrustMarks(hands[0]) : '';
  return `<svg class="sign-art" viewBox="0 0 ${VIEW} ${VIEW}" aria-hidden="true">${hands.map(handMarkup).join('')}${extra}</svg>`;
}
