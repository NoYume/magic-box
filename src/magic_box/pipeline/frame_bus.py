"""Shared-memory frame bus: perception writes the newest camera frame, the game reads it.

Owner: Nikhil

One writer, any number of readers, nobody ever blocks. The block is a double
buffer guarded by a per-slot seqlock. Layout (native-endian, 64-byte aligned):

    offset 0              int64   latest     newest complete slot, -1 = never written
    offset 64 + k*stride  slot k (k = 0, 1):
        +0                uint64  seq        odd while the writer is copying into the slot
        +8                int64   frame_idx
        +16               float64 cam_t
        +64               uint8   image      height x width x channels

Memory ordering: Python has no explicit memory fences. Every field is 8-byte
aligned, so each header store is single-copy atomic, but on weakly ordered CPUs
(aarch64: the Jetson and Apple silicon) nothing forces the image bytes to become
visible before the closing seq store. The reader's seq re-check is the only
guard; re-run tests/pipeline/test_frame_bus.py on the Jetson.
"""

import sys
from multiprocessing import parent_process, resource_tracker
from multiprocessing.shared_memory import SharedMemory

import numpy as np

from magic_box.core.contracts import Frame

_ALIGN = 64
_MAX_RETRIES = 10


def _round_up(n: int) -> int:
    return -(-n // _ALIGN) * _ALIGN


def _slot_stride(shape: tuple[int, int, int]) -> int:
    return _ALIGN + _round_up(shape[0] * shape[1] * shape[2])


def _total_bytes(shape: tuple[int, int, int]) -> int:
    return _ALIGN + 2 * _slot_stride(shape)


class _Slot:
    """Numpy views over one slot of the shared block."""

    def __init__(self, buf: memoryview, offset: int, shape: tuple[int, int, int]) -> None:
        self.seq = np.ndarray((), np.uint64, buf, offset)
        self.frame_idx = np.ndarray((), np.int64, buf, offset + 8)
        self.cam_t = np.ndarray((), np.float64, buf, offset + 16)
        self.image = np.ndarray(shape, np.uint8, buf, offset + _ALIGN)


class FrameBus:
    """Latest-frame slot in shared memory. Build it with create() or attach()."""

    def __init__(self, shm: SharedMemory, width: int, height: int, channels: int) -> None:
        self._shm = shm
        self._shape = (height, width, channels)
        stride = _slot_stride(self._shape)
        self._latest = np.ndarray((), np.int64, shm.buf, 0)
        self._slots = [_Slot(shm.buf, _ALIGN + k * stride, self._shape) for k in (0, 1)]
        self._last_good: Frame | None = None

    @classmethod
    def create(cls, width: int, height: int, channels: int = 4) -> "FrameBus":
        """Create a new segment. The creator owns it and must close() then unlink() it."""
        shape = (height, width, channels)
        bus = cls(SharedMemory(create=True, size=_total_bytes(shape)), width, height, channels)
        bus._latest[...] = -1
        return bus

    @classmethod
    def attach(cls, name: str, width: int, height: int, channels: int = 4) -> "FrameBus":
        """Open an existing segment. Call close() when done, never unlink()."""
        if sys.version_info >= (3, 13):
            shm = SharedMemory(name=name, track=False)
        else:
            shm = SharedMemory(name=name)
            # Before 3.13, attaching registers the segment with this process's
            # resource tracker. Spawned children share the creator's tracker,
            # which keeps names in a set and only cleans up after every process
            # in the tree has exited, so a child must not unregister: that would
            # drop the creator's entry (losing crash cleanup) and make its
            # unlink() raise KeyError in the tracker. An unrelated process owns
            # its own tracker, which would unlink the segment when that process
            # exits, so only it unregisters.
            if parent_process() is None:
                resource_tracker.unregister(shm._name, "shared_memory")
        return cls(shm, width, height, channels)

    @property
    def name(self) -> str:
        return self._shm.name

    def write(self, frame: Frame) -> None:
        """Copy frame into the slot readers are not using, then publish it."""
        image = frame.image
        if image.shape != self._shape or image.dtype != np.uint8:
            raise ValueError(
                f"expected uint8 image of shape {self._shape}, got {image.dtype} {image.shape}"
            )
        # Convert first so a bad field raises before the slot is marked as writing.
        frame_idx = int(frame.frame_idx)
        cam_t = float(frame.cam_t)
        k = 1 if int(self._latest) == 0 else 0
        slot = self._slots[k]
        # Odd = writing. "| 1" instead of "+ 1": a writer killed mid-copy (the
        # launcher restarts perception, which re-attaches) leaves seq odd, and
        # the next write must still end on an even, never-seen-before value.
        start = int(slot.seq) | 1
        slot.seq[...] = start
        slot.frame_idx[...] = frame_idx
        slot.cam_t[...] = cam_t
        np.copyto(slot.image, image)
        slot.seq[...] = start + 1  # even: complete
        self._latest[...] = k

    def read_latest(self) -> Frame | None:
        """Newest complete frame as a private copy; None before the first write.

        Never blocks. If the writer keeps overtaking the reader for _MAX_RETRIES
        attempts, returns the last frame this reader verified (or None).
        """
        for _ in range(_MAX_RETRIES):
            k = int(self._latest)
            if k < 0:
                return None
            slot = self._slots[k]
            seq = int(slot.seq)
            if seq % 2:
                continue
            frame_idx = int(slot.frame_idx)
            cam_t = float(slot.cam_t)
            image = slot.image.copy()
            if int(slot.seq) != seq:
                continue
            self._last_good = Frame(frame_idx=frame_idx, cam_t=cam_t, image=image)
            return self._last_good
        return self._last_good

    def close(self) -> None:
        """Release this process's mapping. The views must go first or close() fails."""
        self._latest = None
        self._slots = []
        self._shm.close()

    def unlink(self) -> None:
        """Destroy the segment. Only the creator calls this, after close()."""
        self._shm.unlink()
