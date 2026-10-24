// Wires a body source -> per-player gesture detectors -> battle rules -> renderer.
//
// URL params:
//   ?src=webcam                       laptop webcam + MediaPipe (default, for dev)
//   ?src=zed&ws=ws://localhost:8765   ZED X tracker on the Jetson

import { createRenderer } from './fx.js';
import { castSpell, createGame, handleGesture, resetGame, step } from './game.js';
import { GestureDetector } from './gestures.js';
import { createWebcamSource, createZedSource } from './sources.js';

const SLOT_LOST_MS = 1500;
const SPELL_KEYS = {
  1: [0, 'fireball'], 2: [0, 'lightning'], 3: [0, 'frost'],
  8: [1, 'fireball'], 9: [1, 'lightning'], 0: [1, 'frost'],
};

const params = new URLSearchParams(location.search);
const statusEl = document.getElementById('status');
const setStatus = (text) => (statusEl.textContent = text);

const game = createGame();
const detectors = [new GestureDetector(), new GestureDetector()];
const slots = [null, null]; // { id, lastSeen }
let latestBodies = [];
let pendingFx = [];

// Keep each tracked person in the same slot; new people take the free slot on their side of the screen.
function assignSlots(bodies, now) {
  const assigned = [];
  for (const body of bodies) {
    const center = body.kp.pelvis ?? body.kp.neck;
    if (!center) continue;
    const sx = 1 - center.x;
    let slot = slots.findIndex((s) => s?.id === body.id);
    if (slot === -1) {
      const preferred = sx < 0.5 ? 0 : 1;
      slot = [preferred, 1 - preferred].find((i) => !slots[i] || now - slots[i].lastSeen > SLOT_LOST_MS) ?? -1;
      if (slot === -1) continue;
      slots[slot] = { id: body.id };
      detectors[slot].reset();
    }
    slots[slot].lastSeen = now;
    assigned.push({ slot, kp: body.kp, sx, sy: center.y });
  }
  return assigned;
}

function onBodies(bodies, now) {
  latestBodies = assignSlots(bodies, now);
  game.players.forEach((p, i) => (p.present = !!slots[i] && now - slots[i].lastSeen < SLOT_LOST_MS));
  for (const { slot, kp, sx, sy } of latestBodies) {
    Object.assign(game.players[slot], { x: sx, y: sy });
    for (const ev of detectors[slot].update(kp, now)) {
      if (ev.type === 'push') Object.assign(ev, { sx: 1 - ev.x, sy: ev.y });
      pendingFx.push(...handleGesture(game, slot, ev, now));
    }
  }
}

window.addEventListener('keydown', (e) => {
  if (e.key === 'r') resetGame(game);
  const spell = SPELL_KEYS[e.key];
  if (spell) pendingFx.push(...castSpell(game, ...spell));
});

// Exposed so the voice/AI layer can cast spells: window.arena.cast(0, 'fireball')
window.arena = { cast: (slot, name) => pendingFx.push(...castSpell(game, slot, name)), game };

function bannerText() {
  if (game.winner !== null) return `PLAYER ${game.winner + 1} WINS!\n(press R)`;
  const missing = game.players.filter((p) => !p.present).length;
  return missing === 2 ? 'Step into the circle…' : '';
}

async function start() {
  const source =
    params.get('src') === 'zed'
      ? createZedSource(params.get('ws') ?? `ws://${location.hostname || 'localhost'}:8765`, onBodies, setStatus)
      : await createWebcamSource(onBodies, setStatus);
  const renderer = await createRenderer(source.canvas);
  let last = performance.now();
  renderer.app.ticker.add(() => {
    const now = performance.now();
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    pendingFx.push(...step(game, dt));
    for (const ev of pendingFx) renderer.onFx(ev, game);
    pendingFx = [];
    renderer.render(game, latestBodies, dt, bannerText());
  });
}

start().catch((err) => {
  setStatus(`Failed to start: ${err.message}`);
  console.error(err);
});
