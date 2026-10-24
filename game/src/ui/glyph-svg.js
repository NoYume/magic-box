// SVG versions of the rune glyphs (same geometry as render/textures.js) for the DOM HUD.

const STROKE = 'fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"';

function rays() {
  const out = [];
  for (let i = 0; i < 5; i++) {
    const a = -Math.PI / 2 + (i - 2) * 0.42;
    const [x1, y1, x2, y2] = [64 + Math.cos(a) * 16, 64 + Math.sin(a) * 16, 64 + Math.cos(a) * 50, 64 + Math.sin(a) * 50];
    out.push(`<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`);
  }
  return out.join('');
}

function arcPath(cx, cy, r, a0, a1) {
  const [x0, y0, x1, y1] = [cx + r * Math.cos(a0), cy + r * Math.sin(a0), cx + r * Math.cos(a1), cy + r * Math.sin(a1)];
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${x0.toFixed(1)} ${y0.toFixed(1)} A${r} ${r} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
}

const BODIES = {
  ward: `<g ${STROKE} stroke-width="7"><path d="${arcPath(64, 64, 30, 0.35, Math.PI - 0.35)}"/>${rays()}</g>`,
  gather: `<g ${STROKE}><circle cx="64" cy="64" r="44" stroke-width="4" opacity="0.7"/>${[0, 1, 2]
    .map((i) => `<path stroke-width="7" d="${arcPath(64, 64, 30, (i * Math.PI * 2) / 3, (i * Math.PI * 2) / 3 + 1.4)}"/>`)
    .join('')}</g><circle cx="64" cy="64" r="10" fill="currentColor"/>`,
  aim: `<g ${STROKE} stroke-width="7"><line x1="64" y1="16" x2="64" y2="96"/><polyline points="50,28 64,12 78,28"/><line x1="42" y1="80" x2="86" y2="80"/></g><circle cx="64" cy="108" r="7" fill="currentColor"/>`,
  ultimate: `<polygon points="64,16 108,64 64,112 20,64" ${STROKE} stroke-width="7"/><polygon points="64,42 86,64 64,86 42,64" fill="currentColor" opacity="0.85"/>`,
};

export function glyphSvg(name, className = 'glyph') {
  return `<svg class="${className}" viewBox="0 0 128 128" aria-hidden="true">${BODIES[name]}</svg>`;
}
