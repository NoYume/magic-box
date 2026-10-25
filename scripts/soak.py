"""Soak test: fake mode, headless, random inputs; reports fps, RSS and growth.

Owner: Daniel

Runs the real `GameLoop` with `FakeSources`, `Intent`, `Engine`, the keyboard voice source
and a real headless `Window`, for `--seconds` of wall time. Random inputs per tick:
movement, pushes, two-hand pushes, ducks, poses, spell keys, hands up in the lobby and
victory, lobby transcripts, mic status flips, players leaving (pause and abandon) and
camera outages (`live=True` with frames withheld). It samples RSS, the gc object count,
projectiles, the crop cache and the loop's PerfStats every `--sample-s`, and exits 1 on a
crash or when growth looks unbounded.

    uv run python scripts/soak.py --seconds 600
    uv run python scripts/soak.py --seconds 60 --fast     # no frame cap, fake clock
"""

import argparse
import copy
import gc
import os
import random
import subprocess
import sys
import time
import traceback
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

TRANSCRIPTS = (
    "my name is Ada, fire",
    "call me Bob",
    "lightning",
    "holy knight",
    "so what do I do now",
    "I'm Zoë the holy knight",
    "fire no wait holy",
    "",
    "!!!",
    "123 456",
    "my name is",
    "hi my name is supercalifragilistic expialidocious",
    "Bob",
)
MIC_STATUSES = ("connected", "reconnecting", "no mic", "connected")


def rss_mb() -> float:
    """Current resident set size in MB (Linux /proc, else `ps`)."""
    try:
        with open("/proc/self/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    except OSError:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True
        )
        return int(out.stdout.strip() or 0) / 1024


class RandomPlayers:
    """Scene-aware random key presses for both fake players."""

    def __init__(self, cfg, rng: random.Random) -> None:
        self.rng = rng
        self.fake = cfg["keys"]["fake"]
        self.spells = cfg["keys"]["spells"]
        self.start_x = float(cfg["fake"]["start_x_m"])
        self.start_z = float(cfg["fake"]["start_z_m"])
        self.held: dict[str, int] = {}  # key -> ticks left
        self.scene = "boot"
        self.states: dict = {}
        self.passive = False  # this match: nobody attacks (plays to a time-out)

    def _hold(self, key: str, ticks: int) -> None:
        self.held[key] = max(self.held.get(key, 0), ticks)

    def keys(self) -> frozenset[str]:
        r = self.rng
        lobbyish = self.scene in ("lobby", "victory")
        if lobbyish and r.random() < 0.01:
            for slot in (0, 1):
                self._hold(self.fake[slot]["hands_up"], r.randint(10, 60))
        for slot in (0, 1):
            k = self.fake[slot]
            st = self.states.get(slot)
            if r.random() < 0.02:  # a walk, biased back toward the start spot
                x = st.root[0] if st is not None else 0.0
                home = self.start_x if slot == 0 else -self.start_x
                toward = k["left"] if x < home else k["right"]
                away = k["right"] if toward == k["left"] else k["left"]
                self._hold(toward if r.random() < 0.6 else away, r.randint(5, 30))
            if r.random() < 0.01:
                z = st.root[2] if st is not None else self.start_z
                self._hold(k["closer"] if z > self.start_z else k["farther"], r.randint(5, 40))
            if self.scene != "fight" or self.passive:
                continue
            if r.random() < 0.03:
                self._hold(k["push"], 1)
            if r.random() < 0.008:
                self._hold(k["two_hand_push"], 1)
            if r.random() < 0.01:
                self._hold(k["duck"], r.randint(5, 20))
            if r.random() < 0.004:
                self._hold(k["hands_up"], r.randint(5, 20))
            if r.random() < 0.004:
                self._hold(k["hands_together"], r.randint(5, 20))
            for key in self.spells[slot]:
                if r.random() < 0.006:
                    self._hold(key, 1)
        keys = frozenset(self.held)
        self.held = {key: n - 1 for key, n in self.held.items() if n > 1}
        return keys


