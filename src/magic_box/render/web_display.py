"""Browser output for a venue with no monitor: the game drawn off-screen and streamed to a browser.

Owner: Adetola + Nikhil

`WebDisplay` is the `Window` (same drawing, same `Display` protocol for the game loop) with the
SDL dummy video driver. After each draw it hands a copy of the screen to an encoder thread, at most
`display.web.stream_fps` times a second (latest frame wins), and a small HTTP server serves:

    /              the page: the stream filling the browser, key presses sent to the game
    /stream.mjpg   multipart JPEG stream (any browser shows it in an <img>)
    /frame.jpg     the newest frame
    /key           POST {"key": "<pygame key name>", "down": true|false} (or {"reset": true})

Keys held in the browser replace pygame's keyboard; the debug-overlay key toggles the overlay and
the quit key ends the game, as in the window. Encoding uses cv2 (imported in the encoder thread),
which releases the GIL, so the 60 fps loop keeps its pace.
"""

import json
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pygame

from magic_box.render.window import Window

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Magic Box</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  html, body { margin: 0; height: 100%; background: #0b0814; overflow: hidden; }
  img { width: 100vw; height: 100vh; object-fit: contain; display: block; }
  #hint { position: fixed; top: 8px; right: 12px; font: 12px monospace; color: #aaa;
          background: rgb(0 0 0 / 0.4); padding: 4px 8px; border-radius: 4px; }
</style></head>
<body>
<img src="/stream.mjpg" alt="Magic Box">
<div id="hint">double-click: fullscreen · F1: depth overlay · Esc: quit</div>
<script>
  const NAMES = { " ": "space", ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up",
                  ArrowDown: "down", Escape: "escape", Enter: "return", Backspace: "backspace",
                  Tab: "tab" };
  const send = (body) => fetch("/key", { method: "POST", body: JSON.stringify(body) });
  const name = (e) => NAMES[e.key] ?? e.key.toLowerCase();
  addEventListener("keydown", (e) => {
    e.preventDefault();
    if (!e.repeat) send({ key: name(e), down: true });
  });
  addEventListener("keyup", (e) => { e.preventDefault(); send({ key: name(e), down: false }); });
  addEventListener("blur", () => send({ reset: true }));
  addEventListener("dblclick", () => document.fullscreenElement
    ? document.exitFullscreen() : document.documentElement.requestFullscreen());
  setTimeout(() => (document.getElementById("hint").style.display = "none"), 8000);
</script>
</body></html>
"""


class _Stream:
    """Latest encoded frame, shared by the encoder thread and every HTTP client."""

    def __init__(self, width: int, quality: int) -> None:
        self.width = width
        self.quality = quality
        self.cond = threading.Condition()
        self.pending: tuple[bytes, int, int] | None = None  # raw RGB, width, height
        self.jpeg: bytes | None = None
        self.seq = 0
        self.running = True

    def submit(self, rgb: bytes, width: int, height: int) -> None:
        with self.cond:
            self.pending = (rgb, width, height)
            self.cond.notify_all()

    def encode_forever(self) -> None:
        import cv2

        while True:
            with self.cond:
                while self.running and self.pending is None:
                    self.cond.wait()
                if not self.running:
                    return
                rgb, width, height = self.pending
                self.pending = None
            image = np.frombuffer(rgb, np.uint8).reshape(height, width, 3)
            if width > self.width:
                size = (self.width, round(height * self.width / width))
                image = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
            ok, jpeg = cv2.imencode(
                ".jpg",
                cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, self.quality],
            )
            if ok:
                with self.cond:
                    self.jpeg = jpeg.tobytes()
                    self.seq += 1
                    self.cond.notify_all()

    def stop(self) -> None:
        with self.cond:
            self.running = False
            self.cond.notify_all()


class WebDisplay(Window):
    def __init__(self, cfg, port: int | None = None) -> None:
        web = cfg["display"]["web"]
        # Off-screen: no fullscreen or vsync (run_demo.sh passes --fullscreen on the Jetson).
        cfg = {**cfg, "display": {**cfg["display"], "fullscreen": False, "vsync": False}}
        super().__init__(cfg, headless=True)
        self._stream = _Stream(web["stream_width"], web["jpeg_quality"])
        self._min_interval_s = 1.0 / web["stream_fps"]
        self._last_submit = 0.0
        self._lock = threading.Lock()
        self._held: set[str] = set()
        self._presses: deque[str] = deque()
        self._encoder = threading.Thread(target=self._stream.encode_forever, daemon=True)
        self._encoder.start()
        address = (web["host"], web["port"] if port is None else port)
        try:
            self._server = ThreadingHTTPServer(address, _handler(self))
        except OSError as exc:
            self._stream.stop()
            super().close()
            raise OSError(f"web: cannot listen on {address} ({exc}); set display.web.port") from exc
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        print(f"web: open http://<this-host>:{self.port}/ in a browser", flush=True)

    def key_event(self, key: str, down: bool) -> None:
        with self._lock:
            if down:
                self._held.add(key)
                self._presses.append(key)
            else:
                self._held.discard(key)

    def release_all(self) -> None:
        with self._lock:
            self._held.clear()

    def pump(self) -> tuple[frozenset[str], bool]:
        pygame.event.pump()
        quit_requested = False
        with self._lock:
            presses, self._presses = list(self._presses), deque()
            held = frozenset(self._held)
        for key in presses:
            if key == self.cfg["keys"]["quit"]:
                quit_requested = True
            elif key == self.cfg["keys"]["debug_overlay"]:
                self.debug = not self.debug
        return held, quit_requested

    def draw(self, view, frame, states, fps: float, dropped: int = 0) -> None:
        super().draw(view, frame, states, fps, dropped)
        now = time.monotonic()
        if now - self._last_submit >= self._min_interval_s:
            self._last_submit = now
            width, height = self.screen.get_size()
            self._stream.submit(pygame.image.tobytes(self.screen, "RGB"), width, height)

    def close(self) -> None:
        self._stream.stop()
        self._server.shutdown()
        self._server.server_close()
        super().close()


def _handler(display: WebDisplay) -> type[BaseHTTPRequestHandler]:
    stream = display._stream

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # one line per request is too noisy at 30 fps
            pass

        def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", PAGE.encode())
            elif path == "/frame.jpg":
                jpeg = stream.jpeg
                if jpeg is None:
                    self._send(HTTPStatus.SERVICE_UNAVAILABLE, "text/plain", b"no frame yet\n")
                else:
                    self._send(HTTPStatus.OK, "image/jpeg", jpeg)
            elif path == "/stream.mjpg":
                self._stream_frames()
            else:
                self._send(HTTPStatus.NOT_FOUND, "text/plain", b"not found\n")

        def _stream_frames(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seen = -1
            try:
                while stream.running:
                    with stream.cond:
                        last = seen
                        stream.cond.wait_for(
                            lambda last=last: stream.seq != last or not stream.running, 1.0
                        )
                        jpeg, seen = stream.jpeg, stream.seq
                    if jpeg is None:
                        continue
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                        + jpeg
                        + b"\r\n"
                    )
            except (BrokenPipeError, ConnectionResetError):
                pass  # the browser went away

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/key":
                self._send(HTTPStatus.NOT_FOUND, "text/plain", b"not found\n")
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            except ValueError:
                self._send(HTTPStatus.BAD_REQUEST, "text/plain", b"bad json\n")
                return
            if body.get("reset"):
                display.release_all()
            elif isinstance(body.get("key"), str):
                display.key_event(body["key"], bool(body.get("down")))
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()

    return Handler
