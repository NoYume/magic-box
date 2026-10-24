// Line illustrations of the body moves, in the same ink style as the hand-sign art: a seated
// figure seen from the camera, with a ghost of the neutral pose to show the motion.

const VIEW = 100;

// A head-and-shoulders figure centered at (cx, cy) with scale s.
function figure(cx, cy, s, cls) {
  const head = `<circle class="${cls}" cx="${cx}" cy="${cy - 22 * s}" r="${9 * s}"/>`;
  const body = `<path class="${cls}" d="M ${cx - 24 * s} ${cy + 26 * s} C ${cx - 24 * s} ${cy - 2 * s}, ${cx - 16 * s} ${cy - 8 * s}, ${cx} ${cy - 8 * s} C ${cx + 16 * s} ${cy - 8 * s}, ${cx + 24 * s} ${cy - 2 * s}, ${cx + 24 * s} ${cy + 26 * s}"/>`;
  return head + body;
}

const ARROW = (x1, y1, x2, y2) => `<path class="art-motion" d="M ${x1} ${y1} L ${x2} ${y2}"/><path class="art-motion" d="M ${x2 - 5} ${y2 - 4} L ${x2} ${y2} L ${x2 - 5} ${y2 + 4}" transform="rotate(${(Math.atan2(y2 - y1, x2 - x1) * 180) / Math.PI} ${x2} ${y2})"/>`;

const ART = {
  // Closer to the camera: the figure grows out of its neutral ghost.
  focus: () => figure(50, 58, 0.8, 'art-ghost') + figure(50, 58, 1.08, 'art-line') + '<circle class="art-thrust" cx="50" cy="56" r="6" style="--i:0"/><circle class="art-thrust" cx="50" cy="56" r="12" style="--i:1"/>',
  // Farther away: the figure shrinks behind a raised crescent.
  brace: () => figure(50, 58, 1.0, 'art-ghost') + figure(50, 60, 0.72, 'art-line') + '<path class="art-guard" d="M 22 30 Q 50 14 78 30"/>',
  // A quick sideways shift, leaving an afterimage.
  dodge: () => figure(40, 58, 0.85, 'art-ghost') + figure(62, 58, 0.85, 'art-line') + ARROW(18, 86, 46, 86),
};

export function bodyArt(move) {
  return `<svg class="sign-art body-art" viewBox="0 0 ${VIEW} ${VIEW}" aria-hidden="true">${ART[move]()}</svg>`;
}
