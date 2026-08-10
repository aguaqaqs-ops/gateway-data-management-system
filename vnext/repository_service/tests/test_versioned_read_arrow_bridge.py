"""Unit and serial tests for the bounded Arrow IPC bridge."""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import ColumnCatalog, TableCatalog, compile_table_plan
from gateway_repository_service.versioned_read.arrow_bridge import (
    ArrowIpcStreamBridge,
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
def test_arrow_bridge_backpressure_and_first_batch_barrier() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()
    producer_waiting = threading.Event()

    def gated_batches() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        producer_waiting.set()
        assert release.wait(timeout=2.0)
        yield from batches[1:]

    cancellation = threading.Event()
    bridge = ArrowIpcStreamBridge(plan, gated_batches(), cancellation)

    async def consume() -> int:
        total = 0
        async for chunk in bridge.iter_bytes():
            total += len(chunk)
        return total

    async def run() -> tuple[int, bool]:
        task = asyncio.create_task(consume())
        assert producer_waiting.wait(timeout=2.0)
        assert not task.done()
        release.set()
        return await task, producer_waiting.is_set()

    total_bytes, was_waiting = asyncio.run(run())
    assert was_waiting
    assert total_bytes > 0


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
def test_arrow_bridge_close_sync_is_idempotent_for_concurrent_callers() -> None:
    plan, batches = _plan_and_batches(batch_count=1, rows_per_batch=1)
    release = threading.Event()

    def gated_rows() -> Iterator[pa.RecordBatch]:
        yield batches[0]
        release.wait(timeout=2.0)

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
