"""Ordered table metadata and degradation facts for the native kernel."""

from __future__ import annotations

from typing import Any

from gateway_backend.capabilities.comparison.contracts import (
    BlankExtension, BlankSummary, ComparisonRecord, ComparisonRecordKind,
    ComparisonSchemaChanges, ComparisonTableFact, ComparisonTableStatus,
    OrderedExtension, OrderedStatus, OrderedSummary, OrderedTablePolicy,
    OrderedTableProcessingMode, ReplayGuarantee, SchemaChangeSource,
    TableComparisonTask, _ComparisonTablePolicy,
)
from gateway_backend.capabilities.comparison.errors import StandardComparisonError
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotTable, SnapshotTableDescriptor,
)


class OrderedComparisonError(StandardComparisonError):
    """An ordered metadata comparison failure."""


def _compare_single_side_ordered(task: TableComparisonTask) -> ComparisonTableFact:
    policy = task.policy
    if type(policy) is not _ComparisonTablePolicy or policy.ordered_policy is None:
        raise OrderedComparisonError("ORDERED_POLICY_MISSING")
    before, current = task.before_descriptor, task.current_descriptor
    if before is None and current is None:
        raise OrderedComparisonError("TABLE_TASK_HAS_NO_SIDE")
    if before is not None and current is not None:
        raise OrderedComparisonError("METADATA_ROUTE_REQUIRES_NATIVE_ROWS")
    added = before is None
    descriptor = current if added else before
    try:
        return _compare_single_side(
            task, descriptor, task.current_table if added else task.before_table,
            added=added, policy=policy,
        )
    except StandardComparisonError as exc:
        assert descriptor is not None
        return _degraded_fact(
            task, before, current,
            _single_side_schema_changes(descriptor, added=added, policy=policy),
            (str(exc),),
        )


def _compare_single_side(
    task: TableComparisonTask,
    descriptor: SnapshotTableDescriptor | None,
    table: SnapshotTable | None,
    *,
    added: bool,
    policy: _ComparisonTablePolicy,
) -> ComparisonTableFact:
    if descriptor is None:
        raise OrderedComparisonError("TABLE_DESCRIPTOR_MISSING")
    assert policy.ordered_policy is not None
    schema_changes = _single_side_schema_changes(descriptor, added=added, policy=policy)
    if table is None or table.reader is None:
        return _degraded_fact(
            task,
            None if added else descriptor,
            descriptor if added else None,
            schema_changes,
            ("TABLE_READER_UNAVAILABLE",),
        )
    return ComparisonTableFact(
        table_name=task.table_name,
        status=ComparisonTableStatus.ADDED_TABLE if added else ComparisonTableStatus.DELETED_TABLE,
        before_descriptor=None if added else descriptor,
        current_descriptor=descriptor if added else None,
        schema_changes=schema_changes,
        row_count_before=None if added else descriptor.row_count,
        row_count_current=descriptor.row_count if added else None,
    )


def _ordered_schema_diagnostics(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    policy: OrderedTablePolicy,
    schema: Any,
) -> tuple[str, ...]:
    before_names = {column.name for column in before.columns}
    current_names = {column.name for column in current.columns}
    required = set(policy.order_key)
    if policy.row_identity_key is not None:
        required.update(policy.row_identity_key)
    missing = sorted((required - before_names) | (required - current_names))
    diagnostics: list[str] = []
    if missing:
        diagnostics.append("ORDERED_REQUIRED_COLUMN_MISSING")
    if schema.incompatible:
        diagnostics.append("INCOMPATIBLE_SELECTED_COLUMNS")
    if schema.selected == ():
        diagnostics.append("NO_SELECTED_COLUMNS")
    if policy.row_identity_key is None:
        diagnostics.append("ROW_IDENTITY_MISSING")
    return tuple(dict.fromkeys(diagnostics))


def _degraded_fact(
    task: TableComparisonTask,
    before: SnapshotTableDescriptor | None,
    current: SnapshotTableDescriptor | None,
    schema_changes: ComparisonSchemaChanges,
    diagnostics: tuple[str, ...],
) -> ComparisonTableFact:
    return ComparisonTableFact(
        table_name=task.table_name,
        status=ComparisonTableStatus.DEGRADED,
        before_descriptor=before,
        current_descriptor=current,
        schema_changes=schema_changes,
        row_count_before=None if before is None else before.row_count,
        row_count_current=None if current is None else current.row_count,
        records=(
            ComparisonRecord(
                table_name=task.table_name,
                record_kind=ComparisonRecordKind.TABLE_DEGRADED,
                diagnostics=diagnostics,
            ),
        ),
        diagnostics=diagnostics,
        ordered_extension=OrderedExtension(
            status=OrderedStatus.DEGRADED,
            ordered_summary=OrderedSummary(degraded_count=1),
            replay_guarantee=ReplayGuarantee.UNSUPPORTED,
            table_processing_mode=OrderedTableProcessingMode.DEGRADED,
            diagnostics=diagnostics,
            policy_digest=task.policy.ordered_policy.policy_digest if task.policy and task.policy.ordered_policy else None,
        ),
        blank_extension=BlankExtension(
            status=OrderedStatus.DEGRADED,
            blank_summary=BlankSummary(degraded_count=1),
            replay_guarantee=ReplayGuarantee.UNSUPPORTED,
            diagnostics=diagnostics,
        ),
    )


def _single_side_schema_changes(
    descriptor: SnapshotTableDescriptor,
    *,
    added: bool,
    policy: _ComparisonTablePolicy,
) -> ComparisonSchemaChanges:
    selected = tuple(sorted(column.name for column in descriptor.columns))
    return ComparisonSchemaChanges(
        current_only_columns=selected if added else (),
        before_only_columns=() if added else selected,
        selected_columns=selected,
        effective_compare_key_current=policy.effective_key_current if added else (),
        effective_compare_key_before=() if added else policy.effective_key_before,
        change_source=SchemaChangeSource.SOURCE_SCHEMA,
    )
