"""Tests for the non-blocking Spark worker.

Owner: Nikhil
"""

import copy
import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from magic_box.ai.chronicle import template_chronicle
from magic_box.ai.incantations import fallback_incantations
from magic_box.ai.worker import AiWorker
from magic_box.core.config import load_config
from tests.ai.fakes import FakeClient
from tests.ai.test_incantations import GOOD
from tests.factories import pin_pre_venue_tuning

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
pin_pre_venue_tuning(CFG)
CLASSES, NAMES = {0: "fire_mage", 1: "lightning_mage"}, {0: "Ada", 1: "Bo"}


class BlockingClient:
    """`complete` blocks until `release` is set, then returns the reply.

    A callable reply is called with the user prompt, so a result can show which job made it.
    """

    def __init__(self, reply: "str | Callable[[str], str]") -> None:
        self.reply = reply
        self.release = threading.Event()

    def complete(self, system: str, user: str) -> str:
        self.release.wait(5.0)
        return self.reply(user) if callable(self.reply) else self.reply


def wait_poll(w, now, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        out = w.poll(now)
        if out:
            return out
        time.sleep(0.01)
    return []


def test_finished_job_returned_once():
    w = AiWorker(CFG, client=FakeClient(RuntimeError("down")))
    w.start_incantations(CLASSES, NAMES, now=0.0)
    assert wait_poll(w, 0.1) == [("incantations", fallback_incantations(CLASSES, CFG))]
    assert w.poll(0.2) == []
    w.close()


def test_timeout_returns_fallback_and_drops_late_result():
    client = BlockingClient(json.dumps(GOOD))
    w = AiWorker(CFG, client=client)
    w.start_incantations(CLASSES, NAMES, now=0.0)
    assert w.poll(1.0) == []
    assert w.poll(CFG["ai"]["timeout_s"] + 0.01) == [
        ("incantations", fallback_incantations(CLASSES, CFG))
    ]
    client.release.set()
    time.sleep(0.1)
    assert w.poll(20.0) == []
    w.close()


def test_new_job_replaces_pending_of_same_kind():
    client = BlockingClient(lambda user: "A tale of Cy." if "Cy" in user else "A tale of Ada.")
    w = AiWorker(CFG, client=client)
    w.start_chronicle([], NAMES, now=0.0)
    w.start_chronicle([], {0: "Cy", 1: "Di"}, now=1.0)
    client.release.set()
    out = wait_poll(w, 1.5)
    assert out == [("chronicle", "A tale of Cy.")] and w.poll(2.0) == []
    w.close()


def test_disabled_resolves_to_fallbacks():
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["enabled"] = False
    w = AiWorker(cfg)
    w.start_chronicle([], NAMES, now=0.0)
    assert wait_poll(w, 0.1) == [("chronicle", template_chronicle([], NAMES, cfg))]
    w.close()


def test_a_stuck_job_does_not_delay_the_other_kind():
    client = BlockingClient(lambda user: "A tale." if "Players:" in user else json.dumps(GOOD))
    w = AiWorker(CFG, client=client)
    w.start_chronicle([], NAMES, now=0.0)  # blocks until release
    w.start_incantations(CLASSES, NAMES, now=0.0)  # also blocks: both run at once
    assert {t.name for t in threading.enumerate()} >= {"spark-chronicle", "spark-incantations"}
    assert all(t.daemon for t in threading.enumerate() if t.name.startswith("spark-"))
    client.release.set()
    out: dict = {}
    end = time.monotonic() + 2.0
    while len(out) < 2 and time.monotonic() < end:
        out.update(w.poll(0.5))
        time.sleep(0.01)
    assert out["chronicle"] == "A tale." and out["incantations"][0] == GOOD["0"]
    w.close()


def test_close_returns_at_once_and_drops_jobs():
    client = BlockingClient("never read")
    w = AiWorker(CFG, client=client)
    w.start_chronicle([], NAMES, now=0.0)
    started = time.monotonic()
    w.close()
    w.close()  # idempotent
    assert time.monotonic() - started < 0.1 and w.closed
    w.start_incantations(CLASSES, NAMES, now=0.0)  # no-op after close
    client.release.set()
    time.sleep(0.05)
    assert w.poll(100.0) == []


QUIT_SCRIPT = """
import sys, threading, time
from magic_box.ai.worker import AiWorker
from magic_box.core.config import load_config

class Hung:
    def available(self):
        return True
    def complete(self, system, user):
        time.sleep(30)  # a Spark call stuck in flight
        return ""

w = AiWorker(load_config(sys.argv[1]), client=Hung())
w.start_incantations({0: "fire_mage", 1: "lightning_mage"}, {0: "A", 1: "B"}, now=0.0)
time.sleep(0.1)
w.close()
"""


def test_interpreter_exits_at_once_with_a_call_in_flight():
    """A ThreadPoolExecutor worker is joined at exit; the old worker held the quit 8 s."""
    config = Path(__file__).resolve().parents[2] / "config.yaml"
    started = time.monotonic()
    done = subprocess.run([sys.executable, "-c", QUIT_SCRIPT, str(config)], timeout=20)
    assert done.returncode == 0
    assert time.monotonic() - started < 5.0  # interpreter start-up plus imports, not 30 s


def test_offline_resolves_to_fallbacks_without_calling_spark(capsys):
    client = BlockingClient(GOOD)
    w = AiWorker(CFG, client=client)
    w.set_offline(True)
    w.start_incantations(CLASSES, NAMES, now=0.0)
    assert wait_poll(w, 0.1) == [("incantations", fallback_incantations(CLASSES, CFG))]
    assert "network check failed" in capsys.readouterr().err
    w.close()
