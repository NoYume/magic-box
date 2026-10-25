// Arena: wires a source (bodies + hands) -> Match (posture, signs, rules, rounds) -> renderer, UI, audio.
//
// URL params:
//   ?src=zed&ws=ws://<jetson>:8765   ZED X box (frames + depth from jetson/tracker.py)
//   ?src=webcam                       laptop webcam, depth estimated from palm size (default)
//   ?src=demo                         two scripted players, no camera needed
// Keys: D debug overlay, H hitboxes, M mute, R reset to the lobby (dev shortcut).
// URL flag: ?debug=1 starts the debug overlay and hitboxes.

import { Sfx } from './audio/sfx.js';
import { Match } from './game/match.js';
import { PHASE } from './game/rounds.js';
import { DebugLayer } from './render/debug-layer.js';
import { Effects } from './render/effects.js';
import { createStage } from './render/stage.js';
import { createDemoSource } from './sources/demo.js';
import { createWebcamSource } from './sources/webcam.js';
import { createZedSource } from './sources/zed.js';
import { applyThemeToDocument, configurePlayerThemes } from './theme.js';
import { DebugPanel } from './ui/debug-panel.js';
import { Hud } from './ui/hud.js';
import { Screens } from './ui/screens.js';
import { SpellFeedback } from './ui/spell-feedback.js';
import { MuseVoiceControl } from './voice/muse.js';

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
  if (!match || match.flow.phase !== PHASE.FIGHT) return false;
  const fx = match.castIncantation(slot, spellName, intensity);
  pendingFx.push(...fx);
  return fx.length > 0 || ['ward', 'gather'].includes(spellName);
}

async function loadFonts() {
  const timeout = new Promise((resolve) => setTimeout(resolve, FONT_TIMEOUT_MS));
  await Promise.race([Promise.all(FONT_FACES.map((f) => document.fonts.load(f))), timeout]);
}

function unavailableReason(status, ability) {
  const name = ability[0].toUpperCase() + ability.slice(1);
  const seconds = status.remainingMs ? Math.ceil(status.remainingMs / 100) / 10 : 0;
  const reasons = {
    invalidPlayer: 'That player is not in this duel.',
    unknownAbility: 'That ability is not in your spellbook.',
    duelNotLive: 'Wait for the fight bell before casting.',
    cooldown: `${name} is recharging — ${seconds.toFixed(1)}s remaining.`,
    chargeRequired: `Ultimate needs full charge — ${Math.round((status.charge ?? 0) * 100)}% ready.`,
    wardBroken: `Ward is shattered — reforms in ${seconds.toFixed(1)}s.`,
    manaRequired: `Not enough mana — ${Math.floor(status.mana ?? 0)} remaining.`,
    chargeFull: 'Charge is already full. Cast Bolt or Ultimate.',
  };
  return reasons[status.reason] ?? `${name} cannot be cast right now.`;
}

