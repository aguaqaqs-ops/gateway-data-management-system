from __future__ import annotations

from collections.abc import Sequence

from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ..comparison.models import (
    ComparisonFacts,
    ComparisonOrderedExtension,
    ComparisonRecord,
    ComparisonRecordsClosure,
    ComparisonTableFact,
    ComparisonTableStatus,
)
from ..comparison.ordered.models import OrderedRecord
from .models import RiskFacts, RiskRowChangeStats, RiskScope, RiskSemanticFacts, RiskRecordsAccess


def extract_risk_facts(
    comparison_facts: ComparisonFacts,
    *,
    requested_tables: Sequence[str] = (),
    records_access: RiskRecordsAccess | None = None,
) -> tuple[RiskFacts, ...]:
    if not isinstance(comparison_facts, ComparisonFacts):
        raise TypeError("comparison_facts must be a ComparisonFacts")
    requested = {
        canonical_identifier(table_name)
        for table_name in requested_tables
        if canonical_identifier(table_name)
    }
    records_ref = comparison_facts.records_ref
    if records_access is not None:
        access_ref = records_access.get_records_closure()
        if access_ref is not None:
            records_ref = access_ref

    facts: list[RiskFacts] = []
    for table_fact in comparison_facts.tables:
        if not isinstance(table_fact, ComparisonTableFact):
            raise TypeError("comparison_facts.tables must contain ComparisonTableFact values")
        if requested and table_fact.table_name not in requested:
            continue
        facts.append(
            _risk_fact_for_table(
                comparison_digest=comparison_facts.comparison_digest,
                table_fact=table_fact,
                records_ref=records_ref,
                standard_records=_standard_records_for_table(records_access, table_fact),
                ordered_records=_ordered_records_for_table(records_access, table_fact),
            )
        )
    return tuple(facts)


def _risk_fact_for_table(
    *,
    comparison_digest,
    table_fact: ComparisonTableFact,
    records_ref: ComparisonRecordsClosure | None,
    standard_records: tuple[ComparisonRecord, ...],
    ordered_records: tuple[OrderedRecord, ...],
) -> RiskFacts:
    risk_scope = _risk_scope_for_table(table_fact)
    row_change_stats = _row_change_stats(table_fact)
    semantic_facts = _semantic_facts_for_table(table_fact, risk_scope=risk_scope)
    before_row_count, after_row_count = _row_counts(table_fact)
    return RiskFacts(
        comparison_digest=comparison_digest,
        table_name=table_fact.table_name,
        table_status=table_fact.status,
        risk_scope=risk_scope,
        schema_changes=table_fact.schema_changes,
        row_change_stats=row_change_stats,
        before_row_count=before_row_count,
        after_row_count=after_row_count,
        degraded=table_fact.status is ComparisonTableStatus.DEGRADED,
        degraded_reasons=_degraded_reasons(table_fact.diagnostics),
        records_ref=records_ref,
        standard_records=standard_records,
        ordered_extension=table_fact.ordered_extension,
        ordered_records=ordered_records,
        semantic_facts=semantic_facts,
        diagnostics=table_fact.diagnostics,
    )


def _risk_scope_for_table(table_fact: ComparisonTableFact) -> RiskScope:
    if table_fact.status in {
        ComparisonTableStatus.ADDED_TABLE,
        ComparisonTableStatus.DELETED_TABLE,
        ComparisonTableStatus.SCHEMA_CHANGED,
        ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
    }:
        return RiskScope.TABLE
    ordered_extension = table_fact.ordered_extension
    if ordered_extension is not None:
        if _ordered_extension_is_degraded(ordered_extension):
            return RiskScope.DEGRADED_TABLE
        return RiskScope.ORDERED_TABLE
    if table_fact.status is ComparisonTableStatus.DEGRADED:
        return RiskScope.DEGRADED_TABLE
    return RiskScope.STANDARD_ROWS


