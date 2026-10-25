"""Debug log for tuning detections on the real rig.

Owner: Daniel

The game sends what its vision pipeline saw for each camera capture when its debug log is on (?log=1
or key L; game/src/debug/telemetry.js): hand landmarks, sign scores and the finger features behind
them, depth, rejections, body slots and posture. Key B marks a bad moment. This module writes
those records next to the tracker's own data for the same captures (matched by seq):

    logs/<session>/telemetry.jsonl          browser records and marks, one JSON object per line
    logs/<session>/zed.jsonl                the tracker's bodies message for every capture
    logs/<session>/frames/<seq>.jpg         a raw frame every KEEP_EVERY captures; on a mark,
    logs/<session>/frames/<seq>.depth.png   every frame of the last RING_SECONDS and its depth (mm)

A session starts with the first browser message and ends after SESSION_IDLE_S without one. Old
sessions are deleted past MAX_LOG_BYTES. Three live routes answer on the tracker port:

    /debug/frame.jpg       newest raw camera frame
    /debug/annotated.jpg   newest browser record drawn on its own frame, oriented like the game
    /debug/state.json      newest browser record and session counters

Everything runs on the tracker's event loop except the mark dump, which uses a worker thread.
jetson/debug_report.py renders and summarizes a saved session.
"""

import collections
import json
import os
import shutil
import struct
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path

import cv2
import numpy as np
import websockets

DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
CAPTURE_FPS = 30
RING_SECONDS = 10
KEEP_EVERY = 15  # captures between saved frames while logging (2 per second at 30 fps)
SESSION_IDLE_S = 30
MAX_LOG_BYTES = 3 * 1024**3
FLUSH_S = 1.0
OPEN_DIR_MODE = 0o777  # the container writes as root; the host user must be able to delete logs
FRAME_HEADER = struct.Struct("<BBI")  # type, reserved, capture seq (docs/protocol.md)
DEPTH_HEADER = struct.Struct("<BBIHH")  # type, reserved, capture seq, width, height
JPEG_QUALITY = 85

SLOT_BGR = ((40, 140, 255), (255, 170, 60))  # P1 orange, P2 blue
REJECTED_BGR = (150, 150, 150)
TEXT_BGR = (240, 240, 240)
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.45
LINE_H = 16
# Same bones as game/src/vision/landmarks.js and game/src/render/debug-layer.js.
HAND_BONES = (
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
    (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
    (17, 18), (18, 19), (19, 20),
)  # fmt: skip
BODY_BONES = (
    ("head", "neck"), ("neck", "l_shoulder"), ("neck", "r_shoulder"),
    ("l_shoulder", "l_wrist"), ("r_shoulder", "r_wrist"), ("neck", "pelvis"),
)  # fmt: skip


def fmt(value, digits=2):
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "-"


def _text(image, text, origin, color):
    cv2.putText(image, text, origin, FONT, FONT_SCALE, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(image, text, origin, FONT, FONT_SCALE, color, 1, cv2.LINE_AA)


def _hand_lines(hand):
    scores = hand.get("scores") or {}
    ext = hand.get("ext") or {}
    return [
        f"P{hand['slot'] + 1} {hand.get('handedness', '?')[:1]} {hand.get('sign')}"
        f"  frame {hand.get('frameSign')} {fmt(hand.get('frameScore'))}"
        f"  vote {fmt(hand.get('vote'))}  z {fmt(hand.get('depth'))}m",
        "  ".join(f"{name} {fmt(score)}" for name, score in scores.items())
        + f"  facing {fmt(hand.get('facing'))}",
        "ext " + " ".join(f"{name[0]}{fmt(value)}" for name, value in ext.items()),
    ]


def annotate(jpeg, bodies_text=None, record=None):
    """Draw ZED skeletons and the browser's hand results on a frame, oriented like the game.

    Flipped only when the record says the game showed a mirror; raw camera view otherwise.
    """
    image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    mirror = bool((record or {}).get("mirror"))
    if mirror:
        image = cv2.flip(image, 1)
    height, width = image.shape[:2]

    def at(x, y):
        return round(((1 - x) if mirror else x) * width), round(y * height)

    body_slots = {}
    for slot, body in enumerate((record or {}).get("bodies") or []):
        if body:
            body_slots[body["id"]] = slot
    for body in json.loads(bodies_text).get("bodies", []) if bodies_text else []:
        slot = body_slots.get(body["id"])
        color = SLOT_BGR[slot] if slot is not None else REJECTED_BGR
        kp = body["kp"]
        for a, b in BODY_BONES:
            if kp.get(a) and kp.get(b):
                pa, pb = at(kp[a]["x"], kp[a]["y"]), at(kp[b]["x"], kp[b]["y"])
                cv2.line(image, pa, pb, color, 2, cv2.LINE_AA)
        for point in kp.values():
            if point:
                cv2.circle(image, at(point["x"], point["y"]), 5, color, 2, cv2.LINE_AA)
        anchor = kp.get("head") or kp.get("neck")
        if anchor:
            seat = f"P{slot + 1}" if slot is not None else "not seated"
            x, y = at(anchor["x"], anchor["y"])
            label = f"body #{body['id']} {seat} z {fmt(anchor['z'])}m"
            _text(image, label, (x - 60, y - 14), color)

    for hand in (record or {}).get("hands", []):
        _draw_hand(image, at, hand["lm"], SLOT_BGR[hand["slot"]], _hand_lines(hand))
    for hand in (record or {}).get("rejected", []):
        label = f"rejected: {hand.get('reason')}  z {fmt(hand.get('depth'))}m"
        _draw_hand(image, at, hand["lm"], REJECTED_BGR, [label])

    if record:
        stats = record.get("stats") or {}
        header = (
            f"seq {record.get('seq')}  {record.get('phase')}  hands {fmt(stats.get('hands'), 0)} Hz"
            f"  render {fmt(stats.get('render'), 0)} fps"
            f"  tracker {fmt(stats.get('tracker'), 0)} fps"
        )
    else:
        header = "no browser record for this frame (turn the game's debug log on: L or ?log=1)"
    _text(image, header, (8, 18), TEXT_BGR)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])[1].tobytes()


