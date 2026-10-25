"""CLI entry: build sources, window and game objects, run the loop.

Owner: Nikhil
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from magic_box.core.config import load_config
from magic_box.game.engine import Engine
from magic_box.intent.fusion import Intent
from magic_box.pipeline.loop import GameLoop
from magic_box.pipeline.processes import LiveRuntime, start_live
from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource, ReplaySources, Sources
from magic_box.render.window import Window
from magic_box.replay.record import SessionRecorder


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="magic_box", description="Magic Box game console")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fake", action="store_true", help="keyboard-driven fake players")
    mode.add_argument("--replay", metavar="DIR", type=Path, help="replay a recorded session")
    parser.add_argument("--record", metavar="DIR", type=Path, help="record this session")
    parser.add_argument("--debug", action="store_true", help="show the debug overlay")
    parser.add_argument("--headless", action="store_true", help="no visible window")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--max-ticks", type=int, default=None, metavar="N")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sources: Sources | None = None
    display: Window | None = None
    runtime: LiveRuntime | None = None
    on_tick = None
    recorder: SessionRecorder | None = None
    try:
        cfg = load_config(args.config)
        if args.fake:
            sources = FakeSources(cfg)
        elif args.replay is not None:
            sources = ReplaySources(args.replay)
        else:
            runtime = start_live(cfg)
            sources = runtime.sources
            on_tick = runtime.supervisor.poll
        if args.record is not None:
            recorder = SessionRecorder(args.record, cfg)
        display = Window(cfg, headless=args.headless)
        display.debug = args.debug
        loop = GameLoop(
            cfg,
            sources,
            display,
            Intent(cfg),
            Engine(cfg),
            KeyboardVoiceSource(cfg),
            on_tick=on_tick,
            camera_ok=(lambda: runtime.supervisor.alive("perception"))
            if runtime is not None
            else None,
            control_q=runtime.control_q if runtime is not None else None,
            recorder=recorder,
        )
        loop.run(max_ticks=args.max_ticks)
        return 0
    except (NotImplementedError, ValueError) as e:
        print(f"cannot start: {e}", file=sys.stderr)
        return 2
    finally:
        if recorder is not None:
            recorder.close()
        if display is not None:
            display.close()
        if sources is not None:
            sources.close()
        if runtime is not None:
            runtime.close()
