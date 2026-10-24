// Laptop webcam source (dev / fallback). Hands from MediaPipe HandLandmarker, bodies from
// MediaPipe Pose. No depth stream: hand depth is estimated from apparent palm size by the
// roster, torso depth from shoulder width, both relative to each player's calibration.

import { createHandDetector } from '../vision/hands.js';
import { createPoseDetector } from '../vision/pose.js';

const VIDEO_CONSTRAINTS = { video: { width: { ideal: 1280 }, height: { ideal: 720 } } };

export class CameraAccessError extends Error {}

export async function createWebcamSource(onStatus) {
  onStatus('Waking the camera.');
  const video = document.createElement('video');
  video.playsInline = true;
  video.muted = true;
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia(VIDEO_CONSTRAINTS);
  } catch (err) {
    throw new CameraAccessError('Camera permission was denied or no camera is connected', { cause: err });
  }
  await video.play();
  const [hands, pose] = await Promise.all([createHandDetector(), createPoseDetector()]);
  onStatus(null);

  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  const stats = { kind: 'webcam', hands: hands.stats };
  let lastVideoTime = -1;

  // Returns { observations?, bodies? } or null when there is nothing new.
  function poll(tMs) {
    if (video.currentTime === lastVideoTime) return null;
    lastVideoTime = video.currentTime;
    ctx.drawImage(video, 0, 0);
    const observations = hands.detect(video, canvas.width, canvas.height, tMs);
    const bodies = pose.detect(video, tMs);
    if (!observations && !bodies) return null;
    return { observations: observations ?? undefined, bodies: bodies ?? undefined };
  }

  return { kind: 'webcam', canvas, mirror: true, poll, stats, getDepthMap: () => null };
}
