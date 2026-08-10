"""Unit and serial tests for the bounded Arrow IPC bridge."""

from __future__ import annotations

import asyncio
import io
import threading
import time
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import ColumnCatalog, TableCatalog, compile_table_plan
from gateway_repository_service.versioned_read.arrow_bridge import (
    ArrowIpcStreamBridge,
    BridgeJoinTimeoutError,
    BridgeStreamAbortedError,
)

pytestmark = pytest.mark.unit


def _plan_and_batches(batch_count: int, rows_per_batch: int) -> tuple[Any, list[pa.RecordBatch]]:
    table = TableCatalog(
        "items",
        (
            ColumnCatalog(
                name="id",
                sql_type="BIGINT",
                nullable=False,
                primary_key_position=1,
            ),
        ),
        row_count=batch_count * rows_per_batch,
    )
    plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
    batches: list[pa.RecordBatch] = []
    value = 0
    for _ in range(batch_count):
        normalized = []
        for _ in range(rows_per_batch):
            value += 1
            normalized.append(plan.normalize_row((value,)))
        batches.append(plan.record_batch(normalized))
    return plan, batches


def _wait_until(condition: Any, *, timeout_seconds: float = 2.0, message: str) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def test_arrow_bridge_sink_peak_stays_bounded_across_many_batches() -> None:
    peak_sizes: list[int] = []

    class TrackingBytesIO(io.BytesIO):
        def getvalue(self) -> bytes:
            value = super().getvalue()
            peak_sizes.append(len(value))
            return value

    with patch(
        "gateway_repository_service.versioned_read.arrow_bridge.io.BytesIO",
        TrackingBytesIO,
    ):
        plan, batches = _plan_and_batches(batch_count=20, rows_per_batch=64)
        cancellation = threading.Event()

        def rows() -> Iterator[pa.RecordBatch]:
            yield from batches

        bridge = ArrowIpcStreamBridge(plan, rows(), cancellation)

        async def consume() -> int:
            total = 0
            async for chunk in bridge.iter_bytes():
                total += len(chunk)
            return total

        total_bytes = asyncio.run(consume())
    assert total_bytes > 0
    assert peak_sizes
    single_batch_peak = max(peak_sizes[:3])
    assert max(peak_sizes) <= single_batch_peak * 2


@pytest.mark.serial
def test_arrow_bridge_backpressure_blocks_producer_until_consumer_reads() -> None:
    plan, batches = _plan_and_batches(batch_count=3, rows_per_batch=64)
    cancellation = threading.Event()
    batches_yielded = 0
    third_batch_requested = threading.Event()

    def tracked_batches() -> Iterator[pa.RecordBatch]:
        nonlocal batches_yielded
        for index, batch in enumerate(batches):
            batches_yielded = index + 1
            if index == 2:
                third_batch_requested.set()
            yield batch

    bridge = ArrowIpcStreamBridge(plan, tracked_batches(), cancellation)
    _wait_until(
        lambda: bridge._queue.full(),
        message="bounded queue did not fill before consumer started",
    )
    assert batches_yielded <= 2
    assert not third_batch_requested.is_set()

    async def consume() -> int:
        total = 0
        async for chunk in bridge.iter_bytes():
            total += len(chunk)
        return total

    total_bytes = asyncio.run(consume())
    assert total_bytes > 0
    assert third_batch_requested.is_set()
    assert bridge._terminal_outcome == "success"


def test_arrow_bridge_worker_failure_aborts_consumer() -> None:
    plan, batches = _plan_and_batches(batch_count=2, rows_per_batch=1)

    def failing_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        raise RuntimeError("conversion failed")

    bridge = ArrowIpcStreamBridge(plan, failing_rows(), threading.Event())

    async def consume() -> None:
        chunks: list[bytes] = []
        async for chunk in bridge.iter_bytes():
            chunks.append(chunk)

    with pytest.raises(BridgeStreamAbortedError):
        asyncio.run(consume())


