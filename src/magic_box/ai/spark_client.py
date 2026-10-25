"""Muse Spark client over an OpenAI-compatible API (spec section 8, ai/).

Owner: Nikhil
"""

import os

from magic_box.core.config import Config


class SparkClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def complete(self, system: str, user: str) -> str:
        """Perform one bounded completion; callers own validation and fallback."""
        from openai import OpenAI

        ai = self.cfg["ai"]
        key = os.environ.get(ai["api_key_env"])
        if not ai["enabled"] or not key:
            raise RuntimeError("Muse Spark is disabled or its API key is unavailable")
        client = OpenAI(
            api_key=key,
            base_url=ai["base_url"],
            timeout=float(ai["timeout_s"]),
        )
        response = client.chat.completions.create(
            model=ai["model"],
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Muse Spark returned an empty completion")
        return content
