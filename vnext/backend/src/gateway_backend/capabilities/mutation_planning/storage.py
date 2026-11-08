"""Small storage-table policy; no ChangeSet or Python row construction."""

from __future__ import annotations

from gateway_backend.capabilities.mutation_planning._decision import (
    choose_mutation_kind, keyed_patchable, storage_views_compatible,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    MutationPolicy, MutationThresholdPolicy, StorageTableDecision, StorageTableSummary,
    StorageTableTaskV1, TableMutationKind,
)


def _same_storage_view(task: StorageTableTaskV1) -> bool:
    assert task.before is not None and task.after is not None
    return storage_views_compatible(task.before.storage_view, task.after.storage_view)


def _patchable(task: StorageTableTaskV1) -> bool:
    assert task.before is not None and task.after is not None
    return _same_storage_view(task) and keyed_patchable(task.after.storage_view)


def choose_table_mutation(
    task: StorageTableTaskV1, summary: StorageTableSummary,
    *, policy: MutationPolicy, threshold: MutationThresholdPolicy,
) -> StorageTableDecision:
    """Choose once from validated native facts and manifest metadata."""
    before, after = task.before, task.after
    if after is not None and not summary.after_identity_validated:
        raise ValueError("after storage identity was not validated")
    if before is not None and before.stream is not None and not summary.before_identity_validated:
        raise ValueError("read before storage identity was not validated")
    if summary.before_rows != (0 if before is None else before.manifest_table.canonical_row_count):
        raise ValueError("before row count and manifest disagree")
    if summary.after_rows != (0 if after is None else after.manifest_table.canonical_row_count):
        raise ValueError("after row count and manifest disagree")
    if after is None:
        return StorageTableDecision(TableMutationKind.REBUILD_TABLE, "TABLE_REMOVED", 0)
    if before is None:
        return StorageTableDecision(TableMutationKind.REBUILD_TABLE, "TABLE_ADDED", summary.after_rows)
    old, new = before.manifest_table, after.manifest_table
    if before.storage_projection_version != after.storage_projection_version:
        return StorageTableDecision(TableMutationKind.REBUILD_TABLE, "PROJECTION_VERSION_CHANGED", summary.after_rows)
    same_shape = (
        old.canonical_schema_digest == new.canonical_schema_digest
        and old.canonical_key_columns == new.canonical_key_columns
        and old.retained_columns == new.retained_columns
        and _same_storage_view(task)
    )
    if not same_shape:
        return StorageTableDecision(TableMutationKind.REBUILD_TABLE, "STORAGE_SHAPE_CHANGED", summary.after_rows)
    same_identity = (
        summary.before_identity_validated and summary.after_identity_validated
        and old.canonical_row_count == new.canonical_row_count
        and old.source_schema_digest == new.source_schema_digest
        and old.canonical_schema_digest == new.canonical_schema_digest
        and old.content_digest == new.content_digest
    )
    if same_identity:
        return StorageTableDecision(TableMutationKind.NOOP, "STORAGE_IDENTITY_UNCHANGED", 0)
    if before.stream is None:
        return StorageTableDecision(TableMutationKind.REBUILD_TABLE, "BEFORE_ROWS_UNAVAILABLE", summary.after_rows)
    if not _patchable(task) or summary.before_rows == 0:
        return StorageTableDecision(TableMutationKind.REBUILD_TABLE, "PATCH_INELIGIBLE", summary.after_rows)
    if summary.net_counts is None:
        raise ValueError("comparable keyed table requires a complete before diff")
    kind = choose_mutation_kind(
        policy=policy, threshold=threshold, patchable=True,
        before_rows=summary.before_rows, after_rows=summary.after_rows,
        changed_rows=summary.net_counts.changed,
    )
    reason = {
        TableMutationKind.NOOP: "NO_NET_STORAGE_CHANGE",
        TableMutationKind.PATCH_DML: "PATCH_WITHIN_THRESHOLD",
        TableMutationKind.REBUILD_TABLE: "PATCH_THRESHOLD_EXCEEDED",
    }[kind]
    return StorageTableDecision(kind, reason, summary.net_counts.inserted if kind is TableMutationKind.PATCH_DML else
                                (summary.after_rows if kind is TableMutationKind.REBUILD_TABLE else 0))
