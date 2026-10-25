"""Browser output (no monitor at the venue): render/web_display.py.

Owner: Adetola + Nikhil
"""

import copy
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from magic_box.core.config import load_config
from magic_box.render.web_display import WebDisplay
from magic_box.replay.fake_input import FakePlayers
from tests.factories import make_view

CFG = load_config(Path(__file__).resolve().parents[2] / "config.yaml")


@pytest.fixture
def web():
    cfg = copy.deepcopy(CFG)
    cfg["display"]["fullscreen"] = True  # run_demo.sh passes --fullscreen on the Jetson
    display = WebDisplay(cfg, port=0)
    yield display
    display.close()


def url(display, path):
    return f"http://127.0.0.1:{display.port}{path}"


def post_key(display, key, down):
    body = json.dumps({"key": key, "down": down}).encode()
    request = urllib.request.Request(url(display, "/key"), data=body, method="POST")
    with urllib.request.urlopen(request, timeout=2) as response:
        assert response.status == 204


def wait_for_jpeg(display, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url(display, "/frame.jpg"), timeout=2) as response:
                return response.read()
        except urllib.error.HTTPError as error:  # 503 until the first frame is encoded
            assert error.code == 503
        time.sleep(0.05)
    raise AssertionError("no frame was encoded")


def test_page_shows_the_stream_and_forwards_keys(web):
    with urllib.request.urlopen(url(web, "/"), timeout=2) as response:
        page = response.read().decode()
    assert "/stream.mjpg" in page and "/key" in page


def test_browser_keys_reach_the_game(web):
    post_key(web, "f", True)
    post_key(web, "1", True)
    held, quit_requested = web.pump()
    assert held == frozenset({"f", "1"}) and not quit_requested
    post_key(web, "f", False)
    assert web.pump()[0] == frozenset({"1"})


def test_f1_toggles_the_overlay_and_escape_quits(web):
    assert not web.debug
    post_key(web, "f1", True)
    post_key(web, "f1", False)
    assert web.pump()[1] is False and web.debug
    post_key(web, "escape", True)
    assert web.pump()[1] is True


def test_drawn_frames_stream_as_jpeg(web):
    states, frame = FakePlayers(CFG).step(frozenset(), 0.0, 0.0)
    web.draw(make_view(), frame, {s.slot: s for s in states}, fps=60.0)
    jpeg = wait_for_jpeg(web)
    assert jpeg[:2] == b"\xff\xd8"
    with urllib.request.urlopen(url(web, "/stream.mjpg"), timeout=2) as response:
        assert response.headers["Content-Type"].startswith("multipart/x-mixed-replace")
        head = response.read(200)
    assert b"Content-Type: image/jpeg" in head
