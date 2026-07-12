from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter

from ..core.digests import DigestRef
from ..capabilities.business_projection import BusinessProjectionResult
from ..capabilities.comparison import ComparisonComputeResult, ComparisonEngine
from ..capabilities.risk_evaluation import (
    RiskEngine,
    RiskEvaluationResult,
    RiskOptions,
    RiskRuleRegistry,
    build_hardcoded_risk_ruleset_registry,
)
from ..capabilities.surface_assembly import ComparisonSurfaceAssemblyInput, ComparisonSurfaceAssemblyResult, SurfaceAssembler
from ..capabilities.comparison.models import ComparisonComputeInput
from ..artifacts import LocalArtifactStore
from ..cache.comparison_core import ComparisonCoreCache
from ..cache.projection_table import ProjectionTableCache
from ..formal_upload_benchmark import benchmark_elapsed_ms, log_formal_upload_benchmark_event
from ..operations import (
    OperationCallerType,
    OperationKind,
    OperationParallelPolicy,
    OperationPlan,
    OperationRecord,
    OperationRuntime,
    OperationRunResult,
    OperationStepContext,
    OperationStepOutcome,
    OperationStepPlan,
)
from .comparison_risk import (
    ComparisonRiskFlowInput,
    ComparisonRiskFlowResult,
    compare_and_evaluate_risk,
    complete_comparison_core_cache,
)
from .business_projection import assemble_business_projection_for_surface


@dataclass(frozen=True, slots=True)
class UploadPreviewFlowInput:
    comparison_input: ComparisonComputeInput
    risk_ruleset_id: str | None = None
    risk_ruleset_registry: RiskRuleRegistry = field(default_factory=build_hardcoded_risk_ruleset_registry)
    risk_options: RiskOptions = field(default_factory=RiskOptions)
    records_store: LocalArtifactStore | None = None
    comparison_engine: ComparisonEngine = field(default_factory=ComparisonEngine)
    comparison_core_cache: ComparisonCoreCache | None = None
    projection_table_cache: ProjectionTableCache | None = None
    risk_engine: RiskEngine = field(default_factory=RiskEngine)
    surface_assembler: SurfaceAssembler = field(default_factory=SurfaceAssembler)
    operation_runtime: OperationRuntime = field(default_factory=OperationRuntime)
    worker_id: str = "upload-preview-worker"
    operation_id: str | None = None
    complete_comparison_core_cache_sync: bool = True
    benchmark_run_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.comparison_input, ComparisonComputeInput):
            raise TypeError("comparison_input must be a ComparisonComputeInput")
        if self.risk_ruleset_id is not None and not isinstance(self.risk_ruleset_id, str):
            raise TypeError("risk_ruleset_id must be a string or None")
        if not isinstance(self.risk_ruleset_registry, RiskRuleRegistry):
            raise TypeError("risk_ruleset_registry must be a RiskRuleRegistry")
        if not isinstance(self.risk_options, RiskOptions):
            raise TypeError("risk_options must be a RiskOptions")
        if self.records_store is not None and not isinstance(self.records_store, LocalArtifactStore):
            raise TypeError("records_store must be a LocalArtifactStore or None")
        if not isinstance(self.comparison_engine, ComparisonEngine):
            raise TypeError("comparison_engine must be a ComparisonEngine")
        if self.comparison_core_cache is not None and not isinstance(self.comparison_core_cache, ComparisonCoreCache):
            raise TypeError("comparison_core_cache must be a ComparisonCoreCache or None")
        if self.projection_table_cache is not None and not isinstance(self.projection_table_cache, ProjectionTableCache):
            raise TypeError("projection_table_cache must be a ProjectionTableCache or None")
        if not isinstance(self.risk_engine, RiskEngine):
            raise TypeError("risk_engine must be a RiskEngine")
        if not isinstance(self.surface_assembler, SurfaceAssembler):
            raise TypeError("surface_assembler must be a SurfaceAssembler")
        if not isinstance(self.operation_runtime, OperationRuntime):
            raise TypeError("operation_runtime must be an OperationRuntime")
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("worker_id must be a non-empty string")
        if self.operation_id is not None and not isinstance(self.operation_id, str):
            raise TypeError("operation_id must be a string or None")
        if not isinstance(self.complete_comparison_core_cache_sync, bool):
            raise TypeError("complete_comparison_core_cache_sync must be a bool")
        if self.benchmark_run_id is not None and not isinstance(self.benchmark_run_id, str):
            raise TypeError("benchmark_run_id must be a string or None")

    def comparison_risk_input(self) -> ComparisonRiskFlowInput:
        return ComparisonRiskFlowInput(
            comparison_input=self.comparison_input,
            risk_ruleset_id=self.risk_ruleset_id,
            risk_ruleset_registry=self.risk_ruleset_registry,
            risk_options=self.risk_options,
            records_store=self.records_store,
            comparison_engine=self.comparison_engine,
            comparison_core_cache=self.comparison_core_cache,
            projection_table_cache=self.projection_table_cache,
            risk_engine=self.risk_engine,
            benchmark_run_id=self.benchmark_run_id,
        )


