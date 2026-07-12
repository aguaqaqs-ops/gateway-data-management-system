from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections import Counter
from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import TYPE_CHECKING

from ...artifacts import ArtifactRef, LocalArtifactStore, RecordsArtifact
from ...core.diagnostics import DiagnosticRecord
from ...core.digests import DigestRef
from ...core.identifiers import canonical_identifier
from ...formal_upload_benchmark import benchmark_elapsed_ms, log_formal_upload_benchmark_event
from ..snapshot_materialization.models import SnapshotTable, SnapshotTableDescriptor
from .digest import (
    ProjectionLogicalDigestParts,
    build_comparison_digest,
    build_comparison_table_fact_digest,
    build_projection_logical_digest,
    build_projection_logical_digest_from_parts,
)
from .facts_builder import (
    _build_degraded_table_fact,
    _build_facts_core_digest,
    _build_records_closure,
    _build_summary,
    _build_table_fact,
    _descriptor_compare_key,
    _descriptor_materialization_digest,
    _descriptor_payload,
    _descriptor_row_counts,
    _schema_changes_payload,
    _summary_digest,
)
from .models import (
    COMPARISON_DEFAULT_DIRECTION,
    ComparisonComputeInput,
    ComparisonComputeResult,
    ComparisonFacts,
    ComparisonPlan,
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonRole,
    ComparisonTableAlias,
    ComparisonTableAccessPolicy,
    ComparisonTableFact,
    ComparisonTableStatus,
    ProjectionTable,
    TableRulesetSnapshot,
    TableRulesetTableRule,
)
from .native_provider import compare_dolt_native_table
from .records_builder import (
    _build_records_artifact,
    _build_row_diff_records,
    _build_side_record,
    _index_projection_rows,
    _iter_projection_rows,
    _record_sort_key,
)
from .planner import (
    BROWSE_ONLY_PROVIDER,
    DOLT_NATIVE_PROVIDER,
    ORDERED_TABLE_COMPARE_PROVIDER,
    SKIPPED_PROVIDER,
    SNAPSHOT_TABLE_COMPARE_PROVIDER,
    SUMMARY_EARLY_EXIT_PROVIDER,
    ComparisonPlanner,
    _resolve_table_rule,
    _resolve_ruleset,
    _summary_table_map,
)
from .ordered import OrderedPreparedRowsCache, OrderedTableCompareInput, compare_ordered_table
from .ordered.policy import build_ordered_table_policy
from .projection import ProjectionBuilder, ProjectionRowsReader, build_projection_schema
from .ruleset_registry import TableRulesetRegistry


if TYPE_CHECKING:
    from ...cache.projection_table import ProjectionTableCache, ProjectionTableCacheKey


@dataclass(frozen=True, slots=True)
class ComparisonEngine:
    planner: ComparisonPlanner = field(default_factory=ComparisonPlanner)
    projection_builder: ProjectionBuilder = field(default_factory=ProjectionBuilder)
    projection_table_cache: ProjectionTableCache | None = None

    def plan(self, compute_input: ComparisonComputeInput) -> ComparisonPlan:
        return self.planner.plan(compute_input)

    def compare(
        self,
        compute_input: ComparisonComputeInput,
        *,
        records_store: LocalArtifactStore | None = None,
    ) -> ComparisonComputeResult:
        total_started_at = perf_counter()
        plan_started_at = perf_counter()
        benchmark_run_id = _benchmark_run_id(compute_input)
        plan = self.planner.plan(compute_input)
        provider_counts = Counter(provider for _table_name, provider in plan.provider_routes)
        log_formal_upload_benchmark_event(
            "comparison_core.plan",
            benchmark_run_id=benchmark_run_id,
            requested_table_count=len(compute_input.requested_tables),
            provider_route_count=len(plan.provider_routes),
            provider_counts=dict(provider_counts),
            summary_early_exit_table_count=len(plan.summary_early_exit_tables),
            row_compare_table_count=len(plan.row_compare_tables),
            duration_ms=benchmark_elapsed_ms(plan_started_at),
        )
        ruleset = _resolve_ruleset(self.planner.ruleset_registry, compute_input)
        table_ruleset_version = compute_input.table_ruleset_version or ruleset.ruleset_version
        before_tables = _summary_table_map(compute_input.before.summary)
        current_tables = _summary_table_map(compute_input.current.summary)
        table_results: list[_TableComparisonOutcome] = []
        all_diagnostics: list[DiagnosticRecord] = list(plan.diagnostics)
        cache_diagnostics: list[DiagnosticRecord] = []
        records_artifacts: list[RecordsArtifact] = []

        provider_by_table = {table_name: provider for table_name, provider in plan.provider_routes}
        alias_by_logical = _reusable_aliases_for_execution(
            compute_input=compute_input,
            provider_by_table=provider_by_table,
            ruleset=ruleset,
            before_tables=before_tables,
            current_tables=current_tables,
        )
        outcomes_by_table: dict[str, _TableComparisonOutcome] = {}
        table_benchmark_events: list[dict[str, object]] = []
        run_reuse_context = _ComparisonRunReuseContext()

        def compare_one(table_name: str) -> _TableComparisonOutcome:
            existing = outcomes_by_table.get(table_name)
            if existing is not None:
                return existing
            table_rule, selector_kind = _resolve_table_rule(ruleset, table_name)
            table_started_at = perf_counter()
            outcome = _compare_table(
                comparison_engine=self,
                table_name=table_name,
                provider=provider_by_table[table_name],
                table_rule=table_rule,
                selector_kind=selector_kind,
                before_descriptor=before_tables.get(table_name),
                current_descriptor=current_tables.get(table_name),
                before_table=_table_for_name(compute_input.before.table_set_ref, table_name),
                current_table=_table_for_name(compute_input.current.table_set_ref, table_name),
                compute_input=compute_input,
                table_ruleset_version=table_ruleset_version,
                records_store=records_store,
                cache_diagnostics=cache_diagnostics,
                run_reuse_context=run_reuse_context,
            )
            outcomes_by_table[table_name] = outcome
            if outcome.records_artifact is not None:
                records_artifacts.append(outcome.records_artifact)
            table_duration_ms = benchmark_elapsed_ms(table_started_at)
            table_benchmark_event = {
                "table_name": table_name,
                "provider": provider_by_table[table_name],
                "status": outcome.table_fact.status.value,
                "row_count_before": (
                    None
                    if outcome.table_fact.row_counts is None
                    else outcome.table_fact.row_counts[0]
                ),
                "row_count_current": (
                    None
                    if outcome.table_fact.row_counts is None
                    else outcome.table_fact.row_counts[1]
                ),
                "early_exit_reason": _early_exit_reason_from_diagnostics(outcome.diagnostics),
                "degrade_reason": _degrade_reason_from_diagnostics(outcome.diagnostics),
                "records_count": len(outcome.records),
                "records_artifact": outcome.records_artifact is not None,
                "duration_ms": table_duration_ms,
            }
            table_benchmark_events.append(table_benchmark_event)
            log_formal_upload_benchmark_event(
                "comparison_core.table",
                benchmark_run_id=benchmark_run_id,
                **table_benchmark_event,
            )
            return outcome

        for table_name in provider_by_table:
            alias = alias_by_logical.get(table_name)
            if alias is None:
                outcome = compare_one(table_name)
            else:
                canonical_outcome = compare_one(alias.canonical_table_name)
                outcome = _alias_outcome_from_canonical(
                    alias=alias,
                    canonical_outcome=canonical_outcome,
                    before_descriptor=before_tables.get(table_name),
                    current_descriptor=current_tables.get(table_name),
                    compute_input=compute_input,
                    ruleset=ruleset,
                    table_ruleset_version=table_ruleset_version,
                )
                outcomes_by_table[table_name] = outcome
                log_formal_upload_benchmark_event(
                    "comparison_core.alias_reuse",
                    benchmark_run_id=benchmark_run_id,
                    table_name=table_name,
                    canonical_table_name=alias.canonical_table_name,
                    alias_scope=alias.alias_scope.value,
                    status=outcome.table_fact.status.value,
                    records_artifact=False,
                    duration_ms=0,
                )
            table_results.append(outcome)
            all_diagnostics.extend(outcome.diagnostics)

        if not compute_input.comparison_options.include_unchanged_tables:
            table_results = [
                result
                for result in table_results
                if result.table_fact.status is not ComparisonTableStatus.UNCHANGED
            ]
        summary = _build_summary(table_results, all_diagnostics)
        table_digests = {
            outcome.table_fact.table_name: build_comparison_table_fact_digest(
                outcome.table_fact,
                comparison_contract_version=compute_input.comparison_contract_version,
                projection_contract_version=compute_input.projection_contract_version,
                table_ruleset_version=table_ruleset_version,
                scalar_encoding_version=compute_input.scalar_encoding_version or "",
            )
            for outcome in table_results
        }
        comparison_digest = build_comparison_digest(
            before_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
            current_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
            comparison_contract_version=compute_input.comparison_contract_version,
            projection_contract_version=compute_input.projection_contract_version,
            table_ruleset_version=table_ruleset_version,
            scalar_encoding_version=compute_input.scalar_encoding_version or "",
            table_ruleset_digest=ruleset.ruleset_digest,
            table_aliases=compute_input.table_aliases,
            requested_tables=compute_input.requested_tables,
            comparison_options=compute_input.comparison_options,
            table_fact_digests=table_digests,
            summary_digest=_summary_digest(summary),
        )
        facts_core_digest = _build_facts_core_digest(
            before_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
            current_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
            comparison_contract_version=compute_input.comparison_contract_version,
            projection_contract_version=compute_input.projection_contract_version,
            table_ruleset_version=table_ruleset_version,
            scalar_encoding_version=compute_input.scalar_encoding_version or "",
            table_ruleset_digest=ruleset.ruleset_digest,
            requested_tables=compute_input.requested_tables,
            comparison_options=compute_input.comparison_options,
            summary=summary,
            table_results=table_results,
            table_aliases=compute_input.table_aliases,
        )
        records_closure = _build_records_closure(
            comparison_digest=comparison_digest,
            facts_core_digest=facts_core_digest,
            table_results=table_results,
        )
        facts = ComparisonFacts(
            comparison_digest=comparison_digest,
            comparison_contract_version=compute_input.comparison_contract_version,
            projection_contract_version=compute_input.projection_contract_version,
            table_ruleset_version=table_ruleset_version,
            before_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
            current_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
            direction=COMPARISON_DEFAULT_DIRECTION,
            summary=summary,
            tables=tuple(outcome.table_fact for outcome in table_results),
            records_ref=records_closure,
            diagnostics=tuple(all_diagnostics),
        )
        final_plan = ComparisonPlan(
            comparison_digest=comparison_digest,
            summary_early_exit_tables=tuple(
                table_name
                for table_name in plan.summary_early_exit_tables
                if table_name not in alias_by_logical
            ),
            row_compare_tables=tuple(
                table_name
                for table_name in plan.row_compare_tables
                if table_name not in alias_by_logical
            ),
            provider_routes=tuple(
                route
                for route in plan.provider_routes
                if route[0] not in alias_by_logical
            ),
            diagnostics=plan.diagnostics,
        )
        result = ComparisonComputeResult(
            facts=facts,
            summary=summary,
            plan=final_plan,
            records_artifacts=tuple(records_artifacts),
            cache_diagnostics=tuple(cache_diagnostics),
            diagnostics=tuple(all_diagnostics),
        )
        log_formal_upload_benchmark_event(
            "comparison_core.run_reuse_summary",
            benchmark_run_id=benchmark_run_id,
            projection_rows_cache_hit_count=run_reuse_context.projection_rows_hit_count,
            projection_rows_cache_miss_count=run_reuse_context.projection_rows_miss_count,
            projection_rows_saved_row_count=run_reuse_context.projection_rows_saved_row_count,
            projection_rows_cache_entry_count=len(run_reuse_context.projection_rows),
            projection_digest_parts_reuse_count=run_reuse_context.projection_digest_parts_reuse_count,
            projection_digest_parts_fallback_count=run_reuse_context.projection_digest_parts_fallback_count,
            projection_digest_parts_saved_row_count=run_reuse_context.projection_digest_parts_saved_row_count,
            ordered_prepare_cache_hit_count=run_reuse_context.ordered_prepared_rows.hit_count,
            ordered_prepare_cache_miss_count=run_reuse_context.ordered_prepared_rows.miss_count,
            ordered_prepare_saved_row_count=run_reuse_context.ordered_prepared_rows.saved_row_count,
            ordered_prepare_cache_entry_count=len(run_reuse_context.ordered_prepared_rows.entries),
            ordered_digest_parts_reuse_count=run_reuse_context.ordered_prepared_rows.ordered_digest_parts_reuse_count,
            ordered_digest_parts_fallback_count=run_reuse_context.ordered_prepared_rows.ordered_digest_parts_fallback_count,
            ordered_digest_parts_saved_row_count=run_reuse_context.ordered_prepared_rows.ordered_digest_parts_saved_row_count,
        )
        log_formal_upload_benchmark_event(
            "comparison_core.total",
            benchmark_run_id=benchmark_run_id,
            provider_route_count=len(plan.provider_routes),
            provider_counts=dict(provider_counts),
            summary_early_exit_table_count=len(plan.summary_early_exit_tables),
            row_compare_table_count=len(plan.row_compare_tables),
            table_count=summary.table_count,
            status=summary.status.value,
            degraded_table_count=summary.degraded_table_count,
            records_artifact_count=len(records_artifacts),
            alias_member_count=len(alias_by_logical),
            alias_skipped_records_count=len(alias_by_logical),
            duration_ms=benchmark_elapsed_ms(total_started_at),
        )
        log_formal_upload_benchmark_event(
            "comparison_core.slow_table_summary",
            benchmark_run_id=benchmark_run_id,
            table_count=len(table_benchmark_events),
            top_slow_tables=_top_slow_table_events(table_benchmark_events, limit=20),
            top_ordered_degraded_tables=_top_ordered_degraded_table_events(
                table_benchmark_events,
                limit=20,
            ),
        )
        return result


