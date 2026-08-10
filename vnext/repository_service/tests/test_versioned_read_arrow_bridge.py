"""Unit tests for the bounded Arrow IPC bridge."""

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
from gateway_repository_service.versioned_read.arrow_bridge import ArrowIpcStreamBridge

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

        async def consume() -> bytes:
            chunks: list[bytes] = []
            async for chunk in bridge.iter_bytes():
                chunks.append(chunk)
            return b"".join(chunks)

        body = asyncio.run(consume())
    assert body
    assert peak_sizes
    assert max(peak_sizes) < sum(peak_sizes)
