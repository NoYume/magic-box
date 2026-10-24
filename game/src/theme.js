// Design tokens: the one palette and type scale for both the Pixi layer and the DOM UI.
// Cabinet / 01: charcoal, warm paper and signal orange. Shared by DOM and Pixi.

const hex = (n) => `#${n.toString(16).padStart(6, '0')}`;

export const COLOR = {
  ink: 0x181917, // panel ground
  inkDeep: 0x0e100f,
  inkRaised: 0x292c27,
  gold: 0xff6434, // signal / call to action (legacy token name)
  goldBright: 0xff946f,
  goldDim: 0x9b6652,
  parchment: 0xf0eee6, // warm paper
  parchmentDim: 0xa6aaa0,
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