@dataclass(frozen=True, slots=True)
class UploadPreviewFlowResult:
    operation: OperationRecord
    run_result: OperationRunResult
    comparison_result: ComparisonComputeResult
    risk_result: RiskEvaluationResult
    surface_result: ComparisonSurfaceAssemblyResult
    business_projection_result: BusinessProjectionResult | None = None
    comparison_risk_result: ComparisonRiskFlowResult | None = None
    surface_duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationRecord):
            raise TypeError("operation must be an OperationRecord")
        if not isinstance(self.run_result, OperationRunResult):
            raise TypeError("run_result must be an OperationRunResult")
        if not isinstance(self.comparison_result, ComparisonComputeResult):
            raise TypeError("comparison_result must be a ComparisonComputeResult")
        if not isinstance(self.risk_result, RiskEvaluationResult):
            raise TypeError("risk_result must be a RiskEvaluationResult")
        if self.business_projection_result is not None and not isinstance(
            self.business_projection_result,
            BusinessProjectionResult,
        ):
            raise TypeError("business_projection_result must be a BusinessProjectionResult or None")
        if self.comparison_risk_result is not None and not isinstance(
            self.comparison_risk_result,
            ComparisonRiskFlowResult,
        ):
            raise TypeError("comparison_risk_result must be a ComparisonRiskFlowResult or None")
        if not isinstance(self.surface_result, ComparisonSurfaceAssemblyResult):
            raise TypeError("surface_result must be a ComparisonSurfaceAssemblyResult")
        if self.surface_duration_ms is not None and (
            not isinstance(self.surface_duration_ms, int)
            or isinstance(self.surface_duration_ms, bool)
            or self.surface_duration_ms < 0
        ):
            raise ValueError("surface_duration_ms must be a non-negative integer or None")


