"""Tests for jetson/debug_log.py: the Arena tracker's detection debug log.

Owner: Daniel
"""

import asyncio
import json
import struct
import sys
from http import HTTPStatus
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jetson"))
import debug_log  # noqa: E402

FRAME_HEADER = struct.Struct("<BBI")
DEPTH_HEADER = struct.Struct("<BBIHH")
FRAME_W, FRAME_H = 96, 60
DEPTH_W, DEPTH_H = 16, 10
DEPTH_MM = 700


def frame_msg(seq):
    image = np.full((FRAME_H, FRAME_W, 3), 80, np.uint8)
    return FRAME_HEADER.pack(1, 0, seq) + cv2.imencode(".jpg", image)[1].tobytes()


def depth_msg(seq):
    depth = np.full((DEPTH_H, DEPTH_W), DEPTH_MM, "<u2")
    return DEPTH_HEADER.pack(2, 0, seq, DEPTH_W, DEPTH_H) + depth.tobytes()


def bodies_msg(seq):
    def point(x, y):
        return {"x": x, "y": y, "z": 0.8}

    kp = {
        "head": point(0.3, 0.2),
        "neck": point(0.3, 0.35),
        "l_shoulder": point(0.38, 0.4),
        "r_shoulder": point(0.22, 0.4),
        "l_wrist": point(0.4, 0.6),
        "r_wrist": None,
        "pelvis": None,
    }
    return json.dumps({"type": "bodies", "seq": seq, "t": 0, "bodies": [{"id": 7, "kp": kp}]})


def record(seq):
    lm = [[0.4 + i * 0.005, 0.5 + i * 0.005] for i in range(21)]
    hand = {
        "id": 1,
        "slot": 0,
        "handedness": "Right",
        "sign": "ward",
        "frameSign": "ward",
        "frameScore": 0.8,
        "vote": 1.0,
        "scores": {"ward": 0.8, "gather": 0.0, "aim": 0.1},
        "facing": 0.7,
        "depth": 0.6,
        "lm": lm,
    }
    return {
        "type": "debug",
        "seq": seq,
        "t": 0,
        "phase": "attract",
        "stats": {"render": 60.0, "hands": 28.0},
        "hands": [hand],
        "rejected": [
            {"reason": "out of play range", "handedness": "Left", "depth": None, "lm": lm}
        ],
        "triangles": [0, 0],
        "bodies": [{"id": 7, "z": 0.8, "stance": "neutral", "lean": 0, "side": 0}, None],
        "rejectedBodies": [],
    }


def feed(log, seqs):
    for seq in seqs:
        log.on_capture(frame_msg(seq), depth_msg(seq), bodies_msg(seq))


def only_session(root):
    sessions = [p for p in root.iterdir() if p.is_dir()]
    assert len(sessions) == 1, sessions
    return sessions[0]


def test_nothing_is_written_until_the_browser_sends_a_record(tmp_path):
    log = debug_log.DebugLog(tmp_path)
    feed(log, range(1, 41))
    assert list(tmp_path.iterdir()) == []