@dataclass(frozen=True, slots=True)
class _TableComparisonOutcome:
    table_fact: ComparisonTableFact
    records: tuple[ComparisonRecord, ...] = field(default_factory=tuple)
    records_ref: ArtifactRef | None = None
    records_artifact: RecordsArtifact | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class _ProjectionRowsCacheEntry:
    source_table_name: str
    rows: tuple[tuple[object, ...], ...]
    columns: tuple[object, ...]
    projection_logical_digest_parts: ProjectionLogicalDigestParts | None = None


@dataclass(slots=True)
class _ComparisonRunReuseContext:
    projection_rows: dict[tuple[object, ...], _ProjectionRowsCacheEntry] = field(default_factory=dict)
    ordered_prepared_rows: OrderedPreparedRowsCache = field(default_factory=OrderedPreparedRowsCache)
    projection_rows_hit_count: int = 0
    projection_rows_miss_count: int = 0
    projection_rows_saved_row_count: int = 0
    projection_digest_parts_reuse_count: int = 0
    projection_digest_parts_fallback_count: int = 0
    projection_digest_parts_saved_row_count: int = 0


def compare(
    compute_input: ComparisonComputeInput,
    *,
    records_store: LocalArtifactStore | None = None,
    engine: ComparisonEngine | None = None,
) -> ComparisonComputeResult:
    return (engine or ComparisonEngine()).compare(compute_input, records_store=records_store)


def _reusable_aliases_for_execution(
    *,
    compute_input: ComparisonComputeInput,
    provider_by_table: Mapping[str, str],
    ruleset: TableRulesetSnapshot,
    before_tables: Mapping[str, SnapshotTableDescriptor],
    current_tables: Mapping[str, SnapshotTableDescriptor],
) -> dict[str, ComparisonTableAlias]:
    aliases: dict[str, ComparisonTableAlias] = {}
    logical_alias_tables = {alias.logical_table_name for alias in compute_input.table_aliases}
    for alias in compute_input.table_aliases:
        if alias.canonical_table_name in logical_alias_tables:
            continue
        logical_provider = provider_by_table.get(alias.logical_table_name)
        canonical_provider = provider_by_table.get(alias.canonical_table_name)
        if logical_provider is None or canonical_provider is None:
            continue
        if logical_provider in {SKIPPED_PROVIDER, ORDERED_TABLE_COMPARE_PROVIDER}:
            continue
        if canonical_provider in {SKIPPED_PROVIDER, ORDERED_TABLE_COMPARE_PROVIDER}:
            continue
        if not _table_rule_allows_alias_reuse(ruleset, alias.logical_table_name):
            continue
        if not _table_rule_allows_alias_reuse(ruleset, alias.canonical_table_name):
            continue
        if not _alias_descriptors_compatible(
            logical=before_tables.get(alias.logical_table_name),
            canonical=before_tables.get(alias.canonical_table_name),
        ):
            continue
        if not _alias_descriptors_compatible(
            logical=current_tables.get(alias.logical_table_name),
            canonical=current_tables.get(alias.canonical_table_name),
        ):
            continue
        aliases[alias.logical_table_name] = alias
    return aliases


