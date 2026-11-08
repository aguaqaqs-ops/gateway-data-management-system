"""Real Arrow storage facts under one active operation budget."""

from __future__ import annotations

import json
import subprocess
import sys
from contextlib import closing
from dataclasses import replace

import pyarrow as pa
import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.mutation_planning.contracts import (
    MutationPolicy, MutationThresholdPolicy, StorageNetCounts, StorageTableSideV1,
    StorageTableTaskV1, TableMutationKind,
)
from gateway_backend.capabilities.mutation_planning.native import prepare_storage_table
from gateway_backend.capabilities.mutation_planning.storage import choose_table_mutation
from gateway_backend.capabilities.storage_projection.contracts import (
    RepositoryImportColumn, RepositoryImportTable,
)
from gateway_backend.capabilities.storage_projection import StorageInputLease, open_storage_input
from gateway_backend.capabilities.storage_projection._digest import compute_manifest_digest, compute_schema_digest
from gateway_backend.capabilities.snapshot_materialization import (
    ArrowSnapshotTableReader, snapshot_table_from_arrow, source_descriptor_from_arrow,
    open_snapshot_table_artifact, publish_canonical_tables,
    SnapshotTableArtifact, SnapshotTableArtifactManifest,
    SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION, ROW_MATERIALIZATION_PROFILE,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_FORMAT_CANONICAL_IPC, ARTIFACT_COMPRESSION_NONE,
)
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, KernelMemoryLimit, NeverCancel, OperationMemoryBudget,
    current_kernel_context, kernel_control_scope, kernel_execution_scope,
)
from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy
from tests.support.mutation_contracts import digest, manifest as manifest_document, manifest_table, storage_view
from tests.support.storage_projection import table_descriptor, typed_column

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
          keyless: bool = False,
          column_names: tuple[str, ...] = ("board", "link_no", "status")) -> StorageTableSideV1:
    view = storage_view()
    manifest = manifest_table(row_count=table.num_rows)
    manifest = replace(manifest, retained_columns=column_names)
    if keyless:
        view = replace(view, canonical_key_policy=CanonicalKeyPolicy.EXPLICIT_KEYLESS,
                       canonical_key_columns=())
        manifest = replace(manifest, canonical_key_policy=CanonicalKeyPolicy.EXPLICIT_KEYLESS,
                           canonical_key_columns=())
    schema_digest = compute_schema_digest(
        columns=[{"name": name, "nullable": False, "sql_type": "VARCHAR(64)"}
                 for name in column_names],
        primary_key=manifest.canonical_key_columns,
    )
    manifest = replace(manifest, source_schema_digest=digest(source_fill * 2),
                       canonical_schema_digest=schema_digest, content_digest=digest(content_fill * 2))
    descriptor = table_descriptor(
        "orders", [typed_column(name, "VARCHAR(64)") for name in column_names],
        primary_key_columns=manifest.canonical_key_columns, row_count=table.num_rows,
        raw_content_digest=manifest.content_digest,
    )
    source = source_descriptor_from_arrow({
        "canonical_name": "orders", "display_name": "orders", "reader_ready": True,
        "primary_key": list(manifest.canonical_key_columns),
        "columns": [{"canonical_name": name, "display_name": name, "ordinal": index,
                     "sql_type": "VARCHAR(64)", "logical_type": "standard", "nullable": False,
                     "labels": None,
                     "declared_type": {"kind": "string", "bits": None, "precision": None,
                                       "scale": None, "bit_width": None}}
                    for index, name in enumerate(column_names)],
    })
    canonical = snapshot_table_from_arrow(descriptor, table, source)
    assert isinstance(canonical.reader, ArrowSnapshotTableReader)
    canonical.reader.mark_canonical_comparison_verified()  # Fixture stands in for the verified IPC writer.
    empty_digest = raw_blob_digest(b"")
    reference = ArtifactRef("storage-fixture-artifact", "application/octet-stream", 0, empty_digest)
    canonical = replace(canonical, artifact=SnapshotTableArtifact(
        manifest_ref=reference,
        manifest=SnapshotTableArtifactManifest(
            artifact_contract_version=SNAPSHOT_TABLE_ARTIFACT_CONTRACT_VERSION,
            snapshot_digest=empty_digest, table_name="orders", descriptor=descriptor,
            row_file_refs=(reference,), row_format=ROW_FORMAT_CANONICAL_IPC,
            compression=ARTIFACT_COMPRESSION_NONE,
            row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
            artifact_content_digest=empty_digest, created_at="2026-11-08T00:00:00Z",
            repository_id="storage-fixture",
        ),
        row_layout_digest=empty_digest,
    ))
    context = current_kernel_context()
    assert context is not None
    complete = manifest_document(tables=(manifest,))
    complete = replace(complete, manifest_digest=compute_manifest_digest(complete))
    lease = open_storage_input(canonical, complete, manifest, context)
    return StorageTableSideV1(manifest, view, "3", lease.stream, lease.schema, lease, complete)


