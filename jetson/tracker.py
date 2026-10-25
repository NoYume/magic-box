"""ZED X camera server: streams body skeletons (JSON), camera frames (JPEG) and a small depth map.

The ZED does what it is good at: body tracking (posture moves, player slots) and depth. Finger
level hand signs run in the browser (MediaPipe) on these frames; the depth map gives each hand a
metric distance so a thrust toward the camera can be measured.
See docs/protocol.md for the message format. Run on the Jetson:
    python3 tracker.py                      # live camera
    python3 tracker.py --record demo.svo2   # live + record for laptop devs
    python3 tracker.py --svo demo.svo2      # replay a recording (any machine with the ZED SDK)
"""

import argparse
import asyncio
import json
import math
import struct
import threading
import time

import cv2
import numpy as np
import pyzed.sl as sl
import websockets
from debug_log import DEFAULT_LOG_DIR, DebugLog, chain_http, receive
from static_site import (
    DEFAULT_GAME_DIR,
    as_process_request,
    same_origin_websockets,
    static_site,
)

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
DETECTION_CONFIDENCE = 40
FRAME_WIDTH = 960  # JPEG width; height follows the camera aspect ratio
DEPTH_WIDTH = 160  # depth map width; height follows the camera aspect ratio
JPEG_QUALITY = 85  # small hands lose finger detail below this (debug log 20261024-235023)
MSG_FRAME = 0x01
MSG_DEPTH = 0x02
FRAME_HEADER = struct.Struct("<BBI")  # type, reserved, capture seq
DEPTH_HEADER = struct.Struct("<BBIHH")  # type, reserved, capture seq, width, height
MM_PER_M = 1000.0
UINT16_MAX = 65535
STATS_PERIOD_S = 5
SEQ_MODULO = 2**32  # capture seq is a u32 on the wire


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--svo", help="replay an .svo/.svo2 file instead of the live camera")
    parser.add_argument("--record", help="record the live session to this .svo2 path")
    parser.add_argument("--max-range", type=float, default=1.6, help="depth and bodies beyond this (meters) are dropped: ignores bystanders")
    parser.add_argument("--depth", default="PERFORMANCE", help="ZED DEPTH_MODE (PERFORMANCE, NEURAL, ...)")
    parser.add_argument(
        "--static", default=str(DEFAULT_GAME_DIR), help="game page served on this port ('' = off)"
    )
    parser.add_argument(
        "--log-dir", default=str(DEFAULT_LOG_DIR), help="game debug log directory, key L ('' = off)"
    )
    return parser.parse_args()


def grab_succeeded(status):
    """SDK 5 reports warnings as codes below SUCCESS; SDK 4 enums may not support ordering."""
    try:
        return status <= sl.ERROR_CODE.SUCCESS
    except TypeError:
        return status == sl.ERROR_CODE.SUCCESS


def open_camera(args):
    zed = sl.Camera()
    init = sl.InitParameters()
    init.camera_resolution = sl.RESOLUTION.SVGA  # ZED X 960x600: fastest mode on the Orin Nano
    init.camera_fps = 30
    init.depth_mode = getattr(sl.DEPTH_MODE, args.depth)
    init.coordinate_units = sl.UNIT.METER
    init.depth_maximum_distance = args.max_range  # farther pixels come back as +inf -> 0 on the wire
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


def serialize_bodies(bodies, width, height, seq):
    out = []
    for body in bodies.body_list:
        if body.tracking_state != sl.OBJECT_TRACKING_STATE.OK:
            continue
        kp = {name: to_point(body.keypoint_2d[i], body.keypoint[i], width, height) for name, i in KEYPOINTS.items()}
        out.append({"id": int(body.id), "kp": kp})
    return json.dumps({"type": "bodies", "seq": seq, "t": int(time.time() * 1000), "bodies": out})


def scaled_size(camera_res, width):
    return width, round(width * camera_res.height / camera_res.width)


def encode_depth(depth_m, seq):
    """float32 meters (NaN/inf = unknown) -> typed binary message of uint16 millimeters (0 = unknown)."""
    valid = np.isfinite(depth_m) & (depth_m > 0)
    mm = np.where(valid, np.clip(depth_m * MM_PER_M, 1, UINT16_MAX), 0).astype("<u2")
    height, width = mm.shape
    return DEPTH_HEADER.pack(MSG_DEPTH, 0, seq, width, height) + mm.tobytes()


