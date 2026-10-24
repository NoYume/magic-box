"""Keyboard-driven fake players for --fake mode (no camera needed).

Turns held keys into PlayerStates plus a synthetic BGRA camera frame drawn
with numpy slicing only.

Owner: Nikhil
"""

import numpy as np

from magic_box.core.config import Config
from magic_box.core.contracts import KEYPOINT_NAMES, Frame, PlayerState, Push
from magic_box.core.geometry import project_point, zone_for_distance

# Body model, meters relative to the pelvis (+y is down).
_HEAD_Y = -0.75
_NECK_Y = -0.6
_SHOULDER_Y = -0.5
_SHOULDER_DX = 0.2
_WRIST_DX = 0.35
_ANKLE_Y = 0.9
_ANKLE_DX = 0.15
_HEAD_RADIUS_M = 0.12
_HANDS_UP_Y = -0.9  # wrist height when hands are raised

_SLOT_BGR = {0: (40, 140, 255), 1: (255, 140, 40)}  # P1 orange, P2 blue


class FakePlayers:
    """Simulates both players from held keys; one `step` per frame."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        fake = cfg["fake"]
        self._fake = fake
        self._keys = cfg["keys"]["fake"]
        cam = cfg["camera"]
        self._w = int(cam["image_width"])
        self._h = int(cam["image_height"])
        self._bg_bgr = tuple(reversed(cfg["render"]["background_rgb"]))
        self._x = {0: float(fake["start_x_m"]), 1: -float(fake["start_x_m"])}
        self._z = {0: float(fake["start_z_m"]), 1: float(fake["start_z_m"])}
        self._prev_push = {0: False, 1: False}
        self._frame_idx = 0

    def step(self, keys: frozenset[str], now: float, dt: float) -> tuple[list[PlayerState], Frame]:
        image = np.empty((self._h, self._w, 4), dtype=np.uint8)
        image[:, :, :3] = self._bg_bgr
        image[:, :, 3] = 255
        states = [self._player(slot, keys, now, dt, image) for slot in (0, 1)]
        frame = Frame(frame_idx=self._frame_idx, cam_t=now, image=image)
        self._frame_idx += 1
        return states, frame

    def _player(
        self, slot: int, keys: frozenset[str], now: float, dt: float, image: np.ndarray
    ) -> PlayerState:
        fake, k = self._fake, self._keys[slot]
        # Player's own left is camera +x, own right is camera -x.
        direction = (k["left"] in keys) - (k["right"] in keys)
        dx = direction * fake["move_speed_mps"] * dt
        self._x[slot] += dx
        depth = (k["farther"] in keys) - (k["closer"] in keys)
        z = self._z[slot] + depth * fake["move_speed_mps"] * dt
        z = min(max(z, fake["min_z_m"]), fake["max_z_m"])
        self._z[slot] = z
        x = self._x[slot]

        pushing = k["push"] in keys
        pushed = pushing and not self._prev_push[slot]
        self._prev_push[slot] = pushing

        duck = fake["duck_m"] if k["duck"] in keys else 0.0
        hands_up = k["hands_up"] in keys
        hands_together = k["hands_together"] in keys
        wrist_y = _HANDS_UP_Y if hands_up else _SHOULDER_Y
        wrist_dx = 0.0 if hands_together else _WRIST_DX
        flags = set()
        if hands_up:
            flags.add("hands_up")
        if hands_together:
            flags.add("hands_together")

        # Ducking lowers the whole upper body; pelvis and ankles stay put.
        pts = {
            "head": (x, _HEAD_Y + duck, z),
            "neck": (x, _NECK_Y + duck, z),
            "pelvis": (x, 0.0, z),
            "l_shoulder": (x + _SHOULDER_DX, _SHOULDER_Y + duck, z),
            "r_shoulder": (x - _SHOULDER_DX, _SHOULDER_Y + duck, z),
            "l_wrist": (x + wrist_dx, wrist_y + duck, z),
            "r_wrist": (x - wrist_dx, wrist_y + duck, z),
            "l_ankle": (x + _ANKLE_DX, _ANKLE_Y, z),
            "r_ankle": (x - _ANKLE_DX, _ANKLE_Y, z),
        }
        f = float(fake["focal_px"])
        cx, cy = self._w / 2, self._h / 2
        px = {name: project_point(pts[name], f, f, cx, cy) for name in KEYPOINT_NAMES}

        xs = [p[0] for p in px.values()]
        ys = [p[1] for p in px.values()]
        head_r = _HEAD_RADIUS_M * f / z
        bx0, by0 = int(min(xs) - head_r), int(px["head"][1] - head_r)
        bx1, by1 = int(max(xs) + head_r), int(max(ys))
        bbox = (bx0, by0, bx1 - bx0, by1 - by0)
        self._fill(image, bbox, _SLOT_BGR[slot])
        hx, hy = px["head"]
        head_box = (int(hx - head_r), int(hy - head_r), int(2 * head_r), int(2 * head_r))
        self._fill(image, head_box, _SLOT_BGR[slot])

        push = Push("R", float(fake["push_speed_mps"]), px["r_wrist"]) if pushed else None
        return PlayerState(
            slot=slot,
            player_id=slot + 1,
            t=now,
            cam_t=now,
            frame_idx=self._frame_idx,
            tracking_ok=True,
            root=pts["pelvis"],
            root_vx=dx / dt if dt else 0.0,
            head=pts["head"],
            wrists={"L": pts["l_wrist"], "R": pts["r_wrist"]},
            wrist_vz={"L": 0.0, "R": -float(fake["push_speed_mps"]) if pushed else 0.0},
            zone=zone_for_distance(z, self._cfg["perception"]["zones"]),
            push=push,
            pose_flags=frozenset(flags),
            bbox_px=bbox,
            keypoints_px=px,
            finger_gesture={"L": None, "R": None},
        )

    def _fill(self, image: np.ndarray, box: tuple[int, int, int, int], bgr: tuple) -> None:
        x, y, w, h = box
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self._w), min(y + h, self._h)
        if x1 > x0 and y1 > y0:
            image[y0:y1, x0:x1, :3] = bgr
