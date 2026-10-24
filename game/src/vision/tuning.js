// Every vision threshold in one place. Tuned for a desk-scale setup: players 0.5-1.2 m from the
// camera, upper body only. Values marked [ZED] want re-checking on the real ZED X.

export const SIGN = {
  // Finger straightness: bend at PIP+DIP (radians). <= OPEN reads fully straight, >= CURLED fully bent.
  BEND_OPEN: 0.45,
  BEND_CURLED: 2.3,
  // Chord/arc ratio of MCP->tip over the finger's segment lengths (1 = straight).
  CHORD_CURLED: 0.55,
  CHORD_OPEN: 0.88,
  // Open palm must face the camera: |palm normal . view axis|.
  FACING_MIN: 0.45,
  FACING_FULL: 0.75,
  // Sword sign: index and middle tips together (gap / palm size).
  SWORD_GAP_MAX: 0.5,
  SWORD_GAP_FULL: 0.3,
  // Fist: thumb tip must not stick out past the knuckles (rise above the middle MCP / palm size),
  // which separates a fist from a thumbs-up.
  FIST_THUMB_RISE_MAX: 0.3,
  FIST_THUMB_RISE_FULL: 0.1,
  // Two-hand triangle: tip-to-tip gaps (/ palm size) and diamond height (index tips above thumbs).
  TOUCH_MAX: 0.55,
  TOUCH_FULL: 0.3,
  DIAMOND_MIN_HEIGHT: 0.6,
  // Plausibility gate against garbage detections: palm width / palm length, finger length / palm length.
  PALM_WIDTH_RATIO: [0.4, 0.95],
  FINGER_LENGTH_RATIO: [0.55, 1.5],
  // A frame classifies as a sign only if its score clears this.
  MIN_SCORE: 0.65,
};

export const SMOOTHING = {
  WINDOW: 6, // frames of majority vote
  ENTER_VOTES: 4, // votes a new sign needs to take over
  STAY_VOTES: 2, // votes the current sign needs to hold on (hysteresis)
};

export const HANDS = {
  NUM_HANDS: 4,
  MIN_HANDEDNESS_SCORE: 0.5,
  EDGE_MARGIN: 0.015, // palm points closer than this to the frame edge = partially in frame
  MATCH_RADIUS: 0.12, // view-normalized distance to keep a hand's identity frame to frame
  LOST_MS: 350, // drop a hand track after this long unseen
  SEAM_HYSTERESIS: 0.03, // a tracked hand must cross the seam by this much to change sides
  INFERENCE_HZ: 30, // cap on hand inference rate (independent of render rate)
};

export const DEPTH = {
  PLAY_NEAR_M: 0.2, // [ZED] hands closer than this are ignored (inside the stereo blind zone)
  PLAY_FAR_M: 1.6, // [ZED] bystanders behind the players are ignored
  PATCH: 1, // median over a (2*PATCH+1)^2 patch around each sampled pixel
  // Webcam: depth from apparent palm size. Nominal palm length (wrist -> middle MCP, + MCP span).
  PALM_M: 0.095,
  WEBCAM_FOCAL: 0.9, // focal length as a fraction of image width (typical laptop camera)
  CALIBRATION_DEPTH_M: 0.75, // assumed distance while the open-palm calibration is held
};

export const THRUST = {
  WINDOW_MS: 140, // velocity is measured across this span to reject single-frame noise
  MIN_SPEED: 0.55, // [ZED] m/s toward the camera
  MIN_TRAVEL: 0.07, // [ZED] meters toward the camera within the window
  FULL_SPEED: 1.6, // m/s at which thrust power saturates
};

// Body posture (ZED body tracking, or MediaPipe Pose on the webcam). Offsets are measured from each
// player's own neutral posture, captured while they hold the joining palm.
export const BODY = {
  PLAY_NEAR_M: 0.3,
  PLAY_FAR_M: 1.6, // [ZED] torsos beyond this are bystanders
  EDGE_MARGIN: 0.02, // both shoulders must be this far inside the frame
  SMOOTHING: 0.35, // EMA factor for the torso (per update)
  LEAN_IN_M: 0.12, // [ZED] torso this much closer than neutral = lean in
  LEAN_BACK_M: 0.1, // [ZED] torso this much farther than neutral = lean back
  LEAN_HYSTERESIS_M: 0.04, // must come back this far inside the threshold to release
  STANCE_HOLD_MS: 200, // a lean must be held this long to count
  DRIFT_PER_UPDATE: 0.01, // neutral slowly follows the player while upright
  DODGE_SHIFT: 0.5, // sideways shift (in shoulder widths) that counts as a dodge
  DODGE_WINDOW_MS: 260, // ...and it must happen within this time (slow sway never dodges)
  DODGE_REARM: 0.25, // return within this many shoulder widths before the next dodge
  WRIST_MATCH_RADIUS: 0.14, // normalized distance from a hand to a body wrist to belong to it
  SHOULDER_M: 0.38, // webcam: shoulder width for estimating torso depth
  WEBCAM_FOCAL: 0.9,
};
