// Debug telemetry for tuning detections on the real rig (?log=1 or key L; B marks a moment).
//
// After each hand inference the game sends the tracker what its vision pipeline saw for that camera
// capture: hand landmarks, per-sign scores and the finger features behind them, depth, rejections,
// body slots and posture. jetson/debug_log.py writes it next to the raw frames of the same capture
// (matched by seq), so a bad detection can be replayed and drawn later. A mark asks the tracker to
// keep every frame of the last few seconds.

const round = (n, digits = 3) => (typeof n === 'number' && Number.isFinite(n) ? Number(n.toFixed(digits)) : null);
const roundValues = (obj, digits) => (obj ? Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, round(v, digits)])) : null);
const points = (landmarks) => landmarks.map((p) => [round(p.x), round(p.y)]);

function hand(h, slot, caster) {
  return {
    id: h.id,
    slot,
    handedness: h.handedness,
    conf: round(h.handScore, 2),
    sign: h.sign,
    frameSign: h.frameSign,
    frameScore: round(h.frameScore, 2),
    vote: round(h.agreement, 2),
    scores: roundValues(h.scores, 2),
    ext: roundValues(h.features?.ext, 2),
    facing: round(h.features?.facing, 2),
    thumbRise: round(h.features?.thumbRise, 2),
    depth: round(h.depth),
    depthSource: h.depthSource ?? null,
    bodySlot: h.bodySlot ?? null,
    phase: caster?.handStates.get(h.id)?.phase ?? null,
    unreadable: h.unreadable ?? 0, // consecutive frames that failed the plausibility gate
    lm: points(h.landmarks),
  };
}

function body(b, posture) {
  if (!b) return null;
  return { id: b.id, z: round(b.torso.z), stance: posture?.stance ?? null, lean: round(posture?.leanOffset), side: round(posture?.lateral, 2) };
}

// One capture's worth of vision state, small enough to send at the hand inference rate.
export function buildRecord({ seq, tMs, view, flow, stats, mirror = false }) {
  return {
    type: 'debug',
    seq,
    mirror,
    t: Math.round(tMs),
    phase: flow.phase,
    stats: roundValues(stats, 1),
    hands: view.slots.flatMap((hands, slot) => hands.map((h) => hand(h, slot, view.casters[slot]))),
    rejected: view.rejected.map((h) => ({ reason: h.reason, handedness: h.handedness, conf: round(h.handScore, 2), depth: round(h.depth), lm: points(h.landmarks) })),
    triangles: view.triangles.map((t) => round(t.score, 2)),
    bodies: view.bodies.map((b, slot) => body(b, view.postures[slot])),
    rejectedBodies: view.rejectedBodies.map((b) => b.id),
  };
}

const BADGE_STYLE =
  'position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:50;padding:2px 10px;border-radius:4px;' +
  'font:600 12px "IBM Plex Mono",monospace;color:#fff;background:#b3261e;pointer-events:none';
const MARK_FLASH_MS = 1200;

// send(message) -> boolean (false while disconnected); undefined when the source has no tracker.
export class Telemetry {
  constructor(send, { enabled = false } = {}) {
    this.send = send;
    this.enabled = Boolean(send) && enabled;
    this.sent = 0;
    this.marks = 0;
    this.badge = null;
    this.flashUntil = 0;
    this.#render();
  }

  get available() {
    return Boolean(this.send);
  }

  toggle() {
    if (!this.send) return;
    this.enabled = !this.enabled;
    this.#render();
  }

  record(args) {
    if (this.enabled && this.send(buildRecord(args))) this.sent += 1;
  }

  mark(seq, tMs) {
    if (!this.send) return;
    this.send({ type: 'mark', seq, t: Math.round(tMs) });
    this.marks += 1;
    this.flashUntil = tMs + MARK_FLASH_MS;
    this.#render(`MARK ${this.marks}`);
    setTimeout(() => this.#render(), MARK_FLASH_MS);
  }

  #render(text) {
    if (typeof document === 'undefined') return;
    if (!this.badge) {
      this.badge = document.createElement('div');
      this.badge.style.cssText = BADGE_STYLE;
      document.body.append(this.badge);
    }
    this.badge.hidden = !text && !this.enabled;
    this.badge.textContent = text ?? '● LOG  [L] off  [B] mark';
  }
}
