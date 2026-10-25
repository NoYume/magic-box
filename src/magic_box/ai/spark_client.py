"""Muse Spark client over an OpenAI-compatible API (spec 2026-10-24 nikhil-pipeline, section 10).

Owner: Nikhil

Verified live on 2026-10-25: chat completions at `https://api.meta.ai/v1` with model
`muse-spark-1.3`. Spark reasons before it answers. `ai.reasoning_effort` caps that so an
incantation set lands inside the `ai.timeout_s` deadline; `null` omits it (model-set effort).
"""

import os
import sys
from collections.abc import Callable, Mapping

from magic_box.core.config import Config


class SparkUnavailable(RuntimeError):
    """Spark is disabled or has no API key; callers fall back."""


def log_line(msg: str) -> None:
    print(f"spark: {msg}", file=sys.stderr, flush=True)


def describe_error(exc: BaseException) -> str:
    """The exception type and HTTP status only, such as `AuthenticationError 401`.

    Never the message: an openai error can echo request details.
    """
    status = getattr(exc, "status_code", None)
    code = "" if status is None else f" {status}"
    return f"{type(exc).__name__}{code}"


def log_fallback(job: str, exc: Exception) -> None:
    """One stderr line: the exception type and HTTP status only."""
    log_line(f"{job} fell back: {describe_error(exc)}")


class SparkClient:
    """Chat completion against `ai.base_url`. The OpenAI client is created on first use.

    `last_model` is the model id the last reply reported (None before the first reply).
    """

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
        self.last_model: str | None = None

    def _api_key(self) -> str | None:
        return (self._env.get(self.cfg["ai"]["api_key_env"]) or "").strip() or None

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
        extra = {}
        if ai.get("reasoning_effort") is not None:
            extra["reasoning_effort"] = ai["reasoning_effort"]
        reply = self._get_client().chat.completions.create(
            model=ai["model"],
            temperature=ai["temperature"],
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **extra,
        )
        self.last_model = getattr(reply, "model", None)
        return reply.choices[0].message.content or ""
