from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from time import perf_counter

from ..capabilities.bundle_assembly import (
    BundleAssemblyInput,
    BundleAssemblyResult,
    BundleAssembler,
    BundleInput,
    BundlePairArtifactClosure,
    BundlePairAssemblyInput,
    BundleProfile,
)
from ..capabilities.comparison import ComparisonComputeResult
from ..capabilities.comparison.models import ComparisonComputeInput
from ..capabilities.business_projection import BusinessProjectionResult
from ..capabilities.snapshot_materialization import SnapshotSummary, build_canonical_table_aliases
from ..capabilities.risk_evaluation import RiskEvaluationResult
from ..capabilities.surface_assembly import (
    ComparisonSurfaceAssemblyInput,
    ComparisonSurfaceAssemblyResult,
    SurfaceAssembler,
)
from ..cache.projection_table import ProjectionTableCache
from ..capabilities.comparison.models import RepositoryBackedComparisonContext
from ..contracts import CacheLookupPolicy
from ..core import DiagnosticRecord
from ..core.digests import DigestRef
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


def build_history_compare_pair_input(
    *,
    pair_id: str,
    before_input_index: int,
    current_input_index: int,
    comparison_flow_input: ComparisonRiskFlowInput,
    before_repository_backed_context: RepositoryBackedComparisonContext | None = None,
    current_repository_backed_context: RepositoryBackedComparisonContext | None = None,
    surface_assembler: SurfaceAssembler | None = None,
) -> "HistoryComparePairInput":
    if not isinstance(comparison_flow_input, ComparisonRiskFlowInput):
        raise TypeError("comparison_flow_input must be a ComparisonRiskFlowInput")
    effective_surface_assembler = surface_assembler or SurfaceAssembler()
    if not isinstance(effective_surface_assembler, SurfaceAssembler):
        raise TypeError("surface_assembler must be a SurfaceAssembler or None")
    return HistoryComparePairInput(
        pair_id=pair_id,
        before_input_index=before_input_index,
        current_input_index=current_input_index,
        comparison_flow_input=comparison_flow_input.with_repository_backed_context(
            before_repository_backed_context=before_repository_backed_context,
            current_repository_backed_context=current_repository_backed_context,
        ).with_comparison_core_cache_lookup_policy(
            CacheLookupPolicy.READ_COMMIT_VALIDATED_ONLY
        ),
        surface_assembler=effective_surface_assembler,
    )


@dataclass(frozen=True, slots=True)
class HistoryComparePairInput:
    pair_id: str
    before_input_index: int
    current_input_index: int
    comparison_flow_input: ComparisonRiskFlowInput
    surface_assembler: SurfaceAssembler = field(default_factory=SurfaceAssembler)

    def __post_init__(self) -> None:
        if not isinstance(self.pair_id, str) or not self.pair_id:
            raise ValueError("pair_id must be a non-empty string")
        for field_name in ("before_input_index", "current_input_index"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.comparison_flow_input, ComparisonRiskFlowInput):
            raise TypeError("comparison_flow_input must be a ComparisonRiskFlowInput")
        if not isinstance(self.surface_assembler, SurfaceAssembler):
            raise TypeError("surface_assembler must be a SurfaceAssembler")


@dataclass(frozen=True, slots=True)
class HistoryComparePairResult:
    pair_id: str
    before_input_index: int
    current_input_index: int
    comparison_result: ComparisonComputeResult
    risk_result: RiskEvaluationResult
    surface_result: ComparisonSurfaceAssemblyResult
    business_projection_result: BusinessProjectionResult | None = None
    comparison_risk_result: ComparisonRiskFlowResult | None = None
    before_summary: SnapshotSummary | None = None
    current_summary: SnapshotSummary | None = None
    surface_duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pair_id, str) or not self.pair_id:
            raise ValueError("pair_id must be a non-empty string")
        for field_name in ("before_input_index", "current_input_index"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.comparison_result, ComparisonComputeResult):
            raise TypeError("comparison_result must be a ComparisonComputeResult")
        if not isinstance(self.risk_result, RiskEvaluationResult):
            raise TypeError("risk_result must be a RiskEvaluationResult")
        if self.comparison_risk_result is not None and not isinstance(
            self.comparison_risk_result,
            ComparisonRiskFlowResult,
        ):
            raise TypeError("comparison_risk_result must be a ComparisonRiskFlowResult or None")
        if not isinstance(self.surface_result, ComparisonSurfaceAssemblyResult):
            raise TypeError("surface_result must be a ComparisonSurfaceAssemblyResult")
        if self.business_projection_result is not None and not isinstance(self.business_projection_result, BusinessProjectionResult):
            raise TypeError("business_projection_result must be a BusinessProjectionResult or None")
        if self.before_summary is not None and not isinstance(self.before_summary, SnapshotSummary):
            raise TypeError("before_summary must be a SnapshotSummary or None")
        if self.current_summary is not None and not isinstance(self.current_summary, SnapshotSummary):
            raise TypeError("current_summary must be a SnapshotSummary or None")
        if self.surface_duration_ms is not None and (
            not isinstance(self.surface_duration_ms, int)
            or isinstance(self.surface_duration_ms, bool)
            or self.surface_duration_ms < 0
        ):
            raise ValueError("surface_duration_ms must be a non-negative integer or None")


