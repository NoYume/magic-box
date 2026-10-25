// Arena: wires a source (bodies + hands) -> Match (posture, signs, rules, rounds) -> renderer, UI, audio.
//
// URL params:
//   ?src=zed&ws=ws://<jetson>:8765   ZED X box (frames + depth from jetson/tracker.py)
//   ?src=webcam                       laptop webcam, depth estimated from palm size (default)
//   ?src=demo                         two scripted players, no camera needed
// Keys: D debug overlay, H hitboxes, M mute, R reset to the lobby (dev shortcut),
//       L debug log on/off, B mark a bad detection (ZED only, see game/src/debug/telemetry.js).
// URL flags: ?debug=1 starts the debug overlay and hitboxes, ?log=1 starts the debug log,
//            ?mirror=1 shows the ZED view as a mirror (default: each player faces the opponent).

import { Sfx } from './audio/sfx.js';
import { Telemetry } from './debug/telemetry.js';
import { Match } from './game/match.js';
import { PHASE } from './game/rounds.js';
import { DebugLayer } from './render/debug-layer.js';
import { Effects } from './render/effects.js';
import { createStage } from './render/stage.js';
import { createDemoSource } from './sources/demo.js';
import { createWebcamSource } from './sources/webcam.js';
import { createZedSource } from './sources/zed.js';
import { applyThemeToDocument } from './theme.js';
import { DebugPanel } from './ui/debug-panel.js';
import { Hud } from './ui/hud.js';
import { Screens } from './ui/screens.js';
import { Spellbook } from './ui/spellbook.js';

const FONT_FACES = ['800 16px "Barlow Condensed"', '600 16px "Barlow Condensed"', '500 16px Barlow', '500 16px "IBM Plex Mono"'];
const FONT_TIMEOUT_MS = 3000;
const MAX_DT_MS = 50;
const FPS_SMOOTHING = 0.05;
const HUD_PHASES = new Set([PHASE.COUNTDOWN, PHASE.FIGHT, PHASE.KO, PHASE.ROUND_END]);

const params = new URLSearchParams(location.search);
const $ = (id) => document.getElementById(id);

let match = null;
let pendingFx = [];

// Voice / AI hook (Muse Voice Transcribe layer): castIncantation(0, 'bolt', 0.8).
// spellName: 'bolt' | 'ward' | 'gather' | 'ultimate'; intensity 0..1. Returns true if it cast.
export function castIncantation(slot, spellName, intensity = 1) {
  if (!match) return false;
  const fx = match.castIncantation(slot, spellName, intensity);
  pendingFx.push(...fx);
  return fx.length > 0 || ['ward', 'gather'].includes(spellName);
}

async function loadFonts() {
  const timeout = new Promise((resolve) => setTimeout(resolve, FONT_TIMEOUT_MS));
  await Promise.race([Promise.all(FONT_FACES.map((f) => document.fonts.load(f))), timeout]);
}

function createSource(kind, onStatus) {
  if (kind === 'demo') return createDemoSource();
  if (kind === 'zed') {
    const url = params.get('ws') ?? `ws://${location.hostname || 'localhost'}:8765`;
    return createZedSource(url, onStatus, { mirror: isFlagOn('mirror') });
  }
  return createWebcamSource(onStatus);
}

function playSound(sfx, ev) {
  const sounds = {
    cast: () => sfx.cast(ev.projectile.empowered, ev.projectile.kind === 'ultimate'),
    hit: () => (ev.damage > 0 ? sfx.impact(ev.damage, ev.projectile.empowered) : sfx.wardHit()),
    wardShatter: () => sfx.shatter(),
    wardUp: () => sfx.wardUp(),
    dodge: () => sfx.whoosh(),
    evade: () => sfx.whoosh(),
    stance: () => ev.stance !== 'neutral' && sfx.stance(ev.stance),
    ko: () => sfx.knockout(),
    tick: () => sfx.tick(ev.value === 1),
    roundStart: () => sfx.begin(),
    joined: () => sfx.joined(),
    matchOver: () => sfx.victory(),
  };
  sounds[ev.kind]?.();
}

function spellbookMode(phase) {
  if (phase === PHASE.ATTRACT) return 'open';
  if (HUD_PHASES.has(phase)) return 'compact';
  return 'hidden';
}

const isFlagOn = (name) => params.get(name) === '1' || params.get(name) === 'true';

