"""Per-player mic capture, PCM16 mono 16 kHz (spec section 8, voice/).

Owner: Nikhil
"""

import queue

import numpy as np


class MicCapture:
    """Non-blocking mono PCM capture with in-process linear resampling."""

    def __init__(
        self, device: str | int | None, channel: int, sample_rate: int, block_ms: int = 20
    ) -> None:
        self.device = device
        self.channel = channel
        self.sample_rate = sample_rate
        self.block_ms = block_ms
        self._chunks: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        info = sd.query_devices(self.device, "input")
        device_rate = int(info["default_samplerate"])
        channels = max(self.channel + 1, 1)
        blocksize = max(1, round(device_rate * self.block_ms / 1000))

        def callback(indata, frames, time_info, status) -> None:
            del frames, time_info, status
            mono = np.asarray(indata[:, self.channel], dtype=np.float32)
            if device_rate != self.sample_rate and len(mono) > 1:
                length = max(1, round(len(mono) * self.sample_rate / device_rate))
                mono = np.interp(
                    np.linspace(0, len(mono) - 1, length),
                    np.arange(len(mono)),
                    mono,
                )
            pcm = np.clip(mono, -1.0, 1.0)
            chunk = (pcm * 32767).astype("<i2").tobytes()
            try:
                self._chunks.put_nowait(chunk)
            except queue.Full:
                try:
                    self._chunks.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._chunks.put_nowait(chunk)
                except queue.Full:
                    pass

        self._stream = sd.InputStream(
            device=self.device,
            samplerate=device_rate,
            channels=channels,
            dtype="float32",
            blocksize=blocksize,
            callback=callback,
        )
        self._stream.start()

    def read(self) -> bytes:
        try:
            return self._chunks.get_nowait()
        except queue.Empty:
            return b""

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
