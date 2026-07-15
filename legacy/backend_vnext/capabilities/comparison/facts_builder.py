from __future__ import annotations

from collections.abc import Mapping, Sequence

from ...artifacts import ArtifactRef
from ...core.diagnostics import DiagnosticRecord
from ...core.digests import DigestRef
from ...core.identifiers import canonical_identifier
from ..snapshot_materialization.models import SnapshotTableDescriptor
from .digest import build_comparison_table_fact_digest
from .models import (
    COMPARISON_RECORDS_CLOSURE_CONTRACT_VERSION,
    ComparisonOptions,
    ComparisonRecordKind,
    ComparisonRecordsClosure,
    ComparisonRecordsClosureMember,
    ComparisonStatus,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTableStatus,
)
from .ordered.models import OrderedRecordKind


def _build_table_fact(
    *,
    table_name: str,
    status: ComparisonTableStatus,
    projection_schema: object,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    row_counts: tuple[int | None, int | None] | None,
    row_change_stats: Mapping[str, object] | None = None,
    schema_changes: Mapping[str, object] | None = None,
    before_projection_logical_digest: DigestRef | None = None,
    current_projection_logical_digest: DigestRef | None = None,
    records_ref: ArtifactRef | None = None,
    diagnostics: tuple[DiagnosticRecord, ...] = (),
) -> ComparisonTableFact:
    return ComparisonTableFact(
        table_name=table_name,
        status=status,
        before_descriptor=_descriptor_payload(before_descriptor),
        current_descriptor=_descriptor_payload(current_descriptor),
        projection_schema=projection_schema,  # type: ignore[arg-type]
        projection_schema_digest=getattr(projection_schema, "projection_schema_digest"),
        before_projection_logical_digest=before_projection_logical_digest,
        current_projection_logical_digest=current_projection_logical_digest,
        row_counts=row_counts,
        row_change_stats=row_change_stats,
        schema_changes=schema_changes,
        records_ref=records_ref,
        diagnostics=diagnostics,
    )


def _build_degraded_table_fact(
    *,
    table_name: str,
    projection_schema: object,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    row_counts: tuple[int | None, int | None] | None,
    diagnostics: tuple[DiagnosticRecord, ...],
    reason: str,
) -> ComparisonTableFact:
    degraded_diagnostics = diagnostics + (
        DiagnosticRecord(
            code="comparison.table.degraded",
            message="table comparison degraded",
            phase="compare",
            severity="WARNING",
            details={"table_name": table_name, "reason": reason},
        ),
    )
    return _build_table_fact(
        table_name=table_name,
        status=ComparisonTableStatus.DEGRADED,
        projection_schema=projection_schema,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        row_counts=row_counts,
        schema_changes=_schema_changes_payload(
            table_schema=projection_schema,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
        ),
        diagnostics=degraded_diagnostics,
    )


def _descriptor_payload(descriptor: SnapshotTableDescriptor | None) -> Mapping[str, object] | None:
    if descriptor is None:
        return None
    return {
        "table_name": descriptor.table_name,
        "display_table_name": descriptor.display_table_name,
        "table_role": descriptor.table_role,
        "columns": [
            {
                "name": column.name,
                "display_name": column.display_name,
                "scalar_type": column.scalar_type,
                "nullable": column.nullable,
            }
            for column in descriptor.columns
        ],
        "compare_key_columns": list(descriptor.compare_key_columns),
        "row_count": descriptor.row_count,
        "materialization_stage": descriptor.materialization_stage,
        "source_ddl_digest": descriptor.source_ddl_digest.to_payload() if descriptor.source_ddl_digest else None,
        "table_raw_sql_digest": descriptor.table_raw_sql_digest.to_payload() if descriptor.table_raw_sql_digest else None,
        "fast_row_digest": descriptor.fast_row_digest.to_payload() if descriptor.fast_row_digest else None,
        "canonical_artifact_ref": descriptor.canonical_artifact_ref,
        "previous_canonical_artifact_ref": descriptor.previous_canonical_artifact_ref,
        "compare_schema_digest": descriptor.compare_schema_digest.to_payload() if descriptor.compare_schema_digest else None,
        "raw_content_digest": descriptor.raw_content_digest.to_payload() if descriptor.raw_content_digest else None,
        "business_content_digest": descriptor.business_content_digest.to_payload() if descriptor.business_content_digest else None,
        "row_layout_digest": descriptor.row_layout_digest.to_payload() if descriptor.row_layout_digest else None,
        "table_ruleset_version": descriptor.table_ruleset_version,
        "row_materialization_profile": descriptor.row_materialization_profile,
        "scalar_encoding_version": descriptor.scalar_encoding_version,
        "degraded_reason": descriptor.degraded_reason,
    }


