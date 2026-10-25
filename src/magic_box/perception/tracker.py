"""Turns each camera Capture into PlayerStates (spec 7.3-7.8).

Owner: Enoch
"""

import dataclasses

from magic_box.core.config import Config
from magic_box.core.contracts import PlayerState
from magic_box.core.geometry import zone_for_distance
from magic_box.perception.bodies import NUM_SLOTS, SlotAssigner
from magic_box.perception.motion import MotionTracker
from magic_box.perception.poses import detect_poses
from magic_box.perception.push import PushDetector
from magic_box.perception.raw import Capture, RawBody

NO_WRIST_VZ = {"L": 0.0, "R": 0.0}


class PlayerTracker:
    """Slots, root, head, wrists, push, poses and zone for up to two players."""

    def __init__(self, cfg: Config) -> None:
        self._perception = cfg["perception"]
        self._zones = cfg["perception"]["zones"]
        self._assigner = SlotAssigner(cfg)
        self._push = {s: PushDetector(cfg) for s in range(NUM_SLOTS)}
        self._motion = {s: MotionTracker(cfg) for s in range(NUM_SLOTS)}
        self._body_id: dict[int, int] = {}
        self._ref_kind: dict[int, str] = {}
        self._last: dict[int, PlayerState] = {}

    @property
    def bound_ids(self) -> dict[int, int | None]:
        return {s: self._assigner.bound_id(s) for s in range(NUM_SLOTS)}

    def step(self, capture: Capture, now: float) -> list[PlayerState]:
        frame = capture.frame
        assigned = self._assigner.assign(capture.bodies, frame.cam_t)
        states: list[PlayerState] = []
        for slot in range(NUM_SLOTS):
            body = assigned.get(slot)
            if body is not None:
                state = self._track(slot, body, now, frame.cam_t, frame.frame_idx)
            elif slot in self._last:
                state = dataclasses.replace(
                    self._last[slot],
                    tracking_ok=False,
                    push=None,
                    root_vx=0.0,
                    wrist_vz=dict(NO_WRIST_VZ),
                    t=now,
                    cam_t=frame.cam_t,
                    frame_idx=frame.frame_idx,
                )
            else:
                continue
            self._last[slot] = state
            states.append(state)
        return states

    def _track(
        self, slot: int, body: RawBody, now: float, cam_t: float, frame_idx: int
    ) -> PlayerState:
        if self._body_id.get(slot) != body.id:
            self._push[slot].reset()
            self._motion[slot].reset()
            self._body_id[slot] = body.id

        kp = body.kp3d
        root = kp.get("pelvis", body.position)
        head = kp.get("head") or kp.get("neck") or root

        ref_kind, ref_z = ("neck", kp["neck"][2]) if "neck" in kp else ("root", root[2])
        if self._ref_kind.get(slot) != ref_kind:
            self._push[slot].clear_windows()  # a reference switch would look like wrist motion
            self._ref_kind[slot] = ref_kind

        wrists = {h: kp[f"{h.lower()}_wrist"] for h in ("L", "R") if f"{h.lower()}_wrist" in kp}
        wrists_px = {
            h: body.kp2d[f"{h.lower()}_wrist"] for h in wrists if f"{h.lower()}_wrist" in body.kp2d
        }
        root_vx = self._motion[slot].update(root, cam_t)
        push, wrist_vz = self._push[slot].update(cam_t, wrists, wrists_px, ref_z)

        return PlayerState(
            slot=slot,
            player_id=body.id,
            t=now,
            cam_t=cam_t,
            frame_idx=frame_idx,
            tracking_ok=True,
            root=root,
            root_vx=root_vx,
            head=head,
            wrists=wrists,
            wrist_vz=wrist_vz,
            zone=zone_for_distance(root[2], self._zones),
            push=push,
            pose_flags=detect_poses(kp, head, self._perception),
            bbox_px=body.bbox_px,
            keypoints_px=dict(body.kp2d),
            finger_gesture={"L": None, "R": None},
        )
