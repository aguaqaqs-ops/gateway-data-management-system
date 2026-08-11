"""Process-local non-blocking permit pools for upload and row-stream admission."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True, slots=True)
class PermitPoolSnapshot:
    capacity: int
    in_use: int
    closed: bool


@final
class PermitLease:
    """Idempotent release handle for a single permit."""

    __slots__ = ("_pool", "_released")

    def __init__(self, pool: PermitPool) -> None:
        self._pool = pool
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._pool._release()

    def __enter__(self) -> PermitLease:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


@final
class PermitPool:
    """Fixed-capacity, thread-safe, non-blocking permit pool.

    Capacity is fixed at construction. ``try_acquire`` never queues. After
    ``close``, new acquires fail while outstanding leases may still release.
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("permit pool capacity must be positive")
        self._capacity = capacity
        self._in_use = 0
        self._closed = False
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def in_use(self) -> int:
        with self._lock:
            return self._in_use

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def snapshot(self) -> PermitPoolSnapshot:
        with self._lock:
            return PermitPoolSnapshot(
                capacity=self._capacity,
                in_use=self._in_use,
                closed=self._closed,
            )

    def try_acquire(self) -> PermitLease | None:
        with self._lock:
            if self._closed:
                return None
            if self._in_use >= self._capacity:
                return None
            self._in_use += 1
            return PermitLease(self)

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def _release(self) -> None:
        with self._lock:
            if self._in_use <= 0:
                raise RuntimeError("permit pool released more leases than acquired")
            self._in_use -= 1
