"""Fake `sounddevice` module for mic tests; never touches PortAudio.

Owner: Nikhil
"""

from typing import Any

import numpy as np


class PortAudioError(Exception):
    pass


class FakeStream:
    def __init__(self, kwargs: dict[str, Any], fail_start: bool = False) -> None:
        self.kwargs = kwargs
        self.fail_start = fail_start
        self.started = False
        self.closed = False

    def start(self) -> None:
        if self.fail_start:
            raise PortAudioError("device busy")
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True

    def feed(self, indata: np.ndarray) -> None:
        self.kwargs["callback"](indata, len(indata), None, None)


class FakeSD:
    PortAudioError = PortAudioError

    def __init__(
        self,
        reject_rates: tuple[int, ...] = (),
        default_rate: float = 48000.0,
        fail_import: bool = False,
        fail_start: bool = False,
    ) -> None:
        self.reject_rates = reject_rates
        self.default_rate = default_rate
        self.fail_import = fail_import
        self.fail_start = fail_start
        self.streams: list[FakeStream] = []

    def InputStream(self, **kwargs: Any) -> FakeStream:  # noqa: N802
        if self.fail_import:
            raise OSError("PortAudio library not found")
        if kwargs.get("samplerate") in self.reject_rates:
            raise PortAudioError("invalid sample rate")
        stream = FakeStream(kwargs, self.fail_start)
        self.streams.append(stream)
        return stream

    def query_devices(self, device: Any, kind: str) -> dict[str, float]:
        return {"default_samplerate": self.default_rate}
