"""Shared comparison → risk → surface pipeline for preview and history jobs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import asdict, dataclass
import json
import logging
from time import perf_counter
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.computation_cache import CacheOperationOwner, ComputationCachePort
from gateway_backend.capabilities.risk_evaluation.persistence import PersistentRiskCandidates
from gateway_backend.artifacts.store import ArtifactStorePort, put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef

from gateway_backend.capabilities.project_identity import (
    ProjectIdentityAssessment,
    ProjectIdentityInput,
    ProjectIdentityStatus,
    assess_project_identity,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableSet
from gateway_backend.capabilities.snapshot_materialization import export_snapshot_table_parquet
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableExportCachePort
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonRequest,
    ComparisonPlan,
    DetailedFactsResult,
    DatasetReplacementResult,
    ComparisonFacts,
    ComparisonMode,
    ComparisonRecordsClosure,
    ComparisonTaskSession as ComparisonTaskSession,
    FailedResult,
    MAX_NATIVE_RECORD_BYTES,
    NativeComparison,
    plan_comparison,
    compare_plan_native as compare_plan_native,
    publish_records_closure_arrow as publish_records_closure_arrow,
    RecordsPublicationContext,
    RecordsPublicationPolicy,
    RecordsDetailPolicy,
)
from gateway_backend.capabilities.risk_evaluation.contracts import RiskEvaluation
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
    RiskExecutionContext,
    RiskEvaluationStatus,
    RiskOptions,
    RiskRulesetSnapshot,
    V1_RISK_RULE_SPECS,
    evaluate_risk,
)
from gateway_backend.capabilities.surface_assembly import (
    SurfaceAssemblyContext,
    SurfaceAssemblyInput,
    SurfaceAssemblyResult,
    SurfaceAssemblyStatus,
    SurfaceIdentityAnnotation,
    SurfaceArtifactIndexEntry,
    SurfaceTableRefs,
    SurfaceRefScope,
    assemble_surface,
)
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    ComparisonRuleSet,
)
from gateway_backend.capabilities.table_access import Reservation, current_kernel_context
from gateway_backend.operations.worker import ExecutionControl

PREVIEW_DEFAULT_VIEW_ID = "initial_to_modified"
_LOG = logging.getLogger(__name__)


class PairPipelineError(Exception):
    """Pair pipeline failed before the job-specific error wrapper."""


class PairPipelineCancelled(Exception):
    """Pair pipeline observed cancellation after publishing the operation terminal."""


@dataclass(frozen=True, slots=True)
class PreviewPairPipelineResult:
    pair_id: str
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    records_closure: ComparisonRecordsClosure | None
    surface_result: SurfaceAssemblyResult
    identity_assessment: ProjectIdentityAssessment | None
    identity_assessment_ref: ArtifactRef | None


@dataclass(frozen=True, slots=True)
class HistoryPairPipelineResult:
    pair_id: str
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    record_count: int
    records_closure: ComparisonRecordsClosure
    surface_result: SurfaceAssemblyResult


def preview_identity_assessment(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    *,
    before_table_set: SnapshotTableSet | None = None,
) -> ProjectIdentityAssessment:
    return assess_project_identity(
        ProjectIdentityInput(
            snapshot_digest=before.snapshot.snapshot_digest,
            table_set=before.table_set if before_table_set is None else before_table_set,
        ),
        ProjectIdentityInput(
            snapshot_digest=current.snapshot.snapshot_digest,
            table_set=current.table_set,
        ),
    )


def declare_pair_comparison_session(
    requests: tuple[ComparisonRequest, ...], *,
    computation_cache: ComputationCachePort | None = None,
    cache_owner: CacheOperationOwner | None = None, repository_id: str | None = None,
) -> ComparisonTaskSession | None:
    """Declare exactly the comparison tasks reachable in this operation."""
    plans: list[ComparisonPlan] = []
    for request in requests:
        plan = plan_comparison(request)
        if not isinstance(plan, ComparisonPlan):
            raise PairPipelineError("comparison task declaration failed")
        plans.append(plan)
    try:
        context = current_kernel_context()
        risk_persistence = (PersistentRiskCandidates(computation_cache, cache_owner, repository_id, context)
            if computation_cache is not None and cache_owner is not None
            and repository_id is not None and context is not None else None)
        return ComparisonTaskSession(tuple(plans), persistent_cache=computation_cache,
            persistent_owner=cache_owner, repository_id=repository_id, risk_persistence=risk_persistence)
    except MemoryError:
        # The optional reuse index may be denied by the same M budget. The
        # pair still executes normally with no retained comparison cache.
        return None


def run_preview_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    store: ArtifactStorePort,
    control: ExecutionControl,
    on_cancel: Callable[[], None],
    view_id: str = PREVIEW_DEFAULT_VIEW_ID,
    rule_set: ComparisonRuleSet | None = None,
    assess_identity: bool = True,
    identity_before_table_set: SnapshotTableSet | None = None,
    repository_id: str | None = None, export_cache: SnapshotTableExportCachePort | None = None,
    dedup_session: ComparisonTaskSession | None = None,
    table_exports: Mapping[str, Mapping[str, ArtifactRef]] | None = None,
) -> PreviewPairPipelineResult:
    assessment: ProjectIdentityAssessment | None = None
    assessment_ref = None
    if assess_identity:
        assessment = preview_identity_assessment(
            before,
            current,
            before_table_set=identity_before_table_set,
        )
        assessment_bytes = canonicalize_json_value(assessment.to_document())
        assessment_ref = put_with_built_ref(
            store,
            assessment_bytes,
            artifact_id=f"project-identity-{assessment.assessment_digest.value.removeprefix('sha256:')}",
            media_type="application/json",
        )
    active_rules = rule_set or comparison_rule_set(migrated_table_ruleset_snapshot())
    request = ComparisonRequest(
        pair_id=pair_id,
        before=before,
        current=current,
        rule_set=active_rules,
        mode=(
            ComparisonMode.DATASET_REPLACEMENT
            if assessment is not None and assessment.status is ProjectIdentityStatus.DIFFERENT_PROJECT
            else ComparisonMode.DETAILED
        ),
    )
    surface = _run_comparison_risk_surface(
        request=request,
        view_id=view_id,
        store=store,
        control=control,
        on_cancel=on_cancel,
        identity_annotation=SurfaceIdentityAnnotation(
            status="NOT_APPLICABLE" if assessment is None else assessment.status.value,
            assessment_digest=None if assessment is None else assessment.assessment_digest,
            assessment_ref=assessment_ref,
        ),
        show_keyless_fallback_hint=True,
        include_all_before_tables=False, repository_id=repository_id, export_cache=export_cache,
        dedup_session=dedup_session, table_exports=table_exports,
    )
    records_closure = surface.published.records_closure
    if (
        surface.comparison_facts.comparison_mode is ComparisonMode.DETAILED
        and records_closure is None
    ):
        raise PairPipelineError("records closure is missing")
    return PreviewPairPipelineResult(
        pair_id=pair_id,
        comparison_digest=surface.comparison_digest,
        risk_digest=surface.risk_digest,
        surface_digest=surface.surface_digest,
        records_closure=records_closure,
        surface_result=surface.surface_result,
        identity_assessment=assessment,
        identity_assessment_ref=assessment_ref,
    )


def run_history_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    rule_set: ComparisonRuleSet,
    store: ArtifactStorePort,
    control: ExecutionControl,
    on_cancel: Callable[[], None],
    repository_id: str | None = None, export_cache: SnapshotTableExportCachePort | None = None,
    dedup_session: ComparisonTaskSession | None = None,
    table_exports: Mapping[str, Mapping[str, ArtifactRef]] | None = None,
) -> HistoryPairPipelineResult:
    request = ComparisonRequest(
        pair_id=pair_id,
        before=before,
        current=current,
        rule_set=rule_set,
        mode=ComparisonMode.DETAILED,
    )
    surface = _run_comparison_risk_surface(
        request=request,
        view_id=pair_id,
        store=store,
        control=control,
        on_cancel=on_cancel,
        include_all_before_tables=True, repository_id=repository_id, export_cache=export_cache,
        dedup_session=dedup_session, table_exports=table_exports,
    )
    if not isinstance(surface.published, DetailedFactsResult):
        raise PairPipelineError("history comparison did not produce detailed facts")
    records_closure = surface.published.records_closure
    if records_closure is None:
        raise PairPipelineError("records closure is missing")
    record_count = sum(entry.record_count for entry in records_closure.records)
    if record_count < 0:
        raise PairPipelineError("records closure record_count is invalid")
    if surface.risk_evaluation is None:
        raise PairPipelineError("risk evaluation digest is missing")
    return HistoryPairPipelineResult(
        pair_id=pair_id,
        comparison_digest=surface.comparison_digest,
        risk_digest=surface.risk_evaluation.risk_evaluation_digest.value,
        surface_digest=surface.surface_digest,
        record_count=int(record_count),
        records_closure=records_closure,
        surface_result=surface.surface_result,
    )


@dataclass(frozen=True, slots=True)
class _ComparisonRiskSurfaceResult:
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    surface_result: SurfaceAssemblyResult
    published: DetailedFactsResult | DatasetReplacementResult
    comparison_facts: ComparisonFacts
    risk_evaluation: RiskEvaluation | None


def _run_comparison_risk_surface(
    *,
    request: ComparisonRequest,
    view_id: str,
    store: ArtifactStorePort,
    control: ExecutionControl,
    on_cancel: Callable[[], None],
    identity_annotation: SurfaceIdentityAnnotation | None = None,
    show_keyless_fallback_hint: bool = False,
    include_all_before_tables: bool = False,
    repository_id: str | None = None, export_cache: SnapshotTableExportCachePort | None = None,
    dedup_session: ComparisonTaskSession | None = None,
    table_exports: Mapping[str, Mapping[str, ArtifactRef]] | None = None,
) -> _ComparisonRiskSurfaceResult:
    context = current_kernel_context()
    checkpoint = context.checkpoint if context is not None else lambda: None
    checkpoint()
    plan = plan_comparison(request)
    checkpoint()
    if isinstance(plan, FailedResult):
        raise PairPipelineError(f"pair planning failed: {plan.diagnostics}")
    if not isinstance(plan, ComparisonPlan):
        raise PairPipelineError("pair planning did not produce a comparison plan")
    if context is None:
        raise PairPipelineError("pair computation requires an operation kernel context")
    comparison_started = perf_counter()
    with closing(compare_plan_native(plan, session=dedup_session)) as native_comparison:
        comparison_elapsed = perf_counter() - comparison_started
        return _finish_comparison_risk_surface(
            native_comparison=native_comparison, request=request,
            view_id=view_id, store=store, control=control,
            on_cancel=on_cancel, identity_annotation=identity_annotation,
            show_keyless_fallback_hint=show_keyless_fallback_hint,
            include_all_before_tables=include_all_before_tables,
            repository_id=repository_id, export_cache=export_cache,
            comparison_elapsed=comparison_elapsed, table_exports=table_exports,
        )


def _finish_comparison_risk_surface(
    *,
    native_comparison: NativeComparison,
    request: ComparisonRequest,
    view_id: str,
    store: ArtifactStorePort,
    control: ExecutionControl,
    on_cancel: Callable[[], None],
    identity_annotation: SurfaceIdentityAnnotation | None,
    show_keyless_fallback_hint: bool,
    include_all_before_tables: bool,
    repository_id: str | None,
    export_cache: SnapshotTableExportCachePort | None,
    comparison_elapsed: float,
    table_exports: Mapping[str, Mapping[str, ArtifactRef]] | None = None,
) -> _ComparisonRiskSurfaceResult:
    context = current_kernel_context()
    if context is None:
        raise PairPipelineError("operation kernel context was lost")
    checkpoint = context.checkpoint
    if native_comparison.session is not None:
        native_comparison.session.optional_comparison_evictor = native_comparison.discard_optional_views
    compared = native_comparison.result
    checkpoint()
    if isinstance(compared, FailedResult):
        raise PairPipelineError(f"pair comparison failed: {compared.diagnostics}")
    published: DetailedFactsResult | DatasetReplacementResult
    record_publication_started = perf_counter()
    record_timings: dict[str, float] = {}
    if isinstance(compared, DatasetReplacementResult):
        if compared.facts is None:
            raise PairPipelineError("replacement comparison did not produce facts")
        published = compared
        comparison_facts = compared.facts
    elif isinstance(compared, DetailedFactsResult) and compared.facts is not None:
        if native_comparison.session is not None:
            limits = RecordsPublicationPolicy()
            closure_upper = (
                4 * limits.max_closure_json_bytes
                + len(compared.facts.tables) * 4096 + 1024 * 1024
            )
            # C retains at most MAX_NATIVE_RECORD_BYTES of Arrow records per
            # family. The writer reserves its largest family scratch after
            # prior family puts, so shed optional Risk retention before any
            # publication side effect when the conservative peak is tight.
            family_upper = (
                2 * limits.max_records_artifact_bytes
                + 2 * MAX_NATIVE_RECORD_BYTES + 1024 * 1024
            )
            if context.memory.available_bytes < closure_upper + family_upper:
                native_comparison.session.risk_evict_for_output()
                checkpoint()
        detail_policy_value = dict(request.options).get(
            "row_diff_detail_policy", RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES.value,
        )
        if not isinstance(detail_policy_value, str):
            raise ValueError("row_diff_detail_policy is invalid")
        closure_result = publish_records_closure_arrow(
            compared, native_comparison.handles, store,
            detail_policy=RecordsDetailPolicy(detail_policy_value),
            context=RecordsPublicationContext(checkpoint=checkpoint, timings=record_timings),
        )
        checkpoint()
        if isinstance(closure_result, FailedResult):
            raise PairPipelineError(f"records closure failed: {closure_result.diagnostics}")
        if not isinstance(closure_result, DetailedFactsResult):
            raise PairPipelineError("records publication did not produce facts")
        closure_facts = closure_result.facts
        if closure_facts is None:
            raise PairPipelineError("records publication did not produce facts")
        published = closure_result
        comparison_facts = closure_facts
    else:
        raise PairPipelineError("pair comparison did not produce facts")
    record_publication_seconds = perf_counter() - record_publication_started
    if control.cancel_requested:
        on_cancel()
        raise PairPipelineCancelled
    risk_conversion: dict[str, float] = {}
    risk_started = perf_counter()
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=comparison_facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
            record_views=native_comparison.risk_handles,
            record_view_metrics=risk_conversion,
            risk_cache_session=native_comparison.session,
            risk_task_keys=native_comparison.task_keys,
        ),
        artifact_store=store,
        execution_context=RiskExecutionContext(
            cancel_requested=context.cancel_probe,
            deadline_monotonic=context.deadline_monotonic,
            operation=context,
        ),
    )
    risk_seconds = perf_counter() - risk_started
    checkpoint()
    if risk.status is not RiskEvaluationStatus.READY or risk.risk_report is None:
        raise PairPipelineError("risk evaluation failed")
    # Surface holds only small facts/refs; its JSON construction and retained
    # result still consume the same operation M after native records seal.
    surface_started = perf_counter()
    def reserve_surface(size: int) -> Reservation:
        try:
            return context.memory.reserve(size)
        except MemoryError:
            if native_comparison.session is None:
                raise
            native_comparison.session.risk_evict_for_output()
            context.checkpoint()
            return context.memory.reserve(size)

    context.resources.enter_context(reserve_surface(
        16 * 1024**2 + len(comparison_facts.tables) * 65536,
    ))
    with reserve_surface(8 * 16 * 1024**2):
        surface = assemble_surface(
        SurfaceAssemblyInput(
            comparison_facts=comparison_facts,
            surface_id=f"surface-{request.pair_id}",
            view_id=view_id,
            before_role="before",
            current_role="current",
            records_closure=published.records_closure,
            risk_report=risk.risk_report,
            risk_annotation_closure=risk.risk_closure,
            table_artifacts=(
                _surface_table_artifacts(
                    request, store=store, repository_id=repository_id, export_cache=export_cache,
                    table_exports=table_exports,
                    include_all_before=(
                        include_all_before_tables
                        or request.mode is ComparisonMode.DATASET_REPLACEMENT
                    ),
                )
            ),
            keyless_fallback_tables=(
                _keyless_fallback_table_names(request)
                if show_keyless_fallback_hint
                else ()
            ),
            ref_scope=SurfaceRefScope.OPERATION_RELATIVE,
            identity_annotation=identity_annotation or SurfaceIdentityAnnotation(),
        ),
        context=SurfaceAssemblyContext(cancel_requested=lambda: control.cancel_requested),
        )
    checkpoint()
    if surface.status is not SurfaceAssemblyStatus.READY or surface.surface is None:
        raise PairPipelineError("surface assembly failed")
    surface_seconds = perf_counter() - surface_started
    native_comparison.commit_cache()
    comparison_metrics = native_comparison.metrics
    measured = {} if comparison_metrics is None else asdict(comparison_metrics)
    native_seconds = (
        measured.get("native_input_read_seconds", 0.0)
        + measured.get("native_index_compare_seconds", 0.0)
        + measured.get("native_records_build_seconds", 0.0)
        + measured.get("ordered_current_summary_seconds", 0.0)
    )
    parquet_seconds = record_timings.get("parquet_write_seconds", 0.0)
    conversion_seconds = risk_conversion.get("necessary_arrow_conversion_seconds", 0.0)
    extraction_seconds = risk_conversion.get("fact_extraction_seconds", 0.0)
    validation_seconds = risk_conversion.get("ruleset_validation_seconds", 0.0)
    rules_seconds = risk_conversion.get("rules_evaluation_seconds", 0.0)
    publication_seconds = risk_conversion.get("publication_seconds", 0.0)
    _LOG.info("s3_pair_metrics %s", json.dumps({
        "pair_id": request.pair_id,
        "mode": request.mode.value,
        "comparison_total_seconds": comparison_elapsed,
        "comparison": measured,
        "comparison_kernel_calls": measured.get("native_calls", 0) - measured.get("ordered_single_side_calls", 0),
        "ordered_single_side_calls": measured.get("ordered_single_side_calls", 0),
        "diff_cache_lookups": measured.get("persistent_cache_lookups", 0),
        "cache_restore_calls": measured.get("cache_restores", 0),
        "cache_records_validation_calls": measured.get("cache_records_validations", 0),
        "digest_rebinds": measured.get("digest_rebinds", 0),
        "comparison_python_other_seconds": max(
            0.0, measured.get("compare_read_build_seconds", 0.0) - native_seconds,
        ),
        "upstream_projection_seconds": None,
        "records_publication_seconds": record_publication_seconds,
        "parquet_write_seconds": parquet_seconds,
        "records_publication_other_seconds": max(0.0, record_publication_seconds - parquet_seconds),
        "risk_total_seconds": risk_seconds,
        "risk_necessary_arrow_conversion_seconds": conversion_seconds,
        "risk_fact_extraction_seconds": extraction_seconds,
        "risk_ruleset_validation_seconds": validation_seconds,
        "risk_rules_evaluation_seconds": rules_seconds,
        "risk_publication_seconds": publication_seconds,
        "risk_digest_jcs_seconds": risk_conversion.get("digest_jcs_seconds", 0.0),
        "risk_report_jcs_seconds": risk_conversion.get("report_jcs_seconds", 0.0),
        "risk_artifact_publication_seconds": risk_conversion.get("artifact_publication_seconds", 0.0),
        "risk_other_seconds": max(
            0.0, risk_seconds - validation_seconds - extraction_seconds
            - rules_seconds - publication_seconds,
        ),
        "surface_and_table_export_seconds": surface_seconds,
        "bundle_assembly_seconds": None,
        "charged_high_water_bytes": context.memory.high_water_bytes,
        "charged_live_bytes": context.memory.used_bytes,
    }, sort_keys=True))
    risk_digest = (
        risk.risk_evaluation.risk_evaluation_digest.value if risk.risk_evaluation else ""
    )
    return _ComparisonRiskSurfaceResult(
        comparison_digest=comparison_facts.comparison_digest.value,
        risk_digest=risk_digest,
        surface_digest=surface.surface.surface_digest.value,
        surface_result=surface,
        published=published,
        comparison_facts=comparison_facts,
        risk_evaluation=risk.risk_evaluation,
    )


def _surface_table_artifacts(
    request: ComparisonRequest,
    *,
    include_all_before: bool,
    store: ArtifactStorePort | None = None, repository_id: str | None = None,
    export_cache: SnapshotTableExportCachePort | None = None,
    table_exports: Mapping[str, Mapping[str, ArtifactRef]] | None = None,
) -> tuple[SurfaceArtifactIndexEntry, ...]:
    def table_map(bound: BoundSnapshotInput) -> dict[str, ArtifactRef]:
        if bound.table_set is None:
            raise PairPipelineError("surface bundle requires canonical table artifacts")
        if table_exports is not None:
            artifacts = dict(table_exports.get(bound.snapshot.snapshot_id, {}))
            expected = {table.descriptor.table_name for table in bound.table_set.tables}
            if set(artifacts) != expected:
                raise PairPipelineError("prevalidated table exports do not cover the complete snapshot")
            return artifacts
        artifacts: dict[str, ArtifactRef] = {}
        for table in bound.table_set.tables:
            artifacts[table.descriptor.table_name] = export_snapshot_table_parquet(table, store=store,
                repository_id=repository_id, export_cache=export_cache)
        return artifacts

    before = table_map(request.before)
    current = table_map(request.current)
    if not include_all_before:
        before = {name: ref for name, ref in before.items() if name not in current}
    return tuple(
        SurfaceArtifactIndexEntry(
            table_name=table_name,
            table_refs=SurfaceTableRefs(
                before_table_ref=(
                    before.get(table_name)
                    or (
                        current.get(table_name)
                        if _same_complete_table_identity(
                            request.before,
                            request.current,
                            table_name,
                        )
                        else None
                    )
                ),
                current_table_ref=current.get(table_name),
            ),
        )
        for table_name in sorted(before.keys() | current.keys())
    )


def _same_complete_table_identity(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    table_name: str,
) -> bool:
    before_descriptor = next(
        (item for item in before.summary.tables if item.table_name == table_name),
        None,
    )
    current_descriptor = next(
        (item for item in current.summary.tables if item.table_name == table_name),
        None,
    )
    before_facts = next(
        (item for item in before.storage_facts if item.storage_rule_view.canonical_table == table_name),
        None,
    )
    current_facts = next(
        (item for item in current.storage_facts if item.storage_rule_view.canonical_table == table_name),
        None,
    )
    return (
        before_descriptor is not None
        and current_descriptor is not None
        and before_facts is not None
        and current_facts is not None
        and before_descriptor.business_schema_digest == current_descriptor.business_schema_digest
        and before_descriptor.row_count == current_descriptor.row_count
        and before_descriptor.raw_content_digest is not None
        and before_descriptor.raw_content_digest == current_descriptor.raw_content_digest
        and before_facts.storage_rule_view == current_facts.storage_rule_view
        and before_facts.source_schema_digest == current_facts.source_schema_digest
        and before_facts.canonical_schema_digest is not None
        and before_facts.canonical_schema_digest == current_facts.canonical_schema_digest
        and before_facts.raw_content_digest == before_descriptor.raw_content_digest
        and current_facts.raw_content_digest == current_descriptor.raw_content_digest
        and before_facts.storage_projection_version is not None
        and before_facts.storage_projection_version == current_facts.storage_projection_version
    )


def _keyless_fallback_table_names(request: ComparisonRequest) -> tuple[str, ...]:
    names: set[str] = set()
    for bound in (request.before, request.current):
        descriptors = {item.table_name: item for item in bound.summary.tables}
        for facts in bound.storage_facts:
            table_name = facts.storage_rule_view.canonical_table
            descriptor = descriptors.get(table_name)
            if (
                descriptor is not None
                and facts.storage_rule_view.canonical_key_policy
                is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS
                and not descriptor.primary_key_columns
            ):
                names.add(table_name)
    return tuple(
        sorted(names)
    )
