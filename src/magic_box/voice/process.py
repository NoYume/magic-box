"""Voice process entry point (spec section 8, voice/).

Owner: Nikhil
"""

from multiprocessing.synchronize import Event

from magic_box.core.config import Config
from magic_box.pipeline.streams import DropOldestQueue


def run(cfg: Config, voice_q: DropOldestQueue, control_q: DropOldestQueue, stop: Event) -> None:
    """Capture mics, stream to Muse, publish VoiceEvents; read VoiceConfig from control_q."""
    raise NotImplementedError("TODO(Nikhil): voice process loop")