def _draw_hand(image, at, landmarks, color, lines):
    points = [at(x, y) for x, y in landmarks]
    for a, b in HAND_BONES:
        cv2.line(image, points[a], points[b], color, 2, cv2.LINE_AA)
    for point in points:
        cv2.circle(image, point, 3, TEXT_BGR, -1, cv2.LINE_AA)
    x, y = points[0]  # wrist
    for i, line in enumerate(lines):
        _text(image, line, (x - 80, y + 22 + i * LINE_H), color)


def _open_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, OPEN_DIR_MODE)
    return path


def _dir_bytes(path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def frame_name(seq):
    return f"{seq:010d}"


class Session:
    """One logging session directory with open line logs."""

    def __init__(self, root):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path, n = root / stamp, 1
        while path.exists():
            n += 1
            path = root / f"{stamp}-{n}"
        self.dir = _open_dir(path)
        self.frames = _open_dir(path / "frames")
        self.telemetry = (path / "telemetry.jsonl").open("a")
        self.zed = (path / "zed.jsonl").open("a")
        self.records = 0
        self.marks = 0
        self.flushed_at = time.monotonic()

    def write_message(self, message):
        self.telemetry.write(json.dumps(message, separators=(",", ":")) + "\n")
        self._maybe_flush()

    def write_bodies(self, text):
        self.zed.write(text + "\n")
        self._maybe_flush()

    def write_frame(self, seq, jpeg):
        (self.frames / f"{frame_name(seq)}.jpg").write_bytes(jpeg)

    def dump(self, captures):
        """Write every capture (frame and depth map) of a ring snapshot. Runs on a worker thread."""
        for seq, jpeg, depth_msg, _ in captures:
            self.write_frame(seq, jpeg)
            _, _, _, width, height = DEPTH_HEADER.unpack_from(depth_msg)
            depth = np.frombuffer(depth_msg, "<u2", width * height, DEPTH_HEADER.size)
            path = self.frames / f"{frame_name(seq)}.depth.png"
            cv2.imwrite(str(path), depth.reshape(height, width))

    def _maybe_flush(self):
        if time.monotonic() - self.flushed_at >= FLUSH_S:
            self.flush()

    def flush(self):
        self.telemetry.flush()
        self.zed.flush()
        self.flushed_at = time.monotonic()

    def close(self):
        self.telemetry.close()
        self.zed.close()


class DebugLog:
    def __init__(self, root, idle_s=SESSION_IDLE_S, max_bytes=MAX_LOG_BYTES):
        self.root = Path(root)
        self.idle_s = idle_s
        self.max_bytes = max_bytes
        self.ring = collections.deque(
            maxlen=RING_SECONDS * CAPTURE_FPS
        )  # (seq, jpeg, depth, bodies)
        self.session = None
        self.last_message_at = 0.0
        self.latest_record = None

    def on_capture(self, frame_msg, depth_msg, bodies_text):
        """Called for every capture the tracker broadcasts (binary messages as sent)."""
        seq = FRAME_HEADER.unpack_from(frame_msg)[2]
        jpeg = frame_msg[FRAME_HEADER.size :]
        self.ring.append((seq, jpeg, depth_msg, bodies_text))
        session = self._live_session()
        if session:
            session.write_bodies(bodies_text)
            if seq % KEEP_EVERY == 0:
                session.write_frame(seq, jpeg)

    def on_message(self, text, client):
        """A text message from a game client. Returns the dump thread for a mark, else None."""
        try:
            message = json.loads(text)
        except ValueError:
            return None
        if not isinstance(message, dict) or message.get("type") not in ("debug", "mark"):
            return None
        message.update(client=client, recv=round(time.time(), 3))
        session = self._live_session() or self._start_session()
        self.last_message_at = time.monotonic()
        session.write_message(message)
        if message["type"] == "debug":
            session.records += 1
            self.latest_record = message
            return None
        session.marks += 1
        session.flush()
        captures = list(self.ring)
        print(f"[debug] mark {session.marks} at seq {message.get('seq')}: {len(captures)} frames")
        thread = threading.Thread(target=session.dump, args=(captures,), daemon=True)
        thread.start()
        return thread

    def http(self, path):
        """Response for a /debug/ route as (status, headers, body), or None for other paths."""
        route = path.split("?", 1)[0]
        if not route.startswith("/debug/"):
            return None
        if route == "/debug/state.json":
            body = json.dumps(self.state()).encode()
            return (
                HTTPStatus.OK,
                {"Content-Type": "application/json", "Cache-Control": "no-store"},
                body,
            )
        if route not in ("/debug/frame.jpg", "/debug/annotated.jpg"):
            return HTTPStatus.NOT_FOUND, {"Content-Type": "text/plain"}, b"not found\n"
        if not self.ring:
            return (
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"Content-Type": "text/plain"},
                b"no frames yet\n",
            )
        headers = {"Content-Type": "image/jpeg", "Cache-Control": "no-store"}
        if route == "/debug/frame.jpg":
            return HTTPStatus.OK, headers, self.ring[-1][1]
        record = self.latest_record
        capture = self._find(record["seq"]) if record else None
        if capture is None:
            capture, record = self.ring[-1], None
        return HTTPStatus.OK, headers, annotate(capture[1], capture[3], record)

    def state(self):
        session = self.session
        return {
            "session": str(session.dir) if session else None,
            "records": session.records if session else 0,
            "marks": session.marks if session else 0,
            "latest_seq": self.ring[-1][0] if self.ring else None,
            "ring_frames": len(self.ring),
            "record": self.latest_record,
        }

    def close(self):
        if self.session:
            self.session.close()
            self.session = None

    def _find(self, seq):
        for capture in reversed(self.ring):
            if capture[0] == seq:
                return capture
        return None

    def _live_session(self):
        if self.session and time.monotonic() - self.last_message_at > self.idle_s:
            print(f"[debug] session idle, closed: {self.session.dir}")
            self.close()
        return self.session

    def _start_session(self):
        _open_dir(self.root)
        self._prune()
        self.session = Session(self.root)
        print(f"[debug] logging to {self.session.dir}")
        return self.session

    def _prune(self):
        sessions = sorted(p for p in self.root.iterdir() if p.is_dir())
        sizes = {p: _dir_bytes(p) for p in sessions}
        total = sum(sizes.values())
        for path in sessions:
            if total <= self.max_bytes:
                break
            shutil.rmtree(path, ignore_errors=True)
            total -= sizes[path]
            print(f"[debug] pruned old session {path.name}")


def chain_http(debug_log, fallback):
    """respond(path, headers) for /debug/ routes, then `fallback` (the game page)."""

    def respond(path, headers):
        if debug_log and headers.get("Upgrade", "").lower() != "websocket":
            response = debug_log.http(path)
            if response:
                return response
        return fallback(path, headers) if fallback else None

    return respond


async def receive(ws, debug_log):
    """Read a game client's messages until it disconnects, logging the text ones when enabled."""
    client = ws.remote_address[0] if ws.remote_address else "?"
    try:
        async for message in ws:
            if debug_log and isinstance(message, str):
                debug_log.on_message(message, client)
    except websockets.ConnectionClosed:
        pass