def _descriptor_compare_key(descriptor: SnapshotTableDescriptor | None) -> tuple[str, ...]:
    if descriptor is None:
        return ()
    return tuple(descriptor.compare_key_columns)


def _descriptor_materialization_digest(descriptor: SnapshotTableDescriptor | None) -> DigestRef | None:
    if descriptor is None:
        return None
    return descriptor.materialization_digest


def _descriptor_row_counts(
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
) -> tuple[int | None, int | None] | None:
    if before_descriptor is None and current_descriptor is None:
        return None
    return (
        None if before_descriptor is None else before_descriptor.row_count,
        None if current_descriptor is None else current_descriptor.row_count,
    )


def _schema_changes_payload(
    *,
    table_schema: object,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
) -> Mapping[str, object]:
    return {
        "before_only_columns": list(getattr(table_schema, "before_only_columns", ())),
        "current_only_columns": list(getattr(table_schema, "current_only_columns", ())),
        "selected_columns": list(getattr(table_schema, "selected_columns", ())),
        "effective_compare_key_before": list(_descriptor_compare_key(before_descriptor)),
        "effective_compare_key_current": list(_descriptor_compare_key(current_descriptor)),
        "effective_compare_key_changed": _descriptor_compare_key(before_descriptor) != _descriptor_compare_key(current_descriptor),
    }


def _build_summary(table_results: Sequence[object], diagnostics: Sequence[DiagnosticRecord]) -> ComparisonSummary:
    status_counts = {
        ComparisonTableStatus.UNCHANGED: 0,
        ComparisonTableStatus.BUSINESS_EQUIVALENT: 0,
        ComparisonTableStatus.ADDED_TABLE: 0,
        ComparisonTableStatus.DELETED_TABLE: 0,
        ComparisonTableStatus.MODIFIED: 0,
        ComparisonTableStatus.SCHEMA_CHANGED: 0,
        ComparisonTableStatus.SCHEMA_ONLY_CHANGED: 0,
        ComparisonTableStatus.DEGRADED: 0,
    }
    row_added_count = 0
    row_deleted_count = 0
    row_modified_count = 0
    for result in table_results:
        status_counts[result.table_fact.status] += 1
        if result.table_fact.status in {
            ComparisonTableStatus.UNCHANGED,
            ComparisonTableStatus.BUSINESS_EQUIVALENT,
        }:
            continue
        if result.table_fact.status == ComparisonTableStatus.DEGRADED:
            continue
        if result.table_fact.records_ref is not None and result.records:
            for record in result.records:
                record_kind = getattr(record, "record_kind", None)
                record_kind_value = record_kind.value if hasattr(record_kind, "value") else str(record_kind)
                if record_kind_value in {
                    ComparisonRecordKind.ROW_ADDED.value,
                    OrderedRecordKind.ORDERED_ROW_ADDED.value,
                }:
                    row_added_count += 1
                elif record_kind_value in {
                    ComparisonRecordKind.ROW_DELETED.value,
                    OrderedRecordKind.ORDERED_ROW_DELETED.value,
                }:
                    row_deleted_count += 1
                elif record_kind_value in {
                    ComparisonRecordKind.ROW_MODIFIED.value,
                    OrderedRecordKind.ORDERED_ROW_MODIFIED.value,
                    OrderedRecordKind.ORDERED_ROW_MOVED.value,
                    OrderedRecordKind.ORDERED_POSITION_CHANGED.value,
                }:
                    row_modified_count += 1
        elif result.table_fact.status == ComparisonTableStatus.ADDED_TABLE:
            row_added_count += _row_count_from_table_fact(result.table_fact)
        elif result.table_fact.status == ComparisonTableStatus.DELETED_TABLE:
            row_deleted_count += _row_count_from_table_fact(result.table_fact)
    if status_counts[ComparisonTableStatus.MODIFIED] > 0 or status_counts[ComparisonTableStatus.ADDED_TABLE] > 0 or status_counts[ComparisonTableStatus.DELETED_TABLE] > 0 or status_counts[ComparisonTableStatus.SCHEMA_CHANGED] > 0 or status_counts[ComparisonTableStatus.SCHEMA_ONLY_CHANGED] > 0:
        summary_status = ComparisonStatus.CHANGED
    elif status_counts[ComparisonTableStatus.BUSINESS_EQUIVALENT] > 0:
        summary_status = ComparisonStatus.BUSINESS_EQUIVALENT
    else:
        summary_status = ComparisonStatus.UNCHANGED
    return ComparisonSummary(
        status=summary_status,
        table_count=len(table_results),
        unchanged_table_count=status_counts[ComparisonTableStatus.UNCHANGED],
        changed_table_count=
        status_counts[ComparisonTableStatus.BUSINESS_EQUIVALENT]
        + status_counts[ComparisonTableStatus.ADDED_TABLE]
        + status_counts[ComparisonTableStatus.DELETED_TABLE]
        + status_counts[ComparisonTableStatus.MODIFIED]
        + status_counts[ComparisonTableStatus.SCHEMA_CHANGED]
        + status_counts[ComparisonTableStatus.SCHEMA_ONLY_CHANGED],
        added_table_count=status_counts[ComparisonTableStatus.ADDED_TABLE],
        deleted_table_count=status_counts[ComparisonTableStatus.DELETED_TABLE],
        schema_changed_table_count=
        status_counts[ComparisonTableStatus.SCHEMA_CHANGED]
        + status_counts[ComparisonTableStatus.SCHEMA_ONLY_CHANGED],
        degraded_table_count=status_counts[ComparisonTableStatus.DEGRADED],
        row_added_count=row_added_count,
        row_deleted_count=row_deleted_count,
        row_modified_count=row_modified_count,
        diagnostics_count=len(diagnostics),
    )


