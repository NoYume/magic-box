"""Background Spark jobs with deadlines and fallbacks; `poll` never waits.

Owner: Nikhil. See the 2026-10-24 nikhil-pipeline spec, section 10.
"""

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from magic_box.ai.chronicle import template_chronicle, write_chronicle
from magic_box.ai.incantations import fallback_incantations, generate_incantations
from magic_box.ai.spark_client import SparkClient
from magic_box.core.config import Config
from magic_box.core.contracts import GameEvent


@dataclass
class _Job:
    future: Future | None  # None: resolves to the fallback at the next poll
    deadline: float
    fallback: Callable[[], object]


class AiWorker:
    """One single-thread executor; at most one pending job per kind."""

    def __init__(self, cfg: Config, client=None) -> None:
        self._cfg = cfg
        self._client = client if client is not None else SparkClient(cfg)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spark")
        self._jobs: dict[str, _Job] = {}

    def _available(self) -> bool:
        return bool(getattr(self._client, "available", lambda: True)())

    def _start(
        self, kind: str, now: float, work: Callable[[], object], fallback: Callable[[], object]
    ) -> None:
        old = self._jobs.pop(kind, None)
        if old is not None and old.future is not None:
            old.future.cancel()
        future = self._executor.submit(work) if self._available() else None
        self._jobs[kind] = _Job(future, now + self._cfg["ai"]["timeout_s"], fallback)

    def start_incantations(
        self, classes: Mapping[int, str], names: Mapping[int, str], now: float
    ) -> None:
        classes, names = dict(classes), dict(names)
        self._start(
            "incantations",
            now,
            lambda: generate_incantations(self._client, classes, names, self._cfg),
            lambda: fallback_incantations(classes, self._cfg),
        )

    def start_chronicle(
        self, events: Sequence[GameEvent], names: Mapping[int, str], now: float
    ) -> None:
        events, names = list(events), dict(names)
        self._start(
            "chronicle",
            now,
            lambda: write_chronicle(self._client, events, names, self._cfg),
            lambda: template_chronicle(events, names, self._cfg),
        )

    def poll(self, now: float) -> list[tuple[str, object]]:
        """Finished results, or fallbacks for jobs past their deadline. Never waits."""
        out: list[tuple[str, object]] = []
        for kind in list(self._jobs):
            job = self._jobs[kind]
            if job.future is None:
                out.append((kind, job.fallback()))
            elif job.future.done():
                try:
                    out.append((kind, job.future.result()))
                except Exception:
                    out.append((kind, job.fallback()))
            elif now >= job.deadline:
                job.future.cancel()  # a late result is never read: the job is dropped
                out.append((kind, job.fallback()))
            else:
                continue
            del self._jobs[kind]
        return out

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
