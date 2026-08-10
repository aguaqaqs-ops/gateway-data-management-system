"""Bounded async bridge from provider Arrow batches to HTTP IPC bytes."""

from __future__ import annotations

import asyncio
import io
import logging
import queue
import threading
import weakref
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.arrow_mapping import CompiledTablePlan
from gateway_repository_service.versioned_read.wire import close_row_iterator

if TYPE_CHECKING:
    from gateway_repository_service.process import DoltRunner

_LOGGER = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 1
_POLL_TIMEOUT_SECONDS = 0.05
_WORKER_JOIN_TIMEOUT_SECONDS = 30.0
_WORKER_REJOIN_TIMEOUT_SECONDS = 2.0
_DOLT_REAP_GRACE_SECONDS = 0.5
_SENTINEL = object()


class BridgeJoinTimeoutError(RuntimeError):
    """Raised when a bridge worker does not exit after cancellation."""


class _BridgeRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: weakref.WeakSet[ArrowIpcStreamBridge] = weakref.WeakSet()

    def register(self, bridge: ArrowIpcStreamBridge) -> None:
        with self._lock:
            self._active.add(bridge)

    def unregister(self, bridge: ArrowIpcStreamBridge) -> None:
        with self._lock:
            self._active.discard(bridge)

    def snapshot(self) -> tuple[ArrowIpcStreamBridge, ...]:
        with self._lock:
            return tuple(self._active)

    def close_all(
        self,
        dolt_runner: DoltRunner | None,
        *,
        join_timeout_seconds: float = _WORKER_JOIN_TIMEOUT_SECONDS,
    ) -> None:
        for bridge in self.snapshot():
            try:
                bridge.close_sync(
                    dolt_runner=dolt_runner,
                    join_timeout_seconds=join_timeout_seconds,
                )
            except BridgeJoinTimeoutError:
                _LOGGER.warning("versioned read bridge did not stop during service shutdown")


BRIDGE_REGISTRY = _BridgeRegistry()


class ArrowIpcStreamBridge:
    """Owns a non-daemon worker thread and bounded queue for Arrow IPC bytes."""

    def __init__(
        self,
        plan: CompiledTablePlan,
        row_iterator: Iterator[pa.RecordBatch],
        cancellation: threading.Event,
        *,
        dolt_runner: DoltRunner | None = None,
    ) -> None:
        self._plan = plan
        self._row_iterator = row_iterator
        self._cancellation = cancellation
        self._dolt_runner = dolt_runner
        self._queue: queue.Queue[bytes | object] = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._worker_done = threading.Event()
        self._worker_joined = threading.Event()
        self._closed = threading.Event()
        self._worker = threading.Thread(
            target=self._run_worker,
            name="versioned-read-arrow-bridge",
            daemon=False,
        )
        BRIDGE_REGISTRY.register(self)
        self._worker.start()

    def is_worker_alive(self) -> bool:
        return self._worker.is_alive()

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        try:
            while True:
                if self._worker_done.is_set() and self._queue.empty():
                    break
                try:
                    item = await asyncio.to_thread(self._queue.get, True, _POLL_TIMEOUT_SECONDS)
                except queue.Empty:
                    await asyncio.sleep(0)
                    continue
                if item is _SENTINEL:
                    break
                if isinstance(item, bytes):
                    yield item
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        await asyncio.to_thread(
            self.close_sync,
            self._dolt_runner,
            _WORKER_JOIN_TIMEOUT_SECONDS,
        )

    def close_sync(
        self,
        dolt_runner: DoltRunner | None = None,
        join_timeout_seconds: float = _WORKER_JOIN_TIMEOUT_SECONDS,
    ) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        self._cancellation.set()
        close_row_iterator(self._row_iterator)
        self._worker.join(timeout=join_timeout_seconds)
        if self._worker.is_alive():
            _LOGGER.warning("versioned read arrow bridge worker did not exit in time")
            close_row_iterator(self._row_iterator)
            runner = dolt_runner or self._dolt_runner
            if runner is not None:
                runner.terminate_active_children(grace_seconds=_DOLT_REAP_GRACE_SECONDS)
            self._worker.join(timeout=_WORKER_REJOIN_TIMEOUT_SECONDS)
            if self._worker.is_alive():
                BRIDGE_REGISTRY.unregister(self)
                raise BridgeJoinTimeoutError("versioned read arrow bridge worker did not exit")
        self._worker_joined.set()
        BRIDGE_REGISTRY.unregister(self)

    def _put_chunk(self, chunk: bytes | object) -> None:
        while not self._cancellation.is_set():
            try:
                self._queue.put(chunk, timeout=_POLL_TIMEOUT_SECONDS)
                return
            except queue.Full:
                continue

    def _flush_sink(self, sink: io.BytesIO) -> None:
        delta = sink.getvalue()
        if delta:
            self._put_chunk(delta)
        sink.seek(0)
        sink.truncate(0)

    def _run_worker(self) -> None:
        sink = io.BytesIO()
        writer: pa.ipc.RecordBatchStreamWriter | None = None
        completed = False
        try:
            writer = pa.ipc.new_stream(sink, self._plan.expected_schema)
            for batch in self._row_iterator:
                if self._cancellation.is_set():
                    return
                writer.write_batch(batch)
                self._flush_sink(sink)
            if self._cancellation.is_set():
                return
            writer.close()
            completed = True
            self._flush_sink(sink)
            if not self._cancellation.is_set():
                self._put_chunk(_SENTINEL)
        except Exception:
            if completed:
                return
        finally:
            if writer is not None and not completed:
                # Avoid writer.close() on failure/cancel to prevent accidental EOS.
                del writer
            close_row_iterator(self._row_iterator)
            self._worker_done.set()