def _table_rule_allows_alias_reuse(
    ruleset: TableRulesetSnapshot,
    table_name: str,
) -> bool:
    table_rule, _selector_kind = _resolve_table_rule(ruleset, table_name)
    if table_rule is None:
        return True
    static_role = table_rule.static_role.strip().upper()
    if static_role in {"ORDERED", "ORDERED_DIFF", "ORDERED_TABLE_COMPARE", "SKIP"}:
        return False
    return static_role in {"STANDARD", "STANDARD_DIFF", "TABLE", "DIFF"}


def _alias_descriptors_compatible(
    *,
    logical: SnapshotTableDescriptor | None,
    canonical: SnapshotTableDescriptor | None,
) -> bool:
    if logical is None and canonical is None:
        return True
    if logical is None or canonical is None:
        return False
    return (
        logical.row_count == canonical.row_count
        and _descriptor_columns_signature(logical) == _descriptor_columns_signature(canonical)
        and tuple(logical.compare_key_columns) == tuple(canonical.compare_key_columns)
        and logical.table_role == canonical.table_role
        and logical.table_ruleset_version == canonical.table_ruleset_version
        and logical.row_materialization_profile == canonical.row_materialization_profile
        and logical.scalar_encoding_version == canonical.scalar_encoding_version
    )


def _descriptor_columns_signature(
    descriptor: SnapshotTableDescriptor,
) -> tuple[tuple[str, str, bool], ...]:
    return tuple(
        (
            column.name,
            column.scalar_type,
            column.nullable,
        )
        for column in descriptor.columns
    )


def _alias_outcome_from_canonical(
    *,
    alias: ComparisonTableAlias,
    canonical_outcome: _TableComparisonOutcome,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    compute_input: ComparisonComputeInput,
    ruleset: TableRulesetSnapshot,
    table_ruleset_version: str,
) -> _TableComparisonOutcome:
    table_rule, _selector_kind = _resolve_table_rule(ruleset, alias.logical_table_name)
    table_schema = build_projection_schema(
        table_name=alias.logical_table_name,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        table_rule=table_rule,
        table_ruleset_version=table_ruleset_version,
        projection_contract_version=compute_input.projection_contract_version,
        scalar_encoding_version=compute_input.scalar_encoding_version or "",
    )
    diagnostics = (
        DiagnosticRecord(
            code="comparison.alias-reuse",
            message="table comparison reused canonical alias result",
            phase="compare",
            severity="INFO",
            details={
                "table_name": alias.logical_table_name,
                "canonical_table_name": alias.canonical_table_name,
                "alias_scope": alias.alias_scope.value,
                "reason": alias.reason,
            },
        ),
    )
    table_fact = _build_table_fact(
        table_name=alias.logical_table_name,
        status=canonical_outcome.table_fact.status,
        projection_schema=table_schema,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
        schema_changes=_schema_changes_payload(
            table_schema=table_schema,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
        ),
        before_projection_logical_digest=canonical_outcome.table_fact.before_projection_logical_digest,
        current_projection_logical_digest=canonical_outcome.table_fact.current_projection_logical_digest,
        diagnostics=diagnostics,
    )
    return _TableComparisonOutcome(table_fact=table_fact, diagnostics=diagnostics)


