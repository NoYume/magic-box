// Body sources. Each one paints camera frames into `canvas` and calls onBodies(bodies, tMs)
// with skeletons in the shared schema (docs/protocol.md).

const MEDIAPIPE_VERSION = '0.10.14';
const MEDIAPIPE_BASE = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MEDIAPIPE_VERSION}`;
const POSE_MODEL =
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task';
const SHOULDER_WIDTH_M = 0.38; // average adult, for estimating depth from a 2D webcam
const WEBCAM_FOCAL = 0.9; // focal length as a fraction of image width (typical laptop cam)

export function createZedSource(url, onBodies, onStatus) {
  const canvas = document.createElement('canvas');
  [canvas.width, canvas.height] = [960, 540];
  const ctx = canvas.getContext('2d');
  let isDecoding = false;
  let ws;

  const connect = () => {
    ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => onStatus(`ZED X connected (${url})`);
    ws.onclose = () => {
      onStatus(`ZED X disconnected, retrying… (${url})`);
      setTimeout(connect, 1000);
    };
    ws.onmessage = async (msg) => {
      if (typeof msg.data === 'string') {
        const packet = JSON.parse(msg.data);
        if (packet.type === 'bodies') onBodies(packet.bodies, performance.now());
        return;
      }
      if (isDecoding) return; // drop frames rather than fall behind
      isDecoding = true;
      try {
        const bitmap = await createImageBitmap(new Blob([msg.data], { type: 'image/jpeg' }));
        if (canvas.width !== bitmap.width) [canvas.width, canvas.height] = [bitmap.width, bitmap.height];
        ctx.drawImage(bitmap, 0, 0);
        bitmap.close();
      } finally {
        isDecoding = false;
      }
    };
  };
  connect();
  return { canvas };
}

export async function createWebcamSource(onBodies, onStatus) {
  onStatus('Starting webcam + MediaPipe (fallback mode)…');
  const { FilesetResolver, PoseLandmarker } = await import(`${MEDIAPIPE_BASE}/vision_bundle.mjs`);
  const video = document.createElement('video');
  video.playsInline = true;
  video.muted = true;
  video.srcObject = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } });
  await video.play();

  const fileset = await FilesetResolver.forVisionTasks(`${MEDIAPIPE_BASE}/wasm`);
  const landmarker = await PoseLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: POSE_MODEL, delegate: 'GPU' },
    runningMode: 'VIDEO',
    numPoses: 2,
  });

  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  onStatus('Webcam fallback running (depth is estimated)');

  const tick = () => {
    ctx.drawImage(video, 0, 0);
    const now = performance.now();
    const result = landmarker.detectForVideo(video, now);
    onBodies(result.landmarks.map((lm, i) => toBody(lm, i)), now);
    requestAnimationFrame(tick);
  };
  tick();
  return { canvas };
}

// MediaPipe landmark indices -> our keypoints. Depth is estimated from shoulder width.
function toBody(lm, index) {
  const mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: (a.z + b.z) / 2 });
  const shoulderWidth = Math.hypot(lm[11].x - lm[12].x, lm[11].y - lm[12].y);
  const bodyZ = (SHOULDER_WIDTH_M * WEBCAM_FOCAL) / Math.max(shoulderWidth, 0.02);
  // MediaPipe z is relative to the hips, roughly in units of image width.
  const point = (p) => (p.visibility !== undefined && p.visibility < 0.5 ? null : { x: p.x, y: p.y, z: bodyZ + p.z * bodyZ });
  return {
    id: `w${index}`,
    kp: {
      head: point(lm[0]),
      neck: point(mid(lm[11], lm[12])),
      l_shoulder: point(lm[11]),
      r_shoulder: point(lm[12]),
      l_wrist: point(lm[15]),
      r_wrist: point(lm[16]),
      pelvis: point(mid(lm[23], lm[24])),
    },
  };
}
