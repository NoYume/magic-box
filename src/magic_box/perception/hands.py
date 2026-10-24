"""Optional finger gesture detection (spec section 8, perception/).

Owner: Enoch
"""

from collections.abc import Mapping

from magic_box.core.contracts import Frame, Px


def detect_finger_gestures(frame: Frame, wrists_px: Mapping[str, Px]) -> dict[str, str | None]:
    raise NotImplementedError("TODO(Enoch): optional finger gesture detection")
