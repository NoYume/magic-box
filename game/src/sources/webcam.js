// Laptop webcam source (dev / fallback). No depth stream: hand depth is estimated from apparent
// palm size by the roster, scaled by each player's calibration.

import { createHandDetector } from '../vision/hands.js';

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
  const detector = await createHandDetector();
  onStatus(null);

  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  const stats = { kind: 'webcam', hands: detector.stats };
  let lastVideoTime = -1;

  function poll(tMs) {
    if (video.currentTime === lastVideoTime) return null;
    ctx.drawImage(video, 0, 0);
    const observations = detector.detect(video, canvas.width, canvas.height, tMs);
    if (observations) lastVideoTime = video.currentTime;
    return observations;
  }

  return { kind: 'webcam', canvas, mirror: true, poll, stats, getDepthMap: () => null };
}
