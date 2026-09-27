"""Shared comparison → risk → surface pipeline for preview and history jobs."""

from __future__ import annotations

from dataclasses import dataclass
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    BaselineReconstructionResult,
    BaselineReconstructionStatus,
    BoundSnapshotInput,
    ComparisonPlan,
    DetailedFactsResult,
    FailedResult,
    PairExecutionInput,
    PairRole,
    PairViewKind,
    TrustedFlowApplicabilityBinding,
    bind_pair_input,
    compare_plan,
    plan_pair,
    publish_records_closure,
)
from gateway_backend.capabilities.risk_evaluation.contracts import RiskEvaluation
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonTablePolicy,
    IdentityStatus,
    InputCompleteness as ComparisonInputCompleteness,
)
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
    SurfaceRefScope,
    assemble_surface,
)
from gateway_backend.domain.workspace.models import InputCompleteness
from gateway_backend.operations.worker import ExecutionControl

PREVIEW_DEFAULT_VIEW_ID = "initial_to_modified"


class PairPipelineError(Exception):
    """Pair pipeline failed before the job-specific error wrapper."""


@dataclass(frozen=True, slots=True)
class PreviewIdentityAssessment:
    schema_version: str
    rule_version: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    status: IdentityStatus
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
        status=IdentityStatus.SAME_PROJECT,
        assessment_digest=assessment_digest,
    )


def run_preview_pair_pipeline(
    *,
    pair_id: str,
    before: BoundSnapshotInput,
    current: BoundSnapshotInput,
    pair_role: PairRole,
    input_completeness: InputCompleteness,
    baseline: BoundSnapshotInput | None,
    store: ArtifactStorePort,
    control: ExecutionControl,
    view_id: str = PREVIEW_DEFAULT_VIEW_ID,
) -> PreviewPairPipelineResult:
    assessment = preview_identity_assessment(before, current)
    baseline_reconstruction = None
    if input_completeness is InputCompleteness.MODIFIED_ONLY and baseline is not None:
        baseline_reconstruction = BaselineReconstructionResult(
            status=BaselineReconstructionStatus.AVAILABLE,
            baseline=baseline,
        )
    bound = bind_pair_input(
        pair_id=pair_id,
        view_kind=PairViewKind.PAIR_COMPARISON,
        pair_role=pair_role,
        before=before if input_completeness is InputCompleteness.FULL else None,
        current=current,
        input_completeness=(
            ComparisonInputCompleteness.FULL
            if input_completeness is InputCompleteness.FULL
            else ComparisonInputCompleteness.MODIFIED_ONLY
        ),
        artifact_scope=ArtifactScope.ALL_CHANGES,
        identity_assessment=assessment,
        baseline_reconstruction=baseline_reconstruction,
    )
    surface = _run_comparison_risk_surface(
        bound=bound,
        pair_id=pair_id,
        view_id=view_id,
        store=store,
        control=control,
        cancel_message="preview pair pipeline cancelled",
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
    table_policies: tuple[ComparisonTablePolicy, ...],
    trusted_flow_binding: TrustedFlowApplicabilityBinding,
    store: ArtifactStorePort,
    control: ExecutionControl,
) -> HistoryPairPipelineResult:
    bound = bind_pair_input(
        pair_id=pair_id,
        view_kind=PairViewKind.HISTORY,
        pair_role=PairRole.HISTORY,
        before=before,
        current=current,
        input_completeness=ComparisonInputCompleteness.FULL,
        artifact_scope=ArtifactScope.ALL_CHANGES,
        trusted_flow_binding=trusted_flow_binding,
        table_policies=table_policies,
    )
    surface = _run_comparison_risk_surface(
        bound=bound,
        pair_id=pair_id,
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
    bound: PairExecutionInput | FailedResult,
    pair_id: str,
    view_id: str,
    store: ArtifactStorePort,
    control: ExecutionControl,
    cancel_message: str,
) -> _ComparisonRiskSurfaceResult:
    if isinstance(bound, FailedResult):
        raise PairPipelineError(f"pair binding failed: {bound.diagnostics}")
    plan = plan_pair(bound)
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
            surface_id=f"surface-{pair_id}",
            view_id=view_id,
            before_role="before",
            current_role="current",
            records_closure=published.records_closure,
            risk_report=risk.risk_report,
            risk_annotation_closure=risk.risk_closure,
            ref_scope=SurfaceRefScope.OPERATION_RELATIVE,
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
