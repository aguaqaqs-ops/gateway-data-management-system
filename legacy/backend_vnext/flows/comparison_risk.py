from __future__ import annotations

from dataclasses import dataclass, field, replace
from time import perf_counter

from ..artifacts import LocalArtifactStore, RecordsArtifact
from ..cache.comparison_core import (
    COMPARISON_CORE_CACHE_PROVENANCE_HISTORY_COMPARE_COMPUTE,
    COMPARISON_CORE_CACHE_PROVENANCE_PREVIEW_COMPLETION,
    ComparisonCoreCache,
    ComparisonCoreCacheEntry,
    ComparisonCoreCacheKey,
    build_comparison_core_cache_key,
)
from ..cache.projection_table import ProjectionTableCache
from ..capabilities.comparison import ComparisonComputeInput, ComparisonComputeResult, ComparisonEngine
from ..capabilities.comparison.models import (
    ComparisonRecord,
    ComparisonRecordKind,
    ComparisonRecordsClosure,
    ComparisonStatus,
    RepositoryBackedComparisonContext,
)
from ..contracts import CacheLookupPolicy, CacheValidationStatus
from ..capabilities.comparison.planner import _resolve_ruleset
from ..capabilities.comparison.ordered.models import OrderedRecord, OrderedRecordKind
from ..core.identifiers import canonical_identifier
from ..formal_upload_benchmark import benchmark_elapsed_ms, log_formal_upload_benchmark_event
from ..capabilities.risk_evaluation import (
    RiskEngine,
    RiskEvaluationInput,
    RiskEvaluationResult,
    RiskOptions,
    RiskRuleRegistry,
    RiskRecordsAccess,
    RiskRulesetSnapshot,
    build_hardcoded_risk_ruleset_registry,
)
from ..core import DiagnosticRecord


@dataclass(frozen=True, slots=True)
class ComparisonRecordsClosureAccess:
    records_closure: ComparisonRecordsClosure | None
    records_artifacts: tuple[RecordsArtifact, ...] = field(default_factory=tuple)

    def get_records_closure(self) -> ComparisonRecordsClosure | None:
        return self.records_closure

    def get_ordered_records(self, table_name: str) -> tuple[OrderedRecord, ...] | None:
        canonical_table_name = canonical_identifier(table_name)
        if not canonical_table_name:
            return None
        for records_artifact in self.records_artifacts:
            if canonical_identifier(records_artifact.manifest.table_name) != canonical_table_name:
                continue
            records: list[OrderedRecord] = []
            for record in records_artifact.read_records():
                record_kind = str(record.get("record_kind") or "")
                if record_kind not in {kind.value for kind in OrderedRecordKind}:
                    continue
                records.append(OrderedRecord(**record))
            return tuple(records)
        return None

    def get_standard_records(self, table_name: str) -> tuple[ComparisonRecord, ...] | None:
        canonical_table_name = canonical_identifier(table_name)
        if not canonical_table_name:
            return None
        for records_artifact in self.records_artifacts:
            if canonical_identifier(records_artifact.manifest.table_name) != canonical_table_name:
                continue
            records: list[ComparisonRecord] = []
            for record in records_artifact.read_records():
                record_kind = str(record.get("record_kind") or "")
                if record_kind not in {kind.value for kind in ComparisonRecordKind}:
                    continue
                records.append(ComparisonRecord(**record))
            return tuple(records)
        return None