def _compare_table(
    *,
    comparison_engine: ComparisonEngine,
    table_name: str,
    provider: str,
    table_rule: TableRulesetTableRule | None,
    selector_kind: str,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    before_table: SnapshotTable | None,
    current_table: SnapshotTable | None,
    compute_input: ComparisonComputeInput,
    table_ruleset_version: str,
    records_store: LocalArtifactStore | None,
    cache_diagnostics: list[DiagnosticRecord],
    run_reuse_context: _ComparisonRunReuseContext | None = None,
) -> _TableComparisonOutcome:
    diagnostics: list[DiagnosticRecord] = []
    table_schema = build_projection_schema(
        table_name=table_name,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        table_rule=table_rule,
        table_ruleset_version=table_ruleset_version,
        projection_contract_version=compute_input.projection_contract_version,
        scalar_encoding_version=compute_input.scalar_encoding_version or "",
    )
    schema_changed = bool(table_schema.before_only_columns or table_schema.current_only_columns)
    key_changed = _descriptor_compare_key(before_descriptor) != _descriptor_compare_key(current_descriptor)
    schema_only_changed = schema_changed or key_changed or not table_schema.selected_columns

    if provider == DOLT_NATIVE_PROVIDER:
        native_outcome = compare_dolt_native_table(
            comparison_engine=comparison_engine,
            table_name=table_name,
            table_rule=table_rule,
            selector_kind=selector_kind,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            before_table=before_table,
            current_table=current_table,
            compute_input=compute_input,
            table_ruleset_version=table_ruleset_version,
            records_store=records_store,
            cache_diagnostics=cache_diagnostics,
            self_project_fn=self_project,
            compare_projected_pair_fn=_compare_projected_pair,
            compare_single_side_fn=_compare_single_side,
            diagnostics=diagnostics,
            table_schema=table_schema,
            schema_changed=schema_changed,
            schema_only_changed=schema_only_changed,
            key_changed=key_changed,
        )
        if native_outcome is not None:
            return native_outcome

    if provider == SKIPPED_PROVIDER:
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.skip",
                message="table was skipped by the comparison ruleset",
                phase="compare",
                severity="INFO",
                details={"table_name": table_name, "selector_kind": selector_kind},
            )
        )
        table_fact = _build_degraded_table_fact(
            table_name=table_name,
            projection_schema=table_schema,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
            diagnostics=tuple(diagnostics),
            reason="SKIPPED",
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    if provider == BROWSE_ONLY_PROVIDER:
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.browse-only",
                message="table is exposed for browsing without row comparison",
                phase="compare",
                severity="INFO",
                details={
                    "table_name": table_name,
                    "selector_kind": selector_kind,
                    "provider": BROWSE_ONLY_PROVIDER,
                },
            )
        )
        table_fact = _build_table_fact(
            table_name=table_name,
            status=ComparisonTableStatus.UNCHANGED,
            projection_schema=table_schema,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
            schema_changes=_schema_changes_payload(
                table_schema=table_schema,
                before_descriptor=before_descriptor,
                current_descriptor=current_descriptor,
            ),
            diagnostics=tuple(diagnostics),
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    if provider == ORDERED_TABLE_COMPARE_PROVIDER:
        ordered_started_at = perf_counter()
        before_projection = None
        if before_table is not None:
            before_projection = self_project(
                table=before_table,
                source_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
                projection_schema=table_schema,
                projection_builder=comparison_engine.projection_builder,
                projection_table_cache=comparison_engine.projection_table_cache,
                cache_diagnostics=cache_diagnostics,
                benchmark_run_id=_benchmark_run_id(compute_input),
                run_reuse_context=run_reuse_context,
                input_side="before",
            )
        current_projection = None
        if current_table is not None:
            current_projection = self_project(
                table=current_table,
                source_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
                projection_schema=table_schema,
                projection_builder=comparison_engine.projection_builder,
                projection_table_cache=comparison_engine.projection_table_cache,
                cache_diagnostics=cache_diagnostics,
                benchmark_run_id=_benchmark_run_id(compute_input),
                run_reuse_context=run_reuse_context,
                input_side="current",
            )
        stable_key_candidates = table_rule.compare_key_columns if table_rule is not None else ()
        if not stable_key_candidates and table_schema.effective_compare_key:
            stable_key_candidates = table_schema.effective_compare_key
        ordered_policy = build_ordered_table_policy(
            table_name=table_name,
            row_identity_key=stable_key_candidates[0] if stable_key_candidates else None,
            stable_key_candidates=stable_key_candidates,
            order_key="no",
            ignored_columns=table_schema.ignored_columns,
            value_columns=table_schema.selected_columns,
            blank_row_policy="PSEUDO_BLANK_BY_MISSING_STABLE_KEY",
            pseudo_key_start=2_000_000_000,
            move_policy="IDENTITY_POSITION_CHANGE",
            policy_version=table_ruleset_version,
        )
        ordered_result = compare_ordered_table(
            OrderedTableCompareInput(
                table_name=table_name,
                projection_schema=table_schema,
                ordered_policy=ordered_policy,
                comparison_contract_version=compute_input.comparison_contract_version,
                projection_contract_version=compute_input.projection_contract_version,
                table_ruleset_version=table_ruleset_version,
                scalar_encoding_version=compute_input.scalar_encoding_version or "",
                row_diff_detail_policy=compute_input.comparison_options.row_diff_detail_policy.value,
                before_descriptor=_descriptor_payload(before_descriptor),
                current_descriptor=_descriptor_payload(current_descriptor),
                before_table=before_table,
                current_table=current_table,
                before_projection=before_projection,
                current_projection=current_projection,
                row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
                records_store=records_store,
                diagnostics=tuple(diagnostics),
                benchmark_run_id=_benchmark_run_id(compute_input),
                prepared_rows_cache=None if run_reuse_context is None else run_reuse_context.ordered_prepared_rows,
            )
        )
        log_formal_upload_benchmark_event(
            "comparison_core.ordered_provider",
            benchmark_run_id=_benchmark_run_id(compute_input),
            table_name=table_name,
            status=ordered_result.table_fact.status.value,
            degrade_reason=ordered_result.degrade_reason,
            planner_mode=ordered_result.planner_mode,
            row_count_before=(
                None
                if ordered_result.table_fact.row_counts is None
                else ordered_result.table_fact.row_counts[0]
            ),
            row_count_current=(
                None
                if ordered_result.table_fact.row_counts is None
                else ordered_result.table_fact.row_counts[1]
            ),
            prepared_row_count_before=ordered_result.prepared_row_count_before,
            prepared_row_count_current=ordered_result.prepared_row_count_current,
            ordered_input_source=ordered_result.ordered_input_source,
            records_count=len(ordered_result.records),
            records_artifact=ordered_result.records_artifact is not None,
            duration_ms=benchmark_elapsed_ms(ordered_started_at),
        )
        return _TableComparisonOutcome(
            table_fact=ordered_result.table_fact,
            records=ordered_result.records,
            records_ref=ordered_result.records_ref,
            records_artifact=ordered_result.records_artifact,
            diagnostics=ordered_result.diagnostics,
        )

    if provider == SUMMARY_EARLY_EXIT_PROVIDER and before_descriptor is not None and current_descriptor is not None:
        early_exit_reason = _summary_early_exit_reason(
            compute_input=compute_input,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
        )
        if early_exit_reason is not None:
            diagnostics.append(
                DiagnosticRecord(
                    code="comparison.summary-early-exit",
                    message="table comparison used summary early exit",
                    phase="compare",
                    severity="INFO",
                    details={
                        "table_name": table_name,
                        "reason": early_exit_reason,
                    },
                )
            )
            table_fact = _build_table_fact(
                table_name=table_name,
                status=ComparisonTableStatus.UNCHANGED,
                projection_schema=table_schema,
                before_descriptor=before_descriptor,
                current_descriptor=current_descriptor,
                row_counts=(before_descriptor.row_count, current_descriptor.row_count),
                schema_changes=_schema_changes_payload(
                    table_schema=table_schema,
                    before_descriptor=before_descriptor,
                    current_descriptor=current_descriptor,
                ),
                diagnostics=tuple(diagnostics),
            )
            return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))
        provider = SNAPSHOT_TABLE_COMPARE_PROVIDER

    projection_digest_summary_outcome = _try_projection_digest_summary_early_exit(
        table_name=table_name,
        projection_schema=table_schema,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        compute_input=compute_input,
        schema_changed=schema_changed,
        schema_only_changed=schema_only_changed,
        diagnostics=diagnostics,
    )
    if projection_digest_summary_outcome is not None:
        return projection_digest_summary_outcome

    if (
        compute_input.before.table_access_policy is ComparisonTableAccessPolicy.SUMMARY_ONLY
        or compute_input.current.table_access_policy is ComparisonTableAccessPolicy.SUMMARY_ONLY
    ) and provider != SUMMARY_EARLY_EXIT_PROVIDER:
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.compare.summary-only",
                message="table readers are not allowed for SUMMARY_ONLY comparison inputs",
                phase="compare",
                severity="WARNING",
                details={"table_name": table_name, "selector_kind": selector_kind},
            )
        )
        table_fact = _build_degraded_table_fact(
            table_name=table_name,
            projection_schema=table_schema,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
            diagnostics=tuple(diagnostics),
            reason="TABLE_ACCESS_POLICY_SUMMARY_ONLY",
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    if table_schema.effective_compare_key == ():
        before_materialization_digest = _descriptor_materialization_digest(before_descriptor)
        current_materialization_digest = _descriptor_materialization_digest(current_descriptor)
        if (
            before_descriptor is not None
            and current_descriptor is not None
            and before_materialization_digest is not None
            and before_materialization_digest == current_materialization_digest
        ):
            table_fact = _build_table_fact(
                table_name=table_name,
                status=ComparisonTableStatus.UNCHANGED,
                projection_schema=table_schema,
                before_descriptor=before_descriptor,
                current_descriptor=current_descriptor,
                row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
                schema_changes=_schema_changes_payload(
                    table_schema=table_schema,
                    before_descriptor=before_descriptor,
                    current_descriptor=current_descriptor,
                ),
                diagnostics=tuple(diagnostics),
            )
            return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))
        table_fact = _build_degraded_table_fact(
            table_name=table_name,
            projection_schema=table_schema,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
            diagnostics=tuple(diagnostics),
            reason="NO_COMPARE_KEY",
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    if before_table is None and current_table is None:
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.compare.reader-missing",
                message="table readers are missing on both sides",
                phase="compare",
                severity="WARNING",
                details={"table_name": table_name},
            )
        )
        table_fact = _build_degraded_table_fact(
            table_name=table_name,
            projection_schema=table_schema,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
            diagnostics=tuple(diagnostics),
            reason="READER_MISSING",
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    if before_table is not None and current_table is not None:
        before_projection = self_project(
            table=before_table,
            source_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
            projection_schema=table_schema,
            projection_builder=comparison_engine.projection_builder,
            projection_table_cache=comparison_engine.projection_table_cache,
            cache_diagnostics=cache_diagnostics,
            benchmark_run_id=_benchmark_run_id(compute_input),
            run_reuse_context=run_reuse_context,
            input_side="before",
        )
        current_projection = self_project(
            table=current_table,
            source_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
            projection_schema=table_schema,
            projection_builder=comparison_engine.projection_builder,
            projection_table_cache=comparison_engine.projection_table_cache,
            cache_diagnostics=cache_diagnostics,
            benchmark_run_id=_benchmark_run_id(compute_input),
            run_reuse_context=run_reuse_context,
            input_side="current",
        )
        return _compare_projected_pair(
            table_name=table_name,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            before_projection=before_projection,
            current_projection=current_projection,
            projection_schema=table_schema,
            comparison_input=compute_input,
        table_ruleset_version=table_ruleset_version,
        records_store=records_store,
        diagnostics=diagnostics,
        table_rule=table_rule,
        schema_only_changed=schema_only_changed,
        schema_changed=schema_changed,
        key_changed=key_changed,
        )

    if before_table is not None:
        before_projection = self_project(
            table=before_table,
            source_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
            projection_schema=table_schema,
            projection_builder=comparison_engine.projection_builder,
            projection_table_cache=comparison_engine.projection_table_cache,
            cache_diagnostics=cache_diagnostics,
            benchmark_run_id=_benchmark_run_id(compute_input),
            run_reuse_context=run_reuse_context,
            input_side="before",
        )
        return _compare_single_side(
            table_name=table_name,
            side="before",
            projection=before_projection,
            descriptor=before_descriptor,
            projection_schema=table_schema,
            comparison_input=compute_input,
            table_ruleset_version=table_ruleset_version,
            records_store=records_store,
            diagnostics=diagnostics,
        )

    current_projection = self_project(
        table=current_table,  # type: ignore[arg-type]
        source_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
        projection_schema=table_schema,
        projection_builder=comparison_engine.projection_builder,
        projection_table_cache=comparison_engine.projection_table_cache,
        cache_diagnostics=cache_diagnostics,
        benchmark_run_id=_benchmark_run_id(compute_input),
        run_reuse_context=run_reuse_context,
        input_side="current",
    )
    return _compare_single_side(
        table_name=table_name,
        side="current",
        projection=current_projection,
        descriptor=current_descriptor,
        projection_schema=table_schema,
        comparison_input=compute_input,
        table_ruleset_version=table_ruleset_version,
        records_store=records_store,
        diagnostics=diagnostics,
    )


def _try_projection_digest_summary_early_exit(
    *,
    table_name: str,
    projection_schema: object,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    compute_input: ComparisonComputeInput,
    schema_changed: bool,
    schema_only_changed: bool,
    diagnostics: list[DiagnosticRecord],
) -> _TableComparisonOutcome | None:
    started_at = perf_counter()
    hit = False
    miss_reason = None
    before_digest = None
    current_digest = None
    accepted_authorities = _accepted_projection_digest_authorities(
        before_descriptor,
        current_descriptor,
    )
    if before_descriptor is None:
        miss_reason = "missing_before"
    elif current_descriptor is None:
        miss_reason = "missing_current"
    elif not getattr(projection_schema, "effective_compare_key", ()):
        miss_reason = "no_compare_key"
    else:
        before_digest, before_miss_reason = _matching_projection_digest_summary(
            descriptor=before_descriptor,
            projection_schema=projection_schema,
            accepted_authorities=accepted_authorities,
        )
        current_digest, current_miss_reason = _matching_projection_digest_summary(
            descriptor=current_descriptor,
            projection_schema=projection_schema,
            accepted_authorities=accepted_authorities,
        )
        if before_digest is None:
            miss_reason = f"before_{before_miss_reason}"
        elif current_digest is None:
            miss_reason = f"current_{current_miss_reason}"
        elif before_digest.projection_logical_digest != current_digest.projection_logical_digest:
            miss_reason = "digest_mismatch"
        else:
            hit = True

    log_formal_upload_benchmark_event(
        "comparison_core.projection_digest_summary_lookup",
        benchmark_run_id=_benchmark_run_id(compute_input),
        table_name=table_name,
        hit=hit,
        miss_reason=miss_reason,
        accepted_authorities=list(accepted_authorities),
        before_authority=(
            None if before_digest is None else before_digest.digest_authority.value
        ),
        current_authority=(
            None if current_digest is None else current_digest.digest_authority.value
        ),
        saved_projection_build=hit,
        duration_ms=benchmark_elapsed_ms(started_at),
    )
    if not hit or before_digest is None or current_digest is None:
        return None

    diagnostics.append(
        DiagnosticRecord(
            code="comparison.projection-digest-summary-early-exit",
            message="table comparison used descriptor projection digest summary",
            phase="compare",
            severity="INFO",
            details={
                "table_name": table_name,
                "before_authority": before_digest.digest_authority.value,
                "current_authority": current_digest.digest_authority.value,
            },
        )
    )
    if schema_changed:
        status = (
            ComparisonTableStatus.SCHEMA_ONLY_CHANGED
            if schema_only_changed
            else ComparisonTableStatus.SCHEMA_CHANGED
        )
    else:
        status = ComparisonTableStatus.UNCHANGED
    if (
        status is ComparisonTableStatus.UNCHANGED
        and before_descriptor is not None
        and current_descriptor is not None
        and before_descriptor.raw_content_digest != current_descriptor.raw_content_digest
    ):
        status = ComparisonTableStatus.BUSINESS_EQUIVALENT
    table_fact = _build_table_fact(
        table_name=table_name,
        status=status,
        projection_schema=projection_schema,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        row_counts=_descriptor_row_counts(before_descriptor, current_descriptor),
        before_projection_logical_digest=before_digest.projection_logical_digest,
        current_projection_logical_digest=current_digest.projection_logical_digest,
        schema_changes=_schema_changes_payload(
            table_schema=projection_schema,
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
        ),
        diagnostics=tuple(diagnostics),
    )
    return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))


