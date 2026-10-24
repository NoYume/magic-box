// Design tokens: the one palette and type scale for both the Pixi layer and the DOM UI.
// "Arcane storybook": ink-indigo panels, gold leaf, parchment text, element-coded magic.

const hex = (n) => `#${n.toString(16).padStart(6, '0')}`;

export const COLOR = {
  ink: 0x0d0b1f, // panel ground
  inkDeep: 0x07061a,
  inkRaised: 0x1a1640,
  gold: 0xd9b46a, // gold leaf: rules, frames, emphasis
  goldBright: 0xf4dca0,
  goldDim: 0x8a6f3c,
  parchment: 0xf3e7cc, // primary text
  parchmentDim: 0xb9ab8e,
  ember: 0xff8a3d, // player I's element
  emberCore: 0xffe2b8,
  frost: 0x6fe3ff, // player II's element
  frostCore: 0xe6fbff,
  verdant: 0x7dee9a, // wards and mana
  verdantCore: 0xe3ffe9,
  violet: 0xb07cff, // ultimate
  violetCore: 0xf1e6ff,
  danger: 0xff5a5a,
};

export const PLAYER_THEME = [
  { name: 'Player I', house: 'House of Ember', numeral: 'I', element: COLOR.ember, core: COLOR.emberCore },
  { name: 'Player II', house: 'House of Frost', numeral: 'II', element: COLOR.frost, core: COLOR.frostCore },
];

export const FONT = {
  display: "'Cinzel', 'Cormorant Garamond', serif",
  story: "'Cormorant Garamond', 'Cinzel', serif",
  ui: "'Inter', system-ui, sans-serif",
};

export const MOTION = {
  easeOut: 'cubic-bezier(0.16, 1, 0.3, 1)',
  easeInOut: 'cubic-bezier(0.65, 0, 0.35, 1)',
  fast: '180ms',
  base: '420ms',
  slow: '900ms',
};

// Publishes the tokens as CSS custom properties so the stylesheet never hard-codes a color.
export function applyThemeToDocument(root = document.documentElement) {
  for (const [name, value] of Object.entries(COLOR)) root.style.setProperty(`--${name}`, hex(value));
  for (const [name, value] of Object.entries(FONT)) root.style.setProperty(`--font-${name}`, value);
  for (const [name, value] of Object.entries(MOTION)) root.style.setProperty(`--${name}`, value);
  PLAYER_THEME.forEach((p, i) => root.style.setProperty(`--p${i}`, hex(p.element)));
}

export const cssColor = hex;
