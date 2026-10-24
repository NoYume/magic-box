"""Muse Spark client over an OpenAI-compatible API (spec section 8, ai/).

Owner: Nikhil
"""

from magic_box.core.config import Config


class SparkClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError("TODO(Nikhil): Spark chat completion")
