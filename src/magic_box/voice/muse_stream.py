"""Muse realtime speech-to-text WebSocket client, ENDPOINTING with CUMULATIVE partials.

Owner: Nikhil

Spec: docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md section 9 and Appendix A.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Sequence
from typing import TypeVar

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake
from websockets.protocol import State

# Keepalive and close tuning (fixed protocol tuning, not game tunables). Venue Wi-Fi can
# leave a half-dead socket: a ping every PING_INTERVAL_S that gets no pong within
# PING_TIMEOUT_S drops it in about 10 s instead of about 40 s, and close() never takes
# longer than CLOSE_TIMEOUT_S (websockets' default close timeout is 10 s).
CLOSE_TIMEOUT_S = 1.0
PING_INTERVAL_S = 5.0
PING_TIMEOUT_S = 5.0

_T = TypeVar("_T")


class MuseError(Exception):
    """The Muse handshake failed (connection, timeout, bad reply or an error frame)."""


async def _bounded(aw: Awaitable[_T], timeout: float) -> _T:
    """Await `aw` for at most `timeout` s; raise asyncio.TimeoutError (and cancel it) after.

    Never asyncio.wait_for: on Python 3.10 it drops a cancel that arrives just as the
    awaited result does, and a session could then never be stopped.
    """
    task = asyncio.ensure_future(aw)
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout)
    finally:
        task.cancel()  # no-op once done
    if not done:
        raise asyncio.TimeoutError
    return task.result()


async def _end_and_close(ws: ClientConnection) -> None:
    try:
        await ws.send(json.dumps({"type": "endStream"}))
    except ConnectionClosed:
        pass
    await ws.close()


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
            ws = await connect(
                self._url,
                open_timeout=self._timeout,
                close_timeout=CLOSE_TIMEOUT_S,
                ping_interval=PING_INTERVAL_S,
                ping_timeout=PING_TIMEOUT_S,
            )
        except (OSError, TimeoutError, asyncio.TimeoutError, InvalidHandshake) as exc:
            raise MuseError(f"cannot connect to Muse: {type(exc).__name__}") from None
        try:
            self.session_id = await self._handshake(ws, keywords)
        except BaseException:
            # Cancelled or failed before the stream was handed over: drop the socket now
            # (a no-op when a MuseError path already closed it).
            ws.transport.abort()
            raise
        self._ws = ws

    async def _handshake(self, ws: ClientConnection, keywords: Sequence[str]) -> str | None:
        """Send the handshake frame and return the reply's sessionId; MuseError on failure."""
        try:
            await ws.send(json.dumps(handshake(self._api_key, self._model, keywords)))
            raw = await _bounded(ws.recv(), self._timeout)
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
        return reply.get("sessionId")

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
        """Send endStream and close; idempotent, never raises, at most CLOSE_TIMEOUT_S.

        A send or close that overruns (a stalled TCP buffer) aborts the socket instead.
        """
        ws = self._ws
        if ws is None:
            return
        self._ws = None
        try:
            await _bounded(_end_and_close(ws), CLOSE_TIMEOUT_S)
        except Exception:  # timed out or a transport error: the socket is aborted below
            pass
        finally:
            if ws.state is not State.CLOSED:
                ws.transport.abort()
        if self.close_code is None:
            self.close_code = ws.close_code
