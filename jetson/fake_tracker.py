"""Fake ZED tracker for front-end dev without the Jetson: same wire format as tracker.py.

Streams a synthetic camera frame (two silhouettes at a desk) and a matching depth map in which
player 1's hand repeatedly thrusts toward the camera. MediaPipe will not find hands in these
drawn frames; use it to check the transport, depth sampling and alignment (debug view, key D).
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

PORT = 8765
FPS = 30
FRAME_W, FRAME_H = 960, 600  # ZED X SVGA aspect (16:10)
DEPTH_W, DEPTH_H = 160, 100
MSG_FRAME = 0x01
MSG_DEPTH = 0x02
DEPTH_HEADER = struct.Struct("<BBHH")
WALL_MM = 0  # the back wall is beyond max range, so it reads as unknown
TORSO_MM = 900
HAND_REST_MM = 650
THRUST_MM = 250
PLAYERS = (0.3, 0.7)  # torso centers, normalized x
HAND = (0.36, 0.42, 0.045, 0.07)  # player 1's hand: cx, cy, rx, ry (normalized)


def ellipse_mask(w, h, cx, cy, rx, ry):
    ys, xs = np.mgrid[0:h, 0:w]
    return ((xs / w - cx) / rx) ** 2 + ((ys / h - cy) / ry) ** 2 < 1


def thrust_mm(t):
    return THRUST_MM * max(0.0, math.sin(t * 2.0)) ** 3


def fake_depth(t):
    depth = np.full((DEPTH_H, DEPTH_W), WALL_MM, np.uint16)
    for cx in PLAYERS:
        depth[ellipse_mask(DEPTH_W, DEPTH_H, cx, 0.78, 0.13, 0.36)] = TORSO_MM
    depth[ellipse_mask(DEPTH_W, DEPTH_H, *HAND)] = HAND_REST_MM - thrust_mm(t)
    return DEPTH_HEADER.pack(MSG_DEPTH, 0, DEPTH_W, DEPTH_H) + depth.astype("<u2").tobytes()


def fake_frame(t):
    ramp = np.linspace(70, 30, FRAME_H, dtype=np.float32)[:, None, None]
    frame = np.broadcast_to(ramp * np.array([1.0, 0.8, 0.7]), (FRAME_H, FRAME_W, 3)).astype(np.uint8).copy()
    for cx in PLAYERS:
        cv2.ellipse(frame, (int(cx * FRAME_W), int(0.78 * FRAME_H)), (int(0.13 * FRAME_W), int(0.36 * FRAME_H)), 0, 0, 360, (95, 80, 70), -1)
        cv2.circle(frame, (int(cx * FRAME_W), int(0.3 * FRAME_H)), int(0.07 * FRAME_W), (120, 105, 95), -1)
    scale = 1 + thrust_mm(t) / THRUST_MM * 0.4  # the hand looks bigger as it nears the camera
    cx, cy, rx, ry = HAND
    cv2.ellipse(frame, (int(cx * FRAME_W), int(cy * FRAME_H)), (int(rx * FRAME_W * scale), int(ry * FRAME_H * scale)), 0, 0, 360, (150, 170, 200), -1)
    cv2.putText(frame, "FAKE TRACKER", (24, FRAME_H - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (170, 170, 170), 1, cv2.LINE_AA)
    return bytes([MSG_FRAME]) + cv2.imencode(".jpg", frame)[1].tobytes()


async def main():
    clients = set()
    hello = json.dumps({"type": "hello", "frame": [FRAME_W, FRAME_H], "depth": [DEPTH_W, DEPTH_H]})

    async def handler(ws):
        clients.add(ws)
        await ws.send(hello)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async with websockets.serve(handler, "0.0.0.0", PORT):
        print(f"fake tracker on ws://localhost:{PORT}")
        start = time.time()
        while True:
            t = time.time() - start
            websockets.broadcast(clients, fake_depth(t))
            websockets.broadcast(clients, fake_frame(t))
            await asyncio.sleep(1 / FPS)


if __name__ == "__main__":
    asyncio.run(main())
