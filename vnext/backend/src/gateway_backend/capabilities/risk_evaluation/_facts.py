"""Bounded, flow-neutral projection of R5 comparison facts for Risk."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonTableFact,
    ComparisonTableStatus,
    OrderedRecordKind,
    OrderedStatus,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RiskFacts,
    RiskOptionsPairs,
    RiskRowChangeStats,
    RiskScope,
)


COMPOSITE_SIGNAL_POINT_TABLE = "composite_signal_point"
UNSUPPORTED_TARGET_PREFIX = "RISK_UNCOVERED_TARGET:"
COMPARISON_FAILED_TOKEN = "COMPARISON_FAILED"
ORDERED_UNSUPPORTED_TOKEN = "ORDERED_DIFF_UNSUPPORTED"
KEY_DEGRADED_TOKEN = "KEY_DEGRADED"


@dataclass(frozen=True, slots=True)
class ExtractedRiskFacts:
    comparison_facts: RiskFacts
    table_fact: ComparisonTableFact
    records: tuple[ComparisonRecord, ...]
    ordered_unsupported: bool
    composite_signal: bool
    comparison_failed: bool
    uncovered_targets: tuple[str, ...]


def extract_risk_facts(
    facts: ComparisonFacts,
    requested_tables: tuple[str, ...] | None,
) -> tuple[ExtractedRiskFacts, ...]:
    requested = None if requested_tables is None else frozenset(requested_tables)
    result: list[ExtractedRiskFacts] = []
    for table in facts.tables:
        if requested is not None and table.table_name not in requested:
            continue
        table_diagnostics = tuple(facts.diagnostics) + tuple(table.diagnostics)
        ordered_unsupported = _ordered_unsupported(table, table_diagnostics)
        key_degraded = _key_degraded(table, table_diagnostics)
        comparison_failed = COMPARISON_FAILED_TOKEN in table_diagnostics
        uncovered_targets = tuple(
            sorted(
                diagnostic.removeprefix(UNSUPPORTED_TARGET_PREFIX)
                for diagnostic in table_diagnostics
                if diagnostic.startswith(UNSUPPORTED_TARGET_PREFIX)
            )
        )
        scope = _risk_scope(table, key_degraded, ordered_unsupported)
        degraded_reasons = tuple(
            sorted(
                reason
                for reason, enabled in (
                    (KEY_DEGRADED_TOKEN, key_degraded),
                    (ORDERED_UNSUPPORTED_TOKEN, ordered_unsupported),
                )
                if enabled
            )
        )
        semantic_facts: RiskOptionsPairs | None = None
        if table.table_name == COMPOSITE_SIGNAL_POINT_TABLE:
            semantic_facts = (("composite_signal_point", True),)
        result.append(
            ExtractedRiskFacts(
                comparison_facts=RiskFacts(
                    comparison_digest=facts.comparison_digest,
                    table_name=table.table_name,
                    table_status=table.status,
                    risk_scope=scope,
                    schema_changes=table.schema_changes,
                    row_change_stats=RiskRowChangeStats(
                        row_added_count=table.row_added_count,
                        row_deleted_count=table.row_deleted_count,
                        row_modified_count=table.row_modified_count,
                    ),
                    degraded=table.status is ComparisonTableStatus.DEGRADED
                    or key_degraded
                    or ordered_unsupported,
                    degraded_reasons=degraded_reasons,
                    records_ref=facts.records_ref,
                    semantic_facts=semantic_facts,
                    diagnostics=_bounded_diagnostics(table_diagnostics),
                ),
                table_fact=table,
                records=table.records,
                ordered_unsupported=ordered_unsupported,
                composite_signal=table.table_name == COMPOSITE_SIGNAL_POINT_TABLE,
                comparison_failed=comparison_failed,
                uncovered_targets=uncovered_targets,
            )
        )
    return tuple(result)


def has_visible_change(item: ExtractedRiskFacts) -> bool:
    table = item.table_fact
    return bool(
        table.status
        not in {ComparisonTableStatus.UNCHANGED, ComparisonTableStatus.BUSINESS_EQUIVALENT}
        or table.schema_changes.before_only_columns
        or table.schema_changes.current_only_columns
        or table.schema_changes.incompatible_columns
        or table.schema_changes.effective_compare_key_changed
        or table.row_added_count
        or table.row_deleted_count
        or table.row_modified_count
        or table.records
        or item.ordered_unsupported
        or item.uncovered_targets
    )


def record_kind_name(record: ComparisonRecord) -> str | None:
    return {
        ComparisonRecordKind.ROW_ADDED: "ROW_ADDED",
        ComparisonRecordKind.ROW_DELETED: "ROW_DELETED",
        ComparisonRecordKind.ROW_MODIFIED: "ROW_MODIFIED",
    }.get(record.record_kind)


def _risk_scope(
    table: ComparisonTableFact,
    key_degraded: bool,
    ordered_unsupported: bool,
) -> RiskScope:
    if table.status in {
        ComparisonTableStatus.ADDED_TABLE,
        ComparisonTableStatus.DELETED_TABLE,
        ComparisonTableStatus.SCHEMA_CHANGED,
        ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
    }:
        return RiskScope.TABLE
    if key_degraded or ordered_unsupported or table.status is ComparisonTableStatus.DEGRADED:
        return RiskScope.DEGRADED_TABLE
    if table.row_added_count or table.row_deleted_count or table.row_modified_count or table.records:
        return RiskScope.STANDARD_ROWS
    return RiskScope.TABLE


def _key_degraded(table: ComparisonTableFact, diagnostics: tuple[str, ...]) -> bool:
    return bool(
        table.status is ComparisonTableStatus.DEGRADED
        or table.schema_changes.effective_compare_key_changed
        or any(KEY_DEGRADED_TOKEN in diagnostic for diagnostic in diagnostics)
    )


def _ordered_unsupported(table: ComparisonTableFact, diagnostics: tuple[str, ...]) -> bool:
    extension = table.ordered_extension
    if extension is not None:
        if extension.status is OrderedStatus.DEGRADED:
            return True
        if any(record.record_kind is OrderedRecordKind.TABLE_DEGRADED for record in extension.records):
            return True
        if any(ORDERED_UNSUPPORTED_TOKEN in diagnostic for diagnostic in extension.diagnostics):
            return True
    return any(ORDERED_UNSUPPORTED_TOKEN in diagnostic for diagnostic in diagnostics)


def _bounded_diagnostics(diagnostics: tuple[str, ...]) -> tuple[str, ...]:
    # The execution layer applies the caller-selected byte/count budgets. Extraction only
    # removes exact duplicate strings so repeated upstream diagnostics cannot multiply work.
    return tuple(dict.fromkeys(diagnostics))
