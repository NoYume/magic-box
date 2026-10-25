"""Voice process entry point (spec section 8, voice/).

Owner: Nikhil
"""

import asyncio
import contextlib
import os
import time
from multiprocessing.synchronize import Event

from magic_box.core.config import Config
from magic_box.core.contracts import VoiceConfig, VoiceEvent
from magic_box.pipeline.streams import DropOldestQueue
from magic_box.voice.matcher import match_incantation
from magic_box.voice.mic import MicCapture
from magic_box.voice.muse_stream import MuseStream


async def _session(
    cfg: Config,
    slot: int,
    mic: MicCapture,
    voice_config: VoiceConfig,
    api_key: str,
    voice_q: DropOldestQueue,
    stop: Event,
) -> None:
    backoff = float(cfg["pipeline"]["restart_backoff_s"])
    silence = bytes(round(cfg["voice"]["sample_rate"] * cfg["voice"]["block_ms"] / 1000) * 2)
    while not stop.is_set():
        stream = MuseStream(cfg, api_key)
        incantations = voice_config.incantations.get(slot, {})
        try:
            await stream.connect(list(incantations.values()))

            async def send(active_stream=stream) -> None:
                while not stop.is_set():
                    await active_stream.send_audio(mic.read() or silence)
                    await asyncio.sleep(float(cfg["voice"]["block_ms"]) / 1000)

            async def receive(active_stream=stream, active_incantations=incantations) -> None:
                handled = False
                async for event in active_stream.events():
                    kind = event.get("type")
                    if kind == "speechStart":
                        handled = False
                    text = str(event.get("transcript") or "").strip()
                    if not text or kind not in {"transcript", "speechComplete"}:
                        continue
                    now = time.monotonic()
                    if voice_config.mode == "transcript":
                        voice_q.put(VoiceEvent(slot, now, "transcript", text, None, 0.0))
                        continue
                    if handled:
                        continue
                    match = match_incantation(
                        text, active_incantations, float(cfg["voice"]["match_threshold"])
                    )
                    if match is not None:
                        handled = True
                        voice_q.put(VoiceEvent(slot, now, "incantation", text, match[0], match[1]))

            tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        except (OSError, RuntimeError, asyncio.TimeoutError):
            await asyncio.sleep(backoff)
        finally:
            with contextlib.suppress(Exception):
                await stream.close()


async def _run_async(
    cfg: Config, voice_q: DropOldestQueue, control_q: DropOldestQueue, stop: Event, api_key: str
) -> None:
    voice = cfg["voice"]
    mics = {
        row["slot"]: MicCapture(
            row["device"], row["channel"], voice["sample_rate"], voice["block_ms"]
        )
        for row in voice["mics"]
    }
    for mic in mics.values():
        mic.start()
    current = VoiceConfig(mode="transcript", incantations={})
    tasks: list[asyncio.Task] = []
    try:
        while not stop.is_set():
            updates = control_q.drain()
            changed = not tasks
            if updates:
                newest = updates[-1]
                if isinstance(newest, VoiceConfig) and newest != current:
                    current = newest
                    changed = True
            if changed:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = [
                    asyncio.create_task(_session(cfg, slot, mic, current, api_key, voice_q, stop))
                    for slot, mic in mics.items()
                ]
            await asyncio.sleep(0.05)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for mic in mics.values():
            mic.stop()


def run(cfg: Config, voice_q: DropOldestQueue, control_q: DropOldestQueue, stop: Event) -> None:
    """Capture two mics and publish attributed Muse events."""
    api_key = os.environ.get(cfg["ai"]["api_key_env"])
    if not api_key:
        stop.wait()
        return
    asyncio.run(_run_async(cfg, voice_q, control_q, stop, api_key))
