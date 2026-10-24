// Design tokens: the one palette and type scale for both the Pixi layer and the DOM UI.
// Brass, midnight ink and vellum. Element colors remain distinct in combat.

const hex = (n) => `#${n.toString(16).padStart(6, '0')}`;

export const COLOR = {
  ink: 0x191b24, // panel ground
  inkDeep: 0x101219,
  inkRaised: 0x2a2d38,
  gold: 0xc5a466, // engraved brass
  goldBright: 0xead5a1,
  goldDim: 0x786441,
  parchment: 0xe9dfc9, // vellum
  parchmentDim: 0xaaa596,
  ember: 0xff6238, // player 01 - punchy solar flame
  emberCore: 0xffeedd,
  frost: 0x00d9d2, // player 02 - vivid arctic cyan
  frostCore: 0xe0ffff,
  verdant: 0x10e885, // wards and mana - luminous emerald
  verdantCore: 0xe3ffe9,
  violet: 0xb57cff, // ultimate - radiant arcane violet
  violetCore: 0xf3e8ff,
  danger: 0xff3b3b,
};

export const PLAYER_THEME = [
  { name: 'Player 01', house: 'Ember', numeral: '01', element: COLOR.ember, core: COLOR.emberCore },
  { name: 'Player 02', house: 'Frost', numeral: '02', element: COLOR.frost, core: COLOR.frostCore },
];

export const FONT = {
  display: "'Barlow Condensed', Impact, sans-serif",
  arcane: "'Cormorant Garamond', Georgia, serif",
  story: "'Barlow', sans-serif",
  ui: "'IBM Plex Mono', monospace",
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
  PLAYER_THEME.forEach((p, i) => {
    root.style.setProperty(`--p${i}`, hex(p.element));
    root.style.setProperty(`--p${i}-core`, hex(p.core));
  });
}

export const cssColor = hex;
