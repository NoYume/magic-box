"""Body filtering and body-to-slot assignment (spec sections 7.1 and 7.2).

Owner: Enoch
"""

import math
from collections.abc import Sequence

from magic_box.core.config import Config
from magic_box.perception.raw import RawBody

NUM_SLOTS = 2


def filter_bodies(bodies: Sequence[RawBody], max_range_m: float) -> list[RawBody]:
    """Keep tracked bodies within range; at most two, nearest first."""
    kept = [
        b
        for b in bodies
        if b.tracking_ok
        and all(math.isfinite(v) for v in b.position)
        and 0.0 < b.position[2] <= max_range_m
    ]
    kept.sort(key=lambda b: b.position[2])
    return kept[:NUM_SLOTS]


class SlotAssigner:
    """Binds tracked bodies to player slots.

    Slot 0 = P1, who appears on the image's right (larger x). A slot keeps its
    ZED id while that id is present, and holds it for `perception.slot_hold_s`
    of camera time after it disappears.
    """

    def __init__(self, cfg: Config) -> None:
        self._max_range_m: float = cfg["camera"]["max_range_m"]
        self._hold_s: float = cfg["perception"]["slot_hold_s"]
        # slot -> (zed id, cam_t last seen)
        self._bindings: dict[int, tuple[int, float]] = {}

    def bound_id(self, slot: int) -> int | None:
        binding = self._bindings.get(slot)
        return binding[0] if binding else None

    def assign(self, bodies: Sequence[RawBody], cam_t: float) -> dict[int, RawBody]:
        present = {b.id: b for b in filter_bodies(bodies, self._max_range_m)}

        for slot, (zed_id, last_seen) in list(self._bindings.items()):
            last_seen = min(last_seen, cam_t)  # the camera clock can rewind (SVO loop)
            if zed_id in present:
                last_seen = cam_t
            elif cam_t - last_seen > self._hold_s:
                del self._bindings[slot]
                continue
            self._bindings[slot] = (zed_id, last_seen)

        bound_ids = {zed_id for zed_id, _ in self._bindings.values()}
        free = [s for s in range(NUM_SLOTS) if s not in self._bindings]
        newcomers = sorted(
            (b for i, b in present.items() if i not in bound_ids),
            key=lambda b: b.position[0],
            reverse=True,
        )
        if len(free) == NUM_SLOTS and len(newcomers) == 1:
            slot = 0 if newcomers[0].position[0] >= 0 else 1
            self._bindings[slot] = (newcomers[0].id, cam_t)
        elif len(free) == NUM_SLOTS:
            for slot, body in zip(free, newcomers, strict=False):  # larger x -> slot 0
                self._bindings[slot] = (body.id, cam_t)
        elif len(free) == 1 and newcomers:
            body = newcomers[0] if free[0] == 0 else newcomers[-1]
            self._bindings[free[0]] = (body.id, cam_t)

        return {slot: present[i] for slot, (i, _) in sorted(self._bindings.items()) if i in present}
