"""Serves the browser game over HTTP on the tracker's WebSocket port, so one port carries both.

websockets calls a `process_request` hook for every incoming HTTP request. A WebSocket upgrade goes
on to the handshake; any other GET is answered with a file from the game directory. Responders
here take (path, headers); as_process_request() adapts one to whichever websockets is installed.
Used by tracker.py and fake_tracker.py.

Owner: Daniel
"""

import mimetypes
from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlsplit

DEFAULT_GAME_DIR = Path(__file__).resolve().parent.parent / "game"
# The game defaults to the webcam source; served from the box, it should read the ZED stream.
START_PAGE = "/?src=zed"
# Browsers refuse module scripts served without a JavaScript MIME type.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
}


def content_type(path):
    guessed = mimetypes.guess_type(path.name)[0]
    return CONTENT_TYPES.get(path.suffix) or guessed or "application/octet-stream"


def static_site(root, start_page=START_PAGE):
    """Return respond(path, headers) serving the files under `root` (see as_process_request)."""
    root = Path(root).resolve()

    def respond(path, headers):
        if headers.get("Upgrade", "").lower() == "websocket":
            return None  # the camera stream: continue with the WebSocket handshake
        if path == "/":
            return HTTPStatus.FOUND, {"Location": start_page}, b""
        url_path = unquote(path.split("?", 1)[0]).lstrip("/") or "index.html"
        file = (root / url_path).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            return HTTPStatus.NOT_FOUND, {"Content-Type": "text/plain"}, b"not found\n"
        headers = {"Content-Type": content_type(file), "Cache-Control": "no-cache"}
        return HTTPStatus.OK, headers, file.read_bytes()

    return respond


def as_process_request(respond):
    """Adapt `respond(path, headers) -> (status, headers, body) | None` to websockets' hook.

    websockets 13 (pinned in the Docker image) calls process_request(path, headers) and takes that
    tuple; 14+ (the repo's uv env) calls process_request(connection, request) and wants a Response.
    """

    def process_request(first, second):
        if isinstance(first, str):
            return _with_length(respond(first, second))
        response = _with_length(respond(second.path, second.headers))
        if response is None:
            return None
        from websockets.datastructures import Headers
        from websockets.http11 import Response

        status, headers, body = response
        return Response(int(status), HTTPStatus(status).phrase, Headers(headers), body)

    return process_request


def _with_length(response):
    if response is None:
        return None
    status, headers, body = response
    return status, {**headers, "Content-Length": str(len(body)), "Connection": "close"}, body


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def same_origin_websockets(respond):
    """Refuse WebSocket handshakes started by other sites' pages, then defer to `respond`.

    Browsers apply no same-origin policy to WebSockets, so without this any page a player has open
    could read the camera stream or write to the debug log. Allowed: no Origin (scripts, not
    browsers), a page on the host the client used to reach the tracker (any port, so the dev
    server works too), and pages served from the client's own machine.
    """

    def guarded(path, headers):
        origin = headers.get("Origin")
        if origin and headers.get("Upgrade", "").lower() == "websocket":
            origin_host = (urlsplit(origin).hostname or "").lower()
            tracker_host = (urlsplit(f"//{headers.get('Host', '')}").hostname or "").lower()
            if origin_host != tracker_host and origin_host not in LOCAL_HOSTS:
                return (
                    HTTPStatus.FORBIDDEN,
                    {"Content-Type": "text/plain"},
                    b"cross-origin refused\n",
                )
        return respond(path, headers) if respond else None

    return guarded
