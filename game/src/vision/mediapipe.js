// Loads MediaPipe Tasks Vision once (pinned CDN version) for the hand and pose detectors.

const MEDIAPIPE_VERSION = '0.10.14';
const MEDIAPIPE_BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}`;

export class VisionLoadError extends Error {}

let loading = null;

export function loadVision() {
  loading ??= (async () => {
    let vision;
    try {
      vision = await import(`${MEDIAPIPE_BASE}/vision_bundle.mjs`);
    } catch (err) {
      throw new VisionLoadError('Could not load MediaPipe from the CDN (offline?)', { cause: err });
    }
    const fileset = await vision.FilesetResolver.forVisionTasks(`${MEDIAPIPE_BASE}/wasm`);
    return { vision, fileset };
  })();
  return loading;
}
