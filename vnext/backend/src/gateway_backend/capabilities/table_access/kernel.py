"""One caller-owned compute lifetime, shared by all stages of an operation.

Reservations model live business inputs and derived buffers, not process RSS.
The process worker supplies its real control and explicit deployment budget.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Hashable

import pyarrow as pa

from gateway_backend.capabilities.table_access.contracts import CancelProbe


class KernelStopped(InterruptedError):
    """A probe stopped compute; the application retains the original reason."""


class KernelMemoryLimit(MemoryError):
    """The next operation allocation would exceed its explicit reservation."""


@dataclass
class _LiveEntry:
    size: int
    borrowers: int = 1


class Reservation:
    def __init__(self, owner: OperationMemoryBudget, keys: tuple[Hashable, ...]) -> None:
        self._owner = owner
        self._keys = keys
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for key in self._keys:
            self._owner.release(key)

    def __enter__(self) -> Reservation:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class OperationMemoryBudget:
    """Explicit reservations with deduplication of actual shared backing buffers."""

    def __init__(self, limit_bytes: int) -> None:
        if type(limit_bytes) is not int or limit_bytes <= 0:
            raise ValueError("operation memory budget must be a positive integer")
        self.limit_bytes = limit_bytes
        self.used_bytes = 0
        self.high_water_bytes = 0
        self._live: dict[Hashable, _LiveEntry] = {}
        self._mappings: dict[Hashable, tuple[int, int]] = {}

    @property
    def available_bytes(self) -> int:
        return self.limit_bytes - self.used_bytes

    def ensure(self, extra_bytes: int) -> None:
        if type(extra_bytes) is not int or extra_bytes < 0:
            raise ValueError("reservation must be a non-negative integer")
        if extra_bytes > self.available_bytes:
            raise KernelMemoryLimit("operation memory reservation exceeded")

    def reserve(self, size: int, *, backing: Hashable | None = None) -> Reservation:
        key = object() if backing is None else backing
        current = self._live.get(key)
        if current is not None:
            if current.size != size:
                raise ValueError("shared backing has inconsistent reservation sizes")
            current.borrowers += 1
        else:
            self.ensure(size)
            self._live[key] = _LiveEntry(size)
            self.used_bytes += size
            self.high_water_bytes = max(self.high_water_bytes, self.used_bytes)
        return Reservation(self, (key,))

    def register_mapping(self, backing: Hashable, buffer: pa.Buffer) -> None:
        if backing not in self._live or self._live[backing].size != buffer.size:
            raise ValueError("mapping must have its complete reservation before opening")
        self._mappings[backing] = (buffer.address, buffer.size)

    def retain_arrow(self, value: pa.Table | pa.RecordBatch) -> Reservation:
        keys: list[Hashable] = []
        unique: dict[Hashable, int] = {}
        for column in value.columns:
            chunks = column.chunks if isinstance(column, pa.ChunkedArray) else (column,)
            for array in chunks:
                for buffer in array.buffers():
                    if buffer is None:
                        continue
                    while buffer.parent is not None:
                        buffer = buffer.parent
                    mapping = next((key for key, (address, size) in self._mappings.items()
                                    if address <= buffer.address and buffer.address + buffer.size <= address + size), None)
                    if mapping is not None:
                        unique[mapping] = self._live[mapping].size
                    else:
                        unique[("arrow", buffer.address, buffer.size)] = buffer.size
        chunks = sum(len(c.chunks) if isinstance(c, pa.ChunkedArray) else 1 for c in value.columns)
        unique[("arrow-headers", id(value))] = 1024 + len(value.columns) * 512 + chunks * 256
        self.ensure(sum(size for key, size in unique.items() if key not in self._live))
        for key, size in unique.items():
            current = self._live.get(key)
            if current is None:
                self._live[key] = _LiveEntry(size)
                self.used_bytes += size
            else:
                current.borrowers += 1
            keys.append(key)
        self.high_water_bytes = max(self.high_water_bytes, self.used_bytes)
        return Reservation(self, tuple(keys))

    def release(self, key: Hashable) -> None:
        current = self._live[key]
        current.borrowers -= 1
        if current.borrowers == 0:
            self.used_bytes -= current.size
            del self._live[key]
            self._mappings.pop(key, None)


@dataclass(frozen=True, slots=True)
class KernelExecutionContext:
    memory: OperationMemoryBudget
    cancel_probe: CancelProbe
    threads: int
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        if type(self.threads) is not int or not 1 <= self.threads <= 256:
            raise ValueError("kernel threads must be in 1..256")
        if self.deadline_monotonic is not None and (
            type(self.deadline_monotonic) is not float or not math.isfinite(self.deadline_monotonic)
        ):
            raise ValueError("kernel deadline must be finite or None")

    def checkpoint(self) -> None:
        if self.cancel_probe.is_set():
            raise KernelStopped("operation control stopped compute")
        if self.deadline_monotonic is not None and time.monotonic() >= self.deadline_monotonic:
            raise TimeoutError("operation compute deadline elapsed")


_active_context: ContextVar[KernelExecutionContext | None] = ContextVar("operation_kernel_context", default=None)


def current_kernel_context() -> KernelExecutionContext | None:
    return _active_context.get()


@contextmanager
def kernel_execution_scope(context: KernelExecutionContext, *, new_operation: bool = False) -> Iterator[KernelExecutionContext]:
    previous = _active_context.get()
    if previous is not None and not new_operation:
        if previous is not context:
            raise ValueError("nested kernel stages must share the operation context")
        yield previous
        return
    token = _active_context.set(context)
    try:
        yield context
    finally:
        _active_context.reset(token)
