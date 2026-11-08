"""Bounded Python rule/type metadata for the Arrow canonical projection kernel."""

from __future__ import annotations

from typing import Any

from gateway_compute._native import _canonical_project_native

from gateway_backend.capabilities.snapshot_materialization import (
    ArrowMetadata,
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
    SnapshotTableDescriptor,
    normalize_sql_type_spelling,
)
from gateway_backend.capabilities.table_rules.contracts import OrderedPolicy, StorageRuleView


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
