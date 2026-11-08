"""Bounded Python rule/type metadata for the Arrow canonical projection kernel."""

from __future__ import annotations

from typing import Any

from gateway_compute._native import _canonical_project_native

from gateway_backend.capabilities.snapshot_materialization import (
    ArrowMetadata,
    ArrowSnapshotTableReader,
    KernelBudgets,
    KernelMemoryLimit,
    KernelResult,
    call_arrow_kernel,
    check_metadata_budget,
    enum_set_labels_for_sql_spelling,
    require_active_kernel_context,
    try_declared_type_for_sql_spelling,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_FORMAT_CANONICAL_IPC,
    SnapshotTable,
    SnapshotTableDescriptor,
    normalize_sql_type_spelling,
)
from gateway_backend.capabilities.table_rules.contracts import OrderedPolicy, StorageRuleView
from gateway_backend.capabilities.storage_projection._digest import compute_manifest_digest, compute_schema_digest
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifest, CanonicalizationManifestTable,
)


class StorageInputLease:
    """One verified canonical reader and its charged Arrow/mmap lifetime."""

    def __init__(self, table: SnapshotTable, reader: ArrowSnapshotTableReader,
                 stream: Any, operation: object) -> None:
        self.table = table
        self.reader = reader
        self.stream = stream
        self.schema = stream.schema
        self.operation = operation
        self.closed = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.stream.close()
        finally:
            try:
                self.reader.close()
            finally:
                try:
                    if self.table.batch_reader is not None:
                        self.table.batch_reader.close()
                finally:
                    if self.table.reader is not None:
                        self.table.reader.close()


def open_storage_input(
    table: SnapshotTable, manifest_table: CanonicalizationManifestTable,
    operation: object,
) -> StorageInputLease:
    """Bind one trusted canonical producer to its actual operation M owner."""
    active = require_active_kernel_context(operation)
    if type(table) is not SnapshotTable or type(table.reader) is not ArrowSnapshotTableReader:
        raise ValueError("storage input requires a canonical Arrow table reader")
    reader = table.reader
    active.require_same_operation(reader.execution_context)
    if table.artifact is None or table.artifact.manifest.row_format != ROW_FORMAT_CANONICAL_IPC:
        raise ValueError("storage input requires a canonical IPC artifact binding")
    if not (reader.canonical_comparison_verified or reader.canonical_artifact_read_verified):
        raise ValueError("storage input has no verified canonical producer")
    if table.artifact.manifest.descriptor != table.descriptor:
        raise ValueError("storage artifact descriptor binding changed")
    descriptor = table.descriptor
    if (
        descriptor.table_name != manifest_table.name
        or descriptor.row_count != manifest_table.canonical_row_count
        or descriptor.raw_content_digest != manifest_table.content_digest
        or descriptor.primary_key_columns != manifest_table.canonical_key_columns
        or tuple(column.name for column in descriptor.columns) != manifest_table.retained_columns
    ):
        raise ValueError("storage input manifest binding differs from canonical reader")
    schema_digest = compute_schema_digest(
        columns=[{"name": column.name, "nullable": column.nullable, "sql_type": column.scalar_type}
                 for column in descriptor.columns],
        primary_key=descriptor.primary_key_columns,
    )
    if schema_digest != manifest_table.canonical_schema_digest:
        raise ValueError("storage input schema digest differs from canonical reader")
    isolated = reader.reopen()
    try:
        stream = isolated.arrow_stream()
        return StorageInputLease(table, isolated, stream, active)
    except BaseException:
        isolated.close()
        raise


def require_storage_input_owner(value: object, stream: object, schema: object, operation: object) -> StorageInputLease:
    active = require_active_kernel_context(operation)
    if (type(value) is not StorageInputLease or value.closed
            or value.stream is not stream or value.schema != schema):
        raise ValueError("storage Arrow stream lacks its verified same-operation input owner")
    active.require_same_operation(value.operation)
    return value


def verify_storage_metadata_manifest(
    manifest: CanonicalizationManifest, table: CanonicalizationManifestTable,
    projection_version: str,
) -> None:
    """Verify a metadata-only before side against the complete frozen manifest."""
    if (type(manifest) is not CanonicalizationManifest
            or manifest.manifest_digest is None
            or compute_manifest_digest(manifest) != manifest.manifest_digest
            or manifest.storage_projection_version != projection_version
            or table not in manifest.tables):
        raise ValueError("storage metadata side lacks a complete manifest binding")


