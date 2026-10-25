"""Simulated ZED bodies and captures for perception tests (no pyzed).

Owner: Enoch
"""

from collections.abc import Iterable, Mapping, Sequence

import numpy as np

from magic_box.core.contracts import Frame, Vec3
from magic_box.core.geometry import project_point
from magic_box.perception.raw import CameraInfo, Capture, RawBody

FOCAL_PX = 525.0
SIZE = (960, 600)  # camera.image_width x image_height (SVGA)


def body_points(x: float, z: float, duck: float = 0.0) -> dict[str, Vec3]:
    """A standing person: pelvis at (x, 0, z), +y down, hands out at shoulder height."""
    return {
        "head": (x, -0.75 + duck, z),
        "neck": (x, -0.6 + duck, z),
        "pelvis": (x, 0.0, z),
        "l_shoulder": (x + 0.2, -0.5 + duck, z),
        "r_shoulder": (x - 0.2, -0.5 + duck, z),
        "l_wrist": (x + 0.35, -0.5 + duck, z),
        "r_wrist": (x - 0.35, -0.5 + duck, z),
        "l_ankle": (x + 0.15, 0.9, z),
        "r_ankle": (x - 0.15, 0.9, z),
    }


def make_body(
    id: int = 1,
    x: float = 0.6,
    z: float = 2.0,
    *,
    duck: float = 0.0,
    overrides: Mapping[str, Vec3] | None = None,
    drop: Iterable[str] = (),
    tracking_ok: bool = True,
    position: Vec3 | None = None,
) -> RawBody:
    kp3d = body_points(x, z, duck) | dict(overrides or {})
    kp3d = {k: v for k, v in kp3d.items() if k not in set(drop)}
    w, h = SIZE
    kp2d = {k: project_point(p, FOCAL_PX, FOCAL_PX, w / 2, h / 2) for k, p in kp3d.items()}
    xs = [p[0] for p in kp2d.values()] or [0.0]
    ys = [p[1] for p in kp2d.values()] or [0.0]
    bbox = (int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))
    return RawBody(
        id=id,
        tracking_ok=tracking_ok,
        confidence=80.0,
        position=position or (x, -0.3, z),
        kp3d=kp3d,
        kp2d=kp2d,
        bbox_px=bbox,
    )


def make_capture(bodies: Sequence[RawBody], frame_idx: int = 0, cam_t: float = 0.0) -> Capture:
    w, h = SIZE
    image = np.zeros((h, w, 4), np.uint8)
    return Capture(frame=Frame(frame_idx=frame_idx, cam_t=cam_t, image=image), bodies=list(bodies))


class FakeStop:
    """Stands in for multiprocessing.Event; wait() records the timeout and never sleeps."""

    def __init__(self) -> None:
        self._set = False
        self.waits: list[float] = []

    def is_set(self) -> bool:
        return self._set

    def set(self) -> None:
        self._set = True

    def wait(self, timeout: float | None = None) -> bool:
        self.waits.append(timeout)
        return self.is_set()


class FakeSource:
    """A scripted camera: opens pops from `opens`, grabs pops from `grabs`."""

    info = CameraInfo("ZED_X", 1, 960, 600, 30.0, "5.0.0", "fake")

    def __init__(self, stop, grabs, opens=()) -> None:
        self.stop = stop
        self.grabs = list(grabs)
        self.opens = list(opens)
        self.is_open = False
        self.open_calls = 0
        self.close_calls = 0

    def open(self) -> None:
        self.open_calls += 1
        item = self.opens.pop(0) if self.opens else None
        if isinstance(item, Exception):
            raise item
        self.is_open = True

    def grab(self):
        if not self.grabs:
            self.stop.set()
            return None
        return self.grabs.pop(0)

    def close(self) -> None:
        self.close_calls += 1
        self.is_open = False


class FakeBus:
    """Stands in for FrameBus."""

    instances: list = []

    @classmethod
    def attach(cls, name, width, height):
        bus = cls()
        bus.name = name
        bus.size = (width, height)
        bus.frames = []
        bus.closed = False
        cls.instances.append(bus)
        return bus

    def write(self, frame) -> None:
        self.frames.append(frame)

    def close(self) -> None:
        self.closed = True


class ListQueue:
    def __init__(self) -> None:
        self.items: list = []

    def put(self, item) -> None:
        self.items.append(item)

    def cancel_join(self) -> None:
        self.cancel_join_calls = getattr(self, "cancel_join_calls", 0) + 1
