"""ZED X body tracker: streams skeletons (JSON) and camera frames (JPEG) over WebSocket.

See docs/protocol.md for the message format. Run on the Jetson:
    python3 tracker.py                      # live camera
    python3 tracker.py --record demo.svo2   # live + record for laptop devs
    python3 tracker.py --svo demo.svo2      # replay a recording (works on any machine with the ZED SDK)
"""

import argparse
import asyncio
import json
import math
import threading
import time

import cv2
import pyzed.sl as sl
import websockets

# Indices into the BODY_34 keypoint array.
KEYPOINTS = {
    "pelvis": 0,
    "neck": 3,
    "l_shoulder": 5,
    "l_wrist": 7,
    "r_shoulder": 12,
    "r_wrist": 14,
    "head": 26,
}
FRAME_WIDTH = 960
FRAME_HEIGHT = 540
JPEG_QUALITY = 70
DETECTION_CONFIDENCE = 40


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--svo", help="replay an .svo/.svo2 file instead of the live camera")
    parser.add_argument("--record", help="record the live session to this .svo2 path")
    parser.add_argument("--max-range", type=float, default=3.5, help="ignore people farther than this (meters)")
    parser.add_argument("--depth", default="PERFORMANCE", help="ZED DEPTH_MODE (PERFORMANCE, NEURAL, ...)")
    return parser.parse_args()


def open_camera(args):
    zed = sl.Camera()
    init = sl.InitParameters()
    init.camera_resolution = sl.RESOLUTION.SVGA  # ZED X 960x600: fastest mode on the Orin Nano
    init.camera_fps = 30
    init.depth_mode = getattr(sl.DEPTH_MODE, args.depth)
    init.coordinate_units = sl.UNIT.METER
    init.coordinate_system = sl.COORDINATE_SYSTEM.IMAGE  # x right, y down, z forward
    if args.svo:
        init.set_from_svo_file(args.svo)
        init.svo_real_time_mode = True

    status = zed.open(init)
    if status != sl.ERROR_CODE.SUCCESS:
        raise RuntimeError(f"ZED open failed: {status}")

    if args.record:
        status = zed.enable_recording(sl.RecordingParameters(args.record, sl.SVO_COMPRESSION_MODE.H264))
        if status != sl.ERROR_CODE.SUCCESS:
            raise RuntimeError(f"ZED recording to {args.record} failed: {status}")

    tracking = sl.PositionalTrackingParameters()
    tracking.set_as_static = True  # the box doesn't move
    zed.enable_positional_tracking(tracking)

    body_params = sl.BodyTrackingParameters()
    body_params.enable_tracking = True
    body_params.enable_body_fitting = True
    body_params.detection_model = sl.BODY_TRACKING_MODEL.HUMAN_BODY_FAST
    body_params.body_format = sl.BODY_FORMAT.BODY_34
    body_params.max_range = args.max_range
    status = zed.enable_body_tracking(body_params)
    if status != sl.ERROR_CODE.SUCCESS:
        raise RuntimeError(f"ZED body tracking failed: {status}")
    return zed


def to_point(kp2d, kp3d, width, height):
    x, y = float(kp2d[0]), float(kp2d[1])
    z = float(kp3d[2])
    if any(math.isnan(v) for v in (x, y, z)) or x < 0 or y < 0:
        return None
    return {"x": x / width, "y": y / height, "z": z}


def serialize_bodies(bodies, width, height):
    out = []
    for body in bodies.body_list:
        if body.tracking_state != sl.OBJECT_TRACKING_STATE.OK:
            continue
        kp = {name: to_point(body.keypoint_2d[i], body.keypoint[i], width, height) for name, i in KEYPOINTS.items()}
        out.append({"id": int(body.id), "kp": kp})
    return json.dumps({"type": "bodies", "t": int(time.time() * 1000), "bodies": out})


class CaptureThread(threading.Thread):
    """Grabs frames off the camera and keeps only the newest packet, so slow clients never lag."""

    def __init__(self, zed):
        super().__init__(daemon=True)
        self.zed = zed
        self.latest = None
        self.seq = 0
        self.fps = 0.0

    def run(self):
        resolution = self.zed.get_camera_information().camera_configuration.resolution
        runtime = sl.BodyTrackingRuntimeParameters()
        runtime.detection_confidence_threshold = DETECTION_CONFIDENCE
        bodies = sl.Bodies()
        image = sl.Mat()
        small = sl.Resolution(FRAME_WIDTH, FRAME_HEIGHT)
        last = time.perf_counter()
        while True:
            status = self.zed.grab()
            if status == sl.ERROR_CODE.END_OF_SVOFILE_REACHED:
                self.zed.set_svo_position(0)
                continue
            if status != sl.ERROR_CODE.SUCCESS:
                print(f"[tracker] grab failed: {status}")
                time.sleep(0.05)
                continue
            self.zed.retrieve_bodies(bodies, runtime)
            self.zed.retrieve_image(image, sl.VIEW.LEFT, sl.MEM.CPU, small)
            frame = cv2.cvtColor(image.get_data(), cv2.COLOR_BGRA2BGR)
            ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                continue
            self.latest = (serialize_bodies(bodies, resolution.width, resolution.height), jpeg.tobytes())
            self.seq += 1
            now = time.perf_counter()
            self.fps = 0.9 * self.fps + 0.1 / max(now - last, 1e-6)
            last = now


async def serve(capture, port):
    clients = set()

    async def handler(ws):
        clients.add(ws)
        print(f"[tracker] client connected ({len(clients)})")
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    async with websockets.serve(handler, "0.0.0.0", port, max_size=None):
        print(f"[tracker] streaming on ws://0.0.0.0:{port}")
        sent_seq = 0
        last_log = time.time()
        while True:
            if capture.seq != sent_seq and capture.latest:
                sent_seq = capture.seq
                text, jpeg = capture.latest
                websockets.broadcast(clients, jpeg)
                websockets.broadcast(clients, text)
            if time.time() - last_log > 5:
                print(f"[tracker] {capture.fps:.1f} fps, {len(clients)} client(s)")
                last_log = time.time()
            await asyncio.sleep(0.005)


def main():
    args = parse_args()
    zed = open_camera(args)
    capture = CaptureThread(zed)
    capture.start()
    try:
        asyncio.run(serve(capture, args.port))
    finally:
        zed.disable_recording()
        zed.close()


if __name__ == "__main__":
    main()
