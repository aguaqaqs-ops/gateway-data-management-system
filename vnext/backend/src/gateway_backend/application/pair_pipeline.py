"""Shared comparison → risk → surface pipeline for preview and history jobs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.store import ArtifactStorePort, put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef

from gateway_backend.capabilities.project_identity import (
    ProjectIdentityAssessment,
    ProjectIdentityInput,
    ProjectIdentityStatus,
    assess_project_identity,
)
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonRequest,
    ComparisonPlan,
    DetailedFactsResult,
    DatasetReplacementResult,
    ComparisonFacts,
    ComparisonMode,
    ComparisonRecordsClosure,
    FailedResult,
    compare_plan,
    plan_comparison,
    publish_records_closure,
)
from gateway_backend.capabilities.risk_evaluation.contracts import RiskEvaluation
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput,
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
from gateway_backend.operations.worker import ExecutionControl

PREVIEW_DEFAULT_VIEW_ID = "initial_to_modified"


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
) -> ProjectIdentityAssessment:
    return assess_project_identity(
        ProjectIdentityInput(
            snapshot_digest=before.snapshot.snapshot_digest,
            table_set=before.table_set,
        ),
        ProjectIdentityInput(
            snapshot_digest=current.snapshot.snapshot_digest,
            table_set=current.table_set,
        ),
    )


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
) -> PreviewPairPipelineResult:
    assessment: ProjectIdentityAssessment | None = None
    assessment_ref = None
    if assess_identity:
        assessment = preview_identity_assessment(before, current)
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
) -> _ComparisonRiskSurfaceResult:
    plan = plan_comparison(request)
    if isinstance(plan, FailedResult):
        raise PairPipelineError(f"pair planning failed: {plan.diagnostics}")
    if not isinstance(plan, ComparisonPlan):
        raise PairPipelineError("pair planning did not produce a comparison plan")
    compared = compare_plan(plan)
    if isinstance(compared, FailedResult):
        raise PairPipelineError(f"pair comparison failed: {compared.diagnostics}")
    published: DetailedFactsResult | DatasetReplacementResult
    if isinstance(compared, DatasetReplacementResult):
        if compared.facts is None:
            raise PairPipelineError("replacement comparison did not produce facts")
        published = compared
        comparison_facts = compared.facts
    elif isinstance(compared, DetailedFactsResult) and compared.facts is not None:
        closure_result = publish_records_closure(compared, store)
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
    if control.cancel_requested:
        on_cancel()
        raise PairPipelineCancelled
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=comparison_facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=store,
    )
    if risk.status is not RiskEvaluationStatus.READY or risk.risk_report is None:
        raise PairPipelineError("risk evaluation failed")
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
                _replacement_surface_table_artifacts(request)
                if request.mode is ComparisonMode.DATASET_REPLACEMENT
                else ()
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
    if surface.status is not SurfaceAssemblyStatus.READY or surface.surface is None:
        raise PairPipelineError("surface assembly failed")
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


def _replacement_surface_table_artifacts(
    request: ComparisonRequest,
) -> tuple[SurfaceArtifactIndexEntry, ...]:
    def table_map(bound: BoundSnapshotInput) -> dict[str, ArtifactRef]:
        if bound.table_set is None:
            raise PairPipelineError("replacement surface requires canonical table artifacts")
        artifacts: dict[str, ArtifactRef] = {}
        for table in bound.table_set.tables:
            if table.artifact is None:
                raise PairPipelineError(
                    f"replacement surface table {table.descriptor.table_name} is missing its artifact"
                )
            artifacts[table.descriptor.table_name] = table.artifact.manifest_ref
        return artifacts

    before = table_map(request.before)
    current = table_map(request.current)
    return tuple(
        SurfaceArtifactIndexEntry(
            table_name=table_name,
            table_refs=SurfaceTableRefs(
                before_table_ref=before.get(table_name),
                current_table_ref=current.get(table_name),
            ),
        )
        for table_name in sorted(before.keys() | current.keys())
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
