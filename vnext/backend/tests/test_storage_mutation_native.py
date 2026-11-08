"""Real Arrow storage facts under one active operation budget."""

from __future__ import annotations

import json
from dataclasses import replace

import pyarrow as pa
import pytest

from gateway_backend.capabilities.mutation_planning.contracts import (
    MutationPolicy, MutationThresholdPolicy, StorageNetCounts, StorageTableSideV1,
    StorageTableTaskV1, TableMutationKind,
)
from gateway_backend.capabilities.mutation_planning.native import prepare_storage_table
from gateway_backend.capabilities.mutation_planning.storage import choose_table_mutation
from gateway_backend.capabilities.storage_projection.contracts import (
    RepositoryImportColumn, RepositoryImportTable,
)
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, NeverCancel, OperationMemoryBudget,
    current_kernel_context, kernel_execution_scope,
)
from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy
from tests.support.mutation_contracts import digest, manifest_table, storage_view

pytestmark = pytest.mark.unit


def _schema() -> pa.Schema:
    def field(name: str) -> pa.Field:
        profile = {
            "declared_type": {"kind": "string", "bits": None, "precision": None,
                              "scale": None, "bit_width": None},
            "labels": None, "logical_type": "standard", "sql_type": "VARCHAR(64)",
        }
        return pa.field(name, pa.string(), nullable=False,
                        metadata={b"gdds.canonical_type": json.dumps(profile).encode()})
    return pa.schema([field("board"), field("link_no"), field("status")],
                     metadata={b"gdds.canonical_mapping_version": b"1"})


def _table(rows: list[tuple[str, str, str]]) -> pa.Table:
    schema = _schema()
    return pa.Table.from_arrays(
        [pa.array([row[column] for row in rows], type=pa.string()) for column in range(3)],
        schema=schema,
    )


def _side(table: pa.Table, *, source_fill: str = "a", content_fill: str = "b",
          keyless: bool = False) -> StorageTableSideV1:
    view = storage_view()
    manifest = manifest_table(row_count=table.num_rows)
    if keyless:
        view = replace(view, canonical_key_policy=CanonicalKeyPolicy.EXPLICIT_KEYLESS,
                       canonical_key_columns=())
        manifest = replace(manifest, canonical_key_policy=CanonicalKeyPolicy.EXPLICIT_KEYLESS,
                           canonical_key_columns=())
    manifest = replace(manifest, source_schema_digest=digest(source_fill),
                       content_digest=digest(content_fill))
    return StorageTableSideV1(
        manifest, view, "3",
        pa.RecordBatchReader.from_batches(table.schema, table.to_batches()), table.schema,
    )


def _task(before: StorageTableSideV1 | None, after: StorageTableSideV1) -> StorageTableTaskV1:
    return StorageTableTaskV1("orders", before, after,
        RepositoryImportTable("orders", tuple(RepositoryImportColumn(name, "VARCHAR(64)", False)
                                             for name in ("board", "link_no", "status")),
                              after.manifest_table.canonical_key_columns,
                              after.manifest_table.canonical_row_count))


def test_native_diff_counts_full_persisted_update_and_releases_table_lease() -> None:
    old_rows = [(str(i), "0", "old" if i == 42 else "same") for i in range(100)]
    new_rows = [(str(i), "0", "new" if i == 42 else "same") for i in range(100)]
    old, new = _table(old_rows), _table(new_rows)
    context = current_kernel_context()
    assert context is not None
    old_charge = context.memory.retain_arrow(old)
    new_charge = context.memory.retain_arrow(new)
    before = _side(old, content_fill="1")
    after = _side(new, content_fill="2")
    baseline = context.memory.used_bytes
    try:
        with prepare_storage_table(_task(before, after), context) as handle:
            summary = handle.summary()
            assert summary.net_counts == StorageNetCounts(0, 1, 0)
            assert handle.patch_locator_count == 1
            assert choose_table_mutation(_task(before, after), summary,
                policy=MutationPolicy.ADAPTIVE_PATCH,
                threshold=MutationThresholdPolicy()).operation is TableMutationKind.PATCH_DML
        assert context.memory.used_bytes == baseline
    finally:
        old_charge.close()
        new_charge.close()


def test_metadata_only_before_and_present_empty_after_keep_unknown_net_diff() -> None:
    old, new = _table([("1", "0", "x")]), _table([])
    context = current_kernel_context()
    assert context is not None
    with context.memory.retain_arrow(new):
        before = replace(_side(old, keyless=True), stream=None, schema=None)
        after = _side(new, keyless=True, content_fill="3")
        task = _task(before, after)
        with prepare_storage_table(task, context) as handle:
            summary = handle.summary()
            assert summary.before_rows == 1 and summary.after_rows == 0
            assert summary.net_counts is None
            assert summary.before_identity_validated and summary.after_identity_validated
            decision = choose_table_mutation(task, summary, policy=MutationPolicy.ADAPTIVE_PATCH,
                                             threshold=MutationThresholdPolicy())
            assert decision.operation is TableMutationKind.REBUILD_TABLE
            assert decision.replay_insert_rows == 0


def test_source_schema_only_change_is_noop_after_complete_keyed_diff() -> None:
    old, new = _table([("1", "0", "same")]), _table([("1", "0", "same")])
    context = current_kernel_context()
    assert context is not None
    with context.memory.retain_arrow(old), context.memory.retain_arrow(new):
        before = _side(old, source_fill="1", content_fill="b")
        after = _side(new, source_fill="2", content_fill="b")
        task = _task(before, after)
        with prepare_storage_table(task, context) as handle:
            summary = handle.summary()
            assert summary.net_counts == StorageNetCounts(0, 0, 0)
            decision = choose_table_mutation(task, summary,
                policy=MutationPolicy.ADAPTIVE_PATCH, threshold=MutationThresholdPolicy())
            assert decision.operation is TableMutationKind.NOOP
            assert decision.reason == "NO_NET_STORAGE_CHANGE"


def test_native_entry_rejects_structural_context_and_closed_context() -> None:
    table = _table([])
    task = _task(None, _side(table))
    class FakeContext:
        memory = OperationMemoryBudget(1024**2)
        cancel_probe = NeverCancel()
        threads = 1
        deadline_monotonic = None
        def require_active(self) -> None: pass

    with pytest.raises(ValueError, match="real kernel operation context"):
        prepare_storage_table(task, FakeContext())  # type: ignore[arg-type]
    closed = KernelExecutionContext(OperationMemoryBudget(1024**2), NeverCancel(), 1)
    with kernel_execution_scope(closed, new_operation=True):
        closed.require_active()
    with pytest.raises(ValueError, match="not active"):
        prepare_storage_table(task, closed)
