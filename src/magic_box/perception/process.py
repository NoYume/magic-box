"""Perception process entry point (spec section 8, perception/).

Owner: Enoch
"""

from multiprocessing.synchronize import Event

from magic_box.core.config import Config
from magic_box.pipeline.streams import DropOldestQueue


def run(cfg: Config, state_q: DropOldestQueue, frame_bus_name: str, stop: Event) -> None:
    """Grab frames, publish them on the frame bus and PlayerStates on state_q until stop is set."""
    raise NotImplementedError("TODO(Enoch): perception process loop")
