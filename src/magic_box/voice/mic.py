"""Per-player mic capture, PCM16 mono 16 kHz (spec section 8, voice/).

Owner: Nikhil
"""


class MicCapture:
    """`sounddevice` must be imported inside the methods, never at module top."""

    def __init__(self, device: str | int | None, channel: int, sample_rate: int) -> None:
        self.device = device
        self.channel = channel
        self.sample_rate = sample_rate

    def start(self) -> None:
        raise NotImplementedError("TODO(Nikhil): start mic capture")

    def read(self) -> bytes:
        raise NotImplementedError("TODO(Nikhil): read PCM16 bytes")

    def stop(self) -> None:
        raise NotImplementedError("TODO(Nikhil): stop mic capture")
