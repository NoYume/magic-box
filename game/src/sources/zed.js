// ZED X source: JPEG frames, depth maps and body skeletons over WebSocket from jetson/tracker.py
// (docs/protocol.md). Abilities come from voice; ZED body tracking remains available for defense.

import { ProtocolError, parseBinaryMessage } from '../vision/depth.js';
import { CaptureSync } from './capture-sync.js';

const RECONNECT_MS = 1000;
const DEFAULT_SIZE = [960, 600];

export async function createZedSource(url, onStatus) {
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = DEFAULT_SIZE;
  const ctx = canvas.getContext('2d');
  const stats = { kind: 'zed', frames: 0, depthMaps: 0, trackerFps: 0, depthSize: null, connected: false };
  const sync = new CaptureSync();
  let frame = { seq: -1, depth: null, bodies: null }; // newest decoded capture
  let bodiesSeq = -1;
  let isDecoding = false;

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
  stats.hands = null;
  connect();

  // Returns a fresh body packet when there is one.
  function poll() {
    let bodies;
    if (frame.seq !== bodiesSeq && frame.bodies) bodies = frame.bodies;
    bodiesSeq = frame.seq;
    return bodies ? { bodies } : null;
  }

  return { kind: 'zed', canvas, mirror: true, poll, stats, getDepthMap: () => frame.depth };
}
