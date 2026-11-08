"""Bounded, flow-neutral projection of R5 comparison facts for Risk."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterator, Mapping
from contextlib import closing, nullcontext
from time import perf_counter

from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonTableFact,
    ComparisonTableStatus,
    SchemaEvolution,
    OrderedRecordKind,
    OrderedStatus,
)
from gateway_backend.capabilities.risk_evaluation.contracts import (
    RiskFacts,
    RiskOptionsPairs,
    RiskRowChangeStats,
    RiskScope,
    RiskOperationPort,
)


COMPOSITE_SIGNAL_POINT_TABLE = "composite_signal_point"
UNSUPPORTED_TARGET_PREFIX = "RISK_UNCOVERED_TARGET:"
COMPARISON_FAILED_TOKEN = "COMPARISON_FAILED"
ORDERED_UNSUPPORTED_TOKEN = "ORDERED_DIFF_UNSUPPORTED"
KEY_DEGRADED_TOKEN = "KEY_DEGRADED"


@dataclass(frozen=True, slots=True)
class RiskRecord:
    record_kind: ComparisonRecordKind
    row_identity: DigestRef | None
    changed_columns: tuple[str, ...]


class RiskRecordView:
    """Reopen the in-memory facts-order minimum projection for each risk rule."""

    def __init__(
        self, handle: object, metrics: dict[str, float] | None = None,
        operation: RiskOperationPort | None = None,
    ) -> None:
        self._handle = handle
        self._metrics = metrics
        self._operation = operation

    def __bool__(self) -> bool:
        summary = getattr(self._handle, "family_summary")
        return bool(summary("STANDARD")[0])

    def __iter__(self) -> Iterator[RiskRecord]:
        reader = getattr(self._handle, "risk_record_batches")()
        with closing(reader):
            for batch in reader:
                operation = self._operation
                if operation is not None:
                    operation.checkpoint()
                # One Arrow→Python conversion per needed column/batch. The
                # full values/field changes never cross into Risk.
                scratch = (nullcontext() if operation is None else operation.memory.reserve(
                    8192 + batch.nbytes * 16 + batch.num_rows * 512,
                ))
                with scratch:
                    started = perf_counter()
                    columns = batch.to_pydict()
                    records = [RiskRecord(
                        record_kind=ComparisonRecordKind(kind),
                        row_identity=None if identity is None else DigestRef("sha256:" + identity.hex()),
                        changed_columns=tuple(changed),
                    ) for kind, identity, changed in zip(
                        columns["record_kind"], columns["row_identity"],
                        columns["changed_columns"], strict=True,
                    )]
                    if self._metrics is not None:
                        self._metrics["necessary_arrow_conversion_seconds"] = (
                            self._metrics.get("necessary_arrow_conversion_seconds", 0.0)
                            + perf_counter() - started
                        )
                    yield from records


@dataclass(frozen=True, slots=True)
class ExtractedRiskFacts:
    comparison_facts: RiskFacts
    table_fact: ComparisonTableFact
    records: tuple[ComparisonRecord, ...] | RiskRecordView
    ordered_unsupported: bool
    composite_signal: bool
    comparison_failed: bool
    uncovered_targets: tuple[str, ...]


def extract_risk_facts(
    facts: ComparisonFacts,
    requested_tables: tuple[str, ...] | None,
    record_views: Mapping[str, object] | None = None,
    record_view_metrics: dict[str, float] | None = None,
    operation: RiskOperationPort | None = None,
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
        view = None if record_views is None else record_views.get(table.table_name)
        records: tuple[ComparisonRecord, ...] | RiskRecordView = (
            table.records if view is None else RiskRecordView(view, record_view_metrics, operation)
        )
        scope = _risk_scope(table, key_degraded, ordered_unsupported, bool(records))
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
                records=records,
                ordered_unsupported=ordered_unsupported,
                composite_signal=table.table_name == COMPOSITE_SIGNAL_POINT_TABLE,
                comparison_failed=comparison_failed,
                uncovered_targets=uncovered_targets,
            )
        )
    return tuple(result)


def has_visible_change(item: ExtractedRiskFacts) -> bool:
    table = item.table_fact
    schema_evolution = table.schema_changes.schema_evolution
    return bool(
        table.status
        not in {ComparisonTableStatus.UNCHANGED, ComparisonTableStatus.BUSINESS_EQUIVALENT}
        or schema_evolution in {SchemaEvolution.COLUMNS_REMOVED, SchemaEvolution.INCOMPATIBLE}
        or table.schema_changes.effective_compare_key_changed
        or table.row_added_count
        or table.row_deleted_count
        or table.row_modified_count
        or item.records
        or item.ordered_unsupported
        or item.uncovered_targets
    )


def record_kind_name(record: ComparisonRecord | RiskRecord) -> str | None:
    return {
        ComparisonRecordKind.ROW_ADDED: "ROW_ADDED",
        ComparisonRecordKind.ROW_DELETED: "ROW_DELETED",
        ComparisonRecordKind.ROW_MODIFIED: "ROW_MODIFIED",
    }.get(record.record_kind)


def _risk_scope(
    table: ComparisonTableFact,
    key_degraded: bool,
    ordered_unsupported: bool,
    has_records: bool,
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
    if table.row_added_count or table.row_deleted_count or table.row_modified_count or has_records:
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
