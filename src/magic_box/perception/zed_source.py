"""ZED 2 camera source, live or SVO playback (spec section 8, perception/).

Owner: Enoch
"""

from typing import Any

from magic_box.core.config import Config
from magic_box.core.contracts import Frame


class ZedSource:
    """Wraps the ZED camera. `pyzed` must be imported inside the methods, never at module top."""

    def __init__(self, cfg: Config, svo_path: str | None = None) -> None:
        self.cfg = cfg
        self.svo_path = svo_path

    def open(self) -> None:
        raise NotImplementedError("TODO(Enoch): open the ZED camera (live or SVO)")

    def grab(self) -> bool:
        raise NotImplementedError("TODO(Enoch): grab the next frame")

    def retrieve_frame(self) -> Frame:
        raise NotImplementedError("TODO(Enoch): retrieve the left image as a Frame")

    def retrieve_bodies(self) -> list[Any]:
        raise NotImplementedError("TODO(Enoch): retrieve tracked bodies")

    def close(self) -> None:
        raise NotImplementedError("TODO(Enoch): close the ZED camera")