def _accepted_projection_digest_authorities(
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
) -> tuple[str, ...]:
    if (
        before_descriptor is not None
        and current_descriptor is not None
        and before_descriptor.materialization_stage == "FINAL"
        and current_descriptor.materialization_stage == "FINAL"
    ):
        return ("FINAL",)
    return ("FINAL", "PROVISIONAL_FAST")


def _matching_projection_digest_summary(
    *,
    descriptor: SnapshotTableDescriptor,
    projection_schema: object,
    accepted_authorities: Sequence[str],
) -> tuple[object | None, str]:
    projection_digests = tuple(getattr(descriptor, "projection_digests", ()))
    if not projection_digests:
        return None, "missing"
    projection_schema_digest = getattr(projection_schema, "projection_schema_digest", None)
    table_ruleset_version = getattr(projection_schema, "table_ruleset_version", None)
    projection_contract_version = getattr(projection_schema, "projection_contract_version", None)
    scalar_encoding_version = getattr(projection_schema, "scalar_encoding_version", None)
    authority_allowed = False
    schema_seen = False
    version_seen = False
    for digest in projection_digests:
        authority = getattr(digest, "digest_authority", None)
        authority_value = getattr(authority, "value", authority)
        if authority_value not in accepted_authorities:
            continue
        authority_allowed = True
        if getattr(digest, "projection_schema_digest", None) != projection_schema_digest:
            continue
        schema_seen = True
        if (
            getattr(digest, "table_ruleset_version", None) != table_ruleset_version
            or getattr(digest, "projection_contract_version", None) != projection_contract_version
            or getattr(digest, "scalar_encoding_version", None) != scalar_encoding_version
        ):
            continue
        version_seen = True
        return digest, "hit"
    if not authority_allowed:
        return None, "authority_not_allowed"
    if not schema_seen:
        return None, "schema_mismatch"
    if not version_seen:
        return None, "version_mismatch"
    return None, "missing"


