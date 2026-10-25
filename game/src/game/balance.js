// Gameplay numbers. Tuned so a round between two engaged players lasts roughly 45-75 s.

export const PLAYER = {
  MAX_HP: 100,
  HP_SEGMENTS: 10, // HUD crystals
  MAX_MANA: 100,
};

export const CONFIRM_MS = {
  ward: 250, // fast enough to answer an incoming bolt
  gather: 300,
  aim: 350,
  ultimate: 1000,
};

export const GATHER = {
  RATE_PER_S: 1, // full charge after one second of holding a fist
  HOLD_MS: 3000, // charge is kept this long after the fist opens (time to form the next sign)
  DECAY_PER_S: 0.5,
};

export const BOLT = {
  BASE_DAMAGE: 8,
  CHARGE_DAMAGE: 14, // added at full charge
  THRUST_DAMAGE: 3, // added at full thrust speed
  EMPOWERED_AT: 0.5, // charge needed for an empowered bolt
  SPEED: 0.85, // view widths per second
  EMPOWERED_SPEED: 0.7,
  COOLDOWN_MS: 1400,
  ARM_GRACE_MS: 300, // the aim sign may blur during the thrust itself
};

export const WARD = {
  DRAIN_PER_S: 8, // mana per second while held
  MANA_PER_DAMAGE: 2.5, // mana spent per point of damage absorbed
  REGEN_PER_S: 14,
  REGEN_DELAY_MS: 600,
  BROKEN_MS: 2500, // after a shatter
  MIN_MANA_TO_RAISE: 10,
};

export const ULTIMATE = {
  DAMAGE: 30,
  WARD_PASS_THROUGH: 0.5, // half of it ignores wards
  SPEED: 0.6,
  COOLDOWN_MS: 20000,
};

export const ROUND = {
  WINS_NEEDED: 2, // best of three
  TIME_LIMIT_S: 90,
  COUNTDOWN_MS: 3000,
  FIGHT_BANNER_MS: 700,
  KO_SLOWMO_MS: 1400,
  KO_TIME_SCALE: 0.25,
  ROUND_END_MS: 2800,
  RESULTS_MS: 10000,
  TUTORIAL_HOLD_MS: 650, // each of the four hand signs must be held this long in onboarding
  JOIN_DECAY: 2, // tutorial progress lost per second when the requested sign drops
  REMATCH_HOLD_MS: 1000,
  IDLE_RESET_MS: 15000, // nobody in frame -> back to the attract screen
  HIT_STOP_MS: 70,
  HEAVY_HIT_STOP_MS: 110,
};

// Rest positions (view space) used when a player has no hands in frame.
export const SEATS = [{ x: 0.25, y: 0.55 }, { x: 0.75, y: 0.55 }];
export const HIT_RADIUS = 0.04; // view units: a projectile within this of its target lands

// Body moves modify and defend; they never deal damage on their own.
export const BODY_MOVES = {
  FOCUS_GATHER_MULT: 2, // lean in: gather charges twice as fast
  BRACE_REDUCTION: 0.4, // lean back: 40% less damage from anything that gets through
  EVADE_MS: 450, // dodge: bolts landing within this window miss (ultimates can't be dodged)
  DODGE_COOLDOWN_MS: 2500,
};