def _row_change_stats(table_fact: ComparisonTableFact) -> RiskRowChangeStats | None:
    if table_fact.row_change_stats is not None:
        payload = table_fact.row_change_stats
        row_added_count = _optional_int(payload.get("inserted_count"))
        row_deleted_count = _optional_int(payload.get("deleted_count"))
        row_modified_count = _optional_int(payload.get("updated_count"))
        return RiskRowChangeStats(
            row_added_count=row_added_count,
            row_deleted_count=row_deleted_count,
            row_modified_count=row_modified_count,
            raw_inserted_count=_optional_int(payload.get("raw_inserted_count")),
            raw_deleted_count=_optional_int(payload.get("raw_deleted_count")),
            raw_updated_count=_optional_int(payload.get("raw_updated_count")),
            suppressed_inserted_count=_optional_int(payload.get("suppressed_inserted_count")),
            suppressed_deleted_count=_optional_int(payload.get("suppressed_deleted_count")),
            artifact_scope=_optional_str(payload.get("artifact_scope")),
            suppression_reason=_optional_str(payload.get("suppression_reason")),
        )
    if table_fact.row_counts is None:
        return None
    before_count, current_count = table_fact.row_counts
    if before_count is None or current_count is None:
        return None
    if before_count == current_count:
        return None
    if current_count > before_count:
        return RiskRowChangeStats(row_added_count=current_count - before_count)
    return RiskRowChangeStats(row_deleted_count=before_count - current_count)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("row_change_stats counts must be non-negative integers")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("row_change_stats string values must be non-empty strings")
    return value


def _row_counts(table_fact: ComparisonTableFact) -> tuple[int | None, int | None]:
    if table_fact.row_counts is None:
        return (None, None)
    before_count, current_count = table_fact.row_counts
    return before_count, current_count


def _semantic_facts_for_table(
    table_fact: ComparisonTableFact,
    *,
    risk_scope: RiskScope,
) -> RiskSemanticFacts | None:
    if risk_scope is not RiskScope.ORDERED_TABLE:
        return None
    return RiskSemanticFacts(
        kind="ORDERED_TABLE",
        payload={
            "table_name": table_fact.table_name,
            "status": table_fact.status.value,
        },
        semantic_contract_version="backend-vnext/risk-semantic/v1",
    )


def _ordered_records_for_table(
    records_access: RiskRecordsAccess | None,
    table_fact: ComparisonTableFact,
) -> tuple[OrderedRecord, ...]:
    if records_access is None or table_fact.ordered_extension is None:
        return ()
    records = records_access.get_ordered_records(table_fact.table_name)
    if records is None:
        return ()
    if not isinstance(records, tuple):
        records = tuple(records)
    normalized: list[OrderedRecord] = []
    for record in records:
        if not isinstance(record, OrderedRecord):
            raise TypeError("get_ordered_records must return OrderedRecord values")
        normalized.append(record)
    return tuple(normalized)


def _standard_records_for_table(
    records_access: RiskRecordsAccess | None,
    table_fact: ComparisonTableFact,
) -> tuple[ComparisonRecord, ...]:
    if records_access is None or table_fact.ordered_extension is not None:
        return ()
    records = records_access.get_standard_records(table_fact.table_name)
    if records is None:
        return ()
    if not isinstance(records, tuple):
        records = tuple(records)
    normalized: list[ComparisonRecord] = []
    for record in records:
        if not isinstance(record, ComparisonRecord):
            raise TypeError("get_standard_records must return ComparisonRecord values")
        normalized.append(record)
    return tuple(normalized)


def _ordered_extension_is_degraded(ordered_extension: ComparisonOrderedExtension) -> bool:
    return (
        ordered_extension.table_processing_mode == "DEGRADED"
        or ordered_extension.replay_guarantee == "UNSUPPORTED"
    )


def _degraded_reasons(diagnostics: tuple[DiagnosticRecord, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    seen: set[str] = set()
    for diagnostic in diagnostics:
        reason = diagnostic.details.get("reason") if diagnostic.details else None
        candidate = reason if isinstance(reason, str) and reason.strip() else diagnostic.code
        if candidate in seen:
            continue
        seen.add(candidate)
        reasons.append(candidate)
    return tuple(reasons)
