// Generates upper-body skeletons in the tracker schema (docs/protocol.md) for tests and the demo.

const SHOULDER_M = 0.38;
const HEAD_ABOVE_NECK_M = 0.17;
const DEFAULT_FOCAL = 0.45; // ZED X-like wide lens, as a fraction of image width

// cx: torso center (camera x, normalized), neckY: normalized, z: meters. wrists: { l, r } camera
// points ({ x, y, z }) or null when the hands are out of view.
export function makeBody({ id = 1, cx, neckY = 0.42, z, frameW = 960, frameH = 600, focal = DEFAULT_FOCAL, wrists = {} }) {
  const pxPerM = (focal * frameW) / z;
  const halfShoulder = (SHOULDER_M / 2) * pxPerM / frameW;
  const shoulderY = neckY + (0.03 * pxPerM) / frameH;
  const point = (x, y, depth = z) => ({ x, y, z: depth });
  return {
    id,
    kp: {
      head: point(cx, neckY - (HEAD_ABOVE_NECK_M * pxPerM) / frameH),
      neck: point(cx, neckY),
      l_shoulder: point(cx + halfShoulder, shoulderY), // the person's left is on the camera's right
      r_shoulder: point(cx - halfShoulder, shoulderY),
      l_wrist: wrists.l ?? null,
      r_wrist: wrists.r ?? null,
      pelvis: null, // below the desk edge at this distance
    },
  };
}