@dataclass(frozen=True, slots=True)
class HistoryCompareFlowInput:
    bundle_root: Path
    bundle_inputs: tuple[BundleInput, ...]
    pair_inputs: tuple[HistoryComparePairInput, ...]
    bundle_profile: BundleProfile | str | None = None
    projection_table_cache: ProjectionTableCache | None = None
    bundle_assembler: BundleAssembler = field(default_factory=BundleAssembler)
    operation_runtime: OperationRuntime = field(default_factory=OperationRuntime)
    worker_id: str = "history-compare-worker"
    operation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.bundle_root, Path):
            raise TypeError("bundle_root must be a Path")
        if not isinstance(self.bundle_inputs, tuple):
            object.__setattr__(self, "bundle_inputs", tuple(self.bundle_inputs))
        normalized_bundle_inputs: list[BundleInput] = []
        for bundle_input in self.bundle_inputs:
            if not isinstance(bundle_input, BundleInput):
                raise TypeError("bundle_inputs must contain BundleInput values")
            normalized_bundle_inputs.append(bundle_input)
        object.__setattr__(self, "bundle_inputs", tuple(normalized_bundle_inputs))
        if not self.bundle_inputs:
            raise ValueError("bundle_inputs must contain at least one input")
        if not isinstance(self.pair_inputs, tuple):
            object.__setattr__(self, "pair_inputs", tuple(self.pair_inputs))
        normalized_pair_inputs: list[HistoryComparePairInput] = []
        for pair_input in self.pair_inputs:
            if not isinstance(pair_input, HistoryComparePairInput):
                raise TypeError("pair_inputs must contain HistoryComparePairInput values")
            normalized_pair_inputs.append(pair_input)
        object.__setattr__(self, "pair_inputs", tuple(normalized_pair_inputs))
        if not self.pair_inputs:
            raise ValueError("pair_inputs must contain at least one pair")
        if len(self.pair_inputs) > 2:
            raise ValueError("history compare flow only supports one or two pairs in the first version")
        if self.bundle_profile is None:
            object.__setattr__(
                self,
                "bundle_profile",
                BundleProfile.MULTI_PAIR if len(self.pair_inputs) > 1 else BundleProfile.SINGLE_PAIR,
            )
        else:
            object.__setattr__(self, "bundle_profile", BundleProfile(self.bundle_profile))
        if self.projection_table_cache is not None and not isinstance(
            self.projection_table_cache,
            ProjectionTableCache,
        ):
            raise TypeError("projection_table_cache must be a ProjectionTableCache or None")
        if not isinstance(self.bundle_assembler, BundleAssembler):
            raise TypeError("bundle_assembler must be a BundleAssembler")
        if not isinstance(self.operation_runtime, OperationRuntime):
            raise TypeError("operation_runtime must be an OperationRuntime")
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("worker_id must be a non-empty string")
        if self.operation_id is not None and not isinstance(self.operation_id, str):
            raise TypeError("operation_id must be a string or None")
        max_index = max(
            max(pair_input.before_input_index, pair_input.current_input_index)
            for pair_input in self.pair_inputs
        )
        if max_index >= len(self.bundle_inputs):
            raise ValueError("pair input indexes must refer to bundle_inputs")


@dataclass(frozen=True, slots=True)
class HistoryCompareFlowResult:
    operation: OperationRecord
    run_result: OperationRunResult
    pair_results: tuple[HistoryComparePairResult, ...]
    bundle_result: BundleAssemblyResult
    bundle_duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationRecord):
            raise TypeError("operation must be an OperationRecord")
        if not isinstance(self.run_result, OperationRunResult):
            raise TypeError("run_result must be an OperationRunResult")
        if not isinstance(self.pair_results, tuple):
            object.__setattr__(self, "pair_results", tuple(self.pair_results))
        for pair_result in self.pair_results:
            if not isinstance(pair_result, HistoryComparePairResult):
                raise TypeError("pair_results must contain HistoryComparePairResult values")
        if not isinstance(self.bundle_result, BundleAssemblyResult):
            raise TypeError("bundle_result must be a BundleAssemblyResult")
        if self.bundle_duration_ms is not None and (
            not isinstance(self.bundle_duration_ms, int)
            or isinstance(self.bundle_duration_ms, bool)
            or self.bundle_duration_ms < 0
        ):
            raise ValueError("bundle_duration_ms must be a non-negative integer or None")


