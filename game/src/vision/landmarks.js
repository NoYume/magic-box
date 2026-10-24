// MediaPipe hand landmark indices (21 points).

export const WRIST = 0;
export const THUMB = [1, 2, 3, 4]; // CMC, MCP, IP, TIP
export const INDEX = [5, 6, 7, 8]; // MCP, PIP, DIP, TIP
export const MIDDLE = [9, 10, 11, 12];
export const RING = [13, 14, 15, 16];
export const PINKY = [17, 18, 19, 20];
export const FINGERS = { index: INDEX, middle: MIDDLE, ring: RING, pinky: PINKY };
export const PALM_POINTS = [WRIST, INDEX[0], MIDDLE[0], RING[0], PINKY[0]];
export const LANDMARK_COUNT = 21;

// Line segments for drawing a hand (debug view and spellbook illustrations).
export const HAND_BONES = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [0, 17], [17, 18], [18, 19], [19, 20],
];
