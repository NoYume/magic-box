"""Muse realtime speech-to-text WebSocket client, ENDPOINTING with CUMULATIVE partials.

Owner: Nikhil

Spec: docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md section 9 and Appendix A.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake


class MuseError(Exception):
    """The Muse handshake failed (connection, timeout, bad reply or an error frame)."""


def handshake(api_key: str, model: str, keywords: Sequence[str]) -> dict:
    """Build the first text frame; `keywords` is omitted when empty."""
    frame: dict = {
        "authorization": {"accessToken": f"Bearer {api_key}"},
        "audioEncoding": "PCM_16KHZ",
        "model": model,
        "mode": "ENDPOINTING",
        "partialMode": "CUMULATIVE",
        "emitAudioProgress": False,
    }
    if keywords:
        frame["keywords"] = list(keywords)
    return frame


class MuseStream:
    def __init__(self, url: str, api_key: str, model: str, handshake_timeout_s: float) -> None:
        self._url = url
        self._api_key = api_key
        self._model = model
        self._timeout = handshake_timeout_s
        self._ws: ClientConnection | None = None
        self.session_id: str | None = None
        self.close_code: int | None = None

    def __repr__(self) -> str:
        return f"MuseStream(url={self._url!r}, model={self._model!r})"

    async def connect(self, keywords: Sequence[str]) -> None:
        try:
            ws = await connect(self._url, open_timeout=self._timeout)
        except (OSError, TimeoutError, asyncio.TimeoutError, InvalidHandshake) as exc:
            raise MuseError(f"cannot connect to Muse: {type(exc).__name__}") from None
        try:
            await ws.send(json.dumps(handshake(self._api_key, self._model, keywords)))
            raw = await asyncio.wait_for(ws.recv(), self._timeout)
            reply = json.loads(raw)
        except asyncio.TimeoutError:
            await ws.close()
            raise MuseError("Muse handshake timed out") from None
        except ConnectionClosed:
            await ws.close()
            raise MuseError("Muse closed the connection during the handshake") from None
        except ValueError:
            await ws.close()
            raise MuseError("Muse sent an invalid handshake reply") from None
        if not isinstance(reply, dict):
            await ws.close()
            raise MuseError("Muse sent an invalid handshake reply")
        if reply.get("type") == "error":
            await ws.close()
            raise MuseError(str(reply.get("message", "Muse error")))
        self.session_id = reply.get("sessionId")
        self._ws = ws

    async def send_audio(self, pcm: bytes) -> None:
        """Send one binary frame. Raises ConnectionClosed if the socket is closed."""
        assert self._ws is not None, "connect() first"
        await self._ws.send(pcm)

    async def events(self) -> AsyncIterator[dict]:
        """Yield parsed JSON dicts until the socket closes, then set `close_code`."""
        assert self._ws is not None, "connect() first"
        ws = self._ws
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    continue
                try:
                    event = json.loads(msg)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    yield event
        except ConnectionClosed:
            pass
        self.close_code = ws.close_code

    async def close(self) -> None:
        ws = self._ws
        if ws is None:
            return
        self._ws = None
        try:
            await ws.send(json.dumps({"type": "endStream"}))
        except ConnectionClosed:
            pass
        await ws.close()
        if self.close_code is None:
            self.close_code = ws.close_code