def run_history_compare(flow_input: HistoryCompareFlowInput) -> HistoryCompareFlowResult:
    if not isinstance(flow_input, HistoryCompareFlowInput):
        raise TypeError("flow_input must be a HistoryCompareFlowInput")

    pair_results: list[HistoryComparePairResult | None] = [None] * len(flow_input.pair_inputs)
    bundle_result: BundleAssemblyResult | None = None
    bundle_duration_ms: int | None = None

    parallel_policy = (
        OperationParallelPolicy.FIXED_DUAL_SLOT
        if len(flow_input.pair_inputs) == 2
        else OperationParallelPolicy.SERIAL
    )
    plan = OperationPlan(
        operation_kind=OperationKind.HISTORY_COMPARE,
        caller_type=OperationCallerType.READ_ONLY_CALLER,
        parallel_policy=parallel_policy,
        request_payload=_history_compare_request_payload(flow_input),
        steps=(
            OperationStepPlan(step_name="LOAD_INPUT"),
            *(
                OperationStepPlan(step_name=f"COMPARE_PAIR_{index}", retryable=True, allow_parallel=len(flow_input.pair_inputs) == 2)
                for index in range(len(flow_input.pair_inputs))
            ),
            OperationStepPlan(step_name="ASSEMBLE_BUNDLE", retryable=True),
            OperationStepPlan(step_name="PUBLISH_RESULT"),
            OperationStepPlan(step_name="ASYNC_COMPARISON_CORE_CACHE_COMPLETION", retryable=True),
            OperationStepPlan(step_name="CLEANUP"),
        ),
    )
    operation = flow_input.operation_runtime.create_operation(
        plan,
        operation_id=flow_input.operation_id,
    )

    def load_input(context: OperationStepContext) -> OperationStepOutcome:
        return OperationStepOutcome.success(
            value={
                "bundle_profile": flow_input.bundle_profile.value,
                "pair_count": len(flow_input.pair_inputs),
                "bundle_input_count": len(flow_input.bundle_inputs),
            }
        )

    def make_compare_pair(index: int):
        pair_input = flow_input.pair_inputs[index]

        def compare_pair(context: OperationStepContext) -> OperationStepOutcome:
            comparison_flow_input = _with_canonical_table_aliases(pair_input)
            comparison_and_risk = compare_and_evaluate_risk(
                comparison_flow_input.with_projection_table_cache(
                    flow_input.projection_table_cache,
                ),
                comparison_core_cache_write=False,
            )
            comparison_result = comparison_and_risk.comparison_result
            risk_result = comparison_and_risk.risk_result
            surface_request = ComparisonSurfaceAssemblyInput(
                comparison_facts=comparison_result.facts,
                records_closure=comparison_result.facts.records_ref,
                risk_report=risk_result.risk_report,
            )
            surface_start = perf_counter()
            base_surface_result = pair_input.surface_assembler.assemble(surface_request)
            business_projection_result = assemble_business_projection_for_surface(
                comparison_input=comparison_flow_input.comparison_input,
                comparison_surface=base_surface_result.comparison_surface,
            )
            surface_result = pair_input.surface_assembler.assemble(
                ComparisonSurfaceAssemblyInput(
                    comparison_facts=comparison_result.facts,
                    records_closure=comparison_result.facts.records_ref,
                    risk_report=risk_result.risk_report,
                    business_projection_result=business_projection_result,
                )
            )
            surface_duration_ms = _elapsed_ms(surface_start)
            pair_result = HistoryComparePairResult(
                pair_id=pair_input.pair_id,
                before_input_index=pair_input.before_input_index,
                current_input_index=pair_input.current_input_index,
                comparison_result=comparison_result,
                risk_result=risk_result,
                comparison_risk_result=comparison_and_risk,
                business_projection_result=business_projection_result,
                before_summary=comparison_flow_input.comparison_input.before.summary,
                current_summary=comparison_flow_input.comparison_input.current.summary,
                surface_result=surface_result,
                surface_duration_ms=surface_duration_ms,
            )
            pair_results[index] = pair_result
            return OperationStepOutcome.success(
                value={
                    "pair_id": pair_result.pair_id,
                    "comparison_digest": comparison_result.facts.comparison_digest.to_payload(),
                    "risk_evaluation_digest": risk_result.risk_evaluation.risk_evaluation_digest.to_payload(),
                    "surface_digest": surface_result.surface_digest.to_payload(),
                }
            )

        return compare_pair

    def assemble_bundle(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal bundle_result, bundle_duration_ms
        resolved_pair_results = _resolved_pair_results(pair_results)
        if len(resolved_pair_results) != len(flow_input.pair_inputs):
            raise RuntimeError("all pair results must be ready before bundle assembly")
        bundle_pairs = []
        for pair_result in resolved_pair_results:
            records_closure = pair_result.comparison_result.facts.records_ref
            bundle_pairs.append(
                BundlePairAssemblyInput(
                    pair_id=pair_result.pair_id,
                    before_input_index=pair_result.before_input_index,
                    current_input_index=pair_result.current_input_index,
                    comparison_surface=pair_result.surface_result.comparison_surface,
                    surface_artifact_closure=BundlePairArtifactClosure(
                        pair_id=pair_result.pair_id,
                        surface_digest=pair_result.surface_result.surface_digest,
                        surface_ref=f"pairs/{pair_result.pair_id}/comparison-surface.json",
                        comparison_records_closure=records_closure,
                        risk_report=pair_result.risk_result.risk_report,
                        business_projection_result=pair_result.business_projection_result,
                        diagnostics_refs=tuple(
                            pair_result.surface_result.comparison_surface.refs.diagnostics_refs
                        ),
                    ),
                )
            )
        bundle_request = BundleAssemblyInput(
            bundle_root=flow_input.bundle_root,
            bundle_profile=flow_input.bundle_profile,
            inputs=flow_input.bundle_inputs,
            pairs=tuple(bundle_pairs),
        )
        bundle_start = perf_counter()
        bundle_result = flow_input.bundle_assembler.assemble(bundle_request)
        bundle_duration_ms = _elapsed_ms(bundle_start)
        return OperationStepOutcome.success(
            value={
                "bundle_digest": bundle_result.manifest.bundle_digest.to_payload(),
                "pair_count": len(bundle_result.manifest.pairs),
                "table_count": bundle_result.manifest.summary.table_count,
                "bundle_duration_ms": bundle_duration_ms,
            }
        )

    def publish_result(context: OperationStepContext) -> OperationStepOutcome:
        if bundle_result is None:
            raise RuntimeError("bundle result must be available before publish")
        resolved_pair_results = _resolved_pair_results(pair_results)
        if len(resolved_pair_results) != len(flow_input.pair_inputs):
            raise RuntimeError("pair results are incomplete")
        ready_payload = _history_compare_ready_payload(
            pair_results=resolved_pair_results,
            bundle_result=bundle_result,
        )
        return OperationStepOutcome.success(
            value=ready_payload,
            ready_closure_digest=DigestRef.from_payload(ready_payload),
        )

    def async_comparison_core_cache_completion(context: OperationStepContext) -> OperationStepOutcome:
        resolved_pair_results = _resolved_pair_results(pair_results)
        if len(resolved_pair_results) != len(flow_input.pair_inputs):
            raise RuntimeError("pair results are incomplete")

        completion_start = perf_counter()
        completion_entries: list[dict[str, object]] = []
        completion_diagnostics: list[DiagnosticRecord] = []
        for pair_input, pair_result in zip(flow_input.pair_inputs, resolved_pair_results):
            comparison_flow_input = _with_canonical_table_aliases(pair_input)
            completion_details, pair_diagnostics = complete_comparison_core_cache(
                comparison_flow_input.with_projection_table_cache(
                    flow_input.projection_table_cache,
                ),
                pair_result.comparison_result,
            )
            completion_diagnostics.extend(pair_diagnostics)
            completion_entries.append(
                {
                    "pair_id": pair_input.pair_id,
                    "status": completion_details.get("comparison_core_cache_status"),
                    "lookup_hit": completion_details.get("comparison_core_cache_lookup_hit"),
                    "write_applied": completion_details.get("comparison_core_cache_write_applied"),
                    "cache_key_digest": completion_details.get("comparison_core_cache_key_digest"),
                }
            )

        completion_duration_ms = _elapsed_ms(completion_start)
        write_count = sum(1 for entry in completion_entries if entry.get("write_applied"))
        hit_count = sum(1 for entry in completion_entries if entry.get("lookup_hit") is True)
        skip_count = sum(
            1
            for entry in completion_entries
            if entry.get("status") in {"SKIPPED", "LOOKUP_FAILED", "WRITE_SKIPPED", "WRITE_FAILED"}
        )
        return OperationStepOutcome.success(
            value={
                "comparison_core_cache_completion_ms": completion_duration_ms,
                "comparison_core_cache_completion_pair_count": len(completion_entries),
                "comparison_core_cache_completion_write_count": write_count,
                "comparison_core_cache_completion_hit_count": hit_count,
                "comparison_core_cache_completion_skip_count": skip_count,
                "comparison_core_cache_completion_statuses": [
                    entry.get("status") for entry in completion_entries
                ],
                "comparison_core_cache_completion_entries": completion_entries,
            },
            diagnostics=tuple(completion_diagnostics),
        )

    def cleanup(context: OperationStepContext) -> OperationStepOutcome:
        # Cleanup only releases transient resources; durable outputs are retained by policy.
        return OperationStepOutcome.success(value={"cleanup": "noop"})

    handlers = {"LOAD_INPUT": load_input}
    for index in range(len(flow_input.pair_inputs)):
        handlers[f"COMPARE_PAIR_{index}"] = make_compare_pair(index)
    handlers.update(
        {
            "ASSEMBLE_BUNDLE": assemble_bundle,
            "PUBLISH_RESULT": publish_result,
            "ASYNC_COMPARISON_CORE_CACHE_COMPLETION": async_comparison_core_cache_completion,
            "CLEANUP": cleanup,
        }
    )
    run_result = flow_input.operation_runtime.run_operation(
        operation.operation_id,
        handlers=handlers,
        worker_id=flow_input.worker_id,
    )

    resolved_pair_results = _resolved_pair_results(pair_results)
    if bundle_result is None or len(resolved_pair_results) != len(flow_input.pair_inputs):
        raise RuntimeError("history compare operation completed without required results")

    return HistoryCompareFlowResult(
        operation=run_result.operation,
        run_result=run_result,
        pair_results=resolved_pair_results,
        bundle_result=bundle_result,
        bundle_duration_ms=bundle_duration_ms,
    )


def _with_canonical_table_aliases(
    pair_input: HistoryComparePairInput,
) -> ComparisonRiskFlowInput:
    aliases = tuple(
        build_canonical_table_aliases(
            pair_input.comparison_flow_input.comparison_input.before.summary,
            pair_id=pair_input.pair_id,
        )
    ) + tuple(
        build_canonical_table_aliases(
            pair_input.comparison_flow_input.comparison_input.current.summary,
            pair_id=pair_input.pair_id,
        )
    )
    if not aliases:
        return pair_input.comparison_flow_input
    return replace(
        pair_input.comparison_flow_input,
        comparison_input=replace(
            pair_input.comparison_flow_input.comparison_input,
            table_aliases=aliases,
        ),
    )


def _history_compare_request_payload(flow_input: HistoryCompareFlowInput) -> Mapping[str, object]:
    payload: dict[str, object] = {
        "operation_kind": OperationKind.HISTORY_COMPARE.value,
        "caller_type": OperationCallerType.READ_ONLY_CALLER.value,
        "bundle_profile": flow_input.bundle_profile.value,
        "pair_count": len(flow_input.pair_inputs),
        "bundle_input_count": len(flow_input.bundle_inputs),
        "pair_requests": [
            {
                "pair_id": pair_input.pair_id,
                "before_input_index": pair_input.before_input_index,
                "current_input_index": pair_input.current_input_index,
                "comparison_contract_version": pair_input.comparison_flow_input.comparison_input.comparison_contract_version,
                "before_snapshot_digest": pair_input.comparison_flow_input.comparison_input.before.snapshot.snapshot_digest.to_payload(),
                "current_snapshot_digest": pair_input.comparison_flow_input.comparison_input.current.snapshot.snapshot_digest.to_payload(),
            }
            for pair_input in flow_input.pair_inputs
        ],
    }
    return payload


def _history_compare_ready_payload(
    *,
    pair_results: tuple[HistoryComparePairResult, ...],
    bundle_result: BundleAssemblyResult,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "bundle_digest": bundle_result.manifest.bundle_digest.to_payload(),
        "pair_digests": [
            pair_result.comparison_result.facts.comparison_digest.to_payload()
            for pair_result in pair_results
        ],
    }
    return payload


def _resolved_pair_results(
    pair_results: list[HistoryComparePairResult | None],
) -> tuple[HistoryComparePairResult, ...]:
    resolved: list[HistoryComparePairResult] = []
    for pair_result in pair_results:
        if pair_result is None:
            return ()
        resolved.append(pair_result)
    return tuple(resolved)


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