function bindKeys({ debugLayer, debugPanel, sfx, telemetry, lastSeq }) {
  const setDebug = (isOn) => {
    debugLayer.setVisible(isOn);
    debugLayer.setHitboxes(isOn);
    debugPanel.setVisible(isOn);
    const button = $('debug-toggle');
    if (button) {
      button.textContent = isOn ? 'Debug on [D]' : 'Debug [D]';
      button.setAttribute('aria-pressed', String(isOn));
    }
  };
  setDebug(isFlagOn('debug'));
  $('debug-toggle')?.addEventListener('click', () => setDebug(!debugLayer.visible));

  window.addEventListener('keydown', (e) => {
    if (e.repeat || e.ctrlKey || e.metaKey || e.altKey || e.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
    const key = e.key.toLowerCase();
    if (key === 'd' || key === 'h') setDebug(!debugLayer.visible);
    if (key === 'm') sfx.toggleMute();
    if (key === 'l') telemetry.toggle();
    if (key === 'b') telemetry.mark(lastSeq(), performance.now());
    if (key === 'r') match = new Match({ mirror: match.roster.mirror });
  });
}

async function start() {
  applyThemeToDocument();
  const screens = new Screens($('screens'));
  const hud = new Hud($('hud'));
  const books = [0, 1].map((slot) => new Spellbook($(`spellbook-${slot}`), slot));
  const debugPanel = new DebugPanel($('debug'));
  await loadFonts();
  const source = await createSource(params.get('src') ?? 'webcam', (msg) => screens.setStatus(msg));
  $('source-label').textContent = { demo: 'Demo / scripted', webcam: 'Live / webcam', zed: 'Live / ZED' }[source.kind] ?? source.kind;
  const stage = await createStage(source.canvas, { mirror: source.mirror });
  const effects = new Effects(stage);
  const debugLayer = new DebugLayer(stage);
  const sfx = new Sfx();
  match = new Match({ mirror: source.mirror });
  window.arena = { castIncantation, get match() { return match; } };
  const telemetry = new Telemetry(source.send, { enabled: isFlagOn('log') });
  let lastSeq = -1;
  bindKeys({ debugLayer, debugPanel, sfx, telemetry, lastSeq: () => lastSeq });

  let renderFps = 60;
  stage.app.ticker.add((ticker) => {
    const now = performance.now();
    const dtMs = Math.min(ticker.deltaMS, MAX_DT_MS);
    renderFps += (1000 / Math.max(ticker.deltaMS, 1) - renderFps) * FPS_SMOOTHING;
    const input = source.poll(now, { phase: match.flow.phase, phaseMs: match.flow.phaseMs, combat: match.combat });
    if (input?.bodies) pendingFx.push(...match.ingestBodies(input.bodies, now));
    if (input?.seq !== undefined) lastSeq = input.seq;
    if (input?.observations) {
      pendingFx.push(...match.ingest(input.observations, now));
      const hands = source.stats.hands;
      const stats = { render: renderFps, hands: hands?.fps, inferMs: hands?.inferMs, tracker: source.stats.trackerFps };
      telemetry.record({ seq: input.seq, tMs: now, view: match.view, flow: match.flow, stats, mirror: source.mirror });
    }
    pendingFx.push(...match.step(dtMs));
    for (const ev of pendingFx) {
      effects.onFx(ev);
      playSound(sfx, ev);
    }
    pendingFx = [];
    const isFight = match.flow.phase === PHASE.FIGHT;
    match.combat.players.forEach((p, slot) => sfx.gather(slot, p.charge, isFight && p.isGathering));
    const snapshot = { combat: match.combat, flow: match.flow, view: match.view, matchStats: match.matchStats };
    stage.frame(dtMs / 1000);
    effects.update(dtMs / 1000, snapshot);
    debugLayer.update(snapshot);
    hud.setVisible(HUD_PHASES.has(match.flow.phase));
    hud.update(snapshot);
    screens.update(snapshot);
    books.forEach((book, slot) => {
      book.setMode(spellbookMode(match.flow.phase));
      book.setCaster(match.view.casters[slot]);
      book.setBody(match.combat.players[slot], match.combat.clockMs);
    });
    debugPanel.update({ renderFps, source, view: match.view, flow: match.flow, telemetry });
  });
}

start().catch((err) => {
  console.error('[arena] failed to start', err);
  const toast = document.querySelector('.toast');
  if (toast) {
    toast.hidden = false;
    toast.textContent = `The arena could not start: ${err.message}. Check the camera and reload.`;
  }
});
