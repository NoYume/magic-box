"""Background Spark jobs with deadlines and fallbacks; `poll` never waits.

Owner: Nikhil. See the 2026-10-24 nikhil-pipeline spec, section 10.

Each job runs on its own daemon thread. A Spark call can take up to `ai.timeout_s` (8 s), and
a `ThreadPoolExecutor` worker is joined at interpreter exit, so an in-flight call used to
hold the quit for that long. Daemon threads are never joined: `close()` returns at once and
the process can exit while a call is still in flight. A replaced or timed-out job's thread
runs to its own end (bounded by the OpenAI client timeout) and its result is dropped.
"""

import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future
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


def _run(future: Future, work: Callable[[], object]) -> None:
    if not future.set_running_or_notify_cancel():
        return
    try:
        future.set_result(work())
    except BaseException as exc:  # handed to poll, which falls back
        future.set_exception(exc)


class AiWorker:
    """At most one pending job per kind, each on its own daemon thread.

    Public API for the loop: `start_incantations`, `start_chronicle`, `poll(now)` and
    `close()`. None of them blocks.
    """

    def __init__(self, cfg: Config, client=None) -> None:
        self._cfg = cfg
        self._client = client if client is not None else SparkClient(cfg)
        self._jobs: dict[str, _Job] = {}
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def _available(self) -> bool:
        return bool(getattr(self._client, "available", lambda: True)())

    def _start(
        self, kind: str, now: float, work: Callable[[], object], fallback: Callable[[], object]
    ) -> None:
        if self._closed:
            return
        self._jobs.pop(kind, None)  # a replaced job's late result is never read
        future: Future | None = None
        if self._available():
            future = Future()
            thread = threading.Thread(
                target=_run, args=(future, work), name=f"spark-{kind}", daemon=True
            )
            thread.start()
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
                out.append((kind, job.fallback()))  # the late result is never read
            else:
                continue
            del self._jobs[kind]
        return out

    def close(self) -> None:
        """Drop every pending job and return at once; never waits for a call in flight.

        Idempotent. After close, `start_*` are no-ops and `poll` returns nothing.
        """
        self._closed = True
        self._jobs.clear()