def encode_frame(bgra, seq):
    ok, jpeg = cv2.imencode(".jpg", cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return FRAME_HEADER.pack(MSG_FRAME, 0, seq) + jpeg.tobytes() if ok else None


class CaptureThread(threading.Thread):
    """Grabs frames off the camera and keeps only the newest packet, so slow clients never lag."""

    def __init__(self, zed):
        super().__init__(daemon=True)
        self.zed = zed
        self.latest = None
        self.seq = 0
        self.fps = 0.0
        camera_res = zed.get_camera_information().camera_configuration.resolution
        self.camera_res = camera_res
        self.frame_res = sl.Resolution(*scaled_size(camera_res, FRAME_WIDTH))
        self.depth_res = sl.Resolution(*scaled_size(camera_res, DEPTH_WIDTH))

    def hello(self):
        return json.dumps({
            "type": "hello",
            "frame": [self.frame_res.width, self.frame_res.height],
            "depth": [self.depth_res.width, self.depth_res.height],
        })

    def run(self):
        runtime = sl.RuntimeParameters()
        body_runtime = sl.BodyTrackingRuntimeParameters()
        body_runtime.detection_confidence_threshold = DETECTION_CONFIDENCE
        bodies = sl.Bodies()
        image = sl.Mat()
        depth = sl.Mat()
        last = time.perf_counter()
        while True:
            status = self.zed.grab(runtime)
            if status == sl.ERROR_CODE.END_OF_SVOFILE_REACHED:
                self.zed.set_svo_position(0)
                continue
            if not grab_succeeded(status):
                print(f"[tracker] grab failed: {status}")
                time.sleep(0.05)
                continue
            self.zed.retrieve_bodies(bodies, body_runtime)
            self.zed.retrieve_image(image, sl.VIEW.LEFT, sl.MEM.CPU, self.frame_res)
            self.zed.retrieve_measure(depth, sl.MEASURE.DEPTH, sl.MEM.CPU, self.depth_res)
            # One capture sequence number ties this grab's frame, depth map and bodies together.
            capture = (self.seq + 1) % SEQ_MODULO
            frame = encode_frame(image.get_data(), capture)
            if frame is None:
                continue
            # Keypoints are in full camera-resolution pixels; normalize by that, not the JPEG size.
            text = serialize_bodies(bodies, self.camera_res.width, self.camera_res.height, capture)
            self.latest = (frame, encode_depth(depth.get_data(), capture), text)
            self.seq += 1
            now = time.perf_counter()
            self.fps = 0.9 * self.fps + 0.1 / max(now - last, 1e-6)
            last = now


async def serve(capture, port, static_dir, log_dir):
    clients = set()
    debug_log = DebugLog(log_dir) if log_dir else None

    async def handler(ws):
        clients.add(ws)
        print(f"[tracker] client connected ({len(clients)})")
        await ws.send(capture.hello())
        try:
            await receive(ws, debug_log)  # debug log records and marks from the game
        finally:
            clients.discard(ws)

    site = static_site(static_dir) if static_dir else None
    hook = as_process_request(same_origin_websockets(chain_http(debug_log, site)))
    async with websockets.serve(handler, "0.0.0.0", port, max_size=None, process_request=hook):
        print(f"[tracker] streaming on ws://0.0.0.0:{port}")
        if static_dir:
            print(f"[tracker] game page: http://<this-host>:{port}/ (from {static_dir})")
        sent_seq = 0
        last_log = time.time()
        while True:
            if capture.seq != sent_seq and capture.latest:
                sent_seq = capture.seq
                frame, depth, text = capture.latest
                websockets.broadcast(clients, depth)  # depth first so it is ready when the frame is processed
                websockets.broadcast(clients, frame)
                websockets.broadcast(clients, text)
                if debug_log:
                    debug_log.on_capture(frame, depth, text)
            if time.time() - last_log > STATS_PERIOD_S:
                print(f"[tracker] {capture.fps:.1f} fps, {len(clients)} client(s)")
                websockets.broadcast(clients, json.dumps({"type": "stats", "fps": round(capture.fps, 1)}))
                last_log = time.time()
            await asyncio.sleep(0.005)


def main():
    args = parse_args()
    zed = open_camera(args)
    capture = CaptureThread(zed)
    capture.start()
    try:
        asyncio.run(serve(capture, args.port, args.static, args.log_dir))
    finally:
        zed.disable_recording()
        zed.close()


if __name__ == "__main__":
    main()