def require_storage_operation(value: object) -> object:
    """Pass the owning Table Access identity check through the existing DAG."""
    return require_active_kernel_context(value)


def storage_memory_limit(message: str) -> KernelMemoryLimit:
    return KernelMemoryLimit(message)


def build_projection_plan(
    descriptor: SnapshotTableDescriptor,
    view: StorageRuleView,
    *,
    canonicalized_input: bool,
    budgets: KernelBudgets,
) -> dict[str, Any]:
    """Normalize small declarations; row/schema binding is rechecked by Rust.

    Missing/unsupported retained columns belong to the core diagnostic owner.
    Python supplies no duplicated precomputed schema failures for these cases.
    """
    if len(descriptor.columns) > budgets["max_columns"] or len(view.retained_columns) > budgets["max_columns"]:
        raise MemoryError("projection column budget exceeded")
    # Conservative source+plan object/string/normalizer envelope, before copies.
    size = 4096 + len(descriptor.columns) * 4096 + len(view.retained_columns) * 4096
    for column in descriptor.columns:
        size += (len(column.name) + len(column.display_name) + len(column.scalar_type or "")) * 32
    for names in (view.retained_columns, view.canonical_key_columns, view.structural_columns):
        for name in names:
            size += len(name) * 32 + 128
    size += (len(view.canonical_table) + len(descriptor.table_name)) * 32
    if size > budgets["max_metadata_bytes"] or size * 8 > budgets["max_live_bytes"]:
        raise MemoryError("projection metadata budget exceeded")
    by_name = {column.name: (index, column) for index, column in enumerate(descriptor.columns)}
    columns: list[ArrowMetadata] = []
    ordered = view.ordered_policy is OrderedPolicy.GID_NO_V1
    non_null = set(view.canonical_key_columns)
    if ordered:
        non_null.add("no")
    for ordinal, name in enumerate(view.retained_columns):
        located = by_name.get(name)
        source_index = located[0] if located is not None else None
        source = located[1] if located is not None else None
        spelling = source.scalar_type if source is not None else None
        if ordered and name == "gid":
            spelling = "INT UNSIGNED"
        spelling = normalize_sql_type_spelling(spelling) if spelling else "UNKNOWN"
        enum_set = enum_set_labels_for_sql_spelling(spelling)
        declared = try_declared_type_for_sql_spelling(spelling)
        logical = "unknown" if declared is None else "standard"
        labels: list[str] | None = None
        if enum_set is not None:
            logical = enum_set[0].lower()
            labels = list(enum_set[1])
            if logical == "set":
                declared = None
        elif spelling == "JSON":
            logical = "json"
        columns.append(
            {
                "canonical_name": name,
                "display_name": source.display_name if source is not None else name,
                "ordinal": ordinal,
                "sql_type": spelling,
                "logical_type": logical,
                "declared_type": None if declared is None else {
                    "kind": declared.kind.value,
                    "bits": declared.bits,
                    "precision": declared.precision,
                    "scale": declared.scale,
                    "bit_width": declared.bit_width,
                },
                "nullable": source.nullable and name not in non_null if source is not None else True,
                "labels": labels,
                "source_index": source_index,
            }
        )
    plan = {
        "stage": descriptor.materialization_stage.value,
        "canonical_table": view.canonical_table,
        "expected_source_row_count": descriptor.row_count,
        "columns": columns,
        "canonical_key_columns": list(view.canonical_key_columns),
        "structural_columns": list(view.structural_columns),
        "row_policy": "ORDERED_GID_NO" if ordered else "KEYED" if view.canonical_key_columns else "KEYLESS",
        "canonicalized_input": canonicalized_input,
        "schema_diagnostics": [],
        "omitted_schema_diagnostic_count": 0,
    }
    check_metadata_budget(plan, budgets)
    return plan


def project_arrow_table(
    table: ArrowMetadata,
    descriptor: SnapshotTableDescriptor,
    view: StorageRuleView,
    *,
    canonicalized_input: bool,
    cancel_probe: object,
    budgets: KernelBudgets,
    deadline_monotonic: float | None,
    pool_threads: int,
) -> KernelResult:
    check_metadata_budget(table, budgets)
    plan = build_projection_plan(descriptor, view, canonicalized_input=canonicalized_input, budgets=budgets)
    return call_arrow_kernel(
        _canonical_project_native,
        [table],
        plan,
        cancel_probe=cancel_probe,
        budgets=budgets,
        deadline_monotonic=deadline_monotonic,
        pool_threads=pool_threads,
    )
