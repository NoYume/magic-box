"""A fake `pyzed.sl` module for tests, so ZedSource runs without the ZED SDK.

Owner: Enoch
"""

import sys
import types
from enum import Enum, IntEnum
from types import SimpleNamespace

import numpy as np

from magic_box.perception.keypoints import PART_NAMES, part_indices
from tests.perception.fakes import FOCAL_PX, SIZE, body_points


def _enum(name: str, *members: str) -> Enum:
    return Enum(name, {m: i for i, m in enumerate(members)})


class _Bag:
    """Attribute bag: the SDK parameter classes are plain settable objects."""

    def __init__(self, *args, **kwargs) -> None:
        pass


def make_fake_sl() -> types.ModuleType:
    """A fresh fake module per call, so per-test knobs never leak."""
    sl = types.ModuleType("pyzed.sl")
    sl.RESOLUTION = _enum("RESOLUTION", "SVGA", "HD1080", "HD1200")
    sl.DEPTH_MODE = _enum("DEPTH_MODE", "PERFORMANCE")
    sl.UNIT = _enum("UNIT", "METER")
    sl.COORDINATE_SYSTEM = _enum("COORDINATE_SYSTEM", "IMAGE")
    sl.BODY_FORMAT = _enum("BODY_FORMAT", "BODY_18", "BODY_34", "BODY_38")
    sl.BODY_TRACKING_MODEL = _enum("BODY_TRACKING_MODEL", "HUMAN_BODY_FAST")
    sl.REFERENCE_FRAME = _enum("REFERENCE_FRAME", "CAMERA")
    sl.VIEW = _enum("VIEW", "LEFT")
    sl.TIME_REFERENCE = _enum("TIME_REFERENCE", "IMAGE")
    sl.SVO_COMPRESSION_MODE = _enum("SVO_COMPRESSION_MODE", "H264")
    sl.OBJECT_TRACKING_STATE = _enum("OBJECT_TRACKING_STATE", "OK", "SEARCHING")
    sl.MODEL = _enum("MODEL", "ZED2", "ZED_X")
    sl.CAMERA_STATE = _enum("CAMERA_STATE", "AVAILABLE")
    sl.ERROR_CODE = IntEnum(
        "ERROR_CODE",
        {
            "CORRUPTED_FRAME": -1,
            "SUCCESS": 0,
            "CAMERA_NOT_DETECTED": 1,
            "END_OF_SVOFILE_REACHED": 2,
            "FAILURE": 3,
        },
    )
    for fmt, names in PART_NAMES.items():
        setattr(sl, f"{fmt}_PARTS", Enum(f"{fmt}_PARTS", {n: i for i, n in enumerate(names)}))

    class InitParameters(_Bag):
        def set_from_svo_file(self, path) -> None:
            self.svo_file = path

    class RecordingParameters(_Bag):
        def __init__(self, video_filename=None, compression_mode=None) -> None:
            self.video_filename = video_filename
            self.compression_mode = compression_mode

    class Mat:
        def __init__(self) -> None:
            self._data = None

        def get_data(self):
            return self._data

    class Bodies:
        def __init__(self) -> None:
            self.body_list = []

    class Camera:
        open_status = sl.ERROR_CODE.SUCCESS
        resolution = SIZE
        model = sl.MODEL.ZED_X
        serial = 4242
        fps = 30.0
        grab_statuses: list = []
        bodies: list = []
        timestamp_ns = 12_500_000_000
        devices: list = []
        last = None

        def __init__(self) -> None:
            Camera.last = self
            self.init = self.positional = self.body_params = None
            self.runtime = self.body_runtime = self.recording = None
            self.svo_positions: list[int] = []
            self.closed = False
            self.image_mats: list = []

        def open(self, init):
            self.init = init
            return Camera.open_status

        def get_camera_information(self):
            w, h = Camera.resolution
            return SimpleNamespace(
                camera_model=Camera.model,
                serial_number=Camera.serial,
                camera_configuration=SimpleNamespace(
                    resolution=SimpleNamespace(width=w, height=h), fps=Camera.fps
                ),
            )

        def enable_recording(self, params):
            self.recording = params
            return sl.ERROR_CODE.SUCCESS

        def disable_recording(self) -> None:
            pass

        def enable_positional_tracking(self, params):
            self.positional = params
            return sl.ERROR_CODE.SUCCESS

        def enable_body_tracking(self, params):
            self.body_params = params
            return sl.ERROR_CODE.SUCCESS

        def grab(self, runtime):
            self.runtime = runtime
            return Camera.grab_statuses.pop(0) if Camera.grab_statuses else sl.ERROR_CODE.SUCCESS

        def set_svo_position(self, pos) -> None:
            self.svo_positions.append(pos)

        def retrieve_bodies(self, bodies, body_runtime):
            self.body_runtime = body_runtime
            bodies.body_list = list(Camera.bodies)
            return sl.ERROR_CODE.SUCCESS

        def retrieve_image(self, mat, view):
            self.image_mats.append(mat)
            w, h = Camera.resolution
            mat._data = np.zeros((h, w, 4), np.uint8)
            return sl.ERROR_CODE.SUCCESS

        def get_timestamp(self, ref):
            return SimpleNamespace(get_nanoseconds=lambda: Camera.timestamp_ns)

        def close(self) -> None:
            self.closed = True

        @staticmethod
        def get_sdk_version() -> str:
            return "5.0.0"

        @staticmethod
        def get_device_list():
            return Camera.devices

    sl.InitParameters = InitParameters
    sl.RuntimeParameters = type("RuntimeParameters", (_Bag,), {})
    sl.PositionalTrackingParameters = type("PositionalTrackingParameters", (_Bag,), {})
    sl.BodyTrackingParameters = type("BodyTrackingParameters", (_Bag,), {})
    sl.BodyTrackingRuntimeParameters = type("BodyTrackingRuntimeParameters", (_Bag,), {})
    sl.RecordingParameters = RecordingParameters
    sl.Mat = Mat
    sl.Bodies = Bodies
    sl.Camera = Camera
    sl.device = lambda model_name, serial: SimpleNamespace(
        camera_model=sl.MODEL[model_name],
        serial_number=serial,
        camera_state=sl.CAMERA_STATE.AVAILABLE,
    )
    return sl


