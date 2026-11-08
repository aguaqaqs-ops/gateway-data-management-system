"""One caller-owned compute lifetime, shared by all stages of an operation.

Reservations model live business inputs and derived buffers, not process RSS.
The process worker supplies its real control and explicit deployment budget.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterator
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from dataclasses import dataclass, field
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

    def bind_backing(self, backing: Hashable) -> None:
        if self._closed or len(self._keys) != 1:
            raise ValueError("only a live single reservation can bind a backing")
        self._keys = (self._owner.bind_backing(self._keys[0], backing),)

    def shrink_to(self, size: int) -> None:
        """Return unused bytes from one unshared phase reservation."""
        if self._closed or len(self._keys) != 1:
            raise ValueError("only a live single reservation can shrink")
        self._owner.shrink(self._keys[0], size)

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
        self._metadata: dict[int, tuple[object, Reservation]] = {}
        self.stage_admissions: list[dict[str, int | str]] = []

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

    def bind_backing(self, old: Hashable, new: Hashable) -> Hashable:
        if old == new:
            return old
        entry = self._live[old]
        if entry.borrowers != 1:
            raise ValueError("backing binding requires sole ownership")
        existing = self._live.get(new)
        if existing is not None:
            if existing.size != entry.size:
                raise ValueError("shared backing has inconsistent reservation sizes")
            existing.borrowers += 1
            self.used_bytes -= entry.size
        else:
            self._live[new] = entry
        del self._live[old]
        return new

    def shrink(self, key: Hashable, size: int) -> None:
        entry = self._live[key]
        if type(size) is not int or size < 0 or size > entry.size or entry.borrowers != 1:
            raise ValueError("phase reservation shrink requires one borrower and a smaller size")
        self.used_bytes -= entry.size - size
        entry.size = size

    def retain_metadata(self, value: object, size: int) -> None:
        # Descriptors escape individual reader.close() through summaries and
        # ParsedTable. Keep their explicit conservative reservation for this
        # operation, without tracing the Python allocator.
        if id(value) not in self._metadata:
            reservation = self.reserve(size, backing=("metadata", id(value)))
            self._metadata[id(value)] = (value, reservation)

    def record_stage_admission(self, name: str, temporary_limit_bytes: int) -> None:
        self.stage_admissions.append({"stage": name, "retained_bytes": self.used_bytes,
                                      "temporary_limit_bytes": temporary_limit_bytes})

    def close(self) -> None:
        for _, reservation in self._metadata.values():
            reservation.close()
        self._metadata.clear()

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
    resources: ExitStack = field(default_factory=ExitStack, repr=False, compare=False)

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
        try:
            context.resources.close()
        finally:
            context.memory.close()


@dataclass(frozen=True, slots=True)
class CombinedCancelProbe:
    first: CancelProbe
    second: CancelProbe

    def is_set(self) -> bool:
        return self.first.is_set() or self.second.is_set()


def merge_kernel_control(
    context: KernelExecutionContext, probe: CancelProbe, deadline_monotonic: float | None,
) -> KernelExecutionContext:
    deadlines = tuple(d for d in (context.deadline_monotonic, deadline_monotonic) if d is not None)
    return KernelExecutionContext(context.memory, CombinedCancelProbe(context.cancel_probe, probe),
                                  context.threads, min(deadlines) if deadlines else None, context.resources)


@contextmanager
def kernel_control_scope(probe: CancelProbe, deadline_monotonic: float | None) -> Iterator[KernelExecutionContext]:
    """Narrow control for nested callers while retaining the operation lifetime."""
    context = current_kernel_context()
    if context is None:
        raise ValueError("kernel control scope requires an operation context")
    merged = merge_kernel_control(context, probe, deadline_monotonic)
    token = _active_context.set(merged)
    try:
        merged.checkpoint()
        yield merged
        merged.checkpoint()
    finally:
        _active_context.reset(token)
