// Tiny 3D vector helpers over plain { x, y, z } objects.

export const vec = (x = 0, y = 0, z = 0) => ({ x, y, z });
export const add = (a, b) => vec(a.x + b.x, a.y + b.y, a.z + b.z);
export const sub = (a, b) => vec(a.x - b.x, a.y - b.y, a.z - b.z);
export const scale = (a, s) => vec(a.x * s, a.y * s, a.z * s);
export const dot = (a, b) => a.x * b.x + a.y * b.y + a.z * b.z;
export const cross = (a, b) => vec(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
export const length = (a) => Math.hypot(a.x, a.y, a.z);
export const dist = (a, b) => length(sub(a, b));
export const mid = (a, b) => scale(add(a, b), 0.5);

export function normalize(a) {
  const len = length(a);
  return len > 0 ? scale(a, 1 / len) : vec();
}

// Angle in radians between two direction vectors (0 = same direction).
export function angleBetween(a, b) {
  const denom = length(a) * length(b);
  if (denom === 0) return 0;
  return Math.acos(Math.min(1, Math.max(-1, dot(a, b) / denom)));
}

// Rotation by Euler angles (radians): roll about z, then pitch about x, then yaw about y.
export function rotate(p, { yaw = 0, pitch = 0, roll = 0 }) {
  const [cr, sr] = [Math.cos(roll), Math.sin(roll)];
  const r1 = vec(p.x * cr - p.y * sr, p.x * sr + p.y * cr, p.z);
  const [cp, sp] = [Math.cos(pitch), Math.sin(pitch)];
  const r2 = vec(r1.x, r1.y * cp - r1.z * sp, r1.y * sp + r1.z * cp);
  const [cy, sy] = [Math.cos(yaw), Math.sin(yaw)];
  return vec(r2.x * cy + r2.z * sy, r2.y, -r2.x * sy + r2.z * cy);
}

export const smoothstep = (edge0, edge1, x) => {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
};
