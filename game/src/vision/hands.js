// MediaPipe Tasks Vision HandLandmarker in the browser: 21 landmarks + handedness per hand.
// Runs on whatever the source paints (ZED frames or the webcam), throttled independently of render.

import { HANDS } from './tuning.js';

const MEDIAPIPE_VERSION = '0.10.14';
const MEDIAPIPE_BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}`;
const HAND_MODEL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task';
const FPS_SMOOTHING = 0.1;

export class HandModelError extends Error {}

async function createLandmarker(fileset, HandLandmarker, delegate) {
  return HandLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: HAND_MODEL, delegate },
    runningMode: 'VIDEO',
    numHands: HANDS.NUM_HANDS,
    minHandDetectionConfidence: 0.5,
    minHandPresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });
}

// Returns { detect(image, frameW, frameH, tMs) -> observations | null, stats }.
export async function createHandDetector() {
  let vision;
  try {
    vision = await import(`${MEDIAPIPE_BASE}/vision_bundle.mjs`);
  } catch (err) {
    throw new HandModelError('Could not load MediaPipe from the CDN (offline?)', { cause: err });
  }
  const { FilesetResolver, HandLandmarker } = vision;
  const fileset = await FilesetResolver.forVisionTasks(`${MEDIAPIPE_BASE}/wasm`);
  let delegate = 'GPU';
  let landmarker;
  try {
    landmarker = await createLandmarker(fileset, HandLandmarker, delegate);
  } catch (gpuErr) {
    console.warn('[hands] GPU delegate unavailable, using CPU', gpuErr);
    delegate = 'CPU';
    landmarker = await createLandmarker(fileset, HandLandmarker, delegate);
  }

  const stats = { delegate, fps: 0, inferMs: 0 };
  const minInterval = 1000 / HANDS.INFERENCE_HZ;
  let lastRun = -Infinity;
  let lastTimestamp = 0;

  function detect(image, frameW, frameH, tMs) {
    if (tMs - lastRun < minInterval) return null;
    const timestamp = Math.max(Math.round(tMs), lastTimestamp + 1); // VIDEO mode needs increasing timestamps
    const started = performance.now();
    const result = landmarker.detectForVideo(image, timestamp);
    const elapsed = performance.now() - started;
    if (lastRun > -Infinity) stats.fps += (1000 / Math.max(tMs - lastRun, 1) - stats.fps) * FPS_SMOOTHING;
    stats.inferMs += (elapsed - stats.inferMs) * FPS_SMOOTHING;
    lastRun = tMs;
    lastTimestamp = timestamp;
    return result.landmarks.map((landmarks, i) => ({
      landmarks,
      world: result.worldLandmarks[i],
      handedness: result.handedness[i]?.[0]?.categoryName ?? 'Unknown',
      handScore: result.handedness[i]?.[0]?.score ?? 0,
      frameW,
      frameH,
      depth: null,
    }));
  }

  return { detect, stats };
}
