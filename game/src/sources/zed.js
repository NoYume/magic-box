// ZED X source: JPEG frames, depth maps and body skeletons over WebSocket from jetson/tracker.py
// (docs/protocol.md). The ZED tracks bodies; MediaPipe finds hands (fingers) on the decoded frames
// and each hand's depth is sampled from the depth map of the same capture (CaptureSync).

import { ProtocolError, handDepthFromMap, parseBinaryMessage } from '../vision/depth.js';
import { createHandDetector } from '../vision/hands.js';
import { DEPTH_SOURCE } from '../vision/roster.js';
import { CaptureSync } from './capture-sync.js';

const RECONNECT_MS = 1000;
const DEFAULT_SIZE = [960, 600];

// Unmirrored by default: two players side by side each see the opponent across from them (the
// left player looks at the right player). mirror: true shows the room like a mirror instead.
export async function createZedSource(url, onStatus, { mirror = false } = {}) {
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = DEFAULT_SIZE;
  const ctx = canvas.getContext('2d');
  const stats = { kind: 'zed', frames: 0, depthMaps: 0, trackerFps: 0, depthSize: null, connected: false };
  const sync = new CaptureSync();
  let frame = { seq: -1, depth: null, bodies: null }; // newest decoded capture
  let detectedSeq = -1;
  let bodiesSeq = -1;
  let isDecoding = false;
  let socket = null;

  async function onFrame({ seq, jpeg }) {
    if (isDecoding) return; // drop frames rather than fall behind (its depth and bodies go too)
    isDecoding = true;
    try {
      const bitmap = await createImageBitmap(new Blob([jpeg], { type: 'image/jpeg' }));
      if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) [canvas.width, canvas.height] = [bitmap.width, bitmap.height];
      ctx.drawImage(bitmap, 0, 0);
      bitmap.close();
      frame = { seq, ...sync.takeFrame(seq) };
      stats.frames += 1;
    } catch (err) {
      console.warn('[zed] could not decode frame', err);
    } finally {
      isDecoding = false;
    }
  }

  function onText(text) {
    const packet = JSON.parse(text);
    if (packet.type === 'stats') stats.trackerFps = packet.fps;
    if (packet.type === 'bodies') sync.addBodies(packet.seq, packet.bodies);
  }

  function onMessage(msg) {
    if (typeof msg.data === 'string') return onText(msg.data);
    try {
      const parsed = parseBinaryMessage(msg.data);
      if (parsed.type === 'frame') return onFrame(parsed);
      sync.addDepth(parsed.seq, parsed);
      stats.depthMaps += 1;
      stats.depthSize = `${parsed.width}x${parsed.height}`;
    } catch (err) {
      if (!(err instanceof ProtocolError)) throw err;
      console.warn('[zed] dropped malformed message:', err.message);
    }
    return undefined;
  }

  const connect = () => {
    const ws = new WebSocket(url);
    socket = ws;
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => {
      stats.connected = true;
      onStatus(null);
    };
    ws.onclose = () => {
      stats.connected = false;
      onStatus('Camera link lost. Reconnecting.');
      setTimeout(connect, RECONNECT_MS);
    };
    ws.onmessage = onMessage;
  };

  onStatus('Connecting to the camera.');
  const detector = await createHandDetector();
  stats.hands = detector.stats;
  connect();

  // Hands on the newest decoded frame, each with depth from that same capture's map. A missing
  // sample stays null: the roster treats it as a stereo dropout, never as a palm-size estimate.
  function detectHands(tMs) {
    if (frame.seq === detectedSeq) return undefined;
    const observations = detector.detect(canvas, canvas.width, canvas.height, tMs);
    if (!observations) return undefined;
    detectedSeq = frame.seq;
    for (const obs of observations) {
      obs.depth = frame.depth ? handDepthFromMap(frame.depth, obs.landmarks) : null;
      obs.depthSource = DEPTH_SOURCE.STEREO;
    }
    return observations;
  }

  // Debug telemetry back to the tracker (game/src/debug/telemetry.js). False while disconnected.
  function send(message) {
    if (socket?.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(message));
    return true;
  }

  // Returns { observations?, bodies?, seq } or null when there is nothing new. seq is the capture
  // the hands and bodies came from.
  function poll(tMs) {
    let bodies;
    if (frame.seq !== bodiesSeq && frame.bodies) bodies = frame.bodies;
    bodiesSeq = frame.seq;
    const observations = detectHands(tMs);
    return observations || bodies ? { observations, bodies, seq: frame.seq } : null;
  }

  return { kind: 'zed', canvas, mirror, poll, send, stats, getDepthMap: () => frame.depth };
}
