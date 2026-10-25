"""Tests for jetson/static_site.py: the game page and the websockets HTTP hook adapter.

Owner: Daniel
"""

import sys
from http import HTTPStatus
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jetson"))
import static_site  # noqa: E402


def make_site(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.js").write_text("export {};")
    (tmp_path.parent / "secret.txt").write_text("no")
    return static_site.static_site(tmp_path)


def test_serves_files_redirects_root_and_blocks_traversal(tmp_path):
    site = make_site(tmp_path)
    assert site("/", {})[:2] == (HTTPStatus.FOUND, {"Location": "/?src=zed"})
    status, headers, body = site("/src/main.js?v=1", {})
    assert status == HTTPStatus.OK and headers["Content-Type"].startswith("text/javascript")
    assert site("/?src=zed", {})[2] == b"<html></html>"
    assert site("/../secret.txt", {})[0] == HTTPStatus.NOT_FOUND
    assert site("/%2e%2e/secret.txt", {})[0] == HTTPStatus.NOT_FOUND
    assert site("/src/main.js", {"Upgrade": "websocket"}) is None


def test_hook_speaks_the_legacy_api(tmp_path):
    hook = static_site.as_process_request(make_site(tmp_path))
    status, headers, body = hook("/index.html", {})
    assert status == HTTPStatus.OK and headers["Content-Length"] == str(len(body))
    assert hook("/index.html", {"Upgrade": "websocket"}) is None


def test_hook_speaks_the_new_api(tmp_path):
    class Request:
        path = "/src/main.js"
        headers = {}

    hook = static_site.as_process_request(make_site(tmp_path))
    response = hook(object(), Request())
    assert response.status_code == 200 and response.body == b"export {};"
    assert response.headers["Content-Type"].startswith("text/javascript")
    Request.headers = {"Upgrade": "websocket"}
    assert hook(object(), Request()) is None
