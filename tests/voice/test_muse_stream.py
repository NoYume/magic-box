"""Tests for the Muse realtime WebSocket client against a local fake server.

Owner: Nikhil
"""

import asyncio

import pytest

from magic_box.voice.muse_stream import MuseError, MuseStream, handshake
from tests.voice.fake_muse import FakeMuse


def arun(coro, timeout=5.0):
    return asyncio.run(asyncio.wait_for(coro, timeout))


def test_handshake_fields():
    assert handshake("k", "muse-voice-transcribe-1.0", ["embers"]) == {
        "authorization": {"accessToken": "Bearer k"},
        "audioEncoding": "PCM_16KHZ",
        "model": "muse-voice-transcribe-1.0",
        "mode": "ENDPOINTING",
        "partialMode": "CUMULATIVE",
        "emitAudioProgress": False,
        "keywords": ["embers"],
    }
    assert "keywords" not in handshake("k", "m", [])


def test_connect_reads_session_id():
    async def go():
        async with FakeMuse([("send", {"sessionId": "abc"}), ("sleep", 0.2)]) as srv:
            ms = MuseStream(srv.url, "k", "m", 1.0)
            await ms.connect(["embers"])
            assert ms.session_id == "abc"
            assert srv.handshakes[0]["authorization"]["accessToken"] == "Bearer k"
            await ms.close()

    arun(go())


def test_handshake_timeout_raises():
    async def go():
        async with FakeMuse([("sleep", 2.0)]) as srv:
            with pytest.raises(MuseError):
                await MuseStream(srv.url, "k", "m", 0.2).connect([])

    arun(go())


def test_error_frame_on_handshake_raises():
    async def go():
        script = [("send", {"type": "error", "message": "bad key", "sessionId": ""})]
        async with FakeMuse(script) as srv:
            with pytest.raises(MuseError, match="bad key"):
                await MuseStream(srv.url, "k", "m", 1.0).connect([])

    arun(go())


def test_connection_refused_raises_muse_error():
    async def go():
        async with FakeMuse([]) as srv:
            url = srv.url
        with pytest.raises(MuseError):
            await MuseStream(url, "k", "m", 1.0).connect([])

    arun(go())


def test_audio_is_binary_and_events_are_yielded():
    script = [
        ("send", {"sessionId": "s"}),
        ("wait_audio", 2),
        ("send", {"type": "speechStart", "turnId": 1, "audioProcessedMs": 0}),
        (
            "send",
            {"type": "transcript", "transcript": "embers", "final": False, "audioProcessedMs": 80},
        ),
        ("send", {"type": "somethingNew"}),
        ("close", 1000),
    ]

    async def go():
        async with FakeMuse(script) as srv:
            ms = MuseStream(srv.url, "k", "m", 1.0)
            await ms.connect([])
            await ms.send_audio(b"\x00\x01" * 640)
            await ms.send_audio(b"\x00\x01" * 640)
            types = [ev.get("type") async for ev in ms.events()]
            assert types == ["speechStart", "transcript", "somethingNew"]
            assert srv.audio == [b"\x00\x01" * 640] * 2 and ms.close_code == 1000

    arun(go())


def test_close_sends_end_stream():
    async def go():
        script = [("send", {"sessionId": "s"}), ("wait_text", "endStream"), ("close", 1000)]
        async with FakeMuse(script) as srv:
            ms = MuseStream(srv.url, "k", "m", 1.0)
            await ms.connect([])
            await ms.close()
            await ms.close()
            await asyncio.sleep(0.1)
            assert srv.texts == [{"type": "endStream"}]

    arun(go())


def test_server_close_code_is_exposed():
    async def go():
        async with FakeMuse([("send", {"sessionId": "s"}), ("close", 1011)]) as srv:
            ms = MuseStream(srv.url, "k", "m", 1.0)
            await ms.connect([])
            assert [ev async for ev in ms.events()] == [] and ms.close_code == 1011

    arun(go())
