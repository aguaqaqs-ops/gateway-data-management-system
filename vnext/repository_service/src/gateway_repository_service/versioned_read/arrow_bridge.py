"""Bounded async bridge from provider Arrow batches to HTTP IPC bytes."""

from __future__ import annotations

import asyncio
import io
import logging
import queue
import threading
import time
import weakref
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Literal

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.arrow_mapping import CompiledTablePlan
from gateway_repository_service.versioned_read.wire import close_row_iterator

if TYPE_CHECKING:
    from gateway_repository_service.process import DoltRunner

_LOGGER = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 1
_POLL_TIMEOUT_SECONDS = 0.05
_WORKER_JOIN_TIMEOUT_SECONDS = 30.0
_SUCCESS_SENTINEL = object()
_FAILURE_SENTINEL = object()
TerminalOutcome = Literal["pending", "success", "failure"]


class BridgeStreamAbortedError(RuntimeError):
    """Raised when an Arrow IPC stream ends before a successful EOS."""


class BridgeJoinTimeoutError(RuntimeError):
    """Raised when a bridge worker does not exit after cancellation."""


class BridgeShutdownError(RuntimeError):
    """Raised when one or more bridge workers survive service shutdown."""

    def __init__(self, failures: tuple[BridgeJoinTimeoutError, ...]) -> None:
        self.failures = failures
        count = len(failures)
        super().__init__(f"{count} versioned read bridge worker(s) did not exit during shutdown")


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
        join_errors: list[BridgeJoinTimeoutError] = []
        for bridge in self.snapshot():
            try:
                bridge.close_sync(
                    dolt_runner=dolt_runner,
                    join_timeout_seconds=join_timeout_seconds,
                )
            except BridgeJoinTimeoutError as exc:
                join_errors.append(exc)
            except Exception:
                _LOGGER.warning("versioned read bridge did not stop during service shutdown", exc_info=True)
        survivors = tuple(bridge for bridge in self.snapshot() if bridge.is_worker_alive())
        if join_errors or survivors:
            if survivors:
                _LOGGER.error(
                    "versioned read bridge workers still alive after shutdown",
                    extra={"count": len(survivors)},
                )
            raise BridgeShutdownError(tuple(join_errors))


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
        stream_owner: object | None = None,
    ) -> None:
        self._plan = plan
        self._row_iterator = row_iterator
        self._cancellation = cancellation
        self._dolt_runner = dolt_runner
        self._stream_owner = stream_owner
        self._queue: queue.Queue[bytes | object] = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._worker_done = threading.Event()
        self._close_lock = threading.Lock()
        self._close_condition = threading.Condition(self._close_lock)
        self._close_requested = False
        self._worker_joined = False
        self._terminal_outcome: TerminalOutcome = "pending"
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
                try:
                    item = await asyncio.to_thread(self._queue.get, True, _POLL_TIMEOUT_SECONDS)
                except queue.Empty:
                    if self._worker_joined:
                        if self._terminal_outcome == "success":
                            break
                        raise BridgeStreamAbortedError("versioned read arrow stream aborted")
                    await asyncio.sleep(0)
                    continue
                if item is _SUCCESS_SENTINEL:
                    break
                if item is _FAILURE_SENTINEL:
                    raise BridgeStreamAbortedError("versioned read arrow stream aborted")
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
        runner = dolt_runner if dolt_runner is not None else self._dolt_runner
        deadline_at = time.monotonic() + join_timeout_seconds
        already_joined = False
        with self._close_condition:
            if self._worker_joined:
                return
            if not self._close_requested:
                self._close_requested = True
                self._cancellation.set()
            while not self._worker_joined:
                remaining = deadline_at - time.monotonic()
                if remaining <= 0:
                    break
                self._close_condition.wait(timeout=min(remaining, _POLL_TIMEOUT_SECONDS))
            already_joined = self._worker_joined

        if already_joined:
            return
        if self._worker.is_alive():
            _LOGGER.warning("versioned read arrow bridge worker did not exit in time")
            if runner is not None and self._stream_owner is not None:
                terminate_owned = getattr(runner, "terminate_owned", None)
                if callable(terminate_owned):
                    terminate_owned(self._stream_owner)
            remaining = deadline_at - time.monotonic()
            join_timeout = remaining if remaining > 0 else _POLL_TIMEOUT_SECONDS
            self._worker.join(timeout=join_timeout)
        if self._worker.is_alive():
            raise BridgeJoinTimeoutError("versioned read arrow bridge worker did not exit")

    def _put_terminal(self, terminal: object) -> bool:
        if terminal is _SUCCESS_SENTINEL:
            is_success = True
        elif terminal is _FAILURE_SENTINEL:
            is_success = False
            with self._close_lock:
                if self._terminal_outcome == "pending":
                    self._terminal_outcome = "failure"
        else:
            raise ValueError(f"unsupported terminal sentinel: {terminal!r}")
        while True:
            try:
                self._queue.put(terminal, timeout=_POLL_TIMEOUT_SECONDS)
                if is_success:
                    with self._close_lock:
                        if self._terminal_outcome == "pending":
                            self._terminal_outcome = "success"
                return True
            except queue.Full:
                if self._cancellation.is_set():
                    if is_success:
                        with self._close_lock:
                            if self._terminal_outcome == "pending":
                                self._terminal_outcome = "failure"
                    return False

    def _put_chunk(self, chunk: bytes) -> bool:
        while True:
            try:
                self._queue.put(chunk, timeout=_POLL_TIMEOUT_SECONDS)
                return True
            except queue.Full:
                if self._cancellation.is_set():
                    return False

    def _flush_sink(self, sink: io.BytesIO) -> bool:
        delta = sink.getvalue()
        if delta and not self._put_chunk(delta):
            return False
        sink.seek(0)
        sink.truncate(0)
        return True

    def _finish_worker(self, *, completed: bool) -> None:
        if not completed:
            self._put_terminal(_FAILURE_SENTINEL)
        self._worker_done.set()
        with self._close_condition:
            self._worker_joined = True
            self._close_condition.notify_all()
        BRIDGE_REGISTRY.unregister(self)

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
                if not self._flush_sink(sink):
                    return
            if self._cancellation.is_set():
                return
            writer.close()
            if not self._flush_sink(sink):
                return
            if not self._put_terminal(_SUCCESS_SENTINEL):
                return
            completed = True
        except Exception:
            if completed:
                return
            self._put_terminal(_FAILURE_SENTINEL)
        finally:
            if writer is not None and not completed:
                del writer
            try:
                close_row_iterator(self._row_iterator)
            finally:
                self._finish_worker(completed=completed)
