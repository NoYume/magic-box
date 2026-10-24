// Hand depth (meters from the camera).
//   ZED:    sample the streamed depth map at palm landmarks (median of a small patch, 0 = invalid)
//   webcam: estimate from apparent palm size, scaled by a per-player calibration

import { PALM_POINTS, MIDDLE, WRIST } from './landmarks.js';
import { DEPTH } from './tuning.js';
import { dist } from './vec.js';

export const MSG_FRAME = 0x01;
export const MSG_DEPTH = 0x02;
const DEPTH_HEADER_BYTES = 6; // type, reserved, u16 width, u16 height (little endian)
const MM_PER_M = 1000;

export class ProtocolError extends Error {}

// Splits a typed binary tracker message (docs/protocol.md).
export function parseBinaryMessage(buffer) {
  const bytes = new Uint8Array(buffer);
  if (bytes.length < 1) throw new ProtocolError('Empty binary message');
  const type = bytes[0];
  if (type === MSG_FRAME) return { type: 'frame', jpeg: bytes.subarray(1) };
  if (type !== MSG_DEPTH) throw new ProtocolError(`Unknown binary message type 0x${type.toString(16)}`);
  if (bytes.length < DEPTH_HEADER_BYTES) throw new ProtocolError('Truncated depth header');
  const view = new DataView(buffer, 0, DEPTH_HEADER_BYTES);
  const width = view.getUint16(2, true);
  const height = view.getUint16(4, true);
  const expected = DEPTH_HEADER_BYTES + width * height * 2;
  if (bytes.length !== expected) throw new ProtocolError(`Depth map is ${bytes.length} bytes, expected ${expected} for ${width}x${height}`);
  const data = new Uint16Array(width * height);
  const src = new DataView(buffer, DEPTH_HEADER_BYTES);
  for (let i = 0; i < data.length; i++) data[i] = src.getUint16(i * 2, true);
  return { type: 'depth', width, height, data };
}

// Builds the wire form of a depth map (used by tests and the scripted demo).
export function encodeDepthMessage(width, height, data) {
  const buffer = new ArrayBuffer(DEPTH_HEADER_BYTES + width * height * 2);
  const view = new DataView(buffer);
  view.setUint8(0, MSG_DEPTH);
  view.setUint16(2, width, true);
  view.setUint16(4, height, true);
  data.forEach((mm, i) => view.setUint16(DEPTH_HEADER_BYTES + i * 2, mm, true));
  return buffer;
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const m = sorted.length >> 1;
  return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2;
}

// Median depth (meters) of the valid pixels in a patch around normalized camera coords (u, v),
// or null when the patch has no valid depth.
export function sampleDepth(map, u, v, patch = DEPTH.PATCH) {
  const cx = Math.floor(u * map.width);
  const cy = Math.floor(v * map.height);
  const values = [];
  for (let y = cy - patch; y <= cy + patch; y++) {
    if (y < 0 || y >= map.height) continue;
    for (let x = cx - patch; x <= cx + patch; x++) {
      if (x < 0 || x >= map.width) continue;
      const mm = map.data[y * map.width + x];
      if (mm > 0) values.push(mm);
    }
  }
  return values.length ? median(values) / MM_PER_M : null;
}

// Hand depth from the map: median over the palm landmarks (normalized camera coords).
export function handDepthFromMap(map, landmarks) {
  const samples = PALM_POINTS.map((i) => sampleDepth(map, landmarks[i].x, landmarks[i].y)).filter((d) => d !== null);
  return samples.length ? median(samples) : null;
}

// Uncalibrated depth from apparent palm length in isotropic image pixels (pinhole model).
export function depthFromPalmSize(image3d, frameW) {
  const apparent = dist(image3d[WRIST], image3d[MIDDLE[0]]);
  if (!(apparent > 0)) return null;
  return (DEPTH.WEBCAM_FOCAL * frameW * DEPTH.PALM_M) / apparent;
}

// Per-player scale learned while the player holds an open palm at a comfortable distance.
export const calibrationScale = (rawDepth) => (rawDepth > 0 ? DEPTH.CALIBRATION_DEPTH_M / rawDepth : 1);

export const isInPlayRange = (depth) => depth !== null && depth >= DEPTH.PLAY_NEAR_M && depth <= DEPTH.PLAY_FAR_M;