def _metadata_side(table: pa.Table, *, keyless: bool) -> StorageTableSideV1:
    view = storage_view()
    manifest_item = manifest_table(row_count=table.num_rows)
    if keyless:
        view = replace(view, canonical_key_policy=CanonicalKeyPolicy.EXPLICIT_KEYLESS,
                       canonical_key_columns=())
        manifest_item = replace(manifest_item, canonical_key_policy=CanonicalKeyPolicy.EXPLICIT_KEYLESS,
                                canonical_key_columns=())
    complete = manifest_document(tables=(manifest_item,))
    complete = replace(complete, manifest_digest=compute_manifest_digest(complete))
    return StorageTableSideV1(manifest_item, view, "3", metadata_manifest=complete)


def _task(before: StorageTableSideV1 | None, after: StorageTableSideV1) -> StorageTableTaskV1:
    return StorageTableTaskV1("orders", before, after,
        RepositoryImportTable("orders", tuple(RepositoryImportColumn(name, "VARCHAR(64)", False)
                                             for name in after.manifest_table.retained_columns),
                              after.manifest_table.canonical_key_columns,
                              after.manifest_table.canonical_row_count))


def _assert_operation_resources_released(context: KernelExecutionContext) -> None:
    # Flush operation-lived metadata only. Arrow/native reservations must
    # already be gone after the table handle and input readers close.
    context.memory.close()
    assert context.memory.used_bytes == 0