def _compare_projected_pair(
    *,
    table_name: str,
    before_descriptor: SnapshotTableDescriptor | None,
    current_descriptor: SnapshotTableDescriptor | None,
    before_projection: ProjectionTable,
    current_projection: ProjectionTable,
    projection_schema: object,
    comparison_input: ComparisonComputeInput,
    table_ruleset_version: str,
    records_store: LocalArtifactStore | None,
    diagnostics: list[DiagnosticRecord],
    table_rule: TableRulesetTableRule | None,
    schema_only_changed: bool,
    schema_changed: bool,
    key_changed: bool,
) -> _TableComparisonOutcome:
    index_started_at = perf_counter()
    before_index, before_duplicate = _index_projection_rows(before_projection)
    current_index, current_duplicate = _index_projection_rows(current_projection)
    log_formal_upload_benchmark_event(
        "comparison_core.row_index",
        benchmark_run_id=_benchmark_run_id(comparison_input),
        table_name=table_name,
        row_count_before=before_projection.row_count,
        row_count_current=current_projection.row_count,
        before_duplicate=before_duplicate is not None,
        current_duplicate=current_duplicate is not None,
        duration_ms=benchmark_elapsed_ms(index_started_at),
    )
    if before_duplicate is not None or current_duplicate is not None:
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.compare.duplicate-key",
                message="duplicate compare key detected during comparison",
                phase="compare",
                severity="WARNING",
                details={
                    "table_name": table_name,
                    "before_duplicate": before_duplicate,
                    "current_duplicate": current_duplicate,
                },
            )
        )
        table_fact = _build_degraded_table_fact(
            table_name=table_name,
            projection_schema=projection_schema,  # type: ignore[arg-type]
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            row_counts=(before_projection.row_count, current_projection.row_count),
            diagnostics=tuple(diagnostics),
            reason="EFFECTIVE_KEY_DUPLICATE",
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    if before_projection.projection_logical_digest is not None and before_projection.projection_logical_digest == current_projection.projection_logical_digest:
        if schema_changed:
            status = ComparisonTableStatus.SCHEMA_ONLY_CHANGED if schema_only_changed else ComparisonTableStatus.SCHEMA_CHANGED
        else:
            status = ComparisonTableStatus.UNCHANGED
        if before_descriptor is not None and current_descriptor is not None and before_descriptor.raw_content_digest != current_descriptor.raw_content_digest:
            status = ComparisonTableStatus.BUSINESS_EQUIVALENT if status == ComparisonTableStatus.UNCHANGED else status
        table_fact = _build_table_fact(
            table_name=table_name,
            status=status,
            projection_schema=projection_schema,  # type: ignore[arg-type]
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            row_counts=(before_projection.row_count, current_projection.row_count),
            before_projection_logical_digest=before_projection.projection_logical_digest,
            current_projection_logical_digest=current_projection.projection_logical_digest,
            schema_changes=_schema_changes_payload(
                table_schema=projection_schema,  # type: ignore[arg-type]
                before_descriptor=before_descriptor,
                current_descriptor=current_descriptor,
            ),
            diagnostics=tuple(diagnostics),
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    records_started_at = perf_counter()
    records = _build_row_diff_records(
        table_name=table_name,
        projection_schema=projection_schema,  # type: ignore[arg-type]
        before_projection=before_projection,
        current_projection=current_projection,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        comparison_input=comparison_input,
    )
    log_formal_upload_benchmark_event(
        "comparison_core.records_build",
        benchmark_run_id=_benchmark_run_id(comparison_input),
        table_name=table_name,
        records_count=len(records),
        duration_ms=benchmark_elapsed_ms(records_started_at),
    )
    scoped_records, row_change_stats, suppression_diagnostic = _apply_standard_artifact_scope(
        records=records,
        table_rule=table_rule,
    )
    if suppression_diagnostic is not None:
        diagnostics.append(
            DiagnosticRecord(
                code="TABLE_RULE_SCOPE_UPDATE_ONLY",
                message="Update-only table scope suppressed row insert/delete records.",
                phase="compare",
                severity="INFO",
                details={
                    "table_name": table_name,
                    **suppression_diagnostic,
                },
            )
        )
    records = scoped_records
    if not records:
        if schema_changed:
            status = ComparisonTableStatus.SCHEMA_ONLY_CHANGED if schema_only_changed else ComparisonTableStatus.SCHEMA_CHANGED
        else:
            status = ComparisonTableStatus.UNCHANGED
        if row_change_stats.get("suppressed_inserted_count", 0) or row_change_stats.get("suppressed_deleted_count", 0):
            status = ComparisonTableStatus.BUSINESS_EQUIVALENT if status == ComparisonTableStatus.UNCHANGED else status
        if before_descriptor is not None and current_descriptor is not None and before_descriptor.raw_content_digest != current_descriptor.raw_content_digest:
            status = ComparisonTableStatus.BUSINESS_EQUIVALENT if status == ComparisonTableStatus.UNCHANGED else status
        table_fact = _build_table_fact(
            table_name=table_name,
            status=status,
            projection_schema=projection_schema,  # type: ignore[arg-type]
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            row_counts=(before_projection.row_count, current_projection.row_count),
            row_change_stats=row_change_stats,
            before_projection_logical_digest=before_projection.projection_logical_digest,
            current_projection_logical_digest=current_projection.projection_logical_digest,
            schema_changes=_schema_changes_payload(
                table_schema=projection_schema,  # type: ignore[arg-type]
                before_descriptor=before_descriptor,
                current_descriptor=current_descriptor,
            ),
            diagnostics=tuple(diagnostics),
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    records = tuple(sorted(records, key=_record_sort_key))
    records_write_started_at = perf_counter()
    records_ref, records_artifact = _build_records_artifact(
        table_name=table_name,
        records=records,
        projection_schema=projection_schema,  # type: ignore[arg-type]
        comparison_input=comparison_input,
        table_ruleset_version=table_ruleset_version,
        diagnostics=tuple(diagnostics),
        records_store=records_store,
    )
    log_formal_upload_benchmark_event(
        "comparison_core.records_write",
        benchmark_run_id=_benchmark_run_id(comparison_input),
        table_name=table_name,
        records_count=len(records),
        records_artifact=records_artifact is not None,
        duration_ms=benchmark_elapsed_ms(records_write_started_at),
    )
    table_fact = _build_table_fact(
        table_name=table_name,
        status=ComparisonTableStatus.MODIFIED,
        projection_schema=projection_schema,  # type: ignore[arg-type]
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        row_counts=(before_projection.row_count, current_projection.row_count),
        row_change_stats=row_change_stats,
        before_projection_logical_digest=before_projection.projection_logical_digest,
        current_projection_logical_digest=current_projection.projection_logical_digest,
        schema_changes=_schema_changes_payload(
            table_schema=projection_schema,  # type: ignore[arg-type]
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
        ),
        records_ref=records_ref,
        diagnostics=tuple(diagnostics),
    )
    return _TableComparisonOutcome(
        table_fact=table_fact,
        records=records,
        records_ref=records_ref,
        records_artifact=records_artifact,
        diagnostics=tuple(diagnostics),
    )


def _compare_single_side(
    *,
    table_name: str,
    side: str,
    projection: ProjectionTable,
    descriptor: SnapshotTableDescriptor | None,
    projection_schema: object,
    comparison_input: ComparisonComputeInput,
    table_ruleset_version: str,
    records_store: LocalArtifactStore | None,
    diagnostics: list[DiagnosticRecord],
) -> _TableComparisonOutcome:
    if descriptor is None:
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.compare.missing-descriptor",
                message="table descriptor is missing for the present side",
                phase="compare",
                severity="WARNING",
                details={"table_name": table_name, "side": side},
            )
        )
        table_fact = _build_degraded_table_fact(
            table_name=table_name,
            projection_schema=projection_schema,  # type: ignore[arg-type]
            before_descriptor=None if side == "current" else descriptor,
            current_descriptor=None if side == "before" else descriptor,
            row_counts=(projection.row_count, None) if side == "before" else (None, projection.row_count),
            diagnostics=tuple(diagnostics),
            reason="READER_MISSING",
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    if projection.projection_logical_digest is None:
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.compare.no-projection-digest",
                message="projection digest could not be computed for the present side",
                phase="compare",
                severity="WARNING",
                details={"table_name": table_name, "side": side},
            )
        )
        table_fact = _build_degraded_table_fact(
            table_name=table_name,
            projection_schema=projection_schema,  # type: ignore[arg-type]
            before_descriptor=None if side == "current" else descriptor,
            current_descriptor=None if side == "before" else descriptor,
            row_counts=(projection.row_count, None) if side == "before" else (None, projection.row_count),
            diagnostics=tuple(diagnostics),
            reason="NO_COMPARE_KEY",
        )
        return _TableComparisonOutcome(table_fact=table_fact, diagnostics=tuple(diagnostics))

    if side == "before":
        status = ComparisonTableStatus.DELETED_TABLE
        record_kind = ComparisonRecordKind.ROW_DELETED
        records = tuple(
            _build_side_record(
                table_name=table_name,
                record_kind=record_kind,
                row_identity=row_identity,
                values=row,
                row_diff_detail_policy=comparison_input.comparison_options.row_diff_detail_policy,
                side="before",
            )
            for row_identity, row in _iter_projection_rows(projection, projection_schema.effective_compare_key)
        )
        row_counts = (projection.row_count, None)
        before_projection_logical_digest = projection.projection_logical_digest
        current_projection_logical_digest = None
    else:
        status = ComparisonTableStatus.ADDED_TABLE
        record_kind = ComparisonRecordKind.ROW_ADDED
        records = tuple(
            _build_side_record(
                table_name=table_name,
                record_kind=record_kind,
                row_identity=row_identity,
                values=row,
                row_diff_detail_policy=comparison_input.comparison_options.row_diff_detail_policy,
                side="current",
            )
            for row_identity, row in _iter_projection_rows(projection, projection_schema.effective_compare_key)
        )
        row_counts = (None, projection.row_count)
        before_projection_logical_digest = None
        current_projection_logical_digest = projection.projection_logical_digest

    records = tuple(sorted(records, key=_record_sort_key))
    records_write_started_at = perf_counter()
    records_ref, records_artifact = _build_records_artifact(
        table_name=table_name,
        records=records,
        projection_schema=projection_schema,  # type: ignore[arg-type]
        comparison_input=comparison_input,
        table_ruleset_version=table_ruleset_version,
        diagnostics=tuple(diagnostics),
        records_store=records_store,
    )
    log_formal_upload_benchmark_event(
        "comparison_core.records_write",
        benchmark_run_id=_benchmark_run_id(comparison_input),
        table_name=table_name,
        records_count=len(records),
        records_artifact=records_artifact is not None,
        duration_ms=benchmark_elapsed_ms(records_write_started_at),
    )
    table_fact = _build_table_fact(
        table_name=table_name,
        status=status,
        projection_schema=projection_schema,  # type: ignore[arg-type]
        before_descriptor=None if side == "current" else descriptor,
        current_descriptor=None if side == "before" else descriptor,
        row_counts=row_counts,
        before_projection_logical_digest=before_projection_logical_digest,
        current_projection_logical_digest=current_projection_logical_digest,
        schema_changes=_schema_changes_payload(
            table_schema=projection_schema,  # type: ignore[arg-type]
            before_descriptor=None if side == "current" else descriptor,
            current_descriptor=None if side == "before" else descriptor,
        ),
        records_ref=records_ref,
        diagnostics=tuple(diagnostics),
    )
    return _TableComparisonOutcome(
        table_fact=table_fact,
        records=records,
        records_ref=records_ref,
        records_artifact=records_artifact,
        diagnostics=tuple(diagnostics),
    )


