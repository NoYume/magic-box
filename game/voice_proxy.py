"""Keep the Meta API key server-side while proxying browser microphone audio to Muse.

Owner: Adetola
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

META_URL = "wss://api.meta.ai/v1/asr/realtime"
MODEL = "muse-voice-transcribe-1.0"
ABILITIES = ("bolt", "ward", "gather", "ultimate")
DEFAULT_KEYWORDS = [
    *ABILITIES,
    *(f"cast {ability}" for ability in ABILITIES),
    "player one",
    "player two",
]


def handshake(api_key: str, keywords: list[str] | None = None) -> dict[str, Any]:
    """Build the fixed Muse handshake; clients cannot override the endpoint or model."""
    requested = keywords or []
    allowed = [word for word in requested if isinstance(word, str) and word in DEFAULT_KEYWORDS]
    return {
        "mode": "ENDPOINTING",
        "authorization": {"accessToken": api_key},
        "audioEncoding": "PCM_16KHZ",
        "model": MODEL,
        "partialMode": "CUMULATIVE",
        "emitAudioProgress": False,
        "keywords": allowed or DEFAULT_KEYWORDS,
        "languageBias": ["english"],
    }


async def send_error(client: Any, message: str) -> None:
    try:
        await client.send(json.dumps({"type": "error", "message": message}))
    except ConnectionClosed:
        pass


async def proxy_session(client: Any, api_key: str) -> None:
    """Relay one browser microphone stream to one upstream Muse session."""
    try:
        first = await asyncio.wait_for(client.recv(), timeout=10)
        if not isinstance(first, str):
            raise ValueError("Expected a start message before audio")
        start = json.loads(first)
        if start.get("type") != "start":
            raise ValueError("Expected a start message before audio")

        async with websockets.connect(META_URL, max_size=None) as upstream:
            await upstream.send(json.dumps(handshake(api_key, start.get("keywords"))))
            acknowledgement = await asyncio.wait_for(upstream.recv(), timeout=10)
            await client.send(acknowledgement)

            async def to_muse() -> None:
                async for message in client:
                    if isinstance(message, bytes):
                        await upstream.send(message)
                    else:
                        packet = json.loads(message)
                        if packet.get("type") == "endStream":
                            await upstream.send(json.dumps({"type": "endStream"}))
                            return

            async def to_browser() -> None:
                async for message in upstream:
                    if isinstance(message, str):
                        await client.send(message)

            browser_task = asyncio.create_task(to_muse())
            muse_task = asyncio.create_task(to_browser())
            done, pending = await asyncio.wait(
                {browser_task, muse_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
    except (asyncio.TimeoutError, json.JSONDecodeError, ValueError) as exc:
        await send_error(client, str(exc))
    except ConnectionClosed:
        pass
    except Exception as exc:  # keep credentials and upstream internals out of the browser
        print(f"[voice-proxy] upstream session failed: {type(exc).__name__}: {exc}")
        await send_error(client, "Muse connection failed. Check the API key and network.")


async def run(host: str, port: int, api_key: str) -> None:
    async with websockets.serve(
        lambda client: proxy_session(client, api_key),
        host,
        port,
        max_size=128 * 1024,
        ping_interval=20,
        ping_timeout=20,
    ):
        print(f"[voice-proxy] listening on ws://{host}:{port}")
        await asyncio.Future()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8766, type=int)
    args = parser.parse_args()
    api_key = os.environ.get("META_MODEL_API_KEY")
    if not api_key:
        raise SystemExit("META_MODEL_API_KEY is not set. Add it to the repository-root .env file.")
    try:
        asyncio.run(run(args.host, args.port, api_key))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
