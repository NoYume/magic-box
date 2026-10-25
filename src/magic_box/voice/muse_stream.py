"""Muse WebSocket client, ENDPOINTING mode with CUMULATIVE partials (spec section 8).

Owner: Nikhil
"""

import json
from collections.abc import AsyncIterator

from magic_box.core.config import Config


class MuseStream:
    def __init__(self, cfg: Config, api_key: str) -> None:
        self.cfg = cfg
        self.api_key = api_key
        self._socket = None

    async def connect(self, keywords: list[str]) -> None:
        import websockets

        voice = self.cfg["voice"]
        self._socket = await websockets.connect(voice["url"], max_size=None)
        await self._socket.send(
            json.dumps(
                {
                    "mode": "ENDPOINTING",
                    "authorization": {"accessToken": self.api_key},
                    "audioEncoding": "PCM_16KHZ",
                    "model": voice["model"],
                    "partialMode": "CUMULATIVE",
                    "emitAudioProgress": False,
                    "keywords": keywords,
                    "languageBias": ["english"],
                }
            )
        )
        acknowledgement = json.loads(await self._socket.recv())
        if acknowledgement.get("type") == "error":
            raise RuntimeError(acknowledgement.get("message", "Muse rejected the session"))

    async def send_audio(self, pcm: bytes) -> None:
        if self._socket is None:
            raise RuntimeError("Muse stream is not connected")
        await self._socket.send(pcm)

    async def events(self) -> AsyncIterator[dict]:
        if self._socket is None:
            raise RuntimeError("Muse stream is not connected")
        async for message in self._socket:
            if isinstance(message, str):
                yield json.loads(message)

    async def close(self) -> None:
        if self._socket is not None:
            try:
                await self._socket.send(json.dumps({"type": "endStream"}))
            finally:
                await self._socket.close()
                self._socket = None
