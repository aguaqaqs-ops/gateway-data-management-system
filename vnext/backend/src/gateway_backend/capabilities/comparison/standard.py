"""Neutral standard comparison core and semantic facts digests.

This module deliberately consumes only the public snapshot and comparison contracts.  The Python
implementation is the small/reference execution path used by unit fixtures; records remain
in-memory semantic values until the S5 artifact writer owns their durable closure.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from gateway_shared_kernel import (
    BinaryScalar,
    BitScalar,
    BooleanScalar,
    DateScalar,
    DateTimeScalar,
    DigestRef,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    TimeDurationScalar,
    TimestampScalar,
    UnsignedIntegerScalar,
    canonicalize_identifier,
    raw_blob_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

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
    _ComparisonTablePolicy,
    ComparisonTableStatus,
    DatasetReplacementResult,
    DetailedFactsResult,
    FailedResult,
    FieldChange,
    KeylessPolicy,
    PairResultStatus,
)
from gateway_backend.capabilities.comparison.errors import StandardComparisonError
from gateway_backend.capabilities.comparison.row_encoding import (
    _EncodedRow,
    _SchemaView,
    _can_table_early_exit,
    _digest_from_key,
    _empty_schema_changes,
    _ignored_values_changed,
    _key_index,
    _read_rows,
    _record_sort_key,
    _row_digest,
    _row_record,
    _schema_changes_from_view,
    _schema_diagnostics,
    _schema_only_fact,
    _schema_record,
    _schema_view,
    _summary_payload,
    _table_digest_payload,
    _ordered_policy_payload,
    _column_map,
    _with_table_digest,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    COMPARISON_PROJECTION_CONTRACT_VERSION,
    SCALAR_ENCODING_VERSION,
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


def compare_plan(
    plan: ComparisonPlan,
) -> DetailedFactsResult | DatasetReplacementResult | FailedResult:
    """Execute one already-bound detailed plan and return neutral semantic facts."""

    if type(plan) is not ComparisonPlan:
        raise TypeError("plan must be ComparisonPlan")
    if plan.mode is ComparisonMode.DATASET_REPLACEMENT:
        return DatasetReplacementResult(
            pair_id=plan.pair_id,
            status=PairResultStatus.CHANGED,
            diagnostics=("DATASET_REPLACEMENT",),
        )
    if plan.mode is not ComparisonMode.DETAILED:
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
            and isinstance(task.policy, _ComparisonTablePolicy)
        ):
            try:
                schema_changes = _schema_changes_from_view(
                    _schema_view(before, current, task.policy), task.policy
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
    if type(policy) is not _ComparisonTablePolicy:
        raise StandardComparisonError("TABLE_POLICY_MISSING")
    if policy.comparison_role in {"BROWSE_ONLY", "SNAPSHOT_ONLY"}:
        return _compare_non_record_role(task, policy)
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
            schema_changes=_empty_schema_changes(before_descriptor, current_descriptor, policy),
            row_count_before=before_descriptor.row_count,
            row_count_current=current_descriptor.row_count,
        )

    schema = _schema_view(before_descriptor, current_descriptor, policy)
    schema_changes = _schema_changes_from_view(schema, policy)
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
    policy: _ComparisonTablePolicy,
    *,
    added: bool,
    artifact_scope: ArtifactScope,
) -> ComparisonTableFact:
    if descriptor is None:
        raise StandardComparisonError("TABLE_DESCRIPTOR_MISSING")
    selected = tuple(
        canonicalize_identifier(column.name)
        for column in descriptor.columns
    )
    schema_changes = ComparisonSchemaChanges(
        current_only_columns=selected if added else (),
        before_only_columns=() if added else selected,
        selected_columns=selected,
        effective_compare_key_current=policy.effective_key_current if added else (),
        effective_compare_key_before=()
        if added
        else policy.effective_key_before,
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
    identity_columns = (
        policy.effective_key_current if added else policy.effective_key_before
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


def _compare_non_record_role(task: Any, policy: _ComparisonTablePolicy) -> ComparisonTableFact:
    before = task.before_descriptor
    current = task.current_descriptor
    if before is None or current is None:
        descriptor = current if current is not None else before
        if descriptor is None:
            raise StandardComparisonError("TABLE_TASK_HAS_NO_SIDE")
        added = before is None
        selected = tuple(sorted(_column_map(descriptor)))
        key = policy.effective_key_current if added else policy.effective_key_before
        return ComparisonTableFact(
            table_name=task.table_name,
            status=ComparisonTableStatus.ADDED_TABLE if added else ComparisonTableStatus.DELETED_TABLE,
            before_descriptor=before,
            current_descriptor=current,
            schema_changes=ComparisonSchemaChanges(
                before_only_columns=() if added else selected,
                current_only_columns=selected if added else (),
                selected_columns=selected,
                effective_compare_key_before=() if added else key,
                effective_compare_key_current=key if added else (),
            ),
            row_count_before=None if before is None else before.row_count,
            row_count_current=None if current is None else current.row_count,
            content_changed=True,
        )

    schema = _schema_view(before, current, policy)
    schema_changed = before.business_schema_digest != current.business_schema_digest
    content_changed = (
        schema_changed
        or before.row_count != current.row_count
        or before.raw_content_digest != current.raw_content_digest
    )
    return ComparisonTableFact(
        table_name=task.table_name,
        status=(
            ComparisonTableStatus.SCHEMA_ONLY_CHANGED
            if schema_changed
            else ComparisonTableStatus.UNCHANGED
        ),
        before_descriptor=before,
        current_descriptor=current,
        schema_changes=_schema_changes_from_view(schema, policy),
        row_count_before=before.row_count,
        row_count_current=current.row_count,
        diagnostics=("BUSINESS_SCHEMA_CHANGED",) if schema_changed else (),
        content_changed=content_changed,
    )


def _compare_keyed(
    table_name: str,
    before_descriptor: SnapshotTableDescriptor,
    current_descriptor: SnapshotTableDescriptor,
    before_rows: tuple[_EncodedRow, ...],
    current_rows: tuple[_EncodedRow, ...],
    schema: _SchemaView,
    policy: _ComparisonTablePolicy,
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
        if column not in schema.before_key
        and column not in schema.incompatible
        and column not in policy.compare_excluded_columns
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
    content_changed = (
        not records
        and not schema_diagnostics
        and _ignored_values_changed(before_descriptor, current_descriptor, policy)
    )
    if not records and not schema_diagnostics:
        status = ComparisonTableStatus.UNCHANGED
    return ComparisonTableFact(
        table_name=table_name,
        status=status,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        schema_changes=_schema_changes_from_view(schema, policy),
        row_count_before=before_descriptor.row_count,
        row_count_current=current_descriptor.row_count,
        row_added_count=len(added),
        row_deleted_count=len(deleted),
        row_modified_count=modified,
        suppressed_added_count=len(added) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        suppressed_deleted_count=len(deleted) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        records=tuple(sorted(records, key=_record_sort_key)),
        diagnostics=tuple(schema_diagnostics),
        content_changed=content_changed,
    )


def _compare_keyless(
    table_name: str,
    before_descriptor: SnapshotTableDescriptor,
    current_descriptor: SnapshotTableDescriptor,
    before_rows: tuple[_EncodedRow, ...],
    current_rows: tuple[_EncodedRow, ...],
    schema: _SchemaView,
    policy: _ComparisonTablePolicy,
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
            schema_changes=_schema_changes_from_view(schema, policy),
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
    content_changed = (
        not added
        and not deleted
        and not schema_diagnostics
        and _ignored_values_changed(before_descriptor, current_descriptor, policy)
    )
    if schema_diagnostics:
        status = ComparisonTableStatus.SCHEMA_CHANGED
    return ComparisonTableFact(
        table_name=table_name,
        status=status,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
            schema_changes=_schema_changes_from_view(schema, policy),
        row_count_before=before_descriptor.row_count,
        row_count_current=current_descriptor.row_count,
        row_added_count=len(added),
        row_deleted_count=len(deleted),
        suppressed_added_count=len(added) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        suppressed_deleted_count=len(deleted) if artifact_scope is ArtifactScope.UPDATE_ONLY else 0,
        records=tuple(sorted(records, key=_record_sort_key)),
        diagnostics=tuple(schema_diagnostics),
        content_changed=content_changed,
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
                "compare_excluded_columns": list(task.policy.compare_excluded_columns),
                "keyless_policy": task.policy.keyless_policy.value,
                "policy_version": task.policy.policy_version,
                "comparison_role": task.policy.comparison_role,
                "effective_key_before": list(task.policy.effective_key_before),
                "effective_key_current": list(task.policy.effective_key_current),
                "ordered_policy": _ordered_policy_payload(task.policy.ordered_policy),
            }
        )
    envelope = {
        "kind": "comparison",
        "algorithm_version": STANDARD_COMPARISON_ALGORITHM_VERSION,
        "before_snapshot_digest": plan.before.snapshot.snapshot_digest.value,
        "current_snapshot_digest": plan.current.snapshot.snapshot_digest.value,
        "comparison_options": [[key, value] for key, value in plan.options],
        "contract_versions": [[key, value] for key, value in plan.contract_versions],
        "ruleset_digest": _required_ruleset_digest(plan),
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
        comparison_mode=plan.mode,
        direction=COMPARISON_DIRECTION,
        summary=summary,
        tables=tables,
        diagnostics=diagnostics,
    )


def _required_ruleset_digest(plan: ComparisonPlan) -> str:
    digest = plan.rule_set.ruleset_digest
    if digest is None:
        raise StandardComparisonError("COMPARISON_RULESET_DIGEST_MISSING")
    return digest.value


def _summary(tables: tuple[ComparisonTableFact, ...]) -> ComparisonSummary:
    unchanged = sum(
        item.status is ComparisonTableStatus.UNCHANGED and not item.content_changed
        for item in tables
    )
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
        item.status in {ComparisonTableStatus.UNCHANGED, ComparisonTableStatus.BUSINESS_EQUIVALENT}
        and not item.content_changed
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


from gateway_backend.capabilities.comparison.row_encoding import (  # noqa: E402
    _declared_type as _declared_type,
)

__all__ = [
    "COMPARISON_DIRECTION",
    "STANDARD_COMPARISON_ALGORITHM_VERSION",
    "StandardComparisonError",
    "compare_plan",
    "_declared_type",
]

