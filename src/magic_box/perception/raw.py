"""Plain capture types handed from the camera layer to the perception logic.

Owner: Enoch
"""

from dataclasses import dataclass

from magic_box.core.contracts import Frame, Px, Vec3


@dataclass(frozen=True)
class RawBody:
    """One tracked body as the camera reports it, keypoints already named."""

    id: int
    tracking_ok: bool
    confidence: float
    position: Vec3
    kp3d: dict[str, Vec3]
    kp2d: dict[str, Px]
    bbox_px: tuple[int, int, int, int]


@dataclass(frozen=True, eq=False)
class Capture:
    """One grabbed frame plus the bodies tracked in it."""

    frame: Frame
    bodies: list[RawBody]


@dataclass(frozen=True)
class CameraInfo:
    """Static facts about the opened camera or recording."""

    model: str
    serial: int
    width: int
    height: int
    fps: float
    sdk_version: str
    source: str
