"""Fake OpenAI factory and fake Spark client for tests (no network).

Owner: Nikhil
"""

from types import SimpleNamespace


class FakeOpenAI:
    """Acts as the `openai_factory`: records constructor kwargs and chat calls."""

    def __init__(self, reply: "str | Exception") -> None:
        self.reply = reply
        self.kwargs: dict | None = None
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=self._create))
        )

    def _create(self, **kw):
        self.calls.append(kw)
        if isinstance(self.reply, Exception):
            raise self.reply
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Stands in for SparkClient: records (system, user) and returns or raises."""

    def __init__(self, reply: "str | Exception") -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply
