// Keeps a camera capture together. The tracker tags each frame, depth map and bodies message
// with the grab's sequence number; JPEG decoding is async, so by the time frame N is decoded the
// depth map of N+1 may already have arrived. Hands found on frame N are sampled against depth N
// and paired with bodies N, and everything older than the newest decoded frame is dropped.

const DEFAULT_MAX_PENDING = 8;

export class CaptureSync {
  constructor({ maxPending = DEFAULT_MAX_PENDING } = {}) {
    this.maxPending = maxPending;
    this.pending = new Map(); // seq -> { depth, bodies }
    this.lastTaken = -1;
  }

  get pendingCount() {
    return this.pending.size;
  }

  addDepth(seq, depth) {
    if (seq > this.lastTaken) this.#entry(seq).depth = depth; // late data for a passed frame: drop
  }

  addBodies(seq, bodies) {
    if (seq > this.lastTaken) this.#entry(seq).bodies = bodies;
  }

  // Frame `seq` finished decoding: returns its depth map and bodies (null when missing) and drops
  // everything up to it. A frame older than one already taken gets nothing.
  takeFrame(seq) {
    const entry = seq > this.lastTaken ? this.pending.get(seq) : undefined;
    for (const key of this.pending.keys()) if (key <= seq) this.pending.delete(key);
    this.lastTaken = Math.max(this.lastTaken, seq);
    return { depth: entry?.depth ?? null, bodies: entry?.bodies ?? null };
  }

  #entry(seq) {
    if (!this.pending.has(seq)) {
      this.pending.set(seq, { depth: null, bodies: null });
      while (this.pending.size > this.maxPending) this.pending.delete(this.pending.keys().next().value);
    }
    return this.pending.get(seq);
  }
}