def _summary_digest(summary: ComparisonSummary) -> DigestRef:
    return DigestRef.from_payload(
        {
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
        }
    )


def _build_facts_core_digest(
    *,
    before_snapshot_digest: DigestRef | str,
    current_snapshot_digest: DigestRef | str,
    comparison_contract_version: str,
    projection_contract_version: str,
    table_ruleset_version: str,
    scalar_encoding_version: str,
    table_ruleset_digest: DigestRef | str | None,
    requested_tables: Sequence[str],
    comparison_options: ComparisonOptions,
    summary: ComparisonSummary,
    table_results: Sequence[object],
    table_aliases: Sequence[object] = (),
) -> DigestRef:
    return DigestRef.from_payload(
        {
            "before_snapshot_digest": DigestRef.parse(str(before_snapshot_digest)).to_payload(),
            "current_snapshot_digest": DigestRef.parse(str(current_snapshot_digest)).to_payload(),
            "comparison_contract_version": comparison_contract_version,
            "projection_contract_version": projection_contract_version,
            "table_ruleset_version": table_ruleset_version,
            "scalar_encoding_version": scalar_encoding_version,
            "table_ruleset_digest": None if table_ruleset_digest is None else DigestRef.parse(str(table_ruleset_digest)).to_payload(),
            "table_aliases": [
                _alias_payload_for_digest(alias)
                for alias in table_aliases
            ],
            "requested_tables": tuple(canonical_identifier(table_name) for table_name in requested_tables),
            "comparison_options": comparison_options,
            "summary": _summary_digest(summary).to_payload(),
            "tables": [
                {
                    "table_name": result.table_fact.table_name,
                    "status": result.table_fact.status.value,
                    "table_fact_digest": build_comparison_table_fact_digest(
                        result.table_fact,
                        comparison_contract_version=comparison_contract_version,
                        projection_contract_version=projection_contract_version,
                        table_ruleset_version=table_ruleset_version,
                        scalar_encoding_version=scalar_encoding_version,
                    ).to_payload(),
                }
                for result in table_results
            ],
        }
    )


def _alias_payload_for_digest(alias: object) -> Mapping[str, object]:
    payload_for_digest = getattr(alias, "payload_for_digest", None)
    if callable(payload_for_digest):
        payload = payload_for_digest()
    elif isinstance(alias, Mapping):
        payload = alias
    else:
        raise TypeError("table_aliases must contain alias payloads")
    if not isinstance(payload, Mapping):
        raise TypeError("table alias payload must be a mapping")
    return dict(payload)


def _build_records_closure(
    *,
    comparison_digest: DigestRef,
    facts_core_digest: DigestRef,
    table_results: Sequence[object],
) -> ComparisonRecordsClosure | None:
    records: list[ComparisonRecordsClosureMember] = []
    for result in table_results:
        if result.records_ref is None:
            continue
        records_manifest_digest = result.records_ref.manifest_digest
        records_content_digest = result.records_ref.content_digest
        records.append(
            ComparisonRecordsClosureMember(
                table_name=result.table_fact.table_name,
                records_ref=result.records_ref,
                records_manifest_digest=records_manifest_digest,
                records_content_digest=records_content_digest,
                record_count=len(result.records),
            )
        )
    if not records:
        return None
    return ComparisonRecordsClosure(
        closure_contract_version=COMPARISON_RECORDS_CLOSURE_CONTRACT_VERSION,
        comparison_digest=comparison_digest,
        facts_core_digest=facts_core_digest,
        records=tuple(records),
    )


def _row_count_from_table_fact(table_fact: ComparisonTableFact) -> int:
    row_counts = table_fact.row_counts
    if row_counts is None:
        return 0
    left, right = row_counts
    if left is not None:
        return left
    if right is not None:
        return right
    return 0
