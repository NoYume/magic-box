"""Fuses voice matches and perception into Actions (spec section 8, intent/).

Owner: Nikhil
"""

from collections.abc import Sequence

from magic_box.core.config import Config
from magic_box.core.contracts import Action, PlayerState, VoiceEvent
from magic_box.intent.dodge import DodgeDetector


class Intent:
    """Stateful edge detector and contract adapter; contains no combat rules."""

    def __init__(self, cfg: Config) -> None:
        self._dodge = DodgeDetector(cfg)
        self._poses: dict[int, frozenset[str]] = {0: frozenset(), 1: frozenset()}
        self._latest: dict[int, PlayerState] = {}
        self._push_speed = float(cfg["perception"]["push_speed_mps"])
        self._two_hand_window = float(cfg["intent"]["two_hand_push_window_s"])
        self._wrist_fast = {slot: {hand: False for hand in ("L", "R")} for slot in (0, 1)}
        self._crossed_at: dict[tuple[int, str], float] = {}
        self._last_cam_t: dict[int, float] = {}

    def update(
        self, states: Sequence[PlayerState], voice: Sequence[VoiceEvent], now: float
    ) -> list[Action]:
        actions: list[Action] = []
        for state in states:
            if not state.tracking_ok:
                self._poses[state.slot] = frozenset()
                self._wrist_fast[state.slot] = {"L": False, "R": False}
                for hand in ("L", "R"):
                    self._crossed_at.pop((state.slot, hand), None)
                self._dodge.update(state)
                continue
            self._latest[state.slot] = state
            previous_cam_t = self._last_cam_t.get(state.slot)
            if previous_cam_t is not None and state.cam_t < previous_cam_t:
                self._wrist_fast[state.slot] = {"L": False, "R": False}
                for hand in ("L", "R"):
                    self._crossed_at.pop((state.slot, hand), None)
            self._last_cam_t[state.slot] = state.cam_t
            for hand in ("L", "R"):
                fast = state.wrist_vz.get(hand, 0.0) <= -self._push_speed
                if fast and not self._wrist_fast[state.slot][hand]:
                    self._crossed_at[(state.slot, hand)] = state.cam_t
                self._wrist_fast[state.slot][hand] = fast
            if state.push is not None:
                other = "L" if state.push.hand == "R" else "R"
                pushed_at = self._crossed_at.get((state.slot, state.push.hand), float("-inf"))
                other_at = self._crossed_at.get((state.slot, other), float("-inf"))
                release = (
                    "two_hand_push" if abs(pushed_at - other_at) <= self._two_hand_window else None
                )
                actions.append(
                    Action(
                        kind="push",
                        slot=state.slot,
                        t=state.t,
                        push=state.push,
                        pose=release,
                        dist=state.root[2],
                    )
                )
            previous = self._poses[state.slot]
            for pose in sorted(state.pose_flags - previous):
                actions.append(
                    Action(kind="pose", slot=state.slot, t=state.t, pose=pose, dist=state.root[2])
                )
            self._poses[state.slot] = state.pose_flags
            dodge = self._dodge.update(state)
            if dodge is not None:
                actions.append(
                    Action(
                        kind="dodge",
                        slot=state.slot,
                        t=state.t,
                        dodge=dodge,
                        dist=state.root[2],
                    )
                )
        for event in voice:
            if event.kind != "incantation" or event.spell_id is None:
                continue
            state = self._latest.get(event.slot)
            actions.append(
                Action(
                    kind="charge",
                    slot=event.slot,
                    t=event.t,
                    spell_id=event.spell_id,
                    match_score=event.match_score,
                    dist=state.root[2] if state else 0.0,
                )
            )
        return sorted(actions, key=lambda action: action.t)
