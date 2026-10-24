// Debug readout (key D): frame rates, classifier output per hand, depth and the key thresholds.

import { BOLT, CONFIRM_MS } from '../game/balance.js';
import { BODY, DEPTH, SIGN, THRUST } from '../vision/tuning.js';

const DEPTH_PREVIEW_MAX_MM = 1600;
const fmt = (n, digits = 2) => (typeof n === 'number' && Number.isFinite(n) ? n.toFixed(digits) : '-');

export class DebugPanel {
  constructor(root) {
    this.root = root;
    this.text = document.createElement('pre');
    this.preview = document.createElement('canvas');
    this.preview.className = 'debug-depth';
    root.append(this.text, this.preview);
    this.visible = false;
    root.hidden = true;
  }

  setVisible(isVisible) {
    this.visible = isVisible;
    this.root.hidden = !isVisible;
  }

  #hands(view) {
    const lines = [];
    view.slots.forEach((hands, slot) => {
      for (const h of hands) {
        const state = view.casters[slot]?.handStates.get(h.id);
        lines.push(`P${slot + 1} #${h.id} ${h.handedness[0]}  sign ${h.sign.padEnd(8)} frame ${h.frameSign.padEnd(8)} score ${fmt(h.frameScore)}  vote ${fmt(h.agreement)}  z ${fmt(h.depth)} m  ${state?.phase ?? ''}`);
      }
    });
    view.rejected.forEach((h) => lines.push(`--  rejected: ${h.reason} (z ${fmt(h.depth)} m)`));
    return lines.length ? lines : ['no hands'];
  }

  #bodies(view) {
    const lines = view.bodies.map((b, slot) => {
      if (!b) return `P${slot + 1} body: none`;
      const posture = view.postures[slot];
      return `P${slot + 1} body #${b.id}  z ${fmt(b.torso.z)} m  lean ${fmt(posture?.leanOffset)} m  side ${fmt(posture?.lateral)} sh  ${posture?.stance ?? '-'}`;
    });
    if (view.rejectedBodies.length) lines.push(`--  ${view.rejectedBodies.length} body(ies) ignored (out of frame or range)`);
    return lines;
  }

  update({ renderFps, source, view, flow }) {
    if (!this.visible) return;
    const hands = source.stats.hands ?? {};
    const lines = [
      `render ${fmt(renderFps, 0)} fps   hands ${fmt(hands.fps, 0)} Hz (${hands.delegate ?? '-'}, ${fmt(hands.inferMs, 1)} ms)   source ${source.kind}`,
      source.kind === 'zed' ? `zed ${source.stats.connected ? 'connected' : 'offline'}  frames ${source.stats.frames}  depth ${source.stats.depthMaps} (${source.stats.depthSize ?? '-'})  tracker ${fmt(source.stats.trackerFps, 1)} fps` : '',
      `phase ${flow.phase}  round ${flow.round}  wins ${flow.wins.join('-')}`,
      '',
      ...this.#bodies(view),
      ...this.#hands(view),
      '',
      `confirm ms  ward ${CONFIRM_MS.ward}  gather ${CONFIRM_MS.gather}  aim ${CONFIRM_MS.aim}  ultimate ${CONFIRM_MS.ultimate}`,
      `thrust  >= ${THRUST.MIN_SPEED} m/s and >= ${THRUST.MIN_TRAVEL} m in ${THRUST.WINDOW_MS} ms   bolt cooldown ${BOLT.COOLDOWN_MS} ms`,
      `sign min score ${SIGN.MIN_SCORE}  facing >= ${SIGN.FACING_MIN}  sword gap <= ${SIGN.SWORD_GAP_MAX}  play depth ${DEPTH.PLAY_NEAR_M}-${DEPTH.PLAY_FAR_M} m`,
      `body  lean in <= -${BODY.LEAN_IN_FRAC * 100}% z  lean back >= ${BODY.LEAN_BACK_FRAC * 100}% z  hold ${BODY.STANCE_HOLD_MS} ms  dodge >= ${BODY.DODGE_SHIFT} sh in ${BODY.DODGE_WINDOW_MS} ms`,
      'keys: D debug   M mute   R reset (dev)',
    ].filter((line) => line !== null);
    this.text.textContent = lines.join('\n');
    this.#drawDepth(source.getDepthMap());
  }

  #drawDepth(map) {
    this.preview.hidden = !map;
    if (!map) return;
    if (this.preview.width !== map.width) [this.preview.width, this.preview.height] = [map.width, map.height];
    const ctx = this.preview.getContext('2d');
    const image = ctx.createImageData(map.width, map.height);
    for (let i = 0; i < map.data.length; i++) {
      const mm = map.data[i];
      const v = mm ? 255 - Math.min(255, (mm / DEPTH_PREVIEW_MAX_MM) * 255) : 0;
      image.data.set([v, v * 0.8, mm ? 90 : 0, 255], i * 4);
    }
    ctx.putImageData(image, 0, 0);
  }
}