class SoakSources:
    """FakeSources plus random transcripts, mic flips, players leaving and camera outages."""

    def __init__(self, inner, rng: random.Random, fps: float) -> None:
        self.inner, self.rng, self.fps = inner, rng, fps
        self.scene = "boot"
        self.gone_until = {0: 0.0, 1: 0.0}
        self.camera_down_until = 0.0
        self.leave_next: int | None = None  # this slot walks off for good (an abandon)
        self.counts: Counter = Counter()

    def poll(self, keys, now, dt):
        from magic_box.core.contracts import VoiceEvent

        got = self.inner.poll(keys, now, dt)
        r = self.rng
        per_tick = 1.0 / self.fps
        voice = list(got.voice)
        if self.leave_next is not None:
            self.gone_until[self.leave_next] = now + 30.0
            self.leave_next = None
        for slot in (0, 1):
            if self.scene == "lobby" and r.random() < per_tick / 3:
                text = r.choice(TRANSCRIPTS)
                voice.append(VoiceEvent(slot, now, "transcript", text, None, 0.0))
                self.counts["transcript"] += 1
            if r.random() < per_tick / 20:
                status = r.choice(MIC_STATUSES)
                voice.append(VoiceEvent(slot, now, "status", status, None, 0.0))
                self.counts["mic " + status] += 1
            if (
                self.scene == "fight"
                and now >= self.gone_until[slot]
                and r.random() < per_tick / 45
            ):
                self.gone_until[slot] = now + r.uniform(0.5, 25.0)
                self.counts["player left"] += 1
        if now >= self.camera_down_until and r.random() < per_tick / 120:
            self.camera_down_until = now + r.uniform(2.0, 8.0)
            self.counts["camera outage"] += 1
        if now < self.camera_down_until:
            return replace(got, states=[], voice=voice, frame=None)
        states = [s for s in got.states if now >= self.gone_until[s.slot]]
        return replace(got, states=states, voice=voice)

    def close(self) -> None:
        self.inner.close()


class SoakDisplay:
    """A real headless Window that draws every tick; keys come from RandomPlayers."""

    def __init__(self, window, players: RandomPlayers, sources: SoakSources, fast: bool) -> None:
        self.window, self.players, self.sources, self.fast = window, players, sources, fast
        self.deadline: float | None = None
        self.view = None
        self.ticks = 0

    def pump(self):
        self.window.pump()  # keep the SDL event queue drained
        if self.deadline is not None and time.monotonic() >= self.deadline:
            return frozenset(), True
        return self.players.keys(), False

    def tick(self) -> float:
        if self.fast:
            return 1 / 60
        return self.window.tick()

    def draw(self, view, frame, states, fps, dropped=0):
        if view.scene == "fight" and (self.view is None or self.view.scene != "fight"):
            roll = (
                self.players.rng.random()
            )  # each match: mostly a brawl, some time-outs and walk-offs
            self.players.passive = roll < 0.15
            if 0.15 <= roll < 0.3:
                self.sources.leave_next = self.players.rng.choice((0, 1))
                self.sources.counts["walk-off match"] += 1
            if self.players.passive:
                self.sources.counts["passive match"] += 1
        self.view = view
        self.players.scene = self.sources.scene = view.scene
        self.players.states = states
        self.ticks += 1
        self.window.draw(view, frame, states, fps, dropped)

    def close(self) -> None:
        self.window.close()


def render_sizes(window) -> dict[str, int]:
    """Sizes of the render caches and FX lists (whatever this render version has)."""
    out: dict[str, int] = {}
    theme = getattr(window, "theme", None)
    for name in ("_text", "_panels", "_glows", "_sized_fonts", "_scaled"):
        if hasattr(theme, name):
            out[name.strip("_")] = len(getattr(theme, name))
    fx = getattr(window, "fx", None)
    for name in ("particles", "texts"):
        if hasattr(fx, name):
            out[name] = len(getattr(fx, name))
    return out


