// ZED X source: JPEG frames + depth maps over WebSocket from jetson/tracker.py (docs/protocol.md).
// Hands are found by MediaPipe on the decoded frames; each hand's depth is sampled from the map.

import { ProtocolError, handDepthFromMap, parseBinaryMessage } from '../vision/depth.js';
import { createHandDetector } from '../vision/hands.js';

const RECONNECT_MS = 1000;
const DEFAULT_SIZE = [960, 600];

export async function createZedSource(url, onStatus) {
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = DEFAULT_SIZE;
  const ctx = canvas.getContext('2d');
  const stats = { kind: 'zed', frames: 0, depthMaps: 0, trackerFps: 0, depthSize: null, connected: false };
  let depthMap = null;
  let frameSeq = 0;
  let detectedSeq = 0;
  let isDecoding = false;

  async function onFrame(jpeg) {
    if (isDecoding) return; // drop frames rather than fall behind
    isDecoding = true;
    try {
      const bitmap = await createImageBitmap(new Blob([jpeg], { type: 'image/jpeg' }));
      if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) [canvas.width, canvas.height] = [bitmap.width, bitmap.height];
      ctx.drawImage(bitmap, 0, 0);
      bitmap.close();
      frameSeq += 1;
      stats.frames += 1;
    } catch (err) {
      console.warn('[zed] could not decode frame', err);
    } finally {
      isDecoding = false;
    }
  }

  function onMessage(msg) {
    if (typeof msg.data === 'string') {
      const packet = JSON.parse(msg.data);
      if (packet.type === 'stats') stats.trackerFps = packet.fps;
      return;
    }
    try {
      const parsed = parseBinaryMessage(msg.data);
      if (parsed.type === 'frame') onFrame(parsed.jpeg);
      else {
        depthMap = parsed;
        stats.depthMaps += 1;
        stats.depthSize = `${parsed.width}x${parsed.height}`;
      }
    } catch (err) {
      if (!(err instanceof ProtocolError)) throw err;
      console.warn('[zed] dropped malformed message:', err.message);
    }
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
  const detector = await createHandDetector();
  stats.hands = detector.stats;
  connect();

  function poll(tMs) {
    if (frameSeq === detectedSeq) return null;
    const observations = detector.detect(canvas, canvas.width, canvas.height, tMs);
    if (!observations) return null;
    detectedSeq = frameSeq;
    for (const obs of observations) obs.depth = depthMap ? handDepthFromMap(depthMap, obs.landmarks) : null;
    return observations;
  }

  return { kind: 'zed', canvas, mirror: true, poll, stats, getDepthMap: () => depthMap };
}
