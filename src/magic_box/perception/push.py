"""Push detection from the wrist's Z velocity relative to the torso (spec 7.5).

Owner: Enoch
"""

from collections.abc import Mapping

from magic_box.core.config import Config
from magic_box.core.contracts import Push, Px, Vec3
from magic_box.perception.kinematics import WindowedVelocity

HANDS = ("L", "R")


class PushDetector:
    """One instance per player slot. Measures wrist_z - ref_z so walking never fires."""

    def __init__(self, cfg: Config) -> None:
        p = cfg["perception"]
        self._speed = p["push_speed_mps"]
        self._min_travel = p["push_min_travel_m"]
        self._rearm_speed = p["push_speed_mps"] * p["push_rearm_ratio"]
        self._cooldown = p["push_cooldown_s"]
        self._window_s = p["push_window_s"]
        self.reset()

    def clear_windows(self) -> None:
        """Drop velocity history only; keeps arming and cooldown (one push, one event)."""
        self._win = {h: WindowedVelocity(self._window_s) for h in HANDS}

    def reset(self) -> None:
        self.clear_windows()
        self._armed = {h: True for h in HANDS}
        self._last_push_t = float("-inf")

    def update(
        self,
        cam_t: float,
        wrists: Mapping[str, Vec3],
        wrists_px: Mapping[str, Px],
        ref_z: float,
    ) -> tuple[Push | None, dict[str, float]]:
        if cam_t < self._last_push_t:  # camera time rewound (SVO loop)
            self._last_push_t = cam_t
        wrist_vz = {h: 0.0 for h in HANDS}
        qualifying: list[tuple[float, str]] = []
        for hand in HANDS:
            if hand not in wrists:
                continue
            win = self._win[hand]
            win.add(cam_t, wrists[hand][2] - ref_z)
            v = win.velocity()
            wrist_vz[hand] = v
            if not self._armed[hand]:
                if -v < self._rearm_speed:
                    self._armed[hand] = True
                continue
            if (
                -v >= self._speed
                and -win.travel() >= self._min_travel
                and cam_t - self._last_push_t >= self._cooldown
            ):
                qualifying.append((-v, hand))
        if not qualifying:
            return None, wrist_vz
        for _, hand in qualifying:
            self._armed[hand] = False
        self._last_push_t = cam_t
        speed, hand = max(qualifying)
        return Push(hand=hand, speed=speed, origin_px=wrists_px[hand]), wrist_vz
