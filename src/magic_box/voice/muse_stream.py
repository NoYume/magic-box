"""Muse WebSocket client, ENDPOINTING mode with CUMULATIVE partials (spec section 8).

Owner: Nikhil
"""

from collections.abc import AsyncIterator

from magic_box.core.config import Config


class MuseStream:
    def __init__(self, cfg: Config, api_key: str) -> None:
        self.cfg = cfg
        self.api_key = api_key

    async def connect(self, keywords: list[str]) -> None:
        raise NotImplementedError("TODO(Nikhil): open the Muse WebSocket")

    async def send_audio(self, pcm: bytes) -> None:
        raise NotImplementedError("TODO(Nikhil): send PCM audio")

    def events(self) -> AsyncIterator[dict]:
        raise NotImplementedError("TODO(Nikhil): yield Muse events")

    async def close(self) -> None:
        raise NotImplementedError("TODO(Nikhil): close the Muse WebSocket")
