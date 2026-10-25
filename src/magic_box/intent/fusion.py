"""Fuses voice matches and perception into Actions (spec section 8, intent/).

Owner: Nikhil
"""

from collections import deque
from collections.abc import Sequence

from magic_box.core.config import Config
from magic_box.core.contracts import Action, PlayerState, VoiceEvent
from magic_box.intent.dodge import DodgeDetector


class _Slot:
    """Per-slot memory between ticks."""

    def __init__(self) -> None:
        self.vz: dict[str, deque[tuple[float, float]]] = {"L": deque(), "R": deque()}
        self.pending: PlayerState | None = None  # state carrying a held push
        self.pose_flags: frozenset[str] = frozenset()
        self.root_z = 0.0


class Intent:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.push_thr: float = cfg["perception"]["push_speed_mps"]
        self.window_s: float = cfg["intent"]["two_hand_window_s"]
        self._slots = (_Slot(), _Slot())
        self._dodge = DodgeDetector(cfg)

    def update(
        self, states: Sequence[PlayerState], voice: Sequence[VoiceEvent], now: float
    ) -> list[Action]:
        # States first so a charge's dist sees this tick's states; voice actions are returned first.
        state_actions: list[Action] = []
        for state in states:
            if state.tracking_ok:
                self._on_state(state, state_actions)
        voice_actions = [a for v in voice if (a := self._on_voice(v)) is not None]
        released: list[Action] = []
        for slot in self._slots:
            pending = slot.pending
            if pending is not None and now >= pending.t + self.window_s:
                released.append(self._release(slot, two_hand=False))
        return voice_actions + state_actions + released

    def _on_voice(self, v: VoiceEvent) -> Action | None:
        if v.kind == "incantation" and v.spell_id is not None:
            return Action(
                "charge",
                v.slot,
                v.t,
                spell_id=v.spell_id,
                match_score=v.match_score,
                dist=self._slots[v.slot].root_z,
            )
        if v.kind == "transcript":
            return Action("speech", v.slot, v.t, text=v.text)
        return None

    def _on_state(self, state: PlayerState, out: list[Action]) -> None:
        slot = self._slots[state.slot]
        slot.root_z = state.root[2]
        for hand, history in slot.vz.items():
            history.append((state.t, state.wrist_vz[hand]))
            while history[0][0] < state.t - self.window_s:
                history.popleft()

        # A lagging other hand releases the held push as two-hand at once.
        pending = slot.pending
        if pending is not None:
            held = pending.push
            assert held is not None
            if state.t >= pending.t + self.window_s:
                out.append(self._release(slot, two_hand=False))  # deadline passed (stall)
            elif self._crossed(state.wrist_vz[_other(held.hand)]):
                out.append(self._release(slot, two_hand=True))

        if state.push is not None and slot.pending is None:
            other = slot.vz[_other(state.push.hand)]
            if any(self._crossed(vz) for _, vz in other):
                out.append(self._push_action(state, two_hand=True))
            else:
                slot.pending = state

        for pose in sorted(state.pose_flags - slot.pose_flags):
            out.append(Action("pose", state.slot, state.t, pose=pose, dist=state.root[2]))
        slot.pose_flags = state.pose_flags

        dodge = self._dodge.update(state)
        if dodge is not None:
            out.append(Action("dodge", state.slot, state.t, dodge=dodge, dist=state.root[2]))

    def _crossed(self, vz: float) -> bool:
        return vz <= -self.push_thr

    def _release(self, slot: _Slot, two_hand: bool) -> Action:
        pending = slot.pending
        assert pending is not None
        slot.pending = None
        return self._push_action(pending, two_hand)

    @staticmethod
    def _push_action(state: PlayerState, two_hand: bool) -> Action:
        return Action(
            "push", state.slot, state.t, push=state.push, dist=state.root[2], two_hand=two_hand
        )


def _other(hand: str) -> str:
    return "R" if hand == "L" else "L"
