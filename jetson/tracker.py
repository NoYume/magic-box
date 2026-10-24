"""ZED X camera server: streams camera frames (JPEG) and a small depth map over WebSocket.

Hand tracking and sign recognition run in the browser (MediaPipe) on these frames; the depth
map gives each hand a metric distance so a thrust toward the camera can be measured.
See docs/protocol.md for the message format. Run on the Jetson:
    python3 tracker.py                      # live camera
    python3 tracker.py --record demo.svo2   # live + record for laptop devs
    python3 tracker.py --svo demo.svo2      # replay a recording (any machine with the ZED SDK)
"""

import argparse
import asyncio
import json
import struct
import threading
import time

import cv2
import numpy as np
import pyzed.sl as sl
import websockets

FRAME_WIDTH = 960  # JPEG width; height follows the camera aspect ratio
DEPTH_WIDTH = 160  # depth map width; height follows the camera aspect ratio
JPEG_QUALITY = 70
MSG_FRAME = 0x01
MSG_DEPTH = 0x02
DEPTH_HEADER = struct.Struct("<BBHH")  # type, reserved, width, height
MM_PER_M = 1000.0
UINT16_MAX = 65535
STATS_PERIOD_S = 5


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--svo", help="replay an .svo/.svo2 file instead of the live camera")
    parser.add_argument("--record", help="record the live session to this .svo2 path")
    parser.add_argument("--max-range", type=float, default=1.6, help="depth beyond this (meters) is dropped: ignores bystanders")
    parser.add_argument("--depth", default="PERFORMANCE", help="ZED DEPTH_MODE (PERFORMANCE, NEURAL, ...)")
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
    return zed


def scaled_size(camera_res, width):
    return width, round(width * camera_res.height / camera_res.width)


def encode_depth(depth_m):
    """float32 meters (NaN/inf = unknown) -> typed binary message of uint16 millimeters (0 = unknown)."""
    valid = np.isfinite(depth_m) & (depth_m > 0)
    mm = np.where(valid, np.clip(depth_m * MM_PER_M, 1, UINT16_MAX), 0).astype("<u2")
    height, width = mm.shape
    return DEPTH_HEADER.pack(MSG_DEPTH, 0, width, height) + mm.tobytes()


def encode_frame(bgra):
    ok, jpeg = cv2.imencode(".jpg", cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return bytes([MSG_FRAME]) + jpeg.tobytes() if ok else None


class CaptureThread(threading.Thread):
    """Grabs frames off the camera and keeps only the newest packet, so slow clients never lag."""

    def __init__(self, zed):
        super().__init__(daemon=True)
        self.zed = zed
        self.latest = None
        self.seq = 0
        self.fps = 0.0
        camera_res = zed.get_camera_information().camera_configuration.resolution
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
            self.zed.retrieve_image(image, sl.VIEW.LEFT, sl.MEM.CPU, self.frame_res)
            self.zed.retrieve_measure(depth, sl.MEASURE.DEPTH, sl.MEM.CPU, self.depth_res)
            frame = encode_frame(image.get_data())
            if frame is None:
                continue
            self.latest = (frame, encode_depth(depth.get_data()))
            self.seq += 1
            now = time.perf_counter()
            self.fps = 0.9 * self.fps + 0.1 / max(now - last, 1e-6)
            last = now


async def serve(capture, port):
    clients = set()

    async def handler(ws):
        clients.add(ws)
        print(f"[tracker] client connected ({len(clients)})")
        await ws.send(capture.hello())
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
                frame, depth = capture.latest
                websockets.broadcast(clients, depth)  # depth first so it is ready when the frame is processed
                websockets.broadcast(clients, frame)
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
        asyncio.run(serve(capture, args.port))
    finally:
        zed.disable_recording()
        zed.close()


if __name__ == "__main__":
    main()