def test_session_holds_records_bodies_and_sampled_frames(tmp_path):
    log = debug_log.DebugLog(tmp_path)
    log.on_message(json.dumps(record(1)), "10.0.0.2")
    feed(log, range(1, 32))
    log.close()
    session = only_session(tmp_path)
    lines = (session / "telemetry.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["client"] == "10.0.0.2"
    assert len((session / "zed.jsonl").read_text().splitlines()) == 31
    saved = sorted(p.name for p in (session / "frames").glob("*.jpg"))
    expected = [f"{s:010d}.jpg" for s in range(1, 32) if s % debug_log.KEEP_EVERY == 0]
    assert saved == expected


def test_mark_keeps_every_ring_frame_with_its_depth_map(tmp_path):
    log = debug_log.DebugLog(tmp_path)
    feed(log, range(1, 21))  # before logging started: only in the ring
    log.on_message(json.dumps(record(20)), "10.0.0.2")
    log.on_message(json.dumps({"type": "mark", "seq": 20, "t": 0}), "10.0.0.2").join(5)
    log.close()
    frames = only_session(tmp_path) / "frames"
    assert len(list(frames.glob("*.jpg"))) == 20
    depth = cv2.imread(str(frames / f"{20:010d}.depth.png"), cv2.IMREAD_UNCHANGED)
    assert depth.dtype == np.uint16 and depth.shape == (DEPTH_H, DEPTH_W)
    assert int(depth[0, 0]) == DEPTH_MM
    kinds = [json.loads(line)["type"] for line in (frames.parent / "telemetry.jsonl").open()]
    assert kinds == ["debug", "mark"]


def test_idle_session_closes_and_the_next_record_opens_a_new_one(tmp_path):
    log = debug_log.DebugLog(tmp_path, idle_s=-1)
    log.on_message(json.dumps(record(1)), "a")
    feed(log, [1])  # idle: closes the session
    log.on_message(json.dumps(record(2)), "a")
    log.close()
    assert len([p for p in tmp_path.iterdir() if p.is_dir()]) == 2


def test_oldest_sessions_are_pruned_past_the_size_cap(tmp_path):
    for name in ("20260101-000000", "20260102-000000"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "telemetry.jsonl").write_bytes(b"x" * 1000)
    log = debug_log.DebugLog(tmp_path, max_bytes=1500)
    log.on_message(json.dumps(record(1)), "a")
    log.close()
    names = sorted(p.name for p in tmp_path.iterdir())
    assert "20260101-000000" not in names and "20260102-000000" in names


def test_annotate_draws_on_the_frame():
    jpeg = frame_msg(1)[FRAME_HEADER.size :]
    plain = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    out = debug_log.annotate(jpeg, bodies_msg(1), record(1))
    drawn = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
    assert drawn.shape == plain.shape
    assert np.abs(drawn.astype(int) - plain.astype(int)).sum() > 0


def test_live_routes(tmp_path):
    log = debug_log.DebugLog(tmp_path)
    assert log.http("/debug/frame.jpg")[0] == HTTPStatus.SERVICE_UNAVAILABLE
    assert log.http("/index.html") is None
    feed(log, [1, 2])
    log.on_message(json.dumps(record(2)), "a")
    status, headers, body = log.http("/debug/frame.jpg")
    assert status == HTTPStatus.OK and headers["Content-Type"] == "image/jpeg" and body
    status, headers, body = log.http("/debug/annotated.jpg?x=1")
    assert status == HTTPStatus.OK and headers["Content-Type"] == "image/jpeg"
    status, _, body = log.http("/debug/state.json")
    state = json.loads(body)
    assert status == HTTPStatus.OK and state["record"]["seq"] == 2 and state["latest_seq"] == 2
    log.close()


def test_chain_http_serves_debug_routes_before_the_game_page(tmp_path):
    log = debug_log.DebugLog(tmp_path)
    feed(log, [1])
    page = (HTTPStatus.OK, {"Content-Type": "text/html"}, b"page")
    hook = debug_log.chain_http(log, lambda path, headers: page)
    assert hook("/debug/frame.jpg", {})[1]["Content-Type"] == "image/jpeg"
    assert hook("/index.html", {}) == page
    assert hook("/debug/frame.jpg", {"Upgrade": "websocket"}) == page  # handshakes pass through
    assert debug_log.chain_http(None, None)("/debug/frame.jpg", {}) is None


def test_receive_logs_text_messages_until_the_client_leaves(tmp_path):
    class FakeSocket:
        remote_address = ("10.0.0.9", 5000)

        def __aiter__(self):
            async def messages():
                yield json.dumps(record(3))
                yield b"\x00binary is ignored"

            return messages()

    log = debug_log.DebugLog(tmp_path)
    asyncio.run(debug_log.receive(FakeSocket(), log))
    assert log.latest_record["seq"] == 3 and log.latest_record["client"] == "10.0.0.9"
    log.close()


def two_tone_jpeg():
    image = np.zeros((FRAME_H, FRAME_W, 3), np.uint8)
    image[:, FRAME_W // 2 :] = 255  # camera right half bright
    return cv2.imencode(".jpg", image)[1].tobytes()


def test_annotate_flips_only_when_the_game_showed_a_mirror():
    cases = (
        (None, False),
        ({**record(1), "mirror": False}, False),
        ({**record(1), "mirror": True}, True),
    )
    for rec, bright_on_left in cases:
        out = debug_log.annotate(two_tone_jpeg(), None, rec)
        drawn = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
        assert (drawn[-3, 3].mean() > 128) == bright_on_left, rec and rec["mirror"]
