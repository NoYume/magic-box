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
  // Fist: thumb tip must not stick out past the knuckles (rise above the middle MCP / palm size),
  // which separates a fist from a thumbs-up (~0.37). [ZED] Real fists with the thumb resting
  // beside the knuckles read ~0.18 (debug log 20261024-235023), so full credit runs up to 0.2.
  FIST_THUMB_RISE_MAX: 0.35,
  FIST_THUMB_RISE_FULL: 0.2,
  // Aim: ring and pinky extension at or below FULL counts as folded, at or above OPEN as not.
  // [ZED] Real two-finger signs leave the ring finger half folded (~0.46, debug log 20261024-235023).
  AIM_FOLD_OPEN: 0.8,
  AIM_FOLD_FULL: 0.4,
  // ...which a loosely relaxed hand also does, so index and middle must be clearly straight
  // (relaxed reads ~0.7, real aims ~0.9).
  AIM_STRAIGHT_MIN: 0.6,
  AIM_STRAIGHT_FULL: 0.9,
  // Two-hand triangle: tip-to-tip gaps (/ palm size) and diamond height (index tips above thumbs).
  TOUCH_MAX: 0.55,
  TOUCH_FULL: 0.3,
  DIAMOND_MIN_HEIGHT: 0.6,
  TRIANGLE_DEPTH_MAX_M: 0.1, // both ultimate hands must be this close in metric depth (touching)
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
  MAX_DEPTH_JUMP_M: 0.25, // a bigger depth change between updates means a different hand
  LOST_MS: 350, // drop a hand track after this long unseen
  SEAM_HYSTERESIS: 0.03, // a tracked hand must cross the seam by this much to change sides
  INFERENCE_HZ: 30, // cap on hand inference rate (independent of render rate)
  // Frames whose shape can't be read (small, blurred or edge-on hands fail the plausibility gate,
  // ~30% of real ZED frames, mostly one at a time) skip the sign vote for this many in a row.
  UNREADABLE_GRACE_FRAMES: 3,
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
  WINDOW_MS: 200, // velocity is measured across this span to reject single-frame noise
  MIN_SPEED: 0.4, // [ZED] m/s toward the camera
  MIN_TRAVEL: 0.05, // [ZED] meters toward the camera within the window
  FULL_SPEED: 1.6, // m/s at which thrust power saturates
};

// Sideways jab toward the opponent (the "finger gun" most players reach for). View widths, over
// THRUST.WINDOW_MS. Needs no depth, so it works the same on the webcam and the ZED.
// [ZED] The ZED X lens is ~110 degrees wide, so a view width is ~2.9 m at 1 m (a webcam's is ~1.2 m):
// these widths were halved for it after the first ZED X debug log (no jab cleared 0.06).
export const JAB = {
  MIN_SPEED: 0.3, // view widths/s toward the opponent's side (~0.9 m/s at 1 m on the ZED X)
  MIN_TRAVEL: 0.035, // view widths toward the opponent within the window (~10 cm at 1 m)
  FULL_SPEED: 1.2, // widths/s at which jab power saturates
};

// Body posture (ZED body tracking, or MediaPipe Pose on the webcam). Offsets are measured from each
// player's own neutral posture, captured while they hold the joining palm.
export const BODY = {
  PLAY_NEAR_M: 0.3,
  PLAY_FAR_M: 1.6, // [ZED] torsos beyond this are bystanders
  EDGE_MARGIN: 0.02, // both shoulders must be this far inside the frame
  SMOOTHING_TAU_MS: 60, // torso EMA time constant, so 15 Hz pose and 30 Hz ZED behave the same
  LEAN_IN_FRAC: 0.09, // torso this fraction closer than neutral depth = lean in (~8 cm at 0.85 m)
  LEAN_BACK_FRAC: 0.08, // torso this fraction farther than neutral = lean back (~7 cm at 0.85 m)
  LEAN_HYSTERESIS_FRAC: 0.03, // must come back this far inside the threshold to release
  STANCE_HOLD_MS: 150, // a lean must be held this long to count
  DRIFT_TAU_MS: 3000, // neutral slowly follows the player while upright
  DODGE_SHIFT: 0.35, // sideways shift (in shoulder widths, unsmoothed) that counts as a dodge
  DODGE_WINDOW_MS: 400, // ...and it must happen within this time (slow sway never dodges)
  DODGE_REARM: 0.2, // return within this many shoulder widths before the next dodge
  WRIST_MATCH_RADIUS: 0.14, // normalized distance from a hand to a body wrist to belong to it
  SHOULDER_M: 0.38, // webcam: shoulder width for estimating torso depth
  WEBCAM_FOCAL: 0.9,
};