def _apply_standard_artifact_scope(
    *,
    records: list[ComparisonRecord],
    table_rule: TableRulesetTableRule | None,
) -> tuple[list[ComparisonRecord], Mapping[str, object], dict[str, object] | None]:
    raw_inserted = sum(1 for record in records if record.record_kind is ComparisonRecordKind.ROW_ADDED)
    raw_deleted = sum(1 for record in records if record.record_kind is ComparisonRecordKind.ROW_DELETED)
    raw_updated = sum(1 for record in records if record.record_kind is ComparisonRecordKind.ROW_MODIFIED)
    stats: dict[str, object] = {
        "raw_inserted_count": raw_inserted,
        "raw_deleted_count": raw_deleted,
        "raw_updated_count": raw_updated,
        "inserted_count": raw_inserted,
        "deleted_count": raw_deleted,
        "updated_count": raw_updated,
        "suppressed_inserted_count": 0,
        "suppressed_deleted_count": 0,
    }
    if table_rule is None or table_rule.artifact_scope != "UPDATE_ONLY":
        return records, stats, None

    scoped_records = [
        record for record in records
        if record.record_kind is ComparisonRecordKind.ROW_MODIFIED
    ]
    stats.update(
        {
            "artifact_scope": "UPDATE_ONLY",
            "suppression_reason": "TABLE_RULE_SCOPE_UPDATE_ONLY",
            "inserted_count": 0,
            "deleted_count": 0,
            "updated_count": len(scoped_records),
            "suppressed_inserted_count": raw_inserted,
            "suppressed_deleted_count": raw_deleted,
        }
    )
    diagnostic = None
    if raw_inserted or raw_deleted:
        diagnostic = {
            "artifact_scope": "UPDATE_ONLY",
            "suppressed_ops": ["INSERT", "DELETE"],
            "suppressed_inserted_count": raw_inserted,
            "suppressed_deleted_count": raw_deleted,
        }
    return scoped_records, stats, diagnostic


def self_project(
    *,
    table: SnapshotTable,
    source_snapshot_digest: DigestRef | str,
    projection_schema: object,
    projection_builder: ProjectionBuilder | None = None,
    projection_table_cache: ProjectionTableCache | None = None,
    cache_diagnostics: list[DiagnosticRecord] | None = None,
    benchmark_run_id: str | None = None,
    run_reuse_context: _ComparisonRunReuseContext | None = None,
    input_side: str | None = None,
) -> ProjectionTable:
    projection_started_at = perf_counter()
    builder = projection_builder or ProjectionBuilder()
    cache_key = _projection_table_cache_key(table=table, projection_schema=projection_schema)
    if projection_table_cache is not None and cache_key is not None:
        try:
            lookup = projection_table_cache.lookup(key=cache_key)
        except Exception as exc:  # pragma: no cover - defensive, hard to trigger reliably
            _append_cache_diagnostic(
                cache_diagnostics,
                code="comparison.projection-cache.lookup-failed",
                message="projection table cache lookup failed",
                severity="WARNING",
                table_name=table.descriptor.table_name,
                cache_key_digest=cache_key.cache_key_digest,
                details={"error": str(exc)},
            )
        else:
            if lookup.hit and isinstance(lookup.value, ProjectionTable):
                _append_cache_diagnostic(
                    cache_diagnostics,
                    code="comparison.projection-cache.hit",
                    message="projection table cache hit",
                    severity="INFO",
                    table_name=table.descriptor.table_name,
                    cache_key_digest=lookup.cache_key_digest,
                )
                projected = replace(
                    lookup.value,
                    source_snapshot_digest=source_snapshot_digest,
                )
                log_formal_upload_benchmark_event(
                    "comparison_core.projection_build",
                    benchmark_run_id=benchmark_run_id,
                    table_name=table.descriptor.table_name,
                    cache_hit=True,
                    row_count=projected.row_count,
                    duration_ms=benchmark_elapsed_ms(projection_started_at),
                )
                return projected
            _append_cache_diagnostic(
                cache_diagnostics,
                code="comparison.projection-cache.miss",
                message="projection table cache miss",
                severity="INFO",
                table_name=table.descriptor.table_name,
                cache_key_digest=cache_key.cache_key_digest,
                details={"miss_reason": lookup.miss_reason},
            )
    rows_reuse_key, rows_reuse_miss_reason = _projection_rows_reuse_key(
        table=table,
        projection_schema=projection_schema,
        input_side=input_side,
    )
    if run_reuse_context is not None and rows_reuse_key is not None:
        cached_rows = run_reuse_context.projection_rows.get(rows_reuse_key)
        if cached_rows is not None:
            run_reuse_context.projection_rows_hit_count += 1
            run_reuse_context.projection_rows_saved_row_count += len(cached_rows.rows)
            projected, projection_digest_stats = _projection_from_cached_rows(
                table=table,
                source_snapshot_digest=source_snapshot_digest,
                projection_schema=projection_schema,
                cached_rows=cached_rows,
            )
            if projection_digest_stats["projection_digest_parts_reused"]:
                run_reuse_context.projection_digest_parts_reuse_count += 1
                run_reuse_context.projection_digest_parts_saved_row_count += len(cached_rows.rows)
            if projection_digest_stats["projection_digest_recompute_fallback"]:
                run_reuse_context.projection_digest_parts_fallback_count += 1
            log_formal_upload_benchmark_event(
                "comparison_core.projection_build",
                benchmark_run_id=benchmark_run_id,
                table_name=table.descriptor.table_name,
                cache_hit=True,
                cache_layer="comparison_run_projection_rows",
                cache_source_table=cached_rows.source_table_name,
                saved_row_count=len(cached_rows.rows),
                row_count=projected.row_count,
                projection_digest=projected.projection_logical_digest is not None,
                **projection_digest_stats,
                duration_ms=benchmark_elapsed_ms(projection_started_at),
            )
            return projected
        run_reuse_context.projection_rows_miss_count += 1
    projection = builder.project(
        table,
        source_snapshot_digest=source_snapshot_digest,
        projection_schema=projection_schema,  # type: ignore[arg-type]
    )
    if run_reuse_context is not None and rows_reuse_key is not None:
        run_reuse_context.projection_rows[rows_reuse_key] = _ProjectionRowsCacheEntry(
            source_table_name=table.descriptor.table_name,
            rows=tuple(tuple(row) for row in projection.reader.iter_rows()),
            columns=tuple(getattr(projection.reader, "columns", ())),
            projection_logical_digest_parts=getattr(
                projection.reader,
                "projection_logical_digest_parts",
                None,
            ),
        )
    if projection_table_cache is not None and cache_key is not None:
        try:
            projection_table_cache.write(key=cache_key, value=projection)
        except Exception as exc:  # pragma: no cover - defensive, hard to trigger reliably
            _append_cache_diagnostic(
                cache_diagnostics,
                code="comparison.projection-cache.write-failed",
                message="projection table cache write failed",
                severity="WARNING",
                table_name=table.descriptor.table_name,
                cache_key_digest=cache_key.cache_key_digest,
                details={"error": str(exc)},
            )
        else:
            _append_cache_diagnostic(
                cache_diagnostics,
                code="comparison.projection-cache.write",
                message="projection table cache write",
                severity="INFO",
                table_name=table.descriptor.table_name,
                cache_key_digest=cache_key.cache_key_digest,
            )
    log_formal_upload_benchmark_event(
        "comparison_core.projection_build",
        benchmark_run_id=benchmark_run_id,
        table_name=table.descriptor.table_name,
        cache_hit=False,
        cache_layer="comparison_run_projection_rows",
        reuse_eligible=rows_reuse_key is not None,
        reuse_miss_reason=rows_reuse_miss_reason,
        row_count=projection.row_count,
        projection_digest=projection.projection_logical_digest is not None,
        duration_ms=benchmark_elapsed_ms(projection_started_at),
    )
    return projection


def _projection_rows_reuse_key(
    *,
    table: SnapshotTable,
    projection_schema: object,
    input_side: str | None,
) -> tuple[tuple[object, ...] | None, str | None]:
    descriptor = table.descriptor
    if input_side is None:
        return None, "missing_side"
    if descriptor.fast_row_digest is None:
        return None, "missing_fast_row_digest"
    selected_columns = tuple(str(column) for column in getattr(projection_schema, "selected_columns", ()))
    if not selected_columns:
        return None, "missing_selected_columns"
    return (
        (
            "projection_rows",
            input_side,
            descriptor.fast_row_digest.to_payload(),
            tuple(
                (
                    column.name,
                    column.scalar_type,
                    column.nullable,
                )
                for column in descriptor.columns
            ),
            descriptor.row_count,
            descriptor.row_materialization_profile,
            descriptor.scalar_encoding_version,
            selected_columns,
            tuple(str(column) for column in getattr(projection_schema, "effective_compare_key", ())),
            getattr(projection_schema, "projection_contract_version", None),
            getattr(projection_schema, "scalar_encoding_version", None),
        ),
        None,
    )


