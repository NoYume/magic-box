"""Tests for the non-blocking Spark worker.

Owner: Nikhil
"""

import copy
import json
import threading
import time
from pathlib import Path

from magic_box.ai.chronicle import template_chronicle
from magic_box.ai.incantations import fallback_incantations
from magic_box.ai.worker import AiWorker
from magic_box.core.config import load_config
from tests.ai.fakes import FakeClient
from tests.ai.test_incantations import GOOD

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")
CLASSES, NAMES = {0: "fire_mage", 1: "lightning_mage"}, {0: "Ada", 1: "Bo"}


class BlockingClient:
    """`complete` blocks until `release` is set, then returns the reply."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.release = threading.Event()

    def complete(self, system: str, user: str) -> str:
        self.release.wait(5.0)
        return self.reply


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
    client = BlockingClient("A tale.")
    w = AiWorker(CFG, client=client)
    w.start_chronicle([], NAMES, now=0.0)
    w.start_chronicle([], {0: "Cy", 1: "Di"}, now=1.0)
    client.release.set()
    out = wait_poll(w, 1.5)
    assert out == [("chronicle", "A tale.")] and w.poll(2.0) == []
    w.close()


def test_disabled_resolves_to_fallbacks():
    cfg = copy.deepcopy(CFG)
    cfg["ai"]["enabled"] = False
    w = AiWorker(cfg)
    w.start_chronicle([], NAMES, now=0.0)
    assert wait_poll(w, 0.1) == [("chronicle", template_chronicle([], NAMES, cfg))]
    w.close()
