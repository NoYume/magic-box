"""Fake ZED tracker for front-end dev without the Jetson: same wire format as tracker.py.

Streams two desk-scale body skeletons (one leans in and out, one dodges side to side), a matching
synthetic camera frame, and a depth map in which player 1's hand repeatedly thrusts toward the
camera. MediaPipe will not find hands in these drawn frames; use it to check the transport,
body slots / posture, depth sampling and alignment (debug view, key D).
For scripted gameplay without a camera use the browser demo source: ?src=demo.

    py fake_tracker.py            # then open http://localhost:5173/?src=zed&ws=ws://localhost:8765
"""

import asyncio
import json
import math
import struct
import time

import cv2
import numpy as np
import websockets
from debug_log import DEFAULT_LOG_DIR, DebugLog, chain_http, receive
from static_site import DEFAULT_GAME_DIR, as_process_request, static_site

PORT = 8765
FPS = 30
FRAME_W, FRAME_H = 960, 600  # ZED X SVGA aspect (16:10)
DEPTH_W, DEPTH_H = 160, 100
MSG_FRAME = 0x01
MSG_DEPTH = 0x02
FRAME_HEADER = struct.Struct("<BBI")  # type, reserved, capture seq
DEPTH_HEADER = struct.Struct("<BBIHH")  # type, reserved, capture seq, width, height
WALL_MM = 0  # the back wall is beyond max range, so it reads as unknown
HAND_REST_MM = 650
THRUST_MM = 250
PLAYERS = (0.3, 0.7)  # torso centers, normalized x
BODY_Z = 0.9
SHOULDER_HALF = 0.09  # normalized half shoulder width at BODY_Z
NECK_Y = 0.42
HAND = (0.36, 0.42, 0.045, 0.07)  # player 1's hand: cx, cy, rx, ry (normalized)


def ellipse_mask(w, h, cx, cy, rx, ry):
    ys, xs = np.mgrid[0:h, 0:w]
    return ((xs / w - cx) / rx) ** 2 + ((ys / h - cy) / ry) ** 2 < 1


def thrust_mm(t):
    return THRUST_MM * max(0.0, math.sin(t * 2.0)) ** 3


def player_pose(index, t):
    """(center x, torso z): player 0 leans in and back, player 1 dodges sideways every few seconds."""
    cx = PLAYERS[index]
    if index == 0:
        return cx, BODY_Z - 0.16 * math.sin(t * 0.7)
    dodge = 0.06 if (t % 4.0) < 0.8 else 0.0
    return cx + dodge, BODY_Z


def fake_bodies(t, seq):
    point = lambda x, y, z: {"x": round(x, 4), "y": round(y, 4), "z": round(z, 3)}
    bodies = []
    for index in range(len(PLAYERS)):
        cx, z = player_pose(index, t)
        half = SHOULDER_HALF * BODY_Z / z
        bodies.append({
            "id": index + 1,
            "kp": {
                "head": point(cx, NECK_Y - 0.17, z),
                "neck": point(cx, NECK_Y, z),
                "l_shoulder": point(cx + half, NECK_Y + 0.03, z),
                "r_shoulder": point(cx - half, NECK_Y + 0.03, z),
                "l_wrist": None,
                "r_wrist": point(HAND[0], HAND[1], (HAND_REST_MM - thrust_mm(t)) / 1000) if index == 0 else None,
                "pelvis": None,
            },
        })
    return json.dumps({"type": "bodies", "seq": seq, "t": int(time.time() * 1000), "bodies": bodies})


def fake_depth(t, seq):
    depth = np.full((DEPTH_H, DEPTH_W), WALL_MM, np.uint16)
    for index in range(len(PLAYERS)):
        cx, z = player_pose(index, t)
        depth[ellipse_mask(DEPTH_W, DEPTH_H, cx, 0.78, 0.13, 0.36)] = int(z * 1000)
    depth[ellipse_mask(DEPTH_W, DEPTH_H, *HAND)] = HAND_REST_MM - thrust_mm(t)
    return DEPTH_HEADER.pack(MSG_DEPTH, 0, seq, DEPTH_W, DEPTH_H) + depth.astype("<u2").tobytes()


def fake_frame(t, seq):
    ramp = np.linspace(70, 30, FRAME_H, dtype=np.float32)[:, None, None]
    frame = np.broadcast_to(ramp * np.array([1.0, 0.8, 0.7]), (FRAME_H, FRAME_W, 3)).astype(np.uint8).copy()
    for index in range(len(PLAYERS)):
        cx, z = player_pose(index, t)
        grow = BODY_Z / z
        cv2.ellipse(frame, (int(cx * FRAME_W), int(0.78 * FRAME_H)), (int(0.13 * FRAME_W * grow), int(0.36 * FRAME_H)), 0, 0, 360, (95, 80, 70), -1)
        cv2.circle(frame, (int(cx * FRAME_W), int((NECK_Y - 0.17) * FRAME_H)), int(0.06 * FRAME_W * grow), (120, 105, 95), -1)
    scale = 1 + thrust_mm(t) / THRUST_MM * 0.4  # the hand looks bigger as it nears the camera
    cx, cy, rx, ry = HAND
    cv2.ellipse(frame, (int(cx * FRAME_W), int(cy * FRAME_H)), (int(rx * FRAME_W * scale), int(ry * FRAME_H * scale)), 0, 0, 360, (150, 170, 200), -1)
    cv2.putText(frame, "FAKE TRACKER", (24, FRAME_H - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (170, 170, 170), 1, cv2.LINE_AA)
    return FRAME_HEADER.pack(MSG_FRAME, 0, seq) + cv2.imencode(".jpg", frame)[1].tobytes()


async def main():
    clients = set()
    debug_log = DebugLog(DEFAULT_LOG_DIR)
    hello = json.dumps({"type": "hello", "frame": [FRAME_W, FRAME_H], "depth": [DEPTH_W, DEPTH_H]})

    async def handler(ws):
        clients.add(ws)
        await ws.send(hello)
        try:
            await receive(ws, debug_log)
        finally:
            clients.discard(ws)

    process_request = as_process_request(chain_http(debug_log, static_site(DEFAULT_GAME_DIR)))
    async with websockets.serve(handler, "0.0.0.0", PORT, process_request=process_request):
        print(f"fake tracker on ws://localhost:{PORT}, game page on http://localhost:{PORT}/")
        start = time.time()
        seq = 0
        while True:
            t = time.time() - start
            seq = (seq + 1) % 2**32  # one capture: depth, frame and bodies share the seq
            depth, frame, bodies = fake_depth(t, seq), fake_frame(t, seq), fake_bodies(t, seq)
            websockets.broadcast(clients, depth)
            websockets.broadcast(clients, frame)
            websockets.broadcast(clients, bodies)
            debug_log.on_capture(frame, depth, bodies)
            await asyncio.sleep(1 / FPS)


if __name__ == "__main__":
    asyncio.run(main())