def _projection_from_cached_rows(
    *,
    table: SnapshotTable,
    source_snapshot_digest: DigestRef | str,
    projection_schema: object,
    cached_rows: _ProjectionRowsCacheEntry,
) -> tuple[ProjectionTable, dict[str, bool]]:
    row_identity_columns = tuple(str(column) for column in getattr(projection_schema, "effective_compare_key", ()))
    projection_logical_digest = None
    digest_parts = cached_rows.projection_logical_digest_parts
    projection_digest_parts_reused = False
    projection_digest_recompute_fallback = False
    if row_identity_columns:
        if digest_parts is not None:
            projection_logical_digest = build_projection_logical_digest_from_parts(
                row_identity_digest=getattr(digest_parts, "row_identity_digest"),
                projected_row_value_digest=getattr(digest_parts, "projected_row_value_digest"),
                projection_schema_digest=getattr(projection_schema, "projection_schema_digest"),
                scalar_encoding_version=getattr(projection_schema, "scalar_encoding_version"),
            )
            projection_digest_parts_reused = True
        else:
            projection_logical_digest = build_projection_logical_digest(
                rows=cached_rows.rows,
                columns=cached_rows.columns,  # type: ignore[arg-type]
                projection_schema_digest=getattr(projection_schema, "projection_schema_digest"),
                row_identity_columns=row_identity_columns,
                scalar_encoding_version=getattr(projection_schema, "scalar_encoding_version"),
            )
            projection_digest_recompute_fallback = True
    projection_reader = ProjectionRowsReader(
        projection_schema=projection_schema,  # type: ignore[arg-type]
        columns=cached_rows.columns,  # type: ignore[arg-type]
        rows=cached_rows.rows,
        projection_logical_digest_parts=digest_parts,  # type: ignore[arg-type]
    )
    return (
        ProjectionTable(
            source_snapshot_digest=source_snapshot_digest,
            source_raw_content_digest=table.descriptor.raw_content_digest,
            source_table_name=table.descriptor.table_name,
            projection_schema=projection_schema,  # type: ignore[arg-type]
            row_count=len(cached_rows.rows),
            projection_logical_digest=projection_logical_digest,
            reader=projection_reader,
        ),
        {
            "projection_digest_parts_reused": projection_digest_parts_reused,
            "projection_digest_wrapper_only": projection_digest_parts_reused,
            "projection_digest_recompute_fallback": projection_digest_recompute_fallback,
        },
    )


def _summary_early_exit_reason(
    *,
    compute_input: ComparisonComputeInput,
    before_descriptor: SnapshotTableDescriptor,
    current_descriptor: SnapshotTableDescriptor,
) -> str | None:
    if not _descriptor_shape_equal(before_descriptor, current_descriptor):
        return None
    if compute_input.before.snapshot.snapshot_digest == compute_input.current.snapshot.snapshot_digest:
        return "SELF_SNAPSHOT"
    final_content_reason = _final_content_digest_match(before_descriptor, current_descriptor)
    if final_content_reason is not None:
        return final_content_reason
    if _provisional_fast_digest_match(before_descriptor, current_descriptor):
        return "PROVISIONAL_FAST_DIGEST"
    return None


def _descriptor_shape_equal(
    before_descriptor: SnapshotTableDescriptor,
    current_descriptor: SnapshotTableDescriptor,
) -> bool:
    return (
        before_descriptor.compare_schema_digest == current_descriptor.compare_schema_digest
        and before_descriptor.row_count == current_descriptor.row_count
        and before_descriptor.compare_key_columns == current_descriptor.compare_key_columns
    )


def _final_content_digest_match(
    before_descriptor: SnapshotTableDescriptor,
    current_descriptor: SnapshotTableDescriptor,
) -> str | None:
    if (
        before_descriptor.materialization_stage != "FINAL"
        or current_descriptor.materialization_stage != "FINAL"
    ):
        return None
    if (
        before_descriptor.canonical_artifact_ref is not None
        and current_descriptor.canonical_artifact_ref is not None
        and before_descriptor.canonical_artifact_ref == current_descriptor.canonical_artifact_ref
    ):
        return "FINAL_CONTENT_DIGEST"
    before_business = before_descriptor.business_content_digest
    current_business = current_descriptor.business_content_digest
    if before_business is not None and before_business == current_business:
        return "FINAL_CONTENT_DIGEST"
    before_raw = before_descriptor.raw_content_digest
    current_raw = current_descriptor.raw_content_digest
    if before_raw is not None and before_raw == current_raw:
        return "FINAL_CONTENT_DIGEST"
    return None


def _provisional_fast_digest_match(
    before_descriptor: SnapshotTableDescriptor,
    current_descriptor: SnapshotTableDescriptor,
) -> bool:
    if (
        before_descriptor.materialization_stage == "FINAL"
        and current_descriptor.materialization_stage == "FINAL"
    ):
        return False
    before_fast = before_descriptor.fast_row_digest
    current_fast = current_descriptor.fast_row_digest
    return before_fast is not None and before_fast == current_fast


def _early_exit_reason_from_diagnostics(
    diagnostics: Sequence[DiagnosticRecord],
) -> str | None:
    for diagnostic in diagnostics:
        if diagnostic.code == "comparison.summary-early-exit":
            reason = diagnostic.details.get("reason")
            return None if reason is None else str(reason)
    return None


def _degrade_reason_from_diagnostics(
    diagnostics: Sequence[DiagnosticRecord],
) -> str | None:
    for diagnostic in diagnostics:
        if diagnostic.code != "comparison.ordered.degraded":
            continue
        reason = diagnostic.details.get("reason")
        return None if reason is None else str(reason)
    return None


def _top_slow_table_events(
    table_events: Sequence[Mapping[str, object]],
    *,
    limit: int,
) -> list[dict[str, object]]:
    return [
        _compact_table_benchmark_event(event)
        for event in sorted(
            table_events,
            key=lambda item: (
                -(int(item.get("duration_ms") or 0)),
                str(item.get("table_name") or ""),
            ),
        )[:limit]
    ]


def _top_ordered_degraded_table_events(
    table_events: Sequence[Mapping[str, object]],
    *,
    limit: int,
) -> list[dict[str, object]]:
    ordered_degraded = [
        event
        for event in table_events
        if event.get("provider") == ORDERED_TABLE_COMPARE_PROVIDER
        and (event.get("degrade_reason") is not None or event.get("status") == "DEGRADED")
    ]
    return _top_slow_table_events(ordered_degraded, limit=limit)


def _compact_table_benchmark_event(event: Mapping[str, object]) -> dict[str, object]:
    keys = (
        "table_name",
        "provider",
        "status",
        "duration_ms",
        "row_count_before",
        "row_count_current",
        "records_count",
        "records_artifact",
        "degrade_reason",
        "early_exit_reason",
    )
    return {key: event[key] for key in keys if key in event and event[key] is not None}


def _benchmark_run_id(compute_input: ComparisonComputeInput) -> str | None:
    runtime_policy = compute_input.runtime_policy
    if not isinstance(runtime_policy, Mapping):
        return None
    value = runtime_policy.get("benchmark_run_id")
    return value if isinstance(value, str) and value else None


def _projection_table_cache_key(
    *,
    table: SnapshotTable,
    projection_schema: object,
) -> ProjectionTableCacheKey | None:
    from ...cache.projection_table import ProjectionTableCacheKey

    descriptor = table.descriptor
    raw_content_digest = descriptor.raw_content_digest
    if raw_content_digest is None:
        return None
    schema_digest = getattr(projection_schema, "projection_schema_digest", None)
    projection_contract_version = getattr(projection_schema, "projection_contract_version", None)
    scalar_encoding_version = getattr(projection_schema, "scalar_encoding_version", None)
    if schema_digest is None or projection_contract_version is None or scalar_encoding_version is None:
        return None
    return ProjectionTableCacheKey(
        source_raw_content_digest=raw_content_digest,
        projection_schema_digest=schema_digest,
        projection_contract_version=projection_contract_version,
        scalar_encoding_version=scalar_encoding_version,
    )


def _append_cache_diagnostic(
    cache_diagnostics: list[DiagnosticRecord] | None,
    *,
    code: str,
    message: str,
    severity: str,
    table_name: str,
    cache_key_digest: DigestRef,
    details: dict[str, object] | None = None,
) -> None:
    if cache_diagnostics is None:
        return
    payload = {
        "table_name": canonical_identifier(table_name),
        "cache_key_digest": cache_key_digest.to_payload(),
    }
    if details:
        payload.update(details)
    cache_diagnostics.append(
        DiagnosticRecord(
            code=code,
            message=message,
            phase="compare",
            severity=severity,
            details=payload,
        )
    )


def _table_for_name(table_set_ref: object | None, table_name: str) -> SnapshotTable | None:
    if table_set_ref is None:
        return None
    tables = getattr(table_set_ref, "tables", None)
    if not isinstance(tables, Mapping):
        return None
    return tables.get(canonical_identifier(table_name))  # type: ignore[return-value]


__all__ = [
    "ComparisonEngine",
    "compare",
]