class FakeClock:
    def __init__(self, step: float) -> None:
        self.t, self.step = 1000.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=600.0, help="wall time to run")
    parser.add_argument("--sample-s", type=float, default=30.0, help="seconds between samples")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--fast", action="store_true", help="no frame cap; fake 60 fps clock")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--debug", action="store_true", help="draw the F1 debug overlay too")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT / "src"))
    from magic_box.ai.worker import AiWorker
    from magic_box.core.config import load_config
    from magic_box.game.engine import Engine
    from magic_box.intent.fusion import Intent
    from magic_box.pipeline.loop import GameLoop
    from magic_box.pipeline.sources import FakeSources, KeyboardVoiceSource
    from magic_box.render import camera_view
    from magic_box.render.window import Window

    cfg = copy.deepcopy(load_config(args.config))
    cfg["ai"]["enabled"] = False  # no network in a soak
    camera_view.configure(cfg["render"])
    rng = random.Random(args.seed)
    sources = SoakSources(FakeSources(cfg), rng, float(cfg["display"]["fps"]))
    players = RandomPlayers(cfg, rng)
    window = Window(cfg, headless=True)
    window.debug = args.debug
    display = SoakDisplay(window, players, sources, args.fast)
    engine = Engine(cfg)
    results: Counter = Counter()
    scenes: Counter = Counter()
    events: Counter = Counter()
    samples: list[dict] = []
    max_proj = 0
    start = time.monotonic()
    last_sample = [start, 0]

    def sample(now: float) -> None:
        dt = now - last_sample[0]
        ticks = display.ticks - last_sample[1]
        last_sample[0], last_sample[1] = now, display.ticks
        perf = dict(getattr(getattr(loop, "_perf", None), "last", {}) or {})
        row = {
            "t": now - start,
            "ticks": display.ticks,
            "fps": ticks / dt if dt > 0 else 0.0,
            "rss_mb": rss_mb(),
            "objects": len(gc.get_objects()),
            "crop_cache": len(getattr(camera_view, "_cache", {})),
            "render": render_sizes(window),
            "scene": display.view.scene if display.view is not None else "-",
            "matches": sum(results.values()),
            "perf": perf,
        }
        samples.append(row)
        print(
            f"[{row['t']:6.0f}s] ticks {row['ticks']:6d} fps {row['fps']:5.1f} "
            f"rss {row['rss_mb']:6.1f} MB objects {row['objects']:7d} "
            f"cache {row['crop_cache']} proj_max {max_proj} scene {row['scene']:7s} "
            f"matches {row['matches']} render "
            + ",".join(f"{k}={v}" for k, v in row["render"].items())
            + " perf "
            + " ".join(f"{k}={v:.1f}" for k, v in perf.items()),
            flush=True,
        )

    def on_tick() -> None:
        nonlocal max_proj
        view = display.view
        if view is not None:
            scenes[view.scene] += 1
            max_proj = max(max_proj, len(view.projectiles))
            for e in view.events:
                events[e.kind] += 1
                if e.kind == "match_end":
                    results[e.data.get("reason")] += 1
        now = time.monotonic()
        if now - last_sample[0] >= args.sample_s:
            sample(now)

    loop = GameLoop(
        cfg,
        sources,
        display,
        Intent(cfg),
        engine,
        KeyboardVoiceSource(cfg),
        on_tick=on_tick,
        ai=AiWorker(cfg),
        clock=FakeClock(1 / 60) if args.fast else time.monotonic,
        live=True,  # so withheld frames are a camera outage
        perception_alive=lambda: True,
    )
    display.deadline = start + args.seconds
    sample(start)
    code = 0
    try:
        loop.run()
    except Exception:
        traceback.print_exc()
        code = 1
    finally:
        display.close()
    end = time.monotonic()
    sample(end)
    wall = end - start
    print("\n== soak summary ==")
    print(f"wall {wall:.0f} s, ticks {display.ticks}, mean fps {display.ticks / wall:.1f}")
    fps_rows = [s["fps"] for s in samples[1:-1] if s["fps"] > 0]
    if fps_rows:
        print(f"fps per sample: min {min(fps_rows):.1f} max {max(fps_rows):.1f}")
    rss = [s["rss_mb"] for s in samples]
    objs = [s["objects"] for s in samples]
    print(f"rss MB: start {rss[0]:.1f} after 1st sample {rss[min(1, len(rss) - 1)]:.1f} ")
    print(f"        end {rss[-1]:.1f} max {max(rss):.1f}")
    print(f"gc objects: start {objs[0]} end {objs[-1]} max {max(objs)}")
    print(f"max projectiles in one view: {max_proj}")
    print(f"crop cache entries at end: {samples[-1]['crop_cache']}")
    for key in samples[-1]["render"]:
        sizes = [s["render"].get(key, 0) for s in samples]
        print(f"render {key}: end {sizes[-1]} max {max(sizes)}")
    print(f"scenes (ticks): {dict(scenes)}")
    print(f"match endings: {dict(results)}")
    print(f"game events: {dict(events)}")
    print(f"injected: {dict(sources.counts)}")
    if code == 0 and len(rss) >= 4:
        settled = rss[len(rss) // 4]
        if rss[-1] > settled * 1.5 + 50:
            print("FAIL: RSS kept growing", file=sys.stderr)
            code = 1
    print("result:", "OK" if code == 0 else "FAIL")
    return code


if __name__ == "__main__":
    sys.exit(main())