def test_fresh_and_cached_canonical_inputs_keep_declaration_order_for_storage_diff() -> None:
    context = current_kernel_context()
    assert context is not None
    names = ("status", "board", "link_no")
    raw_schema = pa.schema([pa.field(name, pa.string(), nullable=False) for name in names])
    def raw(status: str) -> pa.Table:
        return pa.Table.from_arrays(
            [pa.array([value], type=pa.string()) for value in (status, "1", "0")],
            schema=raw_schema,
        )

    old_candidate = _side(raw("old"), content_fill="1", column_names=names)
    new_candidate = _side(raw("new"), content_fill="2", column_names=names)
    assert isinstance(old_candidate.input_owner, StorageInputLease)
    assert isinstance(new_candidate.input_owner, StorageInputLease)
    store = InMemoryArtifactStore()
    published_before, fresh_after = publish_canonical_tables(
        (old_candidate.input_owner.table, new_candidate.input_owner.table),
        snapshot_digest=digest("ee"), store=store,
        repository_id="storage-fresh-writer",
    )
    old_candidate.input_owner.close()
    new_candidate.input_owner.close()
    assert published_before.artifact is not None
    cached_before = open_snapshot_table_artifact(
        store, published_before.artifact.manifest_ref,
        repository_id="storage-fresh-writer", canonical_required=True,
    )
    assert published_before.reader is not None
    published_before.reader.close()
    if published_before.batch_reader is not None:
        published_before.batch_reader.close()
    assert isinstance(cached_before.reader, ArrowSnapshotTableReader)
    assert cached_before.reader.canonical_artifact_read_verified
    assert isinstance(fresh_after.reader, ArrowSnapshotTableReader)
    assert fresh_after.reader.canonical_comparison_verified
    with closing(fresh_after.reader.reopen()) as reader, closing(reader.arrow_stream()) as stream:
        assert b"gdds.canonical_mapping_version" not in (stream.schema.metadata or {})
        assert all(b"gdds.canonical_type" not in (field.metadata or {}) for field in stream.schema)
    assert old_candidate.metadata_manifest is not None
    assert new_candidate.metadata_manifest is not None
    old_lease = open_storage_input(
        cached_before, old_candidate.metadata_manifest, old_candidate.manifest_table, context,
    )
    new_lease = open_storage_input(
        fresh_after, new_candidate.metadata_manifest, new_candidate.manifest_table, context,
    )
    assert old_lease.schema.names == list(names)
    assert new_lease.schema.names == list(names)
    before = replace(old_candidate, stream=old_lease.stream, schema=old_lease.schema, input_owner=old_lease)
    after = replace(new_candidate, stream=new_lease.stream, schema=new_lease.schema, input_owner=new_lease)
    task = _task(before, after)
    with prepare_storage_table(task, context) as handle:
        summary = handle.summary()
        assert summary.net_counts == StorageNetCounts(0, 1, 0)
        decision = choose_table_mutation(task, summary,
            policy=MutationPolicy.ADAPTIVE_PATCH, threshold=MutationThresholdPolicy())
        handle.apply_decision(decision)
    _assert_operation_resources_released(context)


def test_native_diff_counts_full_persisted_update_and_releases_table_lease() -> None:
    old_rows = [(str(i), "0", "old" if i == 42 else "same") for i in range(100)]
    new_rows = [(str(i), "0", "new" if i == 42 else "same") for i in range(100)]
    old, new = _table(old_rows), _table(new_rows)
    context = current_kernel_context()
    assert context is not None
    before = _side(old, content_fill="1")
    after = _side(new, content_fill="2")
    with prepare_storage_table(_task(before, after), context) as handle:
        summary = handle.summary()
        assert summary.net_counts == StorageNetCounts(0, 1, 0)
        assert handle.patch_locator_count == 1
        assert choose_table_mutation(_task(before, after), summary,
            policy=MutationPolicy.ADAPTIVE_PATCH,
            threshold=MutationThresholdPolicy()).operation is TableMutationKind.PATCH_DML
    _assert_operation_resources_released(context)


def test_metadata_only_before_and_present_empty_after_keep_unknown_net_diff() -> None:
    old, new = _table([("1", "0", "x")]), _table([])
    context = current_kernel_context()
    assert context is not None
    before = _metadata_side(old, keyless=True)
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
        handle.apply_decision(decision)
    _assert_operation_resources_released(context)


def test_source_schema_only_change_is_noop_after_complete_keyed_diff() -> None:
    old, new = _table([("1", "0", "same")]), _table([("1", "0", "same")])
    context = current_kernel_context()
    assert context is not None
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
        handle.apply_decision(decision)
    _assert_operation_resources_released(context)


def test_source_only_change_with_metadata_before_rebuilds_without_invented_net_counts() -> None:
    context = current_kernel_context()
    assert context is not None
    old = _side(_table([("1", "0", "same")]), source_fill="1", content_fill="b")
    complete = manifest_document(tables=(old.manifest_table,))
    complete = replace(complete, manifest_digest=compute_manifest_digest(complete))
    before = replace(old, stream=None, schema=None, input_owner=None, metadata_manifest=complete)
    assert old.input_owner is not None
    old.input_owner.close()  # type: ignore[attr-defined]
    after = _side(_table([("1", "0", "same")]), source_fill="2", content_fill="b")
    task = _task(before, after)
    with prepare_storage_table(task, context) as handle:
        summary = handle.summary()
        assert summary.net_counts is None
        decision = choose_table_mutation(task, summary,
            policy=MutationPolicy.ADAPTIVE_PATCH, threshold=MutationThresholdPolicy())
        assert decision.operation is TableMutationKind.REBUILD_TABLE
        assert decision.reason == "BEFORE_ROWS_UNAVAILABLE"
        handle.apply_decision(decision)
    _assert_operation_resources_released(context)


