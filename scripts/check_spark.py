"""Live check of Muse Spark through ai/spark_client.py, called the way the game calls it.

Asks Spark for one match's incantations (two classes, two names) with the game's own prompt
and validation, then optionally for a Duel Chronicle. Prints the latency, the model id the
reply reports and each incantation, marked [spark] or [fallback].

    uv run --env-file .env python scripts/check_spark.py
    uv run --env-file .env python scripts/check_spark.py --classes fire_mage holy_knight --chronicle

Exit codes: 0 Spark answered and at least one incantation came from it; 1 a call failed (the
error type and HTTP status are printed, never the key or the message) or the reply was
unusable; 2 Spark is disabled or the key is missing. Use `--reasoning-effort` to compare
effort levels without editing the config (`default` omits the field).

Owner: Nikhil
"""

import argparse
import copy
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EFFORTS = ("default", "minimal", "low", "medium", "high", "xhigh")


@dataclass
class Call:
    seconds: float
    error: BaseException | None


class TimedClient:
    """Wraps a SparkClient and records each call's latency and exception."""

    def __init__(self, client) -> None:
        self.client = client
        self.calls: list[Call] = []

    def available(self) -> bool:
        return self.client.available()

    def complete(self, system: str, user: str) -> str:
        started = time.monotonic()
        try:
            reply = self.client.complete(system, user)
        except BaseException as exc:
            self.calls.append(Call(time.monotonic() - started, exc))
            raise
        self.calls.append(Call(time.monotonic() - started, None))
        return reply


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, default=REPO_ROOT / "config.yaml")
    p.add_argument("--classes", nargs=2, metavar=("P1", "P2"), help="default: game.default_classes")
    p.add_argument("--names", nargs=2, metavar=("P1", "P2"), default=["Ada", "Bo"])
    p.add_argument("--chronicle", action="store_true", help="also write a Duel Chronicle")
    p.add_argument("--reasoning-effort", choices=EFFORTS, help="override ai.reasoning_effort")
    return p.parse_args(argv)


def sample_events(classes: dict[int, str], names: dict[int, str], cfg: dict) -> list:
    """A short KO match log for the chronicle check."""
    from magic_box.core.contracts import GameEvent

    spell = cfg["game"]["classes"][classes[0]]["spells"][0]["id"]
    return [
        GameEvent(0.0, "match_start", None, {"names": names, "classes": classes}),
        GameEvent(5.0, "cast", 0, {"spell_id": spell, "release": "push", "two_hand": False}),
        GameEvent(6.0, "hit", 0, {"spell_id": spell, "damage": 21.6, "target": 1, "hp_left": 78}),
        GameEvent(9.0, "dodge", 1, {"spell_id": "basic", "dodge": "duck"}),
        GameEvent(40.0, "ko", 0, {"winner": 0}),
        GameEvent(40.0, "match_end", None, {"winner": 0, "reason": "ko", "hp": {0: 64, 1: 0}}),
    ]


def main(argv: Sequence[str] | None = None, env=None, client_factory=None) -> int:
    args = parse_args(argv)
    from magic_box.ai.chronicle import write_chronicle
    from magic_box.ai.incantations import fallback_incantations, generate_incantations
    from magic_box.ai.spark_client import SparkClient, describe_error
    from magic_box.core.config import load_config

    cfg = load_config(args.config)
    if args.reasoning_effort is not None:
        cfg = copy.deepcopy(cfg)
        effort = args.reasoning_effort
        cfg["ai"]["reasoning_effort"] = None if effort == "default" else effort
    ai = cfg["ai"]
    factory = client_factory or (lambda c: SparkClient(c, env=env))
    spark = factory(cfg)
    if not spark.available():
        print(f"FAIL: Spark is disabled (ai.enabled) or ${ai['api_key_env']} is not set")
        return 2
    defaults = cfg["game"]["default_classes"]
    classes = dict(enumerate(args.classes)) if args.classes else {s: defaults[s] for s in (0, 1)}
    names = dict(enumerate(args.names))
    effort = ai.get("reasoning_effort") or "model default"
    print(f"base_url {ai['base_url']}  model {ai['model']}  reasoning_effort {effort}")
    print(f"deadline ai.timeout_s {ai['timeout_s']} s")

    timed = TimedClient(spark)
    result = generate_incantations(timed, classes, names, cfg)
    call = timed.calls[-1]
    if call.error is not None:
        print(f"FAIL incantations after {call.seconds:.2f} s: {describe_error(call.error)}")
        return 1
    print(f"incantations: {call.seconds:.2f} s, reply model {getattr(spark, 'last_model', None)}")
    fallback = fallback_incantations(classes, cfg)
    from_spark = 0
    for slot in sorted(result):
        print(f"  P{slot + 1} {names[slot]} ({classes[slot]})")
        for spell_id, text in result[slot].items():
            source = "fallback" if text == fallback[slot][spell_id] else "spark"
            from_spark += source == "spark"
            print(f"    {spell_id:<13} [{source}] {text}")
    status = 0
    if from_spark == 0:
        print("FAIL: no generated incantation passed validation (all fallback)")
        status = 1
    if call.seconds > ai["timeout_s"] * 0.75:
        print(f"WARN: {call.seconds:.2f} s is close to the {ai['timeout_s']} s deadline")

    if args.chronicle:
        events = sample_events(classes, names, cfg)
        text = write_chronicle(timed, events, names, cfg)
        call = timed.calls[-1]
        if call.error is not None:
            print(f"FAIL chronicle after {call.seconds:.2f} s: {describe_error(call.error)}")
            return 1
        print(f"chronicle: {call.seconds:.2f} s, {len(text.split())} words")
        print(f"  {text}")
    return status


if __name__ == "__main__":
    sys.exit(main())
