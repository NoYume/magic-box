"""Local fake of Meta's Muse realtime speech-to-text WebSocket, for tests.

Owner: Nikhil

Runs on 127.0.0.1 only. The script steps run after the handshake frame arrives:
("send", dict), ("wait_audio", n), ("wait_text", type), ("close", code), ("sleep", s).
`disconnected` is set when the server sees the connection end after the handshake.
"""

import asyncio
import json

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed


class FakeMuse:
    def __init__(self, script: list[tuple]) -> None:
        self.script = script
        self.url = ""
        self.handshakes: list[dict] = []
        self.audio: list[bytes] = []
        self.texts: list[dict] = []
        self.disconnected = asyncio.Event()
        self._server = None

    async def __aenter__(self) -> "FakeMuse":
        self._server = await serve(self._handler, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()
        try:
            await asyncio.wait_for(self._server.wait_closed(), 2.0)
        except asyncio.TimeoutError:
            pass

    async def _read(self, ws) -> None:
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    self.audio.append(msg)
                else:
                    self.texts.append(json.loads(msg))
        except ConnectionClosed:
            pass
        self.disconnected.set()

    async def _wait(self, cond) -> None:
        while not cond():
            await asyncio.sleep(0.01)

    async def _handler(self, ws) -> None:
        reader = None
        try:
            self.handshakes.append(json.loads(await ws.recv()))
            reader = asyncio.ensure_future(self._read(ws))
            for kind, arg in self.script:
                if kind == "send":
                    await ws.send(json.dumps(arg))
                elif kind == "wait_audio":
                    await self._wait(lambda n=arg: len(self.audio) >= n)
                elif kind == "wait_text":
                    await self._wait(lambda ty=arg: any(t.get("type") == ty for t in self.texts))
                elif kind == "close":
                    await ws.close(arg)
                    return
                elif kind == "sleep":
                    await asyncio.sleep(arg)
            await reader
        except ConnectionClosed:
            pass
        finally:
            if reader is not None:
                reader.cancel()
