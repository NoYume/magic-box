// Synthesized sound effects (WebAudio, no asset files). One master gain; M toggles mute.
// Browsers start audio suspended until a user gesture; the cabinet should launch Chrome with
// --autoplay-policy=no-user-gesture-required (see README).

const MASTER_VOLUME = 0.55;
const NOISE_SECONDS = 1;

export class Sfx {
  constructor() {
    this.ctx = new AudioContext();
    this.master = this.ctx.createGain();
    this.master.gain.value = MASTER_VOLUME;
    const comp = this.ctx.createDynamicsCompressor();
    this.master.connect(comp).connect(this.ctx.destination);
    this.noise = this.#noiseBuffer();
    this.isMuted = false;
    this.hums = [null, null];
    const resume = () => this.ctx.state === 'suspended' && this.ctx.resume();
    window.addEventListener('pointerdown', resume);
    window.addEventListener('keydown', resume);
    resume();
  }

  toggleMute() {
    this.isMuted = !this.isMuted;
    this.master.gain.setTargetAtTime(this.isMuted ? 0 : MASTER_VOLUME, this.ctx.currentTime, 0.05);
    return this.isMuted;
  }

  #noiseBuffer() {
    const buffer = this.ctx.createBuffer(1, this.ctx.sampleRate * NOISE_SECONDS, this.ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    return buffer;
  }

  // Envelope helper: attack to peak, exponential decay to silence.
  #env(gain, t, peak, attack, decay) {
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(peak, t + attack);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
  }

  #tone({ type = 'sine', from, to = from, peak = 0.3, attack = 0.005, decay = 0.3, delay = 0 }) {
    const t = this.ctx.currentTime + delay;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(from, t);
    osc.frequency.exponentialRampToValueAtTime(to, t + attack + decay);
    this.#env(gain, t, peak, attack, decay);
    osc.connect(gain).connect(this.master);
    osc.start(t);
    osc.stop(t + attack + decay + 0.05);
  }

  #noise({ filter = 'bandpass', from, to = from, q = 1, peak = 0.3, attack = 0.005, decay = 0.3 }) {
    const t = this.ctx.currentTime;
    const src = this.ctx.createBufferSource();
    src.buffer = this.noise;
    const biquad = this.ctx.createBiquadFilter();
    biquad.type = filter;
    biquad.Q.value = q;
    biquad.frequency.setValueAtTime(from, t);
    biquad.frequency.exponentialRampToValueAtTime(to, t + attack + decay);
    const gain = this.ctx.createGain();
    this.#env(gain, t, peak, attack, decay);
    src.connect(biquad).connect(gain).connect(this.master);
    src.start(t);
    src.stop(t + attack + decay + 0.05);
  }

  tick(isLast) {
    this.#tone({ from: isLast ? 880 : 660, peak: 0.25, decay: 0.18 });
  }

  begin() {
    [440, 554, 659, 880].forEach((f, i) => this.#tone({ type: 'triangle', from: f, peak: 0.16, decay: 0.6, delay: i * 0.05 }));
  }

  joined() {
    this.#tone({ type: 'triangle', from: 523, peak: 0.2, decay: 0.4 });
    this.#tone({ type: 'triangle', from: 784, peak: 0.16, decay: 0.5, delay: 0.09 });
  }

  // Rising hum while a player gathers; pitch follows charge.
  gather(slot, charge, isActive) {
    if (isActive && !this.hums[slot]) this.hums[slot] = this.#startHum();
    if (!isActive && this.hums[slot]) {
      const { osc, gain } = this.hums[slot];
      gain.gain.setTargetAtTime(0.0001, this.ctx.currentTime, 0.06);
      osc.stop(this.ctx.currentTime + 0.3);
      this.hums[slot] = null;
    }
    if (this.hums[slot]) this.hums[slot].osc.frequency.setTargetAtTime(110 + charge * 330, this.ctx.currentTime, 0.05);
  }

  #startHum() {
    const osc = this.ctx.createOscillator();
    const filter = this.ctx.createBiquadFilter();
    const gain = this.ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.value = 110;
    filter.type = 'lowpass';
    filter.frequency.value = 900;
    gain.gain.value = 0.0001;
    gain.gain.setTargetAtTime(0.07, this.ctx.currentTime, 0.08);
    osc.connect(filter).connect(gain).connect(this.master);
    osc.start();
    return { osc, gain };
  }

  cast(isEmpowered, isUltimate) {
    this.#noise({ from: 600, to: isUltimate ? 3000 : 4800, q: 0.8, peak: isUltimate ? 0.5 : 0.35, attack: 0.02, decay: isUltimate ? 0.6 : 0.28 });
    this.#tone({ type: 'triangle', from: isEmpowered ? 330 : 440, to: isEmpowered ? 880 : 990, peak: 0.12, decay: 0.2 });
    if (isUltimate) this.#tone({ type: 'sawtooth', from: 55, to: 110, peak: 0.25, attack: 0.05, decay: 1 });
  }

  impact(damage, isHeavy) {
    this.#tone({ from: isHeavy ? 120 : 160, to: 40, peak: 0.5, decay: isHeavy ? 0.45 : 0.25 });
    this.#noise({ filter: 'lowpass', from: 3000, to: 300, peak: 0.25 + Math.min(damage, 25) * 0.01, decay: 0.25 });
  }

  wardHit() {
    [1318, 1976].forEach((f, i) => this.#tone({ from: f, to: f * 0.98, peak: 0.13, decay: 0.7, delay: i * 0.02 }));
  }

  wardUp() {
    this.#tone({ type: 'triangle', from: 392, to: 523, peak: 0.08, attack: 0.04, decay: 0.3 });
  }

  // Dodge / evade: a short airy sweep.
  whoosh() {
    this.#noise({ from: 400, to: 2400, q: 1.4, peak: 0.22, attack: 0.03, decay: 0.22 });
  }

  // Body stance entered: a low swell for focus, a muted thud for brace.
  stance(stance) {
    if (stance === 'leanIn') this.#tone({ type: 'triangle', from: 196, to: 294, peak: 0.07, attack: 0.08, decay: 0.4 });
    else this.#tone({ from: 98, to: 82, peak: 0.16, attack: 0.01, decay: 0.3 });
  }

  shatter() {
    this.#noise({ filter: 'highpass', from: 2500, to: 6000, peak: 0.35, decay: 0.5 });
    [1568, 2093, 2637].forEach((f, i) => this.#tone({ from: f, to: f * 0.7, peak: 0.08, decay: 0.4, delay: i * 0.03 }));
  }

  knockout() {
    [196, 247, 294, 392].forEach((f, i) => this.#tone({ type: 'sawtooth', from: f, peak: 0.1, attack: 0.02, decay: 1.6, delay: i * 0.03 }));
    this.#tone({ from: 70, to: 30, peak: 0.5, decay: 1.2 });
  }

  victory() {
    [523, 659, 784, 1047].forEach((f, i) => this.#tone({ type: 'triangle', from: f, peak: 0.16, decay: 0.9, delay: i * 0.12 }));
  }
}
