// Laptop webcam source (dev / fallback). MediaPipe Pose supplies body movement for defense;
// abilities come from voice, so the expensive hand-landmark model is not loaded.

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
  const pose = await createPoseDetector();
  onStatus(null);

  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  const stats = { kind: 'webcam', hands: null };
  let lastVideoTime = -1;

  // Returns { observations?, bodies? } or null when there is nothing new.
  function poll(tMs) {
    if (video.currentTime === lastVideoTime) return null;
    lastVideoTime = video.currentTime;
    ctx.drawImage(video, 0, 0);
    const bodies = pose.detect(video, tMs);
    return bodies ? { bodies } : null;
  }

  return { kind: 'webcam', canvas, mirror: true, poll, stats, getDepthMap: () => null };
}