@pytest.mark.serial
def test_arrow_bridge_eos_enqueue_cancel_preserves_failure_terminal() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=128)
    cancellation = threading.Event()
    bridge = ArrowIpcStreamBridge(plan, iter(batches), cancellation)
    _wait_until(
        lambda: bridge._queue.full(),
        message="bounded queue did not fill before EOS cancellation",
    )

    bridge.close_sync()
    assert bridge._terminal_outcome == "failure"

    async def consume() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in bridge.iter_bytes():
            chunks.append(chunk)
        return chunks

    with pytest.raises(BridgeStreamAbortedError):
        asyncio.run(consume())


@pytest.mark.serial
def test_arrow_bridge_queue_full_cancel_preserves_failure_terminal() -> None:
    plan, batches = _plan_and_batches(batch_count=2, rows_per_batch=64)
    cancellation = threading.Event()
    bridge = ArrowIpcStreamBridge(plan, iter(batches), cancellation)
    _wait_until(
        lambda: bridge._queue.full(),
        message="bounded queue did not fill before cancellation",
    )

    bridge.close_sync()
    assert bridge._terminal_outcome == "failure"

    async def consume() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in bridge.iter_bytes():
            chunks.append(chunk)
        return chunks

    with pytest.raises(BridgeStreamAbortedError):
        asyncio.run(consume())


@pytest.mark.serial
def test_arrow_bridge_close_sync_is_idempotent_for_concurrent_callers() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        release.wait()

    bridge = ArrowIpcStreamBridge(plan, gated_rows(), threading.Event())
    errors: list[BaseException] = []

    def close_once() -> None:
        try:
            bridge.close_sync()
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=close_once)
    second = threading.Thread(target=close_once)
    first.start()
    second.start()
    release.set()
    first.join(timeout=5.0)
    second.join(timeout=5.0)
    assert not errors
    assert not bridge.is_worker_alive()


@pytest.mark.serial
def test_close_sync_join_runs_outside_worker_condition_lock() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    finish_worker_entered = threading.Event()
    finish_worker_can_complete = threading.Event()
    bridge = ArrowIpcStreamBridge(plan, iter(batches), threading.Event())
    original_finish_worker = bridge._finish_worker

    def delayed_finish_worker(*, completed: bool) -> None:
        finish_worker_entered.set()
        assert finish_worker_can_complete.wait(timeout=2.0)
        original_finish_worker(completed=completed)

    bridge._finish_worker = delayed_finish_worker  # type: ignore[method-assign]

    async def consume() -> None:
        async for _chunk in bridge.iter_bytes():
            pass

    consumer = threading.Thread(target=lambda: asyncio.run(consume()))
    consumer.start()
    assert finish_worker_entered.wait(timeout=2.0)
    assert consumer.is_alive()
    assert not bridge._worker_joined
    finish_worker_can_complete.set()
    consumer.join(timeout=5.0)
    assert not bridge.is_worker_alive()


@pytest.mark.serial
def test_close_sync_join_timeout_terminates_only_bridge_owned_children() -> None:
    from unittest.mock import MagicMock

    from gateway_repository_service.process import ActiveChildRegistry

    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()
    pre_existing = MagicMock()
    pre_existing.pid = 100
    pre_existing.poll.return_value = None
    bridge_owned = MagicMock()
    bridge_owned.pid = 200
    bridge_owned.poll.return_value = None

    registry = ActiveChildRegistry()
    registry.register(pre_existing)

    runner = MagicMock()
    runner._active_children = registry
    runner.settings.terminate_grace_seconds = 0.01
    terminated: list[int] = []

    def terminate_and_reap(process: MagicMock, *, grace_seconds: float) -> None:
        del grace_seconds
        terminated.append(process.pid)
        process.poll.return_value = 0

    runner.terminate_and_reap.side_effect = terminate_and_reap

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        release.wait()

    bridge = ArrowIpcStreamBridge(plan, gated_rows(), threading.Event(), dolt_runner=runner)
    registry.register(bridge_owned)
    errors: list[BaseException] = []

    def close_in_thread() -> None:
        try:
            bridge.close_sync(join_timeout_seconds=0.05)
        except BaseException as exc:
            errors.append(exc)

    closer = threading.Thread(target=close_in_thread)
    closer.start()
    closer.join(timeout=5.0)
    assert len(errors) == 1
    assert isinstance(errors[0], BridgeJoinTimeoutError)
    assert terminated == [200]
    assert 100 not in terminated
    release.set()
    bridge._worker.join(timeout=5.0)