@dataclass(frozen=True, slots=True)
class ComparisonRiskFlowInput:
    comparison_input: ComparisonComputeInput
    risk_ruleset_id: str | None = None
    risk_ruleset_registry: RiskRuleRegistry = field(default_factory=build_hardcoded_risk_ruleset_registry)
    risk_options: RiskOptions = field(default_factory=RiskOptions)
    records_store: LocalArtifactStore | None = None
    comparison_engine: ComparisonEngine = field(default_factory=ComparisonEngine)
    comparison_core_cache: ComparisonCoreCache | None = None
    comparison_core_cache_lookup_policy: CacheLookupPolicy | str = CacheLookupPolicy.READ_ANY
    projection_table_cache: ProjectionTableCache | None = None
    risk_engine: RiskEngine = field(default_factory=RiskEngine)
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
        object.__setattr__(
            self,
            "comparison_core_cache_lookup_policy",
            CacheLookupPolicy(self.comparison_core_cache_lookup_policy),
        )
        if self.projection_table_cache is not None and not isinstance(self.projection_table_cache, ProjectionTableCache):
            raise TypeError("projection_table_cache must be a ProjectionTableCache or None")
        if not isinstance(self.risk_engine, RiskEngine):
            raise TypeError("risk_engine must be a RiskEngine")
        if self.benchmark_run_id is not None and not isinstance(self.benchmark_run_id, str):
            raise TypeError("benchmark_run_id must be a string or None")

    def risk_ruleset(self) -> RiskRulesetSnapshot:
        return self.risk_ruleset_registry.snapshot(self.risk_ruleset_id)

    def comparison_engine_for_execution(self) -> ComparisonEngine:
        if self.projection_table_cache is None:
            return self.comparison_engine
        return replace(
            self.comparison_engine,
            projection_table_cache=self.projection_table_cache,
        )

    def comparison_core_cache_key(self) -> ComparisonCoreCacheKey:
        ruleset = _resolve_ruleset(self.comparison_engine.planner.ruleset_registry, self.comparison_input)
        return build_comparison_core_cache_key(
            comparison_input=self.comparison_input,
            table_ruleset_digest=ruleset.ruleset_digest,
        )

    def with_projection_table_cache(
        self,
        projection_table_cache: ProjectionTableCache | None,
    ) -> "ComparisonRiskFlowInput":
        if projection_table_cache is None or projection_table_cache is self.projection_table_cache:
            return self
        return replace(self, projection_table_cache=projection_table_cache)

    def with_comparison_core_cache(
        self,
        comparison_core_cache: ComparisonCoreCache | None,
    ) -> "ComparisonRiskFlowInput":
        if comparison_core_cache is None or comparison_core_cache is self.comparison_core_cache:
            return self
        return replace(self, comparison_core_cache=comparison_core_cache)

    def with_comparison_core_cache_lookup_policy(
        self,
        lookup_policy: CacheLookupPolicy | str,
    ) -> "ComparisonRiskFlowInput":
        normalized_policy = CacheLookupPolicy(lookup_policy)
        if normalized_policy is self.comparison_core_cache_lookup_policy:
            return self
        return replace(self, comparison_core_cache_lookup_policy=normalized_policy)

    def with_repository_backed_context(
        self,
        *,
        before_repository_backed_context: RepositoryBackedComparisonContext | None,
        current_repository_backed_context: RepositoryBackedComparisonContext | None,
    ) -> "ComparisonRiskFlowInput":
        if (
            self.comparison_input.before.repository_backed_context == before_repository_backed_context
            and self.comparison_input.current.repository_backed_context == current_repository_backed_context
        ):
            return self
        return replace(
            self,
            comparison_input=replace(
                self.comparison_input,
                before=replace(
                    self.comparison_input.before,
                    repository_backed_context=before_repository_backed_context,
                ),
                current=replace(
                    self.comparison_input.current,
                    repository_backed_context=current_repository_backed_context,
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class ComparisonRiskFlowResult:
    comparison_result: ComparisonComputeResult
    risk_result: RiskEvaluationResult
    comparison_duration_ms: int | None = None
    risk_duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.comparison_result, ComparisonComputeResult):
            raise TypeError("comparison_result must be a ComparisonComputeResult")
        if not isinstance(self.risk_result, RiskEvaluationResult):
            raise TypeError("risk_result must be a RiskEvaluationResult")
        if self.comparison_duration_ms is not None and (
            not isinstance(self.comparison_duration_ms, int)
            or isinstance(self.comparison_duration_ms, bool)
            or self.comparison_duration_ms < 0
        ):
            raise ValueError("comparison_duration_ms must be a non-negative integer or None")
        if self.risk_duration_ms is not None and (
            not isinstance(self.risk_duration_ms, int)
            or isinstance(self.risk_duration_ms, bool)
            or self.risk_duration_ms < 0
        ):
            raise ValueError("risk_duration_ms must be a non-negative integer or None")


def compare_and_evaluate_risk(
    flow_input: ComparisonRiskFlowInput,
    *,
    comparison_core_cache_write: bool = True,
) -> ComparisonRiskFlowResult:
    if not isinstance(flow_input, ComparisonRiskFlowInput):
        raise TypeError("flow_input must be a ComparisonRiskFlowInput")

    if flow_input.benchmark_run_id is not None:
        runtime_policy = dict(flow_input.comparison_input.runtime_policy or {})
        runtime_policy["benchmark_run_id"] = flow_input.benchmark_run_id
        flow_input = replace(
            flow_input,
            comparison_input=replace(
                flow_input.comparison_input,
                runtime_policy=runtime_policy,
            ),
        )

    comparison_engine = flow_input.comparison_engine
    comparison_execution_engine = flow_input.comparison_engine_for_execution()
    comparison_start = perf_counter()
    comparison_result, _ = _compare_with_core_cache(
        flow_input=flow_input,
        comparison_engine=comparison_engine,
        comparison_execution_engine=comparison_execution_engine,
        comparison_core_cache_write=comparison_core_cache_write,
    )
    comparison_duration_ms = _elapsed_ms(comparison_start)
    log_formal_upload_benchmark_event(
        "comparison_risk.comparison_core",
        benchmark_run_id=flow_input.benchmark_run_id,
        comparison_core_cache_write=comparison_core_cache_write,
        table_count=comparison_result.summary.table_count,
        records_artifact_count=len(comparison_result.records_artifacts),
        degraded_table_count=comparison_result.summary.degraded_table_count,
        status=getattr(
            comparison_result.summary.status,
            "value",
            comparison_result.summary.status,
        ),
        blocking_preview_ready=True,
        duration_ms=comparison_duration_ms,
    )
    records_access = _records_access_for(comparison_result)
    risk_input = RiskEvaluationInput(
        comparison_facts=comparison_result.facts,
        records_access=records_access,
        risk_ruleset=flow_input.risk_ruleset(),
        risk_options=flow_input.risk_options,
    )
    risk_start = perf_counter()
    risk_result = flow_input.risk_engine.evaluate(risk_input)
    risk_duration_ms = _elapsed_ms(risk_start)
    log_formal_upload_benchmark_event(
        "comparison_risk.risk_evaluation",
        benchmark_run_id=flow_input.benchmark_run_id,
        table_count=len(risk_result.risk_report.tables),
        blocking_preview_ready=True,
        duration_ms=risk_duration_ms,
    )
    return ComparisonRiskFlowResult(
        comparison_result=comparison_result,
        risk_result=risk_result,
        comparison_duration_ms=comparison_duration_ms,
        risk_duration_ms=risk_duration_ms,
    )


def _comparison_core_cache_write_skip_reason(
    comparison_result: ComparisonComputeResult,
) -> str | None:
    if comparison_result.summary.degraded_table_count > 0:
        return "comparison_table_degraded_present"
    if comparison_result.summary.status is ComparisonStatus.FAILED:
        return "comparison_status_failed"
    return None


def _comparison_core_cache_write_validation_status(
    flow_input: ComparisonRiskFlowInput,
) -> CacheValidationStatus:
    if (
        flow_input.comparison_core_cache_lookup_policy
        is CacheLookupPolicy.READ_COMMIT_VALIDATED_ONLY
        and _comparison_input_has_canonical_repository_identity(flow_input.comparison_input)
    ):
        return CacheValidationStatus.COMMIT_VALIDATED
    return CacheValidationStatus.PROVISIONAL


def _comparison_core_cache_write_provenance(
    flow_input: ComparisonRiskFlowInput,
) -> str:
    if (
        flow_input.comparison_core_cache_lookup_policy
        is CacheLookupPolicy.READ_COMMIT_VALIDATED_ONLY
        and _comparison_input_has_canonical_repository_identity(flow_input.comparison_input)
    ):
        return COMPARISON_CORE_CACHE_PROVENANCE_HISTORY_COMPARE_COMPUTE
    return COMPARISON_CORE_CACHE_PROVENANCE_PREVIEW_COMPLETION


def _comparison_input_has_canonical_repository_identity(
    comparison_input: ComparisonComputeInput,
) -> bool:
    for directed_input in (comparison_input.before, comparison_input.current):
        context = directed_input.repository_backed_context
        if context is None:
            return False
        if not isinstance(context.repository_id, str) or not context.repository_id.strip():
            return False
        if (
            not isinstance(context.resolved_commit_hash, str)
            or not context.resolved_commit_hash.strip()
        ):
            return False
    return True


def complete_comparison_core_cache(
    flow_input: ComparisonRiskFlowInput,
    comparison_result: ComparisonComputeResult,
) -> tuple[dict[str, object], tuple[DiagnosticRecord, ...]]:
    if not isinstance(flow_input, ComparisonRiskFlowInput):
        raise TypeError("flow_input must be a ComparisonRiskFlowInput")
    if not isinstance(comparison_result, ComparisonComputeResult):
        raise TypeError("comparison_result must be a ComparisonComputeResult")

    cache_diagnostics: list[DiagnosticRecord] = []
    cache_key = None
    comparison_core_cache = flow_input.comparison_core_cache

    completion_details: dict[str, object] = {
        "comparison_core_cache_enabled": comparison_core_cache is not None,
        "comparison_core_cache_status": "SKIPPED",
        "comparison_core_cache_lookup_hit": None,
        "comparison_core_cache_write_applied": False,
        "comparison_core_cache_key_digest": None,
    }

    if comparison_core_cache is None:
        return completion_details, tuple(cache_diagnostics)

    try:
        cache_key = flow_input.comparison_core_cache_key()
        lookup = comparison_core_cache.lookup(
            key=cache_key,
            lookup_policy=flow_input.comparison_core_cache_lookup_policy,
        )
    except Exception as exc:  # pragma: no cover - defensive, hard to trigger reliably
        _append_cache_diagnostic(
            cache_diagnostics,
            code="comparison.core-cache.completion.lookup-failed",
            message="comparison core cache completion lookup failed",
            severity="WARNING",
            cache_key_digest=None,
            details={"error": str(exc)},
        )
        completion_details["comparison_core_cache_status"] = "LOOKUP_FAILED"
        return completion_details, tuple(cache_diagnostics)

    completion_details["comparison_core_cache_key_digest"] = lookup.cache_key_digest
    if lookup.hit and isinstance(lookup.value, ComparisonCoreCacheEntry):
        _append_cache_diagnostic(
            cache_diagnostics,
            code="comparison.core-cache.completion.hit",
            message="comparison core cache completion found an existing entry",
            severity="INFO",
            cache_key_digest=lookup.cache_key_digest,
        )
        completion_details["comparison_core_cache_status"] = "ALREADY_PRESENT"
        completion_details["comparison_core_cache_lookup_hit"] = True
        return completion_details, tuple(cache_diagnostics)

    _append_cache_diagnostic(
        cache_diagnostics,
        code="comparison.core-cache.completion.miss",
        message="comparison core cache completion miss",
        severity="INFO",
        cache_key_digest=lookup.cache_key_digest,
        details={"miss_reason": lookup.miss_reason},
    )
    completion_details["comparison_core_cache_lookup_hit"] = False

    skip_reason = _comparison_core_cache_write_skip_reason(comparison_result)
    if skip_reason is not None:
        _append_cache_diagnostic(
            cache_diagnostics,
            code="comparison.core-cache.completion.write-skipped",
            message="comparison core cache completion write skipped",
            severity="WARNING",
            cache_key_digest=cache_key.cache_key_digest,
            details={
                "reason": skip_reason,
                "comparison_status": comparison_result.summary.status.value,
                "degraded_table_count": comparison_result.summary.degraded_table_count,
            },
        )
        completion_details["comparison_core_cache_status"] = "WRITE_SKIPPED"
        return completion_details, tuple(cache_diagnostics)

    records_closure = comparison_result.facts.records_ref
    if records_closure is None:
        _append_cache_diagnostic(
            cache_diagnostics,
            code="comparison.core-cache.completion.write-skipped",
            message="comparison core cache completion write skipped",
            severity="WARNING",
            cache_key_digest=cache_key.cache_key_digest,
            details={"reason": "records_closure_missing"},
        )
        completion_details["comparison_core_cache_status"] = "WRITE_SKIPPED"
        return completion_details, tuple(cache_diagnostics)

    try:
        comparison_core_cache.write(
            key=cache_key,
            value=ComparisonCoreCacheEntry(
                facts=comparison_result.facts,
                records_closure=records_closure,
                records_artifacts=comparison_result.records_artifacts,
            ),
            validation_status=_comparison_core_cache_write_validation_status(flow_input),
            provenance=_comparison_core_cache_write_provenance(flow_input),
        )
    except Exception as exc:  # pragma: no cover - defensive, hard to trigger reliably
        _append_cache_diagnostic(
            cache_diagnostics,
            code="comparison.core-cache.completion.write-failed",
            message="comparison core cache completion write failed",
            severity="WARNING",
            cache_key_digest=cache_key.cache_key_digest,
            details={"error": str(exc)},
        )
        completion_details["comparison_core_cache_status"] = "WRITE_FAILED"
        completion_details["comparison_core_cache_write_applied"] = False
    else:
        _append_cache_diagnostic(
            cache_diagnostics,
            code="comparison.core-cache.completion.write",
            message="comparison core cache completion write",
            severity="INFO",
            cache_key_digest=cache_key.cache_key_digest,
        )
        completion_details["comparison_core_cache_status"] = "WRITTEN"
        completion_details["comparison_core_cache_write_applied"] = True

    return completion_details, tuple(cache_diagnostics)


def _compare_with_core_cache(
    *,
    flow_input: ComparisonRiskFlowInput,
    comparison_engine: ComparisonEngine,
    comparison_execution_engine: ComparisonEngine,
    comparison_core_cache_write: bool = True,
) -> tuple[ComparisonComputeResult, tuple[DiagnosticRecord, ...]]:
    cache_diagnostics: list[DiagnosticRecord] = []
    comparison_core_cache = flow_input.comparison_core_cache
    cache_key = None
    if comparison_core_cache is not None:
        try:
            cache_key = flow_input.comparison_core_cache_key()
            lookup = comparison_core_cache.lookup(
                key=cache_key,
                lookup_policy=flow_input.comparison_core_cache_lookup_policy,
            )
        except Exception as exc:  # pragma: no cover - defensive, hard to trigger reliably
            _append_cache_diagnostic(
                cache_diagnostics,
                code="comparison.core-cache.lookup-failed",
                message="comparison core cache lookup failed",
                severity="WARNING",
                cache_key_digest=None,
                details={"error": str(exc)},
            )
        else:
            if lookup.hit and isinstance(lookup.value, ComparisonCoreCacheEntry):
                _append_cache_diagnostic(
                    cache_diagnostics,
                    code="comparison.core-cache.hit",
                    message="comparison core cache hit",
                    severity="INFO",
                    cache_key_digest=lookup.cache_key_digest,
                )
                plan = comparison_engine.plan(flow_input.comparison_input)
                cached_value = lookup.value
                if cached_value.facts.summary is None:
                    raise ValueError("comparison core cache entry facts must include a summary")
                return (
                    ComparisonComputeResult(
                        facts=cached_value.facts,
                        summary=cached_value.facts.summary,
                        plan=plan,
                        records_artifacts=cached_value.records_artifacts,
                        cache_diagnostics=tuple(cache_diagnostics),
                        diagnostics=cached_value.facts.diagnostics,
                    ),
                    tuple(cache_diagnostics),
                )
            _append_cache_diagnostic(
                cache_diagnostics,
                code="comparison.core-cache.miss",
                message="comparison core cache miss",
                severity="INFO",
                cache_key_digest=lookup.cache_key_digest,
                details={"miss_reason": lookup.miss_reason},
            )

    comparison_result = comparison_execution_engine.compare(
        flow_input.comparison_input,
        records_store=flow_input.records_store,
    )
    if comparison_core_cache_write and comparison_core_cache is not None and cache_key is not None:
        skip_reason = _comparison_core_cache_write_skip_reason(comparison_result)
        if skip_reason is not None:
            _append_cache_diagnostic(
                cache_diagnostics,
                code="comparison.core-cache.write-skipped",
                message="comparison core cache write skipped",
                severity="WARNING",
                cache_key_digest=cache_key.cache_key_digest,
                details={
                    "reason": skip_reason,
                    "comparison_status": comparison_result.summary.status.value,
                    "degraded_table_count": comparison_result.summary.degraded_table_count,
                },
            )
        else:
            records_closure = comparison_result.facts.records_ref
            if records_closure is None:
                _append_cache_diagnostic(
                    cache_diagnostics,
                    code="comparison.core-cache.write-skipped",
                    message="comparison core cache write skipped",
                    severity="WARNING",
                    cache_key_digest=cache_key.cache_key_digest,
                    details={"reason": "records_closure_missing"},
                )
            else:
                try:
                    comparison_core_cache.write(
                        key=cache_key,
                        value=ComparisonCoreCacheEntry(
                            facts=comparison_result.facts,
                            records_closure=records_closure,
                            records_artifacts=comparison_result.records_artifacts,
                        ),
                        validation_status=_comparison_core_cache_write_validation_status(flow_input),
                        provenance=_comparison_core_cache_write_provenance(flow_input),
                    )
                except Exception as exc:  # pragma: no cover - defensive, hard to trigger reliably
                    _append_cache_diagnostic(
                        cache_diagnostics,
                        code="comparison.core-cache.write-failed",
                        message="comparison core cache write failed",
                        severity="WARNING",
                        cache_key_digest=cache_key.cache_key_digest,
                        details={"error": str(exc)},
                    )
                else:
                    _append_cache_diagnostic(
                        cache_diagnostics,
                        code="comparison.core-cache.write",
                        message="comparison core cache write",
                        severity="INFO",
                        cache_key_digest=cache_key.cache_key_digest,
                    )
    if cache_diagnostics:
        comparison_result = replace(
            comparison_result,
            cache_diagnostics=tuple(cache_diagnostics) + comparison_result.cache_diagnostics,
        )
    return comparison_result, tuple(cache_diagnostics)


def _records_access_for(
    comparison_result: ComparisonComputeResult,
) -> RiskRecordsAccess | None:
    records_closure = comparison_result.facts.records_ref
    if records_closure is None and not comparison_result.records_artifacts:
        return None
    return ComparisonRecordsClosureAccess(
        records_closure=records_closure,
        records_artifacts=tuple(comparison_result.records_artifacts),
    )


def _append_cache_diagnostic(
    cache_diagnostics: list[DiagnosticRecord],
    *,
    code: str,
    message: str,
    severity: str,
    cache_key_digest: object | None,
    details: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {}
    if details is not None:
        payload["details"] = details
    if cache_key_digest is not None:
        cache_key_payload = getattr(cache_key_digest, "to_payload", None)
        payload["cache_key_digest"] = (
            cache_key_digest.to_payload() if callable(cache_key_payload) else cache_key_digest
        )
    cache_diagnostics.append(
        DiagnosticRecord(
            code=code,
            message=message,
            phase="comparison",
            severity=severity,
            details=payload,
        )
    )


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