def run_upload_preview(flow_input: UploadPreviewFlowInput) -> UploadPreviewFlowResult:
    if not isinstance(flow_input, UploadPreviewFlowInput):
        raise TypeError("flow_input must be an UploadPreviewFlowInput")

    comparison_result: ComparisonComputeResult | None = None
    risk_result: RiskEvaluationResult | None = None
    comparison_risk_result: ComparisonRiskFlowResult | None = None
    surface_result: ComparisonSurfaceAssemblyResult | None = None
    business_projection_result: BusinessProjectionResult | None = None
    surface_duration_ms: int | None = None

    steps = [
        OperationStepPlan(step_name="LOAD_INPUT"),
        OperationStepPlan(step_name="COMPUTE_ANALYTICS", retryable=True),
        OperationStepPlan(step_name="ASSEMBLE_SURFACE", retryable=True),
        OperationStepPlan(step_name="PUBLISH_RESULT"),
    ]
    if flow_input.complete_comparison_core_cache_sync:
        steps.append(
            OperationStepPlan(step_name="ASYNC_COMPARISON_CORE_CACHE_COMPLETION", retryable=True)
        )
    steps.append(OperationStepPlan(step_name="CLEANUP"))

    plan = OperationPlan(
        operation_kind=OperationKind.UPLOAD_PREVIEW,
        caller_type=OperationCallerType.DIRECT_RESPONSE_CALLER,
        parallel_policy=OperationParallelPolicy.SERIAL,
        request_payload=_preview_request_payload(flow_input),
        steps=tuple(steps),
    )
    operation = flow_input.operation_runtime.create_operation(
        plan,
        operation_id=flow_input.operation_id,
    )

    def load_input(context: OperationStepContext) -> OperationStepOutcome:
        return OperationStepOutcome.success(
            value={
                "comparison_contract_version": flow_input.comparison_input.comparison_contract_version,
                "projection_contract_version": flow_input.comparison_input.projection_contract_version,
                "before_snapshot_digest": flow_input.comparison_input.before.snapshot.snapshot_digest,
                "current_snapshot_digest": flow_input.comparison_input.current.snapshot.snapshot_digest,
            }
        )

    def compute_analytics(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal comparison_result, risk_result, comparison_risk_result
        compare_input = flow_input.comparison_risk_input()
        analytics_started_at = perf_counter()
        comparison_and_risk = compare_and_evaluate_risk(
            compare_input,
            comparison_core_cache_write=False,
        )
        comparison_risk_result = comparison_and_risk
        comparison_result = comparison_and_risk.comparison_result
        risk_result = comparison_and_risk.risk_result
        log_formal_upload_benchmark_event(
            "upload_preview.compute_analytics",
            benchmark_run_id=flow_input.benchmark_run_id,
            comparison_duration_ms=comparison_and_risk.comparison_duration_ms,
            risk_duration_ms=comparison_and_risk.risk_duration_ms,
            comparison_table_count=comparison_result.summary.table_count,
            comparison_records_artifacts=len(comparison_result.records_artifacts),
            risk_table_count=len(risk_result.risk_report.tables),
            blocking_preview_ready=True,
            duration_ms=benchmark_elapsed_ms(analytics_started_at),
        )
        return OperationStepOutcome.success(
            value={
                "comparison_digest": comparison_result.facts.comparison_digest.to_payload(),
                "comparison_table_count": comparison_result.summary.table_count,
                "comparison_records_artifacts": len(comparison_result.records_artifacts),
                "risk_evaluation_digest": risk_result.risk_evaluation.risk_evaluation_digest.to_payload(),
                "risk_table_count": len(risk_result.risk_report.tables),
            }
        )

    def async_comparison_core_cache_completion(context: OperationStepContext) -> OperationStepOutcome:
        if comparison_result is None:
            raise RuntimeError("comparison result must be available before comparison core cache completion")
        completion_details, completion_diagnostics = complete_upload_preview_cache(
            flow_input=flow_input,
            comparison_result=comparison_result,
        )
        return OperationStepOutcome.success(
            value=completion_details,
            diagnostics=completion_diagnostics,
        )

    def assemble_surface(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal business_projection_result, surface_result, surface_duration_ms
        if comparison_result is None or risk_result is None:
            raise RuntimeError("comparison and risk results must be available before surface assembly")
        surface_request = ComparisonSurfaceAssemblyInput(
            comparison_facts=comparison_result.facts,
            records_closure=comparison_result.facts.records_ref,
            risk_report=risk_result.risk_report,
        )
        surface_start = perf_counter()
        base_surface_result = flow_input.surface_assembler.assemble(surface_request)
        projection_started_at = perf_counter()
        business_projection_result = assemble_business_projection_for_surface(
            comparison_input=flow_input.comparison_input,
            comparison_surface=base_surface_result.comparison_surface,
        )
        log_formal_upload_benchmark_event(
            "upload_preview.business_projection",
            benchmark_run_id=flow_input.benchmark_run_id,
            projection_count=len(business_projection_result.projections),
            diagnostics_count=len(business_projection_result.diagnostics),
            blocking_preview_ready=True,
            duration_ms=benchmark_elapsed_ms(projection_started_at),
        )
        surface_result = flow_input.surface_assembler.assemble(
            ComparisonSurfaceAssemblyInput(
                comparison_facts=comparison_result.facts,
                records_closure=comparison_result.facts.records_ref,
                risk_report=risk_result.risk_report,
                business_projection_result=business_projection_result,
            )
        )
        surface_duration_ms = _elapsed_ms(surface_start)
        log_formal_upload_benchmark_event(
            "upload_preview.surface_assembly",
            benchmark_run_id=flow_input.benchmark_run_id,
            surface_table_count=surface_result.comparison_surface.view.table_count,
            blocking_preview_ready=True,
            duration_ms=surface_duration_ms,
        )
        return OperationStepOutcome.success(
            value={
                "surface_digest": surface_result.surface_digest.to_payload(),
                "surface_table_count": surface_result.comparison_surface.view.table_count,
                "surface_risk_level": surface_result.comparison_surface.summary.risk_level.value
                if surface_result.comparison_surface.summary.risk_level is not None
                else None,
            }
        )

    def publish_result(context: OperationStepContext) -> OperationStepOutcome:
        if comparison_result is None or risk_result is None or surface_result is None:
            raise RuntimeError("preview results must be available before publish")
        publish_started_at = perf_counter()
        ready_payload = _preview_ready_payload(
            comparison_result=comparison_result,
            risk_result=risk_result,
            surface_result=surface_result,
        )
        digest_started_at = perf_counter()
        ready_closure_digest = DigestRef.from_payload(ready_payload)
        log_formal_upload_benchmark_event(
            "upload_preview.publish_result",
            benchmark_run_id=flow_input.benchmark_run_id,
            blocking_preview_ready=True,
            ready_closure_digest_ms=benchmark_elapsed_ms(digest_started_at),
            duration_ms=benchmark_elapsed_ms(publish_started_at),
        )
        return OperationStepOutcome.success(
            value=ready_payload,
            ready_closure_digest=ready_closure_digest,
        )

    def cleanup(context: OperationStepContext) -> OperationStepOutcome:
        # Cleanup only releases transient resources; durable outputs are retained by policy.
        return OperationStepOutcome.success(value={"cleanup": "noop"})

    handlers = {
            "LOAD_INPUT": load_input,
            "COMPUTE_ANALYTICS": compute_analytics,
            "ASSEMBLE_SURFACE": assemble_surface,
            "PUBLISH_RESULT": publish_result,
            "CLEANUP": cleanup,
    }
    if flow_input.complete_comparison_core_cache_sync:
        handlers["ASYNC_COMPARISON_CORE_CACHE_COMPLETION"] = async_comparison_core_cache_completion

    run_result = flow_input.operation_runtime.run_operation(
        operation.operation_id,
        handlers=handlers,
        worker_id=flow_input.worker_id,
    )

    if comparison_result is None or risk_result is None or surface_result is None:
        raise RuntimeError("preview operation completed without required results")

    return UploadPreviewFlowResult(
        operation=run_result.operation,
        run_result=run_result,
        comparison_result=comparison_result,
        risk_result=risk_result,
        comparison_risk_result=comparison_risk_result,
        surface_result=surface_result,
        business_projection_result=business_projection_result,
        surface_duration_ms=surface_duration_ms,
    )


def complete_upload_preview_cache(
    *,
    flow_input: UploadPreviewFlowInput,
    comparison_result: ComparisonComputeResult,
) -> tuple[dict[str, object], tuple[object, ...]]:
    completion_start = perf_counter()
    completion_details, completion_diagnostics = complete_comparison_core_cache(
        flow_input.comparison_risk_input(),
        comparison_result,
    )
    completion_details = dict(completion_details)
    completion_status = str(completion_details.get("comparison_core_cache_status"))
    completion_lookup_hit = completion_details.get("comparison_core_cache_lookup_hit")
    completion_write_applied = bool(completion_details.get("comparison_core_cache_write_applied"))
    completion_details["comparison_core_cache_completion_write_count"] = 1 if completion_write_applied else 0
    completion_details["comparison_core_cache_completion_hit_count"] = 1 if completion_lookup_hit is True else 0
    completion_details["comparison_core_cache_completion_skip_count"] = (
        1 if completion_status in {"SKIPPED", "LOOKUP_FAILED", "WRITE_SKIPPED", "WRITE_FAILED"} else 0
    )
    completion_details["comparison_core_cache_completion_ms"] = _elapsed_ms(completion_start)
    log_formal_upload_benchmark_event(
        "upload_preview.cache_completion",
        benchmark_run_id=flow_input.benchmark_run_id,
        comparison_core_cache_status=completion_status,
        comparison_core_cache_lookup_hit=completion_lookup_hit,
        comparison_core_cache_write_applied=completion_write_applied,
        blocking_preview_ready=flow_input.complete_comparison_core_cache_sync,
        duration_ms=completion_details["comparison_core_cache_completion_ms"],
    )
    return completion_details, tuple(completion_diagnostics)


def _preview_request_payload(flow_input: UploadPreviewFlowInput) -> Mapping[str, object]:
    comparison_input = flow_input.comparison_input
    payload: dict[str, object] = {
        "operation_kind": OperationKind.UPLOAD_PREVIEW.value,
        "caller_type": OperationCallerType.DIRECT_RESPONSE_CALLER.value,
        "comparison_contract_version": comparison_input.comparison_contract_version,
        "projection_contract_version": comparison_input.projection_contract_version,
        "before_snapshot_digest": comparison_input.before.snapshot.snapshot_digest.to_payload(),
        "current_snapshot_digest": comparison_input.current.snapshot.snapshot_digest.to_payload(),
        "requested_tables": list(comparison_input.requested_tables),
        "risk_ruleset_id": flow_input.risk_ruleset_id,
    }
    if comparison_input.table_ruleset is not None:
        payload["table_ruleset_version"] = comparison_input.table_ruleset.ruleset_version
        payload["table_ruleset_digest"] = comparison_input.table_ruleset.ruleset_digest.to_payload()
    elif comparison_input.table_ruleset_version is not None:
        payload["table_ruleset_version"] = comparison_input.table_ruleset_version
    if comparison_input.scalar_encoding_version is not None:
        payload["scalar_encoding_version"] = comparison_input.scalar_encoding_version
    return payload


def _preview_ready_payload(
    *,
    comparison_result: ComparisonComputeResult,
    risk_result: RiskEvaluationResult,
    surface_result: ComparisonSurfaceAssemblyResult,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "comparison_digest": comparison_result.facts.comparison_digest.to_payload(),
        "risk_evaluation_digest": risk_result.risk_evaluation.risk_evaluation_digest.to_payload(),
        "surface_digest": surface_result.surface_digest.to_payload(),
    }
    return payload


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
