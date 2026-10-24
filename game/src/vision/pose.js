// Webcam fallback for body tracking: MediaPipe PoseLandmarker -> the tracker's body schema
// (docs/protocol.md). Torso depth is estimated from shoulder width; posture only uses changes
// relative to each player's calibrated neutral, so the absolute error does not matter.

import { loadVision } from './mediapipe.js';
import { BODY } from './tuning.js';

const POSE_MODEL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task';
const POSE_HZ = 15; // posture changes slowly; leaves the GPU to the hand model
const MIN_VISIBILITY = 0.5;
const LM = { nose: 0, lShoulder: 11, rShoulder: 12, lWrist: 15, rWrist: 16, lHip: 23, rHip: 24 };

function toBody(lm) {
  const shoulderWidth = Math.abs(lm[LM.lShoulder].x - lm[LM.rShoulder].x);
  const z = (BODY.SHOULDER_M * BODY.WEBCAM_FOCAL) / Math.max(shoulderWidth, 0.02);
  const point = (p) => (p.visibility !== undefined && p.visibility < MIN_VISIBILITY ? null : { x: p.x, y: p.y, z });
  const mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, visibility: Math.min(a.visibility ?? 1, b.visibility ?? 1) });
  return {
    // MediaPipe pose order is not stable between frames; the side of the frame is.
    id: (lm[LM.lShoulder].x + lm[LM.rShoulder].x) / 2 < 0.5 ? 'pose-camera-left' : 'pose-camera-right',
    kp: {
      head: point(lm[LM.nose]),
      neck: point(mid(lm[LM.lShoulder], lm[LM.rShoulder])),
      l_shoulder: point(lm[LM.lShoulder]),
      r_shoulder: point(lm[LM.rShoulder]),
      l_wrist: point(lm[LM.lWrist]),
      r_wrist: point(lm[LM.rWrist]),
      pelvis: point(mid(lm[LM.lHip], lm[LM.rHip])),
    },
  };
}

// Returns { detect(image, tMs) -> bodies | null }.
export async function createPoseDetector() {
  const { vision, fileset } = await loadVision();
  const landmarker = await vision.PoseLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: POSE_MODEL, delegate: 'GPU' },
    runningMode: 'VIDEO',
    numPoses: 2,
  });
  let lastRun = -Infinity;
  let lastTimestamp = 0;
  return {
    detect(image, tMs) {
      if (tMs - lastRun < 1000 / POSE_HZ) return null;
      lastRun = tMs;
      lastTimestamp = Math.max(Math.round(tMs), lastTimestamp + 1);
      return landmarker.detectForVideo(image, lastTimestamp).landmarks.map(toBody);
    },
  };
}
