// Browser microphone -> local voice proxy -> Muse Voice Transcribe.
// The Model API key remains in the proxy process and is never sent to this page.

import { VOICE_KEYWORDS, parseVoiceCommand } from './commands.js';

const SAMPLE_RATE = 16000;
const RECONNECT_MS = 1500;

function pcm16(samples, inputRate) {
  const ratio = inputRate / SAMPLE_RATE;
  const length = Math.max(1, Math.floor(samples.length / ratio));
  const output = new ArrayBuffer(length * 2);
  const view = new DataView(output);
  for (let i = 0; i < length; i += 1) {
    const from = Math.floor(i * ratio);
    const to = Math.max(from + 1, Math.min(samples.length, Math.floor((i + 1) * ratio)));
    let sum = 0;
    for (let j = from; j < to; j += 1) sum += samples[j];
    const sample = Math.max(-1, Math.min(1, sum / (to - from)));
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return output;
}

function defaultProxyUrl() {
  const override = new URLSearchParams(location.search).get('voiceWs');
  if (override) return override;
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${location.hostname || 'localhost'}:8766`;
}

export class MuseVoiceControl {
  constructor(root, { onCommand, onFeedback, url = defaultProxyUrl() } = {}) {
    this.onCommand = onCommand;
    this.onFeedback = onFeedback;
    this.url = url;
    this.enabled = false;
    this.activeTurnId = null;
    this.handledTurn = false;
    this.handledTurns = new Set();
    this.reconnectTimer = null;
    this.root = document.createElement('aside');
    this.root.className = 'voice-control';
    this.root.innerHTML = `
      <button class="voice-control__button" type="button"><span aria-hidden="true">●</span> Enable voice</button>
      <div class="voice-control__copy"><b>Voice offline</b><span>Say “cast bolt” in solo play.</span></div>`;
    root.append(this.root);
    this.button = this.root.querySelector('button');
    this.title = this.root.querySelector('b');
    this.detail = this.root.querySelector('.voice-control__copy span');
    this.button.addEventListener('click', () => (this.enabled ? this.stop() : this.start()));
  }

  async start() {
    this.button.disabled = true;
    this.#status('Requesting microphone', 'Allow microphone access to cast abilities.');
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: false,
      });
      const Audio = window.AudioContext ?? window.webkitAudioContext;
      this.audio = new Audio({ sampleRate: SAMPLE_RATE });
      await this.audio.resume();
      this.source = this.audio.createMediaStreamSource(this.stream);
      this.processor = this.audio.createScriptProcessor(4096, 1, 1);
      this.silence = this.audio.createGain();
      this.silence.gain.value = 0;
      this.processor.onaudioprocess = (event) => {
        if (this.socket?.readyState !== WebSocket.OPEN) return;
        this.socket.send(pcm16(event.inputBuffer.getChannelData(0), this.audio.sampleRate));
      };
      this.source.connect(this.processor);
      this.processor.connect(this.silence).connect(this.audio.destination);
      this.enabled = true;
      this.button.disabled = false;
      this.button.innerHTML = '<span aria-hidden="true">●</span> Disable voice';
      this.root.classList.add('is-enabled');
      this.#connect();
    } catch (error) {
      console.error('[voice] microphone start failed', error);
      this.button.disabled = false;
      this.#status('Voice unavailable', error.message || 'Microphone access failed.');
    }
  }

  stop() {
    this.enabled = false;
    clearTimeout(this.reconnectTimer);
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({ type: 'endStream' }));
    this.socket?.close();
    this.processor?.disconnect();
    this.source?.disconnect();
    this.silence?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.audio?.close();
    this.button.innerHTML = '<span aria-hidden="true">●</span> Enable voice';
    this.root.classList.remove('is-enabled', 'is-listening');
    this.#status('Voice offline', 'Say “cast bolt” in solo play.');
  }

  #connect() {
    if (!this.enabled) return;
    this.#status('Connecting voice', 'The local Muse proxy must be running.');
    const socket = new WebSocket(this.url);
    this.socket = socket;
    socket.binaryType = 'arraybuffer';
    socket.onopen = () => socket.send(JSON.stringify({ type: 'start', keywords: VOICE_KEYWORDS }));
    socket.onmessage = (message) => this.#message(JSON.parse(message.data));
    socket.onerror = () => this.#status('Voice connection failed', `Could not reach ${this.url}.`);
    socket.onclose = () => {
      this.root.classList.remove('is-listening');
      if (!this.enabled) return;
      this.#status('Voice reconnecting', 'Check the proxy and API key.');
      this.reconnectTimer = setTimeout(() => this.#connect(), RECONNECT_MS);
    };
  }

  #message(event) {
    if (event.type === 'session') {
      this.#status('Voice ready', 'Solo: “cast bolt.” Local: “player one, cast bolt.”');
      return;
    }
    if (event.type === 'error') {
      this.#status('Voice error', event.message || 'Muse rejected the stream.');
      return;
    }
    if (event.type === 'speechStart') {
      this.activeTurnId = event.turnId ?? null;
      this.handledTurn = false;
      this.root.classList.add('is-listening');
      this.#status('Listening', 'Speak one ability command.');
      return;
    }
    if (event.type === 'speechEnd') {
      this.root.classList.remove('is-listening');
      this.title.textContent = 'Recognizing command';
      return;
    }
    if (event.type !== 'transcript' && event.type !== 'speechComplete') return;
    const transcript = event.transcript?.trim();
    if (!transcript) return;
    this.detail.textContent = transcript;
    // Muse deployments differ in whether the completed text is delivered as a final transcript,
    // speechComplete, or both. Partials are display-only so surrounding speech cannot cast early.
    if (event.type === 'transcript' && !event.final) return;
    const turnId = event.turnId ?? this.activeTurnId;
    if ((turnId !== null && this.handledTurns.has(turnId)) || (turnId === null && this.handledTurn)) return;
    const command = parseVoiceCommand(transcript);
    if (turnId !== null) {
      this.handledTurns.add(turnId);
      if (this.handledTurns.size > 128) this.handledTurns.delete(this.handledTurns.values().next().value);
    } else this.handledTurn = true;
    if (!command) {
      this.title.textContent = 'Command not recognized';
      this.onFeedback?.({ success: false, reason: 'Command not recognized. Say “cast” followed by an ability.', slot: null });
      return;
    }
    const result = this.onCommand?.(command) ?? { accepted: false, message: 'No match is active.' };
    console.info('[voice]', command.transcript, result);
    this.onFeedback?.({ success: result.accepted, ability: command.ability, reason: result.message, slot: result.slot ?? command.slot });
    this.#status(result.accepted ? `${command.ability} cast` : 'Command ignored', result.message ?? transcript);
  }

  #status(title, detail) {
    this.title.textContent = title;
    this.detail.textContent = detail;
  }
}
