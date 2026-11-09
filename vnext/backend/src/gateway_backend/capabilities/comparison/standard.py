"""Metadata facts and comparison envelope for the native row kernels."""

from __future__ import annotations

from typing import Any

from gateway_shared_kernel import DigestRef, canonicalize_identifier, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.comparison.contracts import (
    ArtifactScope, ComparisonFacts, ComparisonPlan, ComparisonRecord,
    ComparisonRecordKind, ComparisonSchemaChanges, ComparisonSummary,
    ComparisonTableFact, ComparisonTableStatus, PairResultStatus,
    SchemaEvolution, _ComparisonTablePolicy,
)
from gateway_backend.capabilities.comparison.errors import StandardComparisonError
from gateway_backend.capabilities.comparison.row_encoding import (
    _can_table_early_exit, _column_map, _empty_schema_changes,
    _ordered_policy_payload, _schema_changes_from_view,
    _schema_diagnostics, _schema_only_fact, _schema_view,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    COMPARISON_PROJECTION_CONTRACT_VERSION, SCALAR_ENCODING_VERSION,
    SnapshotTable, SnapshotTableDescriptor,
)

COMPARISON_DIRECTION = "BEFORE_TO_CURRENT"
STANDARD_COMPARISON_ALGORITHM_VERSION = "standard-reference/v1"


def _compare_task_metadata(task: Any) -> ComparisonTableFact:
    if type(task.table_name) is not str:
        raise StandardComparisonError("TABLE_TASK_INVALID")
    policy = task.policy
    if type(policy) is not _ComparisonTablePolicy:
        raise StandardComparisonError("TABLE_POLICY_MISSING")
    if policy.comparison_role in {"BROWSE_ONLY", "SNAPSHOT_ONLY"}:
        return _compare_non_record_role(task, policy)
    if policy.ordered_policy is not None:
        from gateway_backend.capabilities.comparison.ordered import _compare_single_side_ordered

        return _compare_single_side_ordered(task)
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
    if not schema.selected and schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED:
        return ComparisonTableFact(
            table_name=task.table_name,
            status=ComparisonTableStatus.UNCHANGED,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            schema_changes=schema_changes,
            row_count_before=before_descriptor.row_count,
            row_count_current=current_descriptor.row_count,
            content_changed=before_descriptor.row_count != current_descriptor.row_count,
        )
    if not schema.selected:
        return _schema_only_fact(
            task.table_name,
            before_descriptor,
            current_descriptor,
            schema_changes,
            schema_diagnostics,
        )

    raise StandardComparisonError("METADATA_ROUTE_REQUIRES_NATIVE_ROWS")

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
    selected = tuple(sorted(canonicalize_identifier(column.name) for column in descriptor.columns))
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
    return ComparisonTableFact(
        table_name=table_name,
        status=ComparisonTableStatus.ADDED_TABLE if added else ComparisonTableStatus.DELETED_TABLE,
        before_descriptor=None if added else descriptor,
        current_descriptor=descriptor if added else None,
        schema_changes=schema_changes,
        row_count_before=None if added else descriptor.row_count,
        row_count_current=descriptor.row_count if added else None,
        row_added_count=0,
        row_deleted_count=0,
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
    schema_changes = _schema_changes_from_view(schema, policy)
    schema_changed = (
        before.business_schema_digest != current.business_schema_digest
        and schema_changes.schema_evolution is not SchemaEvolution.COLUMNS_ADDED
    )
    content_changed = (
        schema_changed
        or before.row_count != current.row_count
        or (
            schema_changes.schema_evolution is not SchemaEvolution.COLUMNS_ADDED
            and before.raw_content_digest != current.raw_content_digest
        )
    )
    if schema_changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED:
        raise StandardComparisonError("METADATA_ROLE_REQUIRES_NATIVE_ROWS")
    return ComparisonTableFact(
        table_name=task.table_name,
        status=(
            ComparisonTableStatus.SCHEMA_ONLY_CHANGED
            if schema_changed
            else ComparisonTableStatus.UNCHANGED
        ),
        before_descriptor=before,
        current_descriptor=current,
        schema_changes=schema_changes,
        row_count_before=before.row_count,
        row_count_current=current.row_count,
        diagnostics=("BUSINESS_SCHEMA_CHANGED",) if schema_changed else (),
        content_changed=content_changed,
    )

def _build_facts(
    plan: ComparisonPlan,
    tables: tuple[ComparisonTableFact, ...],
    *,
    core_digest: DigestRef,
) -> ComparisonFacts:
    summary = _summary(tables)
    facts_core_digest = core_digest
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

