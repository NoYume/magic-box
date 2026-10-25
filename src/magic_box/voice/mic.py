"""Per-player mic capture: one input stream per device, PCM16 chunks per slot.

See docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md section 9.

Owner: Nikhil
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np


class MicError(Exception):
    """PortAudio is missing or a mic device failed to open."""


def resample(pcm: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear-interpolation resample of int16 samples; output length round(len*dst/src)."""
    if src_rate == dst_rate:
        return pcm.astype(np.int16, copy=False)
    n_out = round(len(pcm) * dst_rate / src_rate)
    if n_out == 0 or len(pcm) == 0:
        return np.zeros(0, np.int16)
    x_out = np.arange(n_out) * (src_rate / dst_rate)
    out = np.interp(x_out, np.arange(len(pcm)), pcm.astype(np.float64))
    return np.rint(out).astype(np.int16)


class _Device:
    """One physical device: its slot->channel map and per-slot sample buffers."""

    def __init__(self, device: str | int | None, slot_channels: dict[int, int]) -> None:
        self.device = device
        self.slot_channels = slot_channels
        self.channels = max(slot_channels.values()) + 1
        self.rate = 0
        self.buffers: dict[int, np.ndarray] = {s: np.zeros(0, np.int16) for s in slot_channels}


class MicHub:
    """Opens one `sounddevice.InputStream` per device and delivers fixed-size chunks.

    The sink is called synchronously from the audio callback thread as
    `sink(slot, pcm16_le_bytes)`; it must hand off to another thread itself.
    """

    def __init__(
        self,
        mics: Sequence[Mapping[str, Any]],
        sample_rate: int,
        chunk_ms: int,
        sink: Callable[[int, bytes], None],
        sd: Any = None,
    ) -> None:
        self._sample_rate = sample_rate
        self._chunk_samples = sample_rate * chunk_ms // 1000
        self._chunk_ms = chunk_ms
        self._sink = sink
        self._sd = sd
        self._streams: list[Any] = []
        grouped: dict[Any, dict[int, int]] = {}
        for m in mics:
            grouped.setdefault(m["device"], {})[int(m["slot"])] = int(m["channel"])
        self._devices = [_Device(dev, sc) for dev, sc in grouped.items()]

    def start(self) -> None:
        sd = self._sd
        if sd is None:
            try:
                import sounddevice as sd
            except (ImportError, OSError) as e:
                raise MicError(f"sounddevice/PortAudio unavailable: {e}") from e
        for dev in self._devices:
            try:
                stream = self._open(sd, dev)
                self._streams.append(stream)
                stream.start()
            except Exception as e:
                self.stop()
                if isinstance(e, MicError):
                    raise
                raise MicError(f"cannot start mic device {dev.device!r}: {e}") from e

    def _open(self, sd: Any, dev: _Device) -> Any:
        def make(rate: int) -> Any:
            return sd.InputStream(
                device=dev.device,
                channels=dev.channels,
                samplerate=rate,
                dtype="int16",
                blocksize=rate * self._chunk_ms // 1000,
                callback=self._make_callback(dev),
            )

        dev.rate = self._sample_rate
        try:
            return make(self._sample_rate)
        except Exception as first:
            try:
                rate = int(sd.query_devices(dev.device, "input")["default_samplerate"])
                dev.rate = rate
                return make(rate)
            except Exception as second:
                raise MicError(
                    f"cannot open mic device {dev.device!r}: {first}; retry failed: {second}"
                ) from second

    def _make_callback(self, dev: _Device) -> Callable[..., None]:
        def callback(indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
            for slot, channel in dev.slot_channels.items():
                try:
                    samples = resample(
                        np.asarray(indata[:, channel], dtype=np.int16), dev.rate, self._sample_rate
                    )
                    buf = np.concatenate((dev.buffers[slot], samples))
                except Exception:
                    continue  # never raise on the audio thread; drop this block
                n = self._chunk_samples
                while len(buf) >= n:
                    chunk, buf = buf[:n], buf[n:]
                    try:
                        self._sink(slot, chunk.tobytes())
                    except Exception:
                        pass  # a failing sink drops that chunk only
                dev.buffers[slot] = buf

        return callback

    def stop(self) -> None:
        streams, self._streams = self._streams, []
        for stream in streams:
            for op in (stream.stop, stream.close):
                try:
                    op()
                except Exception:
                    pass