function createSource(kind, onStatus) {
  if (kind === 'demo') return createDemoSource();
  if (kind === 'zed') return createZedSource(params.get('ws') ?? `ws://${location.hostname || 'localhost'}:8765`, onStatus);
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

function bindKeys({ debugLayer, debugPanel, sfx, resetMatch }) {
  const setDebug = (isOn) => {
    debugLayer.setVisible(isOn);
    debugLayer.setHitboxes(isOn);
    debugPanel.setVisible(isOn);
  };
  setDebug(params.get('debug') === '1' || params.get('debug') === 'true');
  window.addEventListener('keydown', (e) => {
    if (e.repeat || e.ctrlKey || e.metaKey || e.altKey || e.target.closest?.('input, textarea, select, [contenteditable="true"]')) return;
    const key = e.key.toLowerCase();
    if (key === 'd' || key === 'h') setDebug(!debugLayer.visible);
    if (key === 'm') sfx.toggleMute();
    if (key === 'r') resetMatch();
  });
}

async function start() {
  applyThemeToDocument();
  let source = null;
  let activeMode = null;
  const hud = new Hud($('hud'));
  const beginMatch = (mode, characters) => {
    if (!source) {
      screens.setStatus('The arena is still waking up. Try again in a moment.');
      return;
    }
    screens.setStatus(null);
    activeMode = mode;
    configurePlayerThemes(characters, { botSlot: mode === 'bot' ? 1 : null });
    match = new Match({ mirror: source.mirror, mode });
    pendingFx.push(...match.start());
    hud.setPlayers();
    screens.setPlayers();
    screens.showGame();
  };
  const screens = new Screens($('screens'), {
    onStartLocal: (characters) => beginMatch('local', characters),
    onStartBot: () => beginMatch('bot', ['ember', 'frost']),
  });
  const debugPanel = new DebugPanel($('debug'));
  const spellFeedback = new SpellFeedback($('app'));
  const voice = new MuseVoiceControl($('app'), {
    onCommand: ({ slot, ability }) => {
      if (!activeMode) return { accepted: false, message: 'Start a duel first.', slot };
      if (activeMode === 'local' && slot === null) {
        return { accepted: false, message: 'Say “player one” or “player two” before the ability.', slot };
      }
      const target = activeMode === 'bot' ? 0 : slot;
      if (activeMode === 'bot' && slot === 1) {
        return { accepted: false, message: 'Player two is controlled by the Mage Bot.', slot };
      }
      const availability = match.incantationAvailability(target, ability);
      if (!availability.available) {
        return { accepted: false, message: unavailableReason(availability, ability), slot: target };
      }
      const accepted = castIncantation(target, ability, 1);
      return {
        accepted,
        message: accepted ? `${ability} answered the call.` : `${ability} could not be cast.`,
        slot: target,
      };
    },
    onFeedback: (result) => spellFeedback.show(result),
  });
  await loadFonts();
  source = await createSource(params.get('src') ?? 'webcam', (msg) => screens.setStatus(msg));
  const stage = await createStage(source.canvas, { mirror: source.mirror });
  const effects = new Effects(stage);
  const debugLayer = new DebugLayer(stage);
  const sfx = new Sfx();
  match = new Match({ mirror: source.mirror });
  window.arena = { castIncantation, get match() { return match; } };
  bindKeys({
    debugLayer,
    debugPanel,
    sfx,
    resetMatch: () => {
      if (!activeMode) return;
      match = new Match({ mirror: source.mirror, mode: activeMode });
      pendingFx.push(...match.start());
    },
  });

  let renderFps = 60;
  stage.app.ticker.add((ticker) => {
    const now = performance.now();
    const dtMs = Math.min(ticker.deltaMS, MAX_DT_MS);
    renderFps += (1000 / Math.max(ticker.deltaMS, 1) - renderFps) * FPS_SMOOTHING;
    const input = source.poll(now, { phase: match.flow.phase, phaseMs: match.flow.phaseMs, combat: match.combat });
    if (activeMode && input?.bodies) pendingFx.push(...match.ingestBodies(input.bodies, now));
    if (activeMode) pendingFx.push(...match.step(dtMs));
    for (const ev of pendingFx) {
      effects.onFx(ev);
      playSound(sfx, ev);
    }
    pendingFx = [];
    const isFight = activeMode && match.flow.phase === PHASE.FIGHT;
    match.combat.players.forEach((p, slot) => sfx.gather(slot, p.charge, isFight && p.isGathering));
    const snapshot = { combat: match.combat, flow: match.flow, view: match.view, matchStats: match.matchStats };
    stage.frame(dtMs / 1000);
    effects.update(dtMs / 1000, snapshot);
    debugLayer.update(snapshot);
    hud.setVisible(Boolean(activeMode) && HUD_PHASES.has(match.flow.phase));
    hud.update(snapshot);
    screens.update(snapshot);
    debugPanel.update({ renderFps, source, view: match.view, flow: match.flow });
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
