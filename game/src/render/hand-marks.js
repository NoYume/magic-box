// On-hand cast state: a confirm ring that fills while a sign is held, the sign's rune glyph and
// a small-caps label beside the hand. Crisp (not bloomed) so it reads as UI, not as magic.

import { Container, Graphics, Sprite, Text } from 'pixi.js';

import { PHASE } from '../game/caster.js';
import { PHASE as FLOW, SEAT, TUTORIAL_SIGNS } from '../game/rounds.js';
import { SIGNS } from '../vision/signs.js';
import { COLOR, FONT, PLAYER_THEME } from '../theme.js';

const RING_PALMS = 1.25; // ring radius in palm lengths
const GLYPH_PALMS = 0.55;
const RING_WIDTH = 3;
const START = -Math.PI / 2;
const FADE_RATE = 12;

const LABEL = {
  [SIGNS.WARD]: 'Ward',
  [SIGNS.GATHER]: 'Gather',
  [SIGNS.AIM]: 'Bolt',
  [SIGNS.ULTIMATE]: 'Ultimate',
};

function labelFor(state) {
  if (state.phase === PHASE.READY) return 'Shoot';
  if (state.phase === PHASE.BLOCKED) return state.sign === SIGNS.ULTIMATE ? 'Gather first' : 'No mana';
  return LABEL[state.sign] ?? '';
}

function ringColor(state, slot) {
  if (state.phase === PHASE.BLOCKED) return COLOR.danger;
  if (state.sign === SIGNS.ULTIMATE) return COLOR.violet;
  if (state.sign === SIGNS.WARD) return COLOR.verdant;
  if (state.phase === PHASE.DETECTED) return COLOR.gold;
  return PLAYER_THEME[slot].element;
}

export class HandMarks {
  constructor(stage) {
    this.stage = stage;
    this.container = new Container();
    stage.layers.marks.addChild(this.container);
    this.marks = new Map(); // key -> mark
    this.time = 0;
  }

  #create(key) {
    const ring = new Graphics();
    const glyph = new Sprite();
    glyph.anchor.set(0.5);
    const label = new Text({
      text: '',
      style: { fontFamily: FONT.display, fontSize: 15, fontWeight: '600', letterSpacing: 2.5, fill: COLOR.parchment, dropShadow: { color: COLOR.inkDeep, blur: 6, distance: 0, alpha: 0.9 } },
    });
    label.anchor.set(0, 0.5);
    const root = new Container();
    root.addChild(ring, glyph, label);
    root.alpha = 0;
    this.container.addChild(root);
    const mark = { root, ring, glyph, label, seen: true };
    this.marks.set(key, mark);
    return mark;
  }

  update(dt, { view, flow }) {
    this.time += dt;
    this.marks.forEach((m) => (m.seen = false));
    for (const slot of [0, 1]) {
      if (flow.phase === FLOW.ATTRACT) {
        this.#tutorial(slot, view, flow, dt);
        continue;
      }
      const caster = view.casters[slot];
      if (!caster || flow.phase !== FLOW.FIGHT) continue;
      if (caster.ultimate) {
        const hands = view.slots[slot];
        const palm = hands.reduce((s, h) => s + h.palmSpan, 0) / Math.max(1, hands.length);
        this.#draw(`u${slot}`, { ...caster.ultimate, sign: SIGNS.ULTIMATE }, caster.ultimate.at, palm * 1.6, slot, dt);
        continue;
      }
      for (const hand of view.slots[slot]) {
        const state = caster.handStates.get(hand.id);
        if (state && state.phase !== PHASE.IDLE) this.#draw(hand.id, state, hand.view, hand.palmSpan, slot, dt);
      }
    }
    for (const [key, m] of this.marks) {
      if (m.seen) continue;
      m.root.alpha -= dt * FADE_RATE * 0.5;
      if (m.root.alpha <= 0) {
        m.root.destroy({ children: true });
        this.marks.delete(key);
      }
    }
  }

  #tutorial(slot, view, flow, dt) {
    const seat = flow.seats[slot];
    if (!seat || seat.status === SEAT.READY) return;
    const sign = TUTORIAL_SIGNS[seat.tutorialStep];
    const hands = view.slots[slot];
    let at;
    let palmSpan;
    if (sign === SIGNS.ULTIMATE) {
      if (!view.triangles[slot].active || hands.length < 2) return;
      at = {
        x: hands.reduce((sum, hand) => sum + hand.view.x, 0) / hands.length,
        y: hands.reduce((sum, hand) => sum + hand.view.y, 0) / hands.length,
      };
      palmSpan = (hands.reduce((sum, hand) => sum + hand.palmSpan, 0) / hands.length) * 1.6;
    } else {
      const hand = hands.find((candidate) => candidate.sign === sign);
      if (!hand) return;
      at = hand.view;
      palmSpan = hand.palmSpan;
    }
    this.#draw(`tutorial-${slot}`, { phase: PHASE.DETECTED, sign, progress: seat.progress }, at, palmSpan, slot, dt);
  }

  #draw(key, state, at, palmSpan, slot, dt) {
    const t = this.stage.transform;
    const m = this.marks.get(key) ?? this.#create(key);
    m.seen = true;
    m.root.alpha = Math.min(1, m.root.alpha + dt * FADE_RATE);
    const p = t.viewToScreen(at.x, at.y);
    const palm = palmSpan * t.drawnH;
    const r = palm * RING_PALMS;
    const color = ringColor(state, slot);
    m.root.position.set(p.x, p.y);
    m.ring.clear();
    const showRing = state.phase !== PHASE.WARDING;
    if (showRing) {
      m.ring.circle(0, 0, r).stroke({ width: 1, color: COLOR.parchment, alpha: 0.25 });
      const progress = state.phase === PHASE.READY || state.phase === PHASE.CAST ? 1 : Math.max(0, Math.min(1, state.progress));
      if (progress > 0) m.ring.arc(0, 0, r, START, START + progress * Math.PI * 2).stroke({ width: RING_WIDTH, color, cap: 'round' });
      if (state.phase === PHASE.READY) {
        const breathe = 1.08 + 0.05 * Math.sin(this.time * 9);
        m.ring.circle(0, 0, r * breathe).stroke({ width: 1.5, color, alpha: 0.6 });
      }
    }
    const glyphTexture = this.stage.textures.glyphs[state.sign];
    m.glyph.visible = Boolean(glyphTexture);
    if (glyphTexture) {
      m.glyph.texture = glyphTexture;
      m.glyph.tint = color;
      m.glyph.width = m.glyph.height = palm * GLYPH_PALMS;
      m.glyph.position.set(r * 0.72, -r * 0.72);
      m.glyph.alpha = state.phase === PHASE.COOLDOWN ? 0.45 : 1;
    }
    const text = labelFor(state).toUpperCase();
    if (m.label.text !== text) m.label.text = text;
    m.label.position.set(r * 0.72 + palm * GLYPH_PALMS * 0.65, -r * 0.72);
  }
}
