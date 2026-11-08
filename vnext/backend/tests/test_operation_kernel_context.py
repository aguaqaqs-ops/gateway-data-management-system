"""Aggregate reservations and the real parser/materializer Arrow boundary."""

from __future__ import annotations

import pyarrow as pa
import pytest

from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, KernelMemoryLimit, KernelStopped, NeverCancel,
    OperationMemoryBudget, kernel_execution_scope, parse_arrow_sql,
)
from gateway_backend.capabilities.snapshot_materialization import materialize_sql_snapshot
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy, MaterializationStage, SnapshotMaterializationStatus,
    SqlSnapshotMaterializationRequest,
)
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext
from tests.support.table_access_sql import sql_request


def test_shared_arrow_views_count_backing_once_and_release_at_last_owner() -> None:
    table = pa.table({"id": pa.array(range(65536), type=pa.int64())})
    view = table.slice(1, 100).select(["id"])
    memory = OperationMemoryBudget(2 * 1024**2)
    owner = memory.retain_arrow(table)
    base = memory.used_bytes
    borrowed = memory.retain_arrow(view)
    assert base <= memory.used_bytes < base + 16384
    owner.close()
    assert memory.used_bytes >= table.get_total_buffer_size()
    borrowed.close()
    assert memory.used_bytes == 0


def test_parser_and_materializer_share_the_operation_budget_and_stream_lifetime() -> None:
    context = KernelExecutionContext(OperationMemoryBudget(16 * 1024**2), NeverCancel(), 1)
    with kernel_execution_scope(context, new_operation=True):
        request = sql_request("CREATE TABLE t (id INT PRIMARY KEY, name TEXT); INSERT INTO t VALUES (1,'a'),(2,'b');")
        parsed = parse_arrow_sql(request)
        result = materialize_sql_snapshot(SqlSnapshotMaterializationRequest(
            parse_result=parsed, sql_source_digest=request.source.sql_source_digest,
            ruleset=migrated_table_ruleset_snapshot(), table_ruleset_version=1,
            materialization_stage=MaterializationStage.FINAL,
            policy=MaterializationPolicy.READERS_REQUIRED, context=ParserInvocationContext(context.cancel_probe),
        ))
        assert result.status is SnapshotMaterializationStatus.COMPLETE
        assert result.table_set is not None
        table = result.table_set.tables[0]
        assert table.reader is not None and table.batch_reader is not None
        assert table.descriptor.row_count == 2
        assert context.memory.used_bytes > 0
        isolated = table.reader.reopen()
        try:
            with isolated.arrow_stream() as stream:  # type: ignore[attr-defined]
                assert stream.read_all().column("name").to_pylist() == ["a", "b"]
        finally:
            isolated.close()
        table.reader.close()
        table.batch_reader.close()
        for item in parsed.tables:
            if item.reader is not None:
                item.reader.close()


def test_full_retained_first_side_reduces_next_parser_allowance() -> None:
    context = KernelExecutionContext(OperationMemoryBudget(256 * 1024), NeverCancel(), 1)
    with kernel_execution_scope(context, new_operation=True):
        with context.memory.reserve(250 * 1024):
            with pytest.raises(KernelMemoryLimit):
                parse_arrow_sql(sql_request("CREATE TABLE t (id INT); INSERT INTO t VALUES (1);"))
        assert context.memory.used_bytes == 0


def test_stop_probe_preserves_the_original_execution_control_flags() -> None:
    from gateway_backend.application.kernel_execution import ExecutionControlProbe
    from gateway_backend.operations.worker import ExecutionControl

    control = ExecutionControl()
    context = KernelExecutionContext(OperationMemoryBudget(1), ExecutionControlProbe(control), 1)
    control.request_drain()
    with pytest.raises(KernelStopped):
        context.checkpoint()
    assert control.drain_requested
    assert not control.cancel_requested
    assert not control.lease_lost


def test_caller_finite_deadline_survives_an_operation_without_a_deadline() -> None:
    from gateway_backend.capabilities.snapshot_materialization.native import call_arrow_kernel

    context = KernelExecutionContext(OperationMemoryBudget(1024**2), NeverCancel(), 1)
    with kernel_execution_scope(context, new_operation=True):
        with pytest.raises(TimeoutError):
            parse_arrow_sql(sql_request("CREATE TABLE t (id INT);", ParserInvocationContext(NeverCancel(), 0.0)))
        with pytest.raises(TimeoutError):
            call_arrow_kernel(lambda *args: {}, [], {}, cancel_probe=NeverCancel(),
                              budgets={"max_live_bytes": 1024**2}, deadline_monotonic=0.0, pool_threads=1)


def test_reader_keeps_the_callers_stop_probe_after_parser_completion() -> None:
    import threading

    caller_stop = threading.Event()
    context = KernelExecutionContext(OperationMemoryBudget(1024**2), NeverCancel(), 1)
    with kernel_execution_scope(context, new_operation=True):
        result = parse_arrow_sql(sql_request("CREATE TABLE t (id INT); INSERT INTO t VALUES (1);",
                                            ParserInvocationContext(caller_stop)))
        reader = result.tables[0].reader
        assert reader is not None
        caller_stop.set()
        try:
            with pytest.raises(KernelStopped):
                tuple(reader.iter_rows())
        finally:
            reader.close()
