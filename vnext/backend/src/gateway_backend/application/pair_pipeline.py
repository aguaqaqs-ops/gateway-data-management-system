"""Shared comparison → risk → surface pipeline for preview and history jobs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput,
    ComparisonRequest,
    ComparisonPlan,
    DetailedFactsResult,
    ComparisonMode,
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
    SurfaceRefScope,
    assemble_surface,
)
from gateway_backend.capabilities.table_rules import comparison_rule_set, migrated_table_ruleset_snapshot
from gateway_backend.capabilities.table_rules.contracts import ComparisonRuleSet
from gateway_backend.operations.worker import ExecutionControl

PREVIEW_DEFAULT_VIEW_ID = "initial_to_modified"


class PreviewIdentityStatus(StrEnum):
    SAME_PROJECT = "SAME_PROJECT"
    DIFFERENT_PROJECT = "DIFFERENT_PROJECT"
    UNVERIFIABLE = "UNVERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PairPipelineError(Exception):
    """Pair pipeline failed before the job-specific error wrapper."""


@dataclass(frozen=True, slots=True)
class PreviewIdentityAssessment:
    schema_version: str
    rule_version: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    status: PreviewIdentityStatus
    assessment_digest: DigestRef
    comparable_columns: tuple[str, ...] = ()
    before_row_count: int = 0
    current_row_count: int = 0
    before_distinct_entry_count: int = 0
    current_distinct_entry_count: int = 0
    matched_entry_count: int = 0
    before_entry_set_digest: DigestRef | None = None
    current_entry_set_digest: DigestRef | None = None
    diagnostics: tuple[object, ...] = ()
    requires_continuation_confirmation: bool = False
    requires_submit_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class PreviewPairPipelineResult:
    pair_id: str
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    surface_result: SurfaceAssemblyResult


@dataclass(frozen=True, slots=True)
class HistoryPairPipelineResult:
    pair_id: str
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    record_count: int
    surface_result: SurfaceAssemblyResult


def preview_identity_assessment(
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
) -> PreviewIdentityAssessment:
    assessment_digest = raw_blob_digest(
        f"{before.snapshot.snapshot_digest.value}:{current.snapshot.snapshot_digest.value}".encode()
    )
    return PreviewIdentityAssessment(
        schema_version="project-identity-assessment/v1",
        rule_version="version-manager-overlap/v1",
        before_snapshot_digest=before.snapshot.snapshot_digest,
        current_snapshot_digest=current.snapshot.snapshot_digest,
        status=PreviewIdentityStatus.SAME_PROJECT,
        assessment_digest=assessment_digest,
    )


def run_preview_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    store: ArtifactStorePort,
    control: ExecutionControl,
    view_id: str = PREVIEW_DEFAULT_VIEW_ID,
    rule_set: ComparisonRuleSet | None = None,
) -> PreviewPairPipelineResult:
    assessment = preview_identity_assessment(before, current)
    active_rules = rule_set or comparison_rule_set(migrated_table_ruleset_snapshot())
    request = ComparisonRequest(
        pair_id=pair_id,
        before=before,
        current=current,
        rule_set=active_rules,
        mode=(
            ComparisonMode.DATASET_REPLACEMENT
            if assessment.status is PreviewIdentityStatus.DIFFERENT_PROJECT
            else ComparisonMode.DETAILED
        ),
    )
    surface = _run_comparison_risk_surface(
        request=request,
        view_id=view_id,
        store=store,
        control=control,
        cancel_message="preview pair pipeline cancelled",
        identity_annotation=SurfaceIdentityAnnotation(
            status=assessment.status.value,
            assessment_digest=assessment.assessment_digest,
        ),
    )
    return PreviewPairPipelineResult(
        pair_id=pair_id,
        comparison_digest=surface.comparison_digest,
        risk_digest=surface.risk_digest,
        surface_digest=surface.surface_digest,
        surface_result=surface.surface_result,
    )


def run_history_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    rule_set: ComparisonRuleSet,
    store: ArtifactStorePort,
    control: ExecutionControl,
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
        cancel_message="history compare pair pipeline cancelled",
    )
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
        surface_result=surface.surface_result,
    )


@dataclass(frozen=True, slots=True)
class _ComparisonRiskSurfaceResult:
    comparison_digest: str
    risk_digest: str
    surface_digest: str
    surface_result: SurfaceAssemblyResult
    published: DetailedFactsResult
    risk_evaluation: RiskEvaluation | None


def _run_comparison_risk_surface(
    *,
    request: ComparisonRequest,
    view_id: str,
    store: ArtifactStorePort,
    control: ExecutionControl,
    cancel_message: str,
    identity_annotation: SurfaceIdentityAnnotation | None = None,
) -> _ComparisonRiskSurfaceResult:
    plan = plan_comparison(request)
    if isinstance(plan, FailedResult):
        raise PairPipelineError(f"pair planning failed: {plan.diagnostics}")
    if not isinstance(plan, ComparisonPlan):
        raise PairPipelineError("pair planning did not produce a comparison plan")
    compared = compare_plan(plan)
    if isinstance(compared, FailedResult):
        raise PairPipelineError(f"pair comparison failed: {compared.diagnostics}")
    if not isinstance(compared, DetailedFactsResult) or compared.facts is None:
        raise PairPipelineError("pair comparison did not produce facts")
    published = publish_records_closure(compared, store)
    if isinstance(published, FailedResult):
        raise PairPipelineError(f"records closure failed: {published.diagnostics}")
    if not isinstance(published, DetailedFactsResult) or published.facts is None:
        raise PairPipelineError("records publication did not produce facts")
    if control.cancel_requested:
        raise PairPipelineError(cancel_message)
    risk = evaluate_risk(
        RiskEvaluationInput(
            comparison_facts=published.facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            risk_options=RiskOptions(),
        ),
        artifact_store=store,
    )
    if risk.status is not RiskEvaluationStatus.READY or risk.risk_report is None:
        raise PairPipelineError("risk evaluation failed")
    surface = assemble_surface(
        SurfaceAssemblyInput(
            comparison_facts=published.facts,
            surface_id=f"surface-{request.pair_id}",
            view_id=view_id,
            before_role="before",
            current_role="current",
            records_closure=published.records_closure,
            risk_report=risk.risk_report,
            risk_annotation_closure=risk.risk_closure,
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
        comparison_digest=published.facts.comparison_digest.value,
        risk_digest=risk_digest,
        surface_digest=surface.surface.surface_digest.value,
        surface_result=surface,
        published=published,
        risk_evaluation=risk.risk_evaluation,
    )
