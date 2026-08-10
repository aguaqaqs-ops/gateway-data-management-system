"""Bounded async bridge from provider Arrow batches to HTTP IPC bytes."""

from __future__ import annotations

import asyncio
import io
import logging
import queue
import threading
from collections.abc import AsyncIterator, Iterator

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_service.arrow_mapping import CompiledTablePlan
from gateway_repository_service.versioned_read.wire import close_row_iterator

_LOGGER = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 1
_POLL_TIMEOUT_SECONDS = 0.05
_WORKER_JOIN_TIMEOUT_SECONDS = 30.0
_SENTINEL = object()


class ArrowIpcStreamBridge:
    """Owns a non-daemon worker thread and bounded queue for Arrow IPC bytes."""

    def __init__(
        self,
        plan: CompiledTablePlan,
        row_iterator: Iterator[pa.RecordBatch],
        cancellation: threading.Event,
    ) -> None:
        self._plan = plan
        self._row_iterator = row_iterator
        self._cancellation = cancellation
        self._queue: queue.Queue[bytes | object] = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._worker_done = threading.Event()
        self._worker = threading.Thread(
            target=self._run_worker,
            name="versioned-read-arrow-bridge",
            daemon=False,
        )
        self._worker.start()

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
        self._cancellation.set()
        close_row_iterator(self._row_iterator)
        await asyncio.to_thread(self._worker.join, _WORKER_JOIN_TIMEOUT_SECONDS)
        if self._worker.is_alive():
            _LOGGER.warning("versioned read arrow bridge worker did not exit in time")

    def _put_chunk(self, chunk: bytes | object) -> None:
        while not self._cancellation.is_set():
            try:
                self._queue.put(chunk, timeout=_POLL_TIMEOUT_SECONDS)
                return
            except queue.Full:
                continue

    def _run_worker(self) -> None:
        sink = io.BytesIO()
        writer: pa.ipc.RecordBatchStreamWriter | None = None
        last_pos = 0
        completed = False
        try:
            writer = pa.ipc.new_stream(sink, self._plan.expected_schema)
            for batch in self._row_iterator:
                if self._cancellation.is_set():
                    return
                writer.write_batch(batch)
                current = sink.tell()
                if current > last_pos:
                    self._put_chunk(sink.getvalue()[last_pos:current])
                    last_pos = current
            if self._cancellation.is_set():
                return
            writer.close()
            completed = True
            current = sink.tell()
            if current > last_pos:
                self._put_chunk(sink.getvalue()[last_pos:current])
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
