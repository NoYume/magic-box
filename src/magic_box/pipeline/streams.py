"""Drop-oldest multiprocessing stream queue for perception/voice -> game.

Owner: Nikhil
"""

import multiprocessing
import queue
import time
from collections.abc import Callable
from multiprocessing.context import BaseContext


def spawn_context() -> BaseContext:
    """The only multiprocessing context the project uses."""
    return multiprocessing.get_context("spawn")


class DropOldestQueue:
    """Bounded queue whose put() and drain() never block.

    When full, put() discards the oldest item to make room. Never calls
    qsize(), which is unimplemented on macOS.
    """

    def __init__(self, maxsize: int, ctx: BaseContext | None = None) -> None:
        ctx = ctx or spawn_context()
        self._queue = ctx.Queue(maxsize)
        self._dropped = ctx.Value("i", 0)

    def put(self, item) -> None:
        try:
            self._queue.put_nowait(item)
            return
        except queue.Full:
            pass
        try:
            # Short timeout: the feeder thread may not have flushed yet.
            self._queue.get(timeout=0.05)
            with self._dropped.get_lock():
                self._dropped.value += 1
        except queue.Empty:
            pass
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            # Another producer refilled the slot; drop the new item instead.
            with self._dropped.get_lock():
                self._dropped.value += 1

    def drain(self, max_items: int | None = None) -> list:
        items: list = []
        while max_items is None or len(items) < max_items:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return items

    def cancel_join(self) -> None:
        """Producer side, at exit: don't wait for the feeder thread to flush to a dead reader.

        Without this a child with more than ~64 KB queued and no reader never exits. Losing
        the unread items is fine for a drop-oldest stream.
        """
        self._queue.cancel_join_thread()

    @property
    def dropped(self) -> int:
        return self._dropped.value


class ParentAwareStop:
    """Wraps a stop Event so a child also stops when its parent process is gone.

    After a native crash or an OOM kill of the game, children would keep the ZED and the
    mics open and block the launcher's restart. The parent check runs at most once per
    `check_s`, so calling `is_set()` every frame stays cheap.
    """

    def __init__(
        self,
        stop,
        parent_alive: Callable[[], bool] | None = None,
        check_s: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._stop = stop
        self._parent_alive = parent_alive if parent_alive is not None else _parent_alive
        self._check_s = check_s
        self._clock = clock
        self._next_check = 0.0
        self._orphaned = False

    def is_set(self) -> bool:
        if self._stop.is_set() or self._orphaned:
            return True
        now = self._clock()
        if now >= self._next_check:
            self._next_check = now + self._check_s
            if not self._parent_alive():
                self._orphaned = True
                return True
        return False

    def wait(self, timeout: float | None = None) -> bool:
        return self._stop.wait(timeout)


def _parent_alive() -> bool:
    parent = multiprocessing.parent_process()
    return parent is None or parent.is_alive()
