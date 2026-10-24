"""Fake ZED tracker for front-end dev without the Jetson: two synthetic players step and punch.

    py fake_tracker.py            # then open game/index.html?src=zed&ws=ws://localhost:8765
"""

import asyncio
import json
import math
import time

import cv2
import numpy as np
import websockets

PORT = 8765
FPS = 30
WIDTH, HEIGHT = 960, 540
PUNCH_PERIOD_S = 1.7


def fake_body(body_id, cx, t, phase):
    step = 0.5 * math.sin(t * 0.6 + phase)  # slow step forward/back (meters)
    z = 2.2 + step
    punch_t = (t + phase) % PUNCH_PERIOD_S
    reach = 0.5 * min(1.0, punch_t / 0.15) if punch_t < 0.5 else 0.0  # fast jab out, then retract
    point = lambda x, y, zz: {"x": x, "y": y, "z": zz}
    return {
        "id": body_id,
        "kp": {
            "head": point(cx, 0.2, z),
            "neck": point(cx, 0.3, z),
            "l_shoulder": point(cx - 0.05, 0.32, z),
            "r_shoulder": point(cx + 0.05, 0.32, z),
            "l_wrist": point(cx - 0.08, 0.5, z),
            "r_wrist": point(cx + 0.08 + reach * 0.1, 0.42, z - 0.1 - reach),
            "pelvis": point(cx, 0.55, z),
        },
    }


def fake_frame(t):
    frame = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
    frame[:] = (40 + 20 * math.sin(t), 20, 50)
    cv2.putText(frame, "FAKE TRACKER", (30, HEIGHT - 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (200, 200, 200), 2)
    return cv2.imencode(".jpg", frame)[1].tobytes()


async def main():
    clients = set()

    async def handler(ws):
        clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async with websockets.serve(handler, "0.0.0.0", PORT):
        print(f"fake tracker on ws://localhost:{PORT}")
        start = time.time()
        while True:
            t = time.time() - start
            bodies = [fake_body(1, 0.7, t, 0.0), fake_body(2, 0.3, t, 0.8)]
            websockets.broadcast(clients, fake_frame(t))
            websockets.broadcast(clients, json.dumps({"type": "bodies", "t": int(time.time() * 1000), "bodies": bodies}))
            await asyncio.sleep(1 / FPS)


if __name__ == "__main__":
    asyncio.run(main())