def fake_body(
    id: int,
    *,
    ok: bool = True,
    x: float = 0.5,
    z: float = 2.0,
    empty: tuple[str, ...] = (),
) -> SimpleNamespace:
    """A BODY_34 body as the SDK reports it. Needs the fake installed (uses its enums).

    `empty` names arrays (`keypoint`, `keypoint_2d`, `bounding_box_2d`) the SDK left empty.
    """
    sl = sys.modules["pyzed.sl"]
    points = body_points(x, z)
    w, h = SIZE
    kp3d = np.full((34, 3), np.nan)
    kp2d = np.full((34, 2), np.nan)
    for name, (idx, *_) in part_indices("BODY_34").items():
        px, py, pz = points[name]
        kp3d[idx] = (px, py, pz)
        kp2d[idx] = (FOCAL_PX * px / pz + w / 2, FOCAL_PX * py / pz + h / 2)
    lo, hi = np.nanmin(kp2d, axis=0), np.nanmax(kp2d, axis=0)
    corners = np.array([[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]])
    return SimpleNamespace(
        id=id,
        confidence=80.0,
        tracking_state=sl.OBJECT_TRACKING_STATE.OK if ok else sl.OBJECT_TRACKING_STATE.SEARCHING,
        position=np.array([x, -0.3, z]),
        keypoint=np.empty((0, 3)) if "keypoint" in empty else kp3d,
        keypoint_2d=np.empty((0, 2)) if "keypoint_2d" in empty else kp2d,
        bounding_box_2d=np.empty((0, 2)) if "bounding_box_2d" in empty else corners,
    )


def install_fake_sl(monkeypatch) -> types.ModuleType:
    sl = make_fake_sl()
    pkg = types.ModuleType("pyzed")
    pkg.sl = sl
    monkeypatch.setitem(sys.modules, "pyzed", pkg)
    monkeypatch.setitem(sys.modules, "pyzed.sl", sl)
    return sl
