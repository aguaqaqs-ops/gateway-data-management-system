"""Neutral standard comparison core and semantic facts digests.

This module deliberately consumes only the public snapshot and comparison contracts.  The Python
implementation is the small/reference execution path used by unit fixtures; records remain
in-memory semantic values until the S5 artifact writer owns their durable closure.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Iterable

from gateway_shared_kernel import (
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    CanonicalEncodingError,
    CollectionSemantics,
    DateScalar,
    DateTimeScalar,
    DeclaredType,
    DeclaredTypeKind,
    DigestKind,
    DigestRef,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    TypedScalar,
    UnsignedIntegerScalar,
    canonicalize_identifier,
    encode_collection,
    encode_typed_scalar,
    raw_blob_digest,
    semantic_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_shared_kernel.uleb128 import encode_uleb128

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SqlDeclaredTypeMappingError,
    declared_type_for_sql_spelling,
)
from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope,
    ComparisonFacts,
    ComparisonMode,
    ComparisonPlan,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonSchemaChanges,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTablePolicy,
    ComparisonTableStatus,
    DetailedFactsResult,
    FailedResult,
    FieldChange,
    KeylessPolicy,
    PairResultStatus,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    COMPARISON_PROJECTION_CONTRACT_VERSION,
    SCALAR_ENCODING_VERSION,
    SnapshotColumnDescriptor,
    SnapshotTable,
    SnapshotTableDescriptor,
)


COMPARISON_DIRECTION = "BEFORE_TO_CURRENT"
STANDARD_COMPARISON_ALGORITHM_VERSION = "standard-reference/v1"

_TYPED_SCALAR_TYPES = (
    NullScalar,
    BooleanScalar,
    SignedIntegerScalar,
    UnsignedIntegerScalar,
    StringScalar,
    BinaryScalar,
    BitScalar,
    DateScalar,
    DateTimeScalar,
    TimestampScalar,
    TimeDurationScalar,
    Float32Scalar,
    Float64Scalar,
)


class StandardComparisonError(ValueError):
    """A table-local comparison failure that must not be treated as an empty table."""


@dataclass(frozen=True, slots=True)
class _EncodedRow:
    values: tuple[tuple[str, object], ...]
    frames: tuple[tuple[str, bytes], ...]

    def frame_map(self) -> dict[str, bytes]:
        return dict(self.frames)

    def value_map(self) -> dict[str, object]:
        return dict(self.values)


@dataclass(frozen=True, slots=True)
class _SchemaView:
    before_columns: dict[str, SnapshotColumnDescriptor]
    current_columns: dict[str, SnapshotColumnDescriptor]
    before_only: tuple[str, ...]
    current_only: tuple[str, ...]
    selected: tuple[str, ...]
    incompatible: tuple[str, ...]
    before_key: tuple[str, ...]
    current_key: tuple[str, ...]
    key_changed: bool
    key_invalid: bool


def compare_plan(plan: ComparisonPlan) -> DetailedFactsResult | FailedResult:
    """Execute one already-bound detailed plan and return neutral semantic facts."""

    if type(plan) is not ComparisonPlan:
        raise TypeError("plan must be ComparisonPlan")
    if plan.comparison_mode is not ComparisonMode.DETAILED:
        return FailedResult(
            pair_id=plan.pair_id,
            status=PairResultStatus.FAILED,
            diagnostics=("COMPARISON_MODE_NOT_DETAILED",),
        )

    try:
        table_facts = tuple(_compare_task_safely(task) for task in plan.tasks)
        facts = _build_facts(
            plan,
            tuple(
                _with_table_digest(fact)
                for fact in table_facts
            ),
        )
    except StandardComparisonError as exc:
        return FailedResult(
            pair_id=plan.pair_id,
            status=PairResultStatus.FAILED,
            diagnostics=(str(exc),),
        )
    status = facts.summary.status
    return DetailedFactsResult(
        pair_id=plan.pair_id,
        status=status,
        facts=facts,
        diagnostics=facts.diagnostics,
    )


def _compare_task_safely(task: Any) -> ComparisonTableFact:
    try:
        return _compare_task(task)
    except Exception as exc:
        before = task.before_descriptor
        current = task.current_descriptor
        diagnostic = str(exc) if isinstance(exc, StandardComparisonError) else type(exc).__name__
        schema_changes = ComparisonSchemaChanges()
        if (
            before is not None
            and current is not None
            and isinstance(task.policy, ComparisonTablePolicy)
        ):
            try:
                schema_changes = _schema_changes_from_view(
                    _schema_view(before, current, task.policy)
                )
            except Exception:
                schema_changes = ComparisonSchemaChanges()
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
                    diagnostics=(diagnostic,),
                ),
            ),
            diagnostics=(diagnostic,),
        )


def _compare_task(task: Any) -> ComparisonTableFact:
    if type(task.table_name) is not str:
        raise StandardComparisonError("TABLE_TASK_INVALID")
    policy = task.policy
    if type(policy) is not ComparisonTablePolicy:
        raise StandardComparisonError("TABLE_POLICY_MISSING")
    if policy.ordered_policy is not None:
        from gateway_backend.capabilities.comparison.ordered import compare_ordered_task

        return compare_ordered_task(task)
    before_descriptor = task.before_descriptor
    current_descriptor = task.current_descriptor
    if before_descriptor is None and current_descriptor is None:
        raise StandardComparisonError("TABLE_TASK_HAS_NO_SIDE")
    if before_descriptor is None:
        return _compare_single_side(
            task.table_name,
            current_descriptor,
            task.current_table,
            policy,
            added=True,
            artifact_scope=task.artifact_scope,
        )
    if current_descriptor is None:
        return _compare_single_side(
            task.table_name,
            before_descriptor,
            task.before_table,
            policy,
            added=False,
            artifact_scope=task.artifact_scope,
        )

    if _can_table_early_exit(before_descriptor, current_descriptor, policy):
        return ComparisonTableFact(
            table_name=task.table_name,
            status=ComparisonTableStatus.UNCHANGED,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            schema_changes=_empty_schema_changes(before_descriptor, current_descriptor),
            row_count_before=before_descriptor.row_count,
            row_count_current=current_descriptor.row_count,
        )

    schema = _schema_view(before_descriptor, current_descriptor, policy)
    schema_changes = ComparisonSchemaChanges(
        before_only_columns=schema.before_only,
        current_only_columns=schema.current_only,
        selected_columns=schema.selected,
        effective_compare_key_before=schema.before_key,
        effective_compare_key_current=schema.current_key,
        effective_compare_key_changed=schema.key_changed,
        incompatible_columns=schema.incompatible,
    )
    schema_diagnostics = _schema_diagnostics(schema, policy)
    if schema.key_invalid or schema.key_changed:
        return ComparisonTableFact(
            table_name=task.table_name,
            status=ComparisonTableStatus.DEGRADED,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            schema_changes=schema_changes,
            row_count_before=before_descriptor.row_count,
            row_count_current=current_descriptor.row_count,
            records=(
                ComparisonRecord(
                    table_name=task.table_name,
                    record_kind=ComparisonRecordKind.TABLE_DEGRADED,
                    diagnostics=tuple(schema_diagnostics),
                ),
            ),
            diagnostics=tuple(schema_diagnostics),
        )
    if not schema.selected:
        return _schema_only_fact(
            task.table_name,
            before_descriptor,
            current_descriptor,
            schema_changes,
            schema_diagnostics,
        )

    before_rows = _read_rows(task.before_table, before_descriptor, schema.selected)
    current_rows = _read_rows(task.current_table, current_descriptor, schema.selected)
    if not schema.before_key:
        fact = _compare_keyless(
            task.table_name,
            before_descriptor,
            current_descriptor,
            before_rows,
            current_rows,
            schema,
            policy,
            task.artifact_scope,
            schema_diagnostics,
        )
    else:
        fact = _compare_keyed(
            task.table_name,
            before_descriptor,
            current_descriptor,
            before_rows,
            current_rows,
            schema,
            policy,
            task.artifact_scope,
            schema_diagnostics,
        )
    return fact


def _compare_single_side(
    table_name: str,
    descriptor: SnapshotTableDescriptor | None,
    table: SnapshotTable | None,
    policy: ComparisonTablePolicy,
    *,
    added: bool,
    artifact_scope: ArtifactScope,
) -> ComparisonTableFact:
    if descriptor is None:
        raise StandardComparisonError("TABLE_DESCRIPTOR_MISSING")
    selected = tuple(
        canonicalize_identifier(column.name)
        for column in descriptor.columns
        if canonicalize_identifier(column.name) not in policy.ignored_columns
    )
    schema_changes = ComparisonSchemaChanges(
        current_only_columns=selected if added else (),
        before_only_columns=() if added else selected,
        selected_columns=selected,
        effective_compare_key_current=tuple(
            canonicalize_identifier(name) for name in descriptor.compare_key_columns
        )
        if added
        else (),
        effective_compare_key_before=()
        if added
        else tuple(canonicalize_identifier(name) for name in descriptor.compare_key_columns),
    )
    if table is None or table.reader is None:
        return ComparisonTableFact(
            table_name=table_name,
            status=ComparisonTableStatus.DEGRADED,
            before_descriptor=None if added else descriptor,
            current_descriptor=descriptor if added else None,
            schema_changes=schema_changes,
            row_count_before=None if added else descriptor.row_count,
            row_count_current=descriptor.row_count if added else None,
            diagnostics=("TABLE_READER_UNAVAILABLE",),
        )
    rows = _read_rows(table, descriptor, selected)
    records: list[ComparisonRecord] = []
    kind = ComparisonRecordKind.ROW_ADDED if added else ComparisonRecordKind.ROW_DELETED
    identity_columns = tuple(
        canonicalize_identifier(item) for item in descriptor.compare_key_columns
    ) or selected
    for row in rows:
        record = ComparisonRecord(
            table_name=table_name,
            record_kind=kind,
            row_identity=_row_digest(row, identity_columns),
            before_values=()
            if added
            else tuple(sorted(row.value_map().items())),
            current_values=tuple(sorted(row.value_map().items())) if added else (),
        )
        if artifact_scope is ArtifactScope.ALL_CHANGES:
            records.append(record)
    return ComparisonTableFact(
        table_name=table_name,
        status=ComparisonTableStatus.ADDED_TABLE if added else ComparisonTableStatus.DELETED_TABLE,
        before_descriptor=None if added else descriptor,
        current_descriptor=descriptor if added else None,
        schema_changes=schema_changes,
        row_count_before=None if added else descriptor.row_count,
        row_count_current=descriptor.row_count if added else None,
        row_added_count=len(rows) if added else 0,
        row_deleted_count=0 if added else len(rows),
        suppressed_added_count=len(rows) if added and artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        suppressed_deleted_count=len(rows) if not added and artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        records=tuple(records),
    )


def _compare_keyed(
    table_name: str,
    before_descriptor: SnapshotTableDescriptor,
    current_descriptor: SnapshotTableDescriptor,
    before_rows: tuple[_EncodedRow, ...],
    current_rows: tuple[_EncodedRow, ...],
    schema: _SchemaView,
    policy: ComparisonTablePolicy,
    artifact_scope: ArtifactScope,
    schema_diagnostics: list[str],
) -> ComparisonTableFact:
    before_index = _key_index(before_rows, schema.before_key, table_name)
    current_index = _key_index(current_rows, schema.current_key, table_name)
    records: list[ComparisonRecord] = []
    added = sorted(current_index.keys() - before_index.keys())
    deleted = sorted(before_index.keys() - current_index.keys())
    modified = 0
    for key in added:
        if artifact_scope is ArtifactScope.ALL_CHANGES:
            records.append(
                _row_record(
                    table_name,
                    ComparisonRecordKind.ROW_ADDED,
                    current_index[key],
                    schema.selected,
                    current=True,
                    identity_columns=schema.current_key,
                )
            )
    for key in deleted:
        if artifact_scope is ArtifactScope.ALL_CHANGES:
            records.append(
                _row_record(
                    table_name,
                    ComparisonRecordKind.ROW_DELETED,
                    before_index[key],
                    schema.selected,
                    current=False,
                    identity_columns=schema.before_key,
                )
            )
    compare_columns = tuple(
        column
        for column in schema.selected
        if column not in schema.before_key and column not in schema.incompatible
    )
    for key in sorted(before_index.keys() & current_index.keys()):
        before = before_index[key]
        current = current_index[key]
        changed = tuple(
            column
            for column in compare_columns
            if before.frame_map()[column] != current.frame_map()[column]
        )
        if not changed:
            continue
        modified += 1
        field_changes = tuple(
            FieldChange(
                table_name=table_name,
                row_identity=_digest_from_key(key),
                column_name=column,
                before_value=before.value_map()[column],
                current_value=current.value_map()[column],
            )
            for column in changed
        )
        records.append(
            ComparisonRecord(
                table_name=table_name,
                record_kind=ComparisonRecordKind.ROW_MODIFIED,
                row_identity=_digest_from_key(key),
                changed_columns=changed,
                before_values=tuple((column, before.value_map()[column]) for column in changed),
                current_values=tuple((column, current.value_map()[column]) for column in changed),
                field_changes=field_changes,
            )
        )
    if schema_diagnostics:
        records.append(
            _schema_record(table_name, schema_diagnostics, schema.selected)
        )
    status = ComparisonTableStatus.MODIFIED
    if schema_diagnostics:
        status = ComparisonTableStatus.SCHEMA_CHANGED
    if not records and not schema_diagnostics:
        status = (
            ComparisonTableStatus.SCHEMA_ONLY_CHANGED
            if _ignored_values_changed(before_descriptor, current_descriptor, policy)
            else ComparisonTableStatus.UNCHANGED
        )
        if status is ComparisonTableStatus.SCHEMA_ONLY_CHANGED:
            schema_diagnostics.append("IGNORED_COLUMNS_CHANGED")
            records.append(_schema_record(table_name, schema_diagnostics, schema.selected))
    return ComparisonTableFact(
        table_name=table_name,
        status=status,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        schema_changes=_schema_changes_from_view(schema),
        row_count_before=before_descriptor.row_count,
        row_count_current=current_descriptor.row_count,
        row_added_count=len(added),
        row_deleted_count=len(deleted),
        row_modified_count=modified,
        suppressed_added_count=len(added) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        suppressed_deleted_count=len(deleted) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        records=tuple(sorted(records, key=_record_sort_key)),
        diagnostics=tuple(schema_diagnostics),
    )


def _compare_keyless(
    table_name: str,
    before_descriptor: SnapshotTableDescriptor,
    current_descriptor: SnapshotTableDescriptor,
    before_rows: tuple[_EncodedRow, ...],
    current_rows: tuple[_EncodedRow, ...],
    schema: _SchemaView,
    policy: ComparisonTablePolicy,
    artifact_scope: ArtifactScope,
    schema_diagnostics: list[str],
) -> ComparisonTableFact:
    if policy.keyless_policy is KeylessPolicy.DEGRADE_NO_COMPARE_KEY:
        diagnostics = tuple(schema_diagnostics) + ("DEGRADE_NO_COMPARE_KEY",)
        return ComparisonTableFact(
            table_name=table_name,
            status=ComparisonTableStatus.DEGRADED,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            schema_changes=_schema_changes_from_view(schema),
            row_count_before=before_descriptor.row_count,
            row_count_current=current_descriptor.row_count,
            diagnostics=diagnostics,
            records=(_schema_record(table_name, diagnostics, schema.selected),),
        )
    before_counts = Counter(_row_digest(row, schema.selected).value for row in before_rows)
    current_counts = Counter(_row_digest(row, schema.selected).value for row in current_rows)
    added = sorted((current_counts - before_counts).elements())
    deleted = sorted((before_counts - current_counts).elements())
    records: list[ComparisonRecord] = []
    for identity in added:
        if artifact_scope is ArtifactScope.ALL_CHANGES:
            records.append(
                ComparisonRecord(
                    table_name=table_name,
                    record_kind=ComparisonRecordKind.ROW_ADDED,
                    row_identity=DigestRef(identity),
                )
            )
    for identity in deleted:
        if artifact_scope is ArtifactScope.ALL_CHANGES:
            records.append(
                ComparisonRecord(
                    table_name=table_name,
                    record_kind=ComparisonRecordKind.ROW_DELETED,
                    row_identity=DigestRef(identity),
                )
            )
    if schema_diagnostics:
        records.append(_schema_record(table_name, schema_diagnostics, schema.selected))
    status = ComparisonTableStatus.MODIFIED if added or deleted else ComparisonTableStatus.UNCHANGED
    if not added and not deleted and _ignored_values_changed(
        before_descriptor, current_descriptor, policy
    ):
        status = ComparisonTableStatus.SCHEMA_ONLY_CHANGED
        schema_diagnostics.append("IGNORED_COLUMNS_CHANGED")
        records.append(_schema_record(table_name, schema_diagnostics, schema.selected))
    if schema_diagnostics:
        status = ComparisonTableStatus.SCHEMA_CHANGED
    return ComparisonTableFact(
        table_name=table_name,
        status=status,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        schema_changes=_schema_changes_from_view(schema),
        row_count_before=before_descriptor.row_count,
        row_count_current=current_descriptor.row_count,
        row_added_count=len(added),
        row_deleted_count=len(deleted),
        suppressed_added_count=len(added) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        suppressed_deleted_count=len(deleted) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        records=tuple(sorted(records, key=_record_sort_key)),
        diagnostics=tuple(schema_diagnostics),
    )


def _build_facts(plan: ComparisonPlan, tables: tuple[ComparisonTableFact, ...]) -> ComparisonFacts:
    summary = _summary(tables)
    table_payloads = tuple(_table_digest_payload(table) for table in tables)
    core_payload = {
        "kind": "comparison-facts-core",
        "algorithm_version": STANDARD_COMPARISON_ALGORITHM_VERSION,
        "summary": _summary_payload(summary),
        "tables": table_payloads,
    }
    facts_core_digest = raw_blob_digest(canonicalize_json_value(core_payload))
    table_policy_payloads = []
    for task in sorted(plan.tasks, key=lambda item: item.table_name):
        if task.policy is None:
            continue
        table_policy_payloads.append(
            {
                "table_name": task.policy.table_name,
                "ignored_columns": list(task.policy.ignored_columns),
                "keyless_policy": task.policy.keyless_policy.value,
                "policy_version": task.policy.policy_version,
                "ordered_policy": _ordered_policy_payload(task.policy.ordered_policy),
            }
        )
    envelope = {
        "kind": "comparison",
        "algorithm_version": STANDARD_COMPARISON_ALGORITHM_VERSION,
        "before_snapshot_digest": plan.before.snapshot.snapshot_digest.value,
        "current_snapshot_digest": plan.current.snapshot.snapshot_digest.value,
        "comparison_options": [[key, value] for key, value in plan.comparison_options],
        "contract_versions": [[key, value] for key, value in plan.contract_versions],
        "artifact_scope": plan.artifact_scope.value,
        "projection_contract_version": COMPARISON_PROJECTION_CONTRACT_VERSION,
        "scalar_encoding_version": SCALAR_ENCODING_VERSION,
        "facts_core_digest": facts_core_digest.value,
        "table_policies": table_policy_payloads,
    }
    comparison_digest = raw_blob_digest(canonicalize_json_value(envelope))
    diagnostics = tuple(
        diagnostic
        for table in tables
        for diagnostic in table.diagnostics
    )
    return ComparisonFacts(
        comparison_digest=comparison_digest,
        facts_core_digest=facts_core_digest,
        comparison_contract_version=str(
            dict(plan.contract_versions).get("comparison_contract_version", "unknown")
        ),
        projection_contract_version=COMPARISON_PROJECTION_CONTRACT_VERSION,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        before_snapshot_digest=plan.before.snapshot.snapshot_digest,
        current_snapshot_digest=plan.current.snapshot.snapshot_digest,
        comparison_mode=plan.comparison_mode,
        project_identity_status=plan.identity_status,
        assessment_digest=plan.assessment_digest,
        direction=COMPARISON_DIRECTION,
        summary=summary,
        tables=tables,
        diagnostics=diagnostics,
    )


def _summary(tables: tuple[ComparisonTableFact, ...]) -> ComparisonSummary:
    unchanged = sum(item.status is ComparisonTableStatus.UNCHANGED for item in tables)
    degraded = sum(item.status is ComparisonTableStatus.DEGRADED for item in tables)
    added_tables = sum(item.status is ComparisonTableStatus.ADDED_TABLE for item in tables)
    deleted_tables = sum(item.status is ComparisonTableStatus.DELETED_TABLE for item in tables)
    schema_changed = sum(
        item.status
        in {ComparisonTableStatus.SCHEMA_CHANGED, ComparisonTableStatus.SCHEMA_ONLY_CHANGED}
        for item in tables
    )
    changed = len(tables) - unchanged
    if degraded:
        status = PairResultStatus.DEGRADED
    elif changed == 0:
        status = PairResultStatus.UNCHANGED
    elif all(
        item.status
        in {ComparisonTableStatus.UNCHANGED, ComparisonTableStatus.BUSINESS_EQUIVALENT}
        for item in tables
    ):
        status = PairResultStatus.BUSINESS_EQUIVALENT
    else:
        status = PairResultStatus.CHANGED
    return ComparisonSummary(
        status=status,
        table_count=len(tables),
        unchanged_table_count=unchanged,
        changed_table_count=changed,
        added_table_count=added_tables,
        deleted_table_count=deleted_tables,
        schema_changed_table_count=schema_changed,
        degraded_table_count=degraded,
        row_added_count=sum(item.row_added_count for item in tables),
        row_deleted_count=sum(item.row_deleted_count for item in tables),
        row_modified_count=sum(item.row_modified_count for item in tables),
        suppressed_added_count=sum(item.suppressed_added_count for item in tables),
        suppressed_deleted_count=sum(item.suppressed_deleted_count for item in tables),
        diagnostics_count=sum(len(item.diagnostics) for item in tables),
    )


def _schema_view(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    policy: ComparisonTablePolicy,
) -> _SchemaView:
    before_columns = _column_map(before)
    current_columns = _column_map(current)
    before_names = set(before_columns)
    current_names = set(current_columns)
    before_only = tuple(sorted(before_names - current_names))
    current_only = tuple(sorted(current_names - before_names))
    selected = tuple(sorted((before_names & current_names) - set(policy.ignored_columns)))
    incompatible = tuple(
        column
        for column in selected
        if _column_signature(before_columns[column]) != _column_signature(current_columns[column])
    )
    before_key = tuple(canonicalize_identifier(item) for item in before.compare_key_columns)
    current_key = tuple(canonicalize_identifier(item) for item in current.compare_key_columns)
    key_invalid = (
        len(set(before_key)) != len(before_key)
        or len(set(current_key)) != len(current_key)
        or any(item not in before_columns for item in before_key)
        or any(item not in current_columns for item in current_key)
        or any(item not in selected for item in before_key)
        or any(item not in selected for item in current_key)
        or any(item in incompatible for item in before_key)
        or any(item in incompatible for item in current_key)
    )
    return _SchemaView(
        before_columns=before_columns,
        current_columns=current_columns,
        before_only=before_only,
        current_only=current_only,
        selected=selected,
        incompatible=incompatible,
        before_key=before_key,
        current_key=current_key,
        key_changed=before_key != current_key,
        key_invalid=key_invalid,
    )


def _schema_diagnostics(schema: _SchemaView, policy: ComparisonTablePolicy) -> list[str]:
    diagnostics: list[str] = []
    if any(item not in policy.ignored_columns for item in schema.before_only):
        diagnostics.append("BEFORE_ONLY_COLUMNS")
    if any(item not in policy.ignored_columns for item in schema.current_only):
        diagnostics.append("CURRENT_ONLY_COLUMNS")
    if schema.incompatible:
        diagnostics.append("INCOMPATIBLE_SELECTED_COLUMNS")
    if schema.key_changed:
        diagnostics.append("EFFECTIVE_KEY_CHANGED")
    if any(item in policy.ignored_columns for item in schema.before_key + schema.current_key):
        diagnostics.append("EFFECTIVE_KEY_IGNORED")
    return diagnostics


def _ignored_values_changed(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    policy: ComparisonTablePolicy,
) -> bool:
    return (
        bool(policy.ignored_columns)
        and before.raw_content_digest is not None
        and current.raw_content_digest is not None
        and before.raw_content_digest != current.raw_content_digest
    )


def _schema_only_fact(
    table_name: str,
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    changes: ComparisonSchemaChanges,
    diagnostics: list[str],
) -> ComparisonTableFact:
    if not diagnostics:
        diagnostics = ["NO_SELECTED_COLUMNS"]
    record = _schema_record(table_name, diagnostics, changes.selected_columns)
    return ComparisonTableFact(
        table_name=table_name,
        status=ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
        before_descriptor=before,
        current_descriptor=current,
        schema_changes=changes,
        row_count_before=before.row_count,
        row_count_current=current.row_count,
        records=(record,),
        diagnostics=tuple(diagnostics),
    )


def _read_rows(
    table: SnapshotTable | None,
    descriptor: SnapshotTableDescriptor,
    selected: tuple[str, ...],
) -> tuple[_EncodedRow, ...]:
    if table is None or table.reader is None:
        raise StandardComparisonError("TABLE_READER_UNAVAILABLE")
    columns = tuple(descriptor.columns)
    selected_set = set(selected)
    rows: list[_EncodedRow] = []
    reader = table.reader
    try:
        for raw_row in reader.iter_rows():
            if type(raw_row) is not tuple or len(raw_row) != len(columns):
                raise StandardComparisonError("ROW_SHAPE_MISMATCH")
            values: list[tuple[str, object]] = []
            frames: list[tuple[str, bytes]] = []
            for column, cell in zip(columns, raw_row, strict=True):
                name = canonicalize_identifier(column.name)
                if name not in selected_set:
                    continue
                values.append((name, cell))
                frames.append((name, _encode_cell(column, cell)))
            rows.append(
                _EncodedRow(
                    values=tuple(sorted(values)),
                    frames=tuple(sorted(frames)),
                )
            )
    finally:
        reader.close()
    return tuple(rows)


def _key_index(
    rows: tuple[_EncodedRow, ...],
    key_columns: tuple[str, ...],
    table_name: str,
) -> dict[bytes, _EncodedRow]:
    result: dict[bytes, _EncodedRow] = {}
    for row in rows:
        key = _row_frame(row.frame_map(), key_columns)
        if key in result:
            raise StandardComparisonError(f"DUPLICATE_EFFECTIVE_KEY:{table_name}")
        result[key] = row
    return result


def _row_record(
    table_name: str,
    kind: ComparisonRecordKind,
    row: _EncodedRow,
    selected: tuple[str, ...],
    *,
    current: bool,
    identity_columns: tuple[str, ...] | None = None,
) -> ComparisonRecord:
    values = tuple((name, row.value_map()[name]) for name in selected if name in row.value_map())
    return ComparisonRecord(
        table_name=table_name,
        record_kind=kind,
        row_identity=_row_digest(row, identity_columns or selected),
        before_values=values if not current else (),
        current_values=values if current else (),
    )


def _schema_record(
    table_name: str,
    diagnostics: Iterable[str],
    selected: tuple[str, ...],
) -> ComparisonRecord:
    return ComparisonRecord(
        table_name=table_name,
        record_kind=ComparisonRecordKind.SCHEMA_CHANGE,
        changed_columns=selected,
        diagnostics=tuple(diagnostics),
    )


def _record_sort_key(record: ComparisonRecord) -> tuple[str, str, tuple[str, ...]]:
    return (
        record.record_kind.value,
        "" if record.row_identity is None else record.row_identity.value,
        record.changed_columns,
    )


def _row_digest(row: _EncodedRow, columns: tuple[str, ...]) -> DigestRef:
    return semantic_digest(DigestKind.ROW, _row_frame(row.frame_map(), columns)).digest_ref


def _row_frame(frames: dict[str, bytes], columns: tuple[str, ...]) -> bytes:
    encoded = bytearray(encode_uleb128(len(columns)))
    for name in sorted(columns, key=lambda item: item.encode("utf-8")):
        name_bytes = name.encode("utf-8")
        frame = frames[name]
        encoded.extend(encode_uleb128(len(name_bytes)))
        encoded.extend(name_bytes)
        encoded.extend(frame)
    return bytes(encoded)


def _encode_cell(column: SnapshotColumnDescriptor, cell: object) -> bytes:
    if type(cell).__name__ == "SqlSetValue":
        members = getattr(cell, "members", None)
        if type(members) is not tuple or any(type(item) is not str for item in members):
            raise StandardComparisonError("SET_VALUE_INVALID")
        string_type = DeclaredType(kind=DeclaredTypeKind.STRING)
        return encode_collection(
            CollectionSemantics.SEQUENCE,
            items=tuple(
                encode_typed_scalar(string_type, StringScalar(item)).scalar_frame
                for item in members
            ),
        ).collection_frame
    if not isinstance(cell, _TYPED_SCALAR_TYPES):
        raise StandardComparisonError("SCALAR_VALUE_INVALID")
    if isinstance(cell, NullScalar):
        return encode_typed_scalar(
            DeclaredType(kind=DeclaredTypeKind.NULL), cell
        ).scalar_frame
    declared = _declared_type(column.scalar_type, cell)
    try:
        return encode_typed_scalar(declared, cell).scalar_frame
    except (CanonicalEncodingError, TypeError, ValueError) as exc:
        raise StandardComparisonError("SCALAR_TYPE_MISMATCH") from exc


def _declared_type(spelling: str | None, cell: TypedScalar) -> DeclaredType:
    if spelling is None or spelling == "":
        return _infer_declared_type(cell)
    try:
        return declared_type_for_sql_spelling(spelling)
    except SqlDeclaredTypeMappingError:
        raise StandardComparisonError("SCALAR_TYPE_UNKNOWN") from None


def _infer_declared_type(cell: TypedScalar) -> DeclaredType:
    if isinstance(cell, NullScalar):
        return DeclaredType(kind=DeclaredTypeKind.NULL)
    if isinstance(cell, BooleanScalar):
        return DeclaredType(kind=DeclaredTypeKind.BOOLEAN)
    if isinstance(cell, SignedIntegerScalar):
        return DeclaredType(kind=DeclaredTypeKind.SIGNED_INTEGER, bits=64)
    if isinstance(cell, UnsignedIntegerScalar):
        return DeclaredType(kind=DeclaredTypeKind.UNSIGNED_INTEGER, bits=64)
    if isinstance(cell, Float32Scalar):
        return DeclaredType(kind=DeclaredTypeKind.FLOAT32)
    if isinstance(cell, Float64Scalar):
        return DeclaredType(kind=DeclaredTypeKind.FLOAT64)
    if isinstance(cell, StringScalar):
        return DeclaredType(kind=DeclaredTypeKind.STRING)
    if isinstance(cell, BinaryScalar):
        return DeclaredType(kind=DeclaredTypeKind.BINARY)
    if isinstance(cell, BitScalar):
        return DeclaredType(kind=DeclaredTypeKind.BIT, bit_width=max(1, len(cell.raw_bytes) * 8))
    if isinstance(cell, DateScalar):
        return DeclaredType(kind=DeclaredTypeKind.DATE)
    if isinstance(cell, DateTimeScalar):
        return DeclaredType(kind=DeclaredTypeKind.DATETIME)
    if isinstance(cell, TimestampScalar):
        return DeclaredType(kind=DeclaredTypeKind.TIMESTAMP)
    if isinstance(cell, TimeDurationScalar):
        return DeclaredType(kind=DeclaredTypeKind.TIME_DURATION)
    raise StandardComparisonError("SCALAR_TYPE_UNKNOWN")


def _column_map(descriptor: SnapshotTableDescriptor) -> dict[str, SnapshotColumnDescriptor]:
    result: dict[str, SnapshotColumnDescriptor] = {}
    for column in descriptor.columns:
        name = canonicalize_identifier(column.name)
        if name in result:
            raise StandardComparisonError("CANONICAL_COLUMN_COLLISION")
        result[name] = column
    return result


def _column_signature(column: SnapshotColumnDescriptor) -> tuple[str | None, bool]:
    return (None if column.scalar_type is None else column.scalar_type.upper(), column.nullable)


def _can_table_early_exit(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
    policy: ComparisonTablePolicy,
) -> bool:
    return (
        before.compare_schema_digest == current.compare_schema_digest
        and before.row_count == current.row_count
        and before.raw_content_digest is not None
        and before.raw_content_digest == current.raw_content_digest
        and policy.table_name == canonicalize_identifier(before.table_name)
    )


def _empty_schema_changes(
    before: SnapshotTableDescriptor,
    current: SnapshotTableDescriptor,
) -> ComparisonSchemaChanges:
    key = tuple(canonicalize_identifier(item) for item in before.compare_key_columns)
    return ComparisonSchemaChanges(
        selected_columns=tuple(sorted(set(_column_map(before)) & set(_column_map(current)))),
        effective_compare_key_before=key,
        effective_compare_key_current=tuple(
            canonicalize_identifier(item) for item in current.compare_key_columns
        ),
    )


def _schema_changes_from_view(schema: _SchemaView) -> ComparisonSchemaChanges:
    return ComparisonSchemaChanges(
        before_only_columns=schema.before_only,
        current_only_columns=schema.current_only,
        selected_columns=schema.selected,
        effective_compare_key_before=schema.before_key,
        effective_compare_key_current=schema.current_key,
        effective_compare_key_changed=schema.key_changed,
        incompatible_columns=schema.incompatible,
    )


def _with_table_digest(fact: ComparisonTableFact) -> ComparisonTableFact:
    return replace(
        fact,
        table_fact_digest=raw_blob_digest(
            canonicalize_json_value(_table_digest_payload(fact))
        ),
    )


def _table_digest_payload(fact: ComparisonTableFact) -> dict[str, object]:
    before_columns = (
        _column_map(fact.before_descriptor) if fact.before_descriptor is not None else {}
    )
    current_columns = (
        _column_map(fact.current_descriptor) if fact.current_descriptor is not None else {}
    )
    return {
        "table_name": fact.table_name,
        "status": fact.status.value,
        "schema_changes": {
            "before_only": list(fact.schema_changes.before_only_columns),
            "current_only": list(fact.schema_changes.current_only_columns),
            "selected": list(fact.schema_changes.selected_columns),
            "key_before": list(fact.schema_changes.effective_compare_key_before),
            "key_current": list(fact.schema_changes.effective_compare_key_current),
            "key_changed": fact.schema_changes.effective_compare_key_changed,
            "incompatible": list(fact.schema_changes.incompatible_columns),
        },
        "row_count_before": fact.row_count_before,
        "row_count_current": fact.row_count_current,
        "row_added_count": fact.row_added_count,
        "row_deleted_count": fact.row_deleted_count,
        "row_modified_count": fact.row_modified_count,
        "suppressed_added_count": fact.suppressed_added_count,
        "suppressed_deleted_count": fact.suppressed_deleted_count,
        "records": [
            _record_digest_payload(record, before_columns, current_columns)
            for record in fact.records
        ],
        "ordered_extension": _ordered_extension_digest_payload(
            fact.ordered_extension, before_columns, current_columns
        ),
        "blank_extension": _blank_extension_digest_payload(fact.blank_extension),
    }


def _record_digest_payload(
    record: ComparisonRecord,
    before_columns: dict[str, SnapshotColumnDescriptor],
    current_columns: dict[str, SnapshotColumnDescriptor],
) -> dict[str, object]:
    return {
        "kind": record.record_kind.value,
        "row_identity": None if record.row_identity is None else record.row_identity.value,
        "changed_columns": list(record.changed_columns),
        "before_values": [
            [
                name,
                _value_digest_payload(value, before_columns.get(name)),
            ]
            for name, value in record.before_values
        ],
        "current_values": [
            [
                name,
                _value_digest_payload(value, current_columns.get(name)),
            ]
            for name, value in record.current_values
        ],
        "field_changes": [
            {
                "column": item.column_name,
                "before": _value_digest_payload(
                    item.before_value,
                    before_columns.get(item.column_name),
                ),
                "current": _value_digest_payload(
                    item.current_value,
                    current_columns.get(item.column_name),
                ),
            }
            for item in record.field_changes
        ],
    }


def _ordered_policy_payload(policy: Any) -> dict[str, object] | None:
    if policy is None:
        return None
    return {
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "order_key": list(policy.order_key),
        "row_identity_key": None if policy.row_identity_key is None else list(policy.row_identity_key),
        "stable_key_candidates": list(policy.stable_key_candidates),
        "value_columns": list(policy.value_columns),
        "ignored_columns": list(policy.ignored_columns),
        "blank_row_policy": policy.blank_row_policy.value,
        "move_policy": policy.move_policy,
        "ambiguity_policy": policy.ambiguity_policy,
        "tail_change_policy": policy.tail_change_policy,
        "table_processing_mode_policy": policy.table_processing_mode_policy,
        "policy_digest": None if policy.policy_digest is None else policy.policy_digest.value,
    }


def _ordered_extension_digest_payload(
    extension: Any,
    before_columns: dict[str, SnapshotColumnDescriptor],
    current_columns: dict[str, SnapshotColumnDescriptor],
) -> dict[str, object] | None:
    if extension is None:
        return None
    return {
        "contract_version": extension.contract_version,
        "status": extension.status.value,
        "summary": {
            "row_added": extension.ordered_summary.row_added_count,
            "row_deleted": extension.ordered_summary.row_deleted_count,
            "row_modified": extension.ordered_summary.row_modified_count,
            "row_moved": extension.ordered_summary.row_moved_count,
            "position_changed": extension.ordered_summary.position_changed_count,
            "degraded": extension.ordered_summary.degraded_count,
        },
        "before_ordered_digest": (
            None if extension.before_ordered_digest is None else extension.before_ordered_digest.value
        ),
        "current_ordered_digest": (
            None if extension.current_ordered_digest is None else extension.current_ordered_digest.value
        ),
        "replay_guarantee": extension.replay_guarantee.value,
        "table_processing_mode": (
            None if extension.table_processing_mode is None else extension.table_processing_mode.value
        ),
        "policy_digest": None if extension.policy_digest is None else extension.policy_digest.value,
        "records": [
            {
                "record_kind": record.record_kind.value,
                "semantic_kind": record.semantic_kind.value,
                "entity_key_kind": record.entity_key_kind.value,
                "row_identity": None if record.row_identity is None else record.row_identity.value,
                "before_position": record.before_position,
                "current_position": record.current_position,
                "changed_columns": list(record.changed_columns),
                "before_values": [
                    [name, _value_digest_payload(value, before_columns.get(name))]
                    for name, value in record.before_values
                ],
                "current_values": [
                    [name, _value_digest_payload(value, current_columns.get(name))]
                    for name, value in record.current_values
                ],
            }
            for record in extension.records
        ],
    }


def _blank_extension_digest_payload(extension: Any) -> dict[str, object] | None:
    if extension is None:
        return None
    return {
        "contract_version": extension.contract_version,
        "status": extension.status.value,
        "summary": {
            "inserted": extension.blank_summary.interval_inserted_count,
            "deleted": extension.blank_summary.interval_deleted_count,
            "changed": extension.blank_summary.blank_changed_count,
            "degraded": extension.blank_summary.degraded_count,
        },
        "before_occupancy_digest": (
            None
            if extension.before_occupancy_digest is None
            else extension.before_occupancy_digest.value
        ),
        "current_occupancy_digest": (
            None
            if extension.current_occupancy_digest is None
            else extension.current_occupancy_digest.value
        ),
        "replay_guarantee": extension.replay_guarantee.value,
        "records": [
            {
                "record_kind": record.record_kind.value,
                "semantic_kind": record.semantic_kind.value,
                "entity_key_kind": record.entity_key_kind.value,
                "interval": {
                    "before_start": record.interval.before_start,
                    "before_end": record.interval.before_end,
                    "current_start": record.interval.current_start,
                    "current_end": record.interval.current_end,
                    "row_count": record.interval.row_count,
                    "interval_digest": (
                        None
                        if record.interval.interval_digest is None
                        else record.interval.interval_digest.value
                    ),
                },
                "before_occupancy": record.before_occupancy,
                "current_occupancy": record.current_occupancy,
            }
            for record in extension.records
        ],
    }


def _value_digest_payload(
    value: object,
    column: SnapshotColumnDescriptor | None,
) -> str:
    if isinstance(value, _TYPED_SCALAR_TYPES):
        if column is None:
            return encode_typed_scalar(_infer_declared_type(value), value).scalar_frame.hex()
        return _encode_cell(column, value).hex()
    if type(value).__name__ == "SqlSetValue":
        members = getattr(value, "members", ())
        string_type = DeclaredType(kind=DeclaredTypeKind.STRING)
        return encode_collection(
            CollectionSemantics.SEQUENCE,
            items=tuple(
                encode_typed_scalar(string_type, StringScalar(item)).scalar_frame
                for item in members
            ),
        ).collection_frame.hex()
    raise StandardComparisonError("SCALAR_VALUE_INVALID")


def _summary_payload(summary: ComparisonSummary) -> dict[str, object]:
    return {
        "status": summary.status.value,
        "table_count": summary.table_count,
        "unchanged_table_count": summary.unchanged_table_count,
        "changed_table_count": summary.changed_table_count,
        "added_table_count": summary.added_table_count,
        "deleted_table_count": summary.deleted_table_count,
        "schema_changed_table_count": summary.schema_changed_table_count,
        "degraded_table_count": summary.degraded_table_count,
        "row_added_count": summary.row_added_count,
        "row_deleted_count": summary.row_deleted_count,
        "row_modified_count": summary.row_modified_count,
        "suppressed_added_count": summary.suppressed_added_count,
        "suppressed_deleted_count": summary.suppressed_deleted_count,
    }


def _digest_from_key(key: bytes) -> DigestRef:
    return semantic_digest(DigestKind.ROW, key).digest_ref