def test_storage_rule_digest_only_change_uses_the_shared_comparability_rule() -> None:
    old, new = _table([("1", "0", "same")]), _table([("1", "0", "same")])
    context = current_kernel_context()
    assert context is not None
    before = _side(old, source_fill="1")
    after = _side(new, source_fill="2")
    before = replace(before, storage_view=replace(before.storage_view, storage_rule_digest=digest("11")))
    after = replace(after, storage_view=replace(after.storage_view, storage_rule_digest=digest("22")))
    task = _task(before, after)
    with prepare_storage_table(task, context) as handle:
        summary = handle.summary()
        assert summary.net_counts == StorageNetCounts(0, 0, 0)
        decision = choose_table_mutation(task, summary,
            policy=MutationPolicy.ADAPTIVE_PATCH, threshold=MutationThresholdPolicy())
        assert decision.operation is TableMutationKind.NOOP
        handle.apply_decision(decision)
    _assert_operation_resources_released(context)


def test_native_entry_rejects_structural_context_and_closed_context() -> None:
    table = _table([])
    after = _side(table)
    task = _task(None, after)
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
    assert after.input_owner is not None
    after.input_owner.close()  # type: ignore[attr-defined]


def test_uncharged_replacement_stream_cannot_claim_a_verified_identity() -> None:
    context = current_kernel_context()
    assert context is not None
    after = _side(_table([("1", "0", "same")]))
    replacement = _table([("1", "0", "different")])
    spoofed = replace(after,
        stream=pa.RecordBatchReader.from_batches(replacement.schema, replacement.to_batches()),
        schema=replacement.schema)
    try:
        with pytest.raises(ValueError, match="verified same-operation input owner"):
            prepare_storage_table(_task(None, spoofed), context)
    finally:
        spoofed.stream.close()  # type: ignore[union-attr]
        assert after.input_owner is not None
        after.input_owner.close()  # type: ignore[attr-defined]


@pytest.mark.parametrize("field,fill", [("content_digest", "9"), ("source_schema_digest", "8")])
def test_rebound_manifest_item_cannot_reuse_a_verified_stream(field: str, fill: str) -> None:
    context = current_kernel_context()
    assert context is not None
    after = _side(_table([("1", "0", "same")]))
    if field == "content_digest":
        altered = replace(after.manifest_table, content_digest=digest(fill * 2))
    else:
        assert field == "source_schema_digest"
        altered = replace(after.manifest_table, source_schema_digest=digest(fill * 2))
    complete = manifest_document(tables=(altered,))
    complete = replace(complete, manifest_digest=compute_manifest_digest(complete))
    spoofed = replace(after, manifest_table=altered, metadata_manifest=complete)
    try:
        with pytest.raises(ValueError, match="verified same-operation input owner"):
            prepare_storage_table(_task(None, spoofed), context)
    finally:
        assert after.input_owner is not None
        after.input_owner.close()  # type: ignore[attr-defined]


def test_merged_operation_scope_accepts_its_original_verified_reader() -> None:
    context = current_kernel_context()
    assert context is not None
    after = _side(_table([("1", "0", "same")]))
    with kernel_control_scope(NeverCancel(), None) as merged:
        with prepare_storage_table(_task(None, after), merged) as handle:
            assert handle.summary().after_rows == 1
            # Closing the operation wrapper cannot release the charge while
            # its table still owns native Arrow references.
            handle._operation.close()
            assert context.memory.used_bytes > 0
    _assert_operation_resources_released(context)


