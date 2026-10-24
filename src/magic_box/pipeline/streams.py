"""Drop-oldest multiprocessing stream queue for perception/voice -> game.

Owner: Nikhil
"""

import multiprocessing
import queue
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

    @property
    def dropped(self) -> int:
        return self._dropped.value
