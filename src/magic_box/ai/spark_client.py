"""Muse Spark client over an OpenAI-compatible API (spec 2026-10-24 nikhil-pipeline, section 10).

Owner: Nikhil
"""

import os
from collections.abc import Callable, Mapping

from magic_box.core.config import Config


class SparkUnavailable(RuntimeError):
    """Spark is disabled or has no API key; callers fall back."""


class SparkClient:
    """Chat completion against `ai.base_url`. The OpenAI client is created on first use."""

    def __init__(
        self,
        cfg: Config,
        env: Mapping[str, str] | None = None,
        openai_factory: Callable[..., object] | None = None,
    ) -> None:
        self.cfg = cfg
        self._env = os.environ if env is None else env
        self._factory = openai_factory
        self._client = None

    def _api_key(self) -> str | None:
        return self._env.get(self.cfg["ai"]["api_key_env"]) or None

    def available(self) -> bool:
        """True when Spark is enabled and a key is present."""
        return bool(self.cfg["ai"]["enabled"]) and self._api_key() is not None

    def _get_client(self):
        if self._client is None:
            factory = self._factory
            if factory is None:
                from openai import OpenAI

                factory = OpenAI
            ai = self.cfg["ai"]
            self._client = factory(
                base_url=ai["base_url"],
                api_key=self._api_key(),
                timeout=ai["timeout_s"],
                max_retries=0,
            )
        return self._client

    def complete(self, system: str, user: str) -> str:
        if not self.available():
            raise SparkUnavailable("Spark is disabled or the API key is missing")
        ai = self.cfg["ai"]
        reply = self._get_client().chat.completions.create(
            model=ai["model"],
            temperature=ai["temperature"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return reply.choices[0].message.content or ""
