// Debug overlay (key D): raw hand landmarks and body skeletons, drawn through the same transform
// as the feed, so misalignment is visible at a glance. Rejected hands and bodies are grey.

import { Graphics } from 'pixi.js';

import { HIT_RADIUS } from '../game/balance.js';
import { HAND_BONES } from '../vision/landmarks.js';
import { COLOR, PLAYER_THEME } from '../theme.js';

const REJECTED = 0x8a8a8a;
const JOINT_RADIUS = 3.5;
const BODY_BONES = [['head', 'neck'], ['neck', 'l_shoulder'], ['neck', 'r_shoulder'], ['l_shoulder', 'l_wrist'], ['r_shoulder', 'r_wrist'], ['neck', 'pelvis']];

export class DebugLayer {
  constructor(stage) {
    this.stage = stage;
    this.g = new Graphics();
    stage.layers.debug.addChild(this.g);
    this.visible = false;
    this.hitboxes = false;
  }

  setVisible(isVisible) {
    this.visible = isVisible;
    this.g.visible = isVisible;
  }

  setHitboxes(isVisible) {
    this.hitboxes = isVisible;
  }

  #hand(landmarks, color, alpha) {
    const t = this.stage.transform;
    const pts = landmarks.map((p) => t.camToScreen(p.x, p.y));
    for (const [a, b] of HAND_BONES) this.g.moveTo(pts[a].x, pts[a].y).lineTo(pts[b].x, pts[b].y).stroke({ width: 2, color, alpha });
    for (const p of pts) this.g.circle(p.x, p.y, JOINT_RADIUS).fill({ color: COLOR.parchment, alpha });
  }

  #body(kp, color, alpha) {
    const t = this.stage.transform;
    const at = (name) => kp[name] && t.camToScreen(kp[name].x, kp[name].y);
    for (const [a, b] of BODY_BONES) {
      const [pa, pb] = [at(a), at(b)];
      if (pa && pb) this.g.moveTo(pa.x, pa.y).lineTo(pb.x, pb.y).stroke({ width: 3, color, alpha: alpha * 0.7 });
    }
    for (const name of Object.keys(kp)) {
      const p = at(name);
      if (p) this.g.circle(p.x, p.y, JOINT_RADIUS * 1.6).stroke({ width: 2, color, alpha });
    }
  }

  #hitbox(point, color, alpha = 0.9, radius = HIT_RADIUS) {
    const p = this.stage.transform.viewToScreen(point.x, point.y);
    const r = this.stage.transform.viewLength(radius);
    this.g.circle(p.x, p.y, r).stroke({ width: 2, color, alpha });
    this.g.circle(p.x, p.y, 2.5).fill({ color, alpha });
  }

  #hitboxes(combat) {
    combat.players.forEach((player, slot) => {
      const color = PLAYER_THEME[slot].element;
      this.#hitbox(player.core, color);
      if (player.isWarding && player.wardAt) this.#hitbox(player.wardAt, COLOR.verdantCore, 0.95);
    });
    combat.projectiles.forEach((projectile) => {
      const color = projectile.kind === 'ultimate' ? COLOR.violetCore : PLAYER_THEME[projectile.from].core;
      this.#hitbox(projectile, color, 1);
      const target = combat.players[1 - projectile.from];
      const goal = target.isWarding && target.wardAt ? target.wardAt : target.core;
      const from = this.stage.transform.viewToScreen(projectile.x, projectile.y);
      const to = this.stage.transform.viewToScreen(goal.x, goal.y);
      this.g.moveTo(from.x, from.y).lineTo(to.x, to.y).stroke({ width: 1, color, alpha: 0.35 });
    });
  }

  update({ view, combat }) {
    this.g.clear();
    if (!this.visible) return;
    const t = this.stage.transform;
    const top = t.viewToScreen(0.5, 0);
    const bottom = t.viewToScreen(0.5, 1);
    this.g.moveTo(top.x, top.y).lineTo(bottom.x, bottom.y).stroke({ width: 1, color: COLOR.danger, alpha: 0.6 });
    view.bodies.forEach((body, slot) => body && this.#body(body.kp, PLAYER_THEME[slot].element, 0.9));
    view.rejectedBodies.forEach((body) => this.#body(body.kp, REJECTED, 0.5));
    view.slots.forEach((hands, slot) => hands.forEach((h) => this.#hand(h.landmarks, PLAYER_THEME[slot].element, 0.95)));
    view.rejected.forEach((h) => this.#hand(h.landmarks, REJECTED, 0.6));
    if (this.hitboxes) this.#hitboxes(combat);
  }
}