def test_rebuild_discards_old_arrow_and_patch_locators_before_render() -> None:
    old = _table([(str(i), "0", "old") for i in range(1001)])
    new = _table([(str(i), "0", "new") for i in range(1001)])
    context = current_kernel_context()
    assert context is not None
    before = _side(old, content_fill="1")
    after = _side(new, content_fill="2")
    task = _task(before, after)
    with prepare_storage_table(task, context) as handle:
        decision = choose_table_mutation(task, handle.summary(),
            policy=MutationPolicy.ADAPTIVE_PATCH, threshold=MutationThresholdPolicy())
        assert decision.operation is TableMutationKind.REBUILD_TABLE
        assert handle.patch_locator_count == 1000
        with_old = context.memory.used_bytes
        handle.apply_decision(decision)
        assert handle.patch_locator_count == 0
        assert context.memory.used_bytes < with_old
        assert context.memory.used_bytes > 0
    _assert_operation_resources_released(context)


def test_empty_multibatch_input_rejects_header_growth_before_stream_consumption() -> None:
    schema = _schema()
    empty = pa.RecordBatch.from_arrays([pa.array([], type=pa.string()) for _ in range(3)], schema=schema)
    after = _side(pa.Table.from_batches([empty] * 64, schema=schema))
    context = current_kernel_context()
    assert context is not None
    original_limit = context.memory.limit_bytes
    # Keep the verified input charged, then leave less than the native
    # all-batch header reservation. The failure must release every owner.
    context.memory.limit_bytes = context.memory.used_bytes + 64 * 1024**2 + 128 * 1024
    try:
        with pytest.raises(KernelMemoryLimit):
            prepare_storage_table(_task(None, after), context)
    finally:
        context.memory.limit_bytes = original_limit
    _assert_operation_resources_released(context)


@pytest.mark.serial
@pytest.mark.parametrize("threads", [1, 2])
def test_storage_diff_is_stable_across_batch_boundaries_and_pool_sizes(threads: int) -> None:
    # Each child initializes the process-wide kernel pool exactly once. The
    # main pytest process has N=1, so a real N=2 needs its own process.
    script = """
import json
import pyarrow as pa
from gateway_compute._native import _init_kernel_native
from gateway_backend.capabilities.table_access import (
    KernelExecutionContext, NeverCancel, OperationMemoryBudget, kernel_execution_scope,
)
from gateway_backend.capabilities.mutation_planning.native import prepare_storage_table
from tests.test_storage_mutation_native import _side, _table, _task

_init_kernel_native(THREADS)
old_rows = [("1", "0", "a"), ("2", "0", "b"), ("3", "0", "c")]
new_rows = [("3", "0", "c"), ("2", "0", "changed"), ("4", "0", "d")]
observed = []
for batch_size in (3, 1):
    context = KernelExecutionContext(OperationMemoryBudget(512 * 1024**2), NeverCancel(), THREADS)
    with kernel_execution_scope(context):
        old = _table(old_rows)
        new = _table(new_rows)
        old = pa.Table.from_batches(old.to_batches(max_chunksize=batch_size), schema=old.schema)
        new = pa.Table.from_batches(new.to_batches(max_chunksize=batch_size), schema=new.schema)
        before = _side(old, content_fill="1")
        after = _side(new, content_fill="2")
        with prepare_storage_table(_task(before, after), context) as handle:
            counts = handle.summary().net_counts
            assert counts is not None
            observed.append((counts.inserted, counts.updated, counts.deleted, handle.patch_locator_count))
    assert context.memory.used_bytes == 0
assert observed == [(1, 1, 1, 3), (1, 1, 1, 3)]
print(json.dumps(observed))
""".replace("THREADS", str(threads))
    result = subprocess.run([sys.executable, "-c", script], check=False,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [[1, 1, 1, 3], [1, 1, 1, 3]]
