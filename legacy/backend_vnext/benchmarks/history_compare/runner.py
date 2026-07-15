from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from ...artifacts import LocalArtifactStore
from ...cache import FilesystemComparisonCoreCache, FilesystemProjectionTableCache
from ...cache.comparison_core import ComparisonCoreCache
from ...cache.projection_table import ProjectionTableCache
from ...capabilities.bundle_assembly import BundleInput
from ...capabilities.comparison import (
    ComparisonEngine,
    ComparisonInput,
    ComparisonRole,
    DirectedComparisonInput,
    RepositoryBackedComparisonContext,
)
from ...capabilities.comparison.planner import (
    DOLT_NATIVE_PROVIDER,
    ORDERED_TABLE_COMPARE_PROVIDER,
    SNAPSHOT_TABLE_COMPARE_PROVIDER,
    SUMMARY_EARLY_EXIT_PROVIDER,
)
from ...capabilities.repository_import import (
    RepositoryImportProvider,
    RepositoryImportProviderRunner,
    RepositoryImportValidationPolicy,
)
from ...capabilities.repository_import.repository_ref_readback import (
    LOCAL_REPOSITORY_SERVER_CONTRACT_VERSION,
    _RepositoryImportRepositoryBackend,
)
from ...capabilities.risk_evaluation import RiskEngine
from ...capabilities.snapshot_materialization import (
    RepositoryRefMaterializationInput,
    SnapshotMaterializationResult,
    Snapshot,
    SnapshotTable,
    SnapshotTableSet,
    materialize_repository_ref,
    read_repository_ref_summary_snapshot,
)
from ...capabilities.table_rules import default_table_rule_registry
from ...capabilities.snapshot_materialization.readers import RepositoryRefLazySnapshotTableReader
from ...capabilities.snapshot_materialization.repository_ref import _render_repository_table_create_sql
from ...core import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ...flows import (
    ComparisonRiskFlowInput,
    HistoryCompareFlowInput,
    build_history_compare_pair_input,
    run_history_compare,
)
from ...repository_server import (
    LocalRepositoryTableAccessProvider,
    RepositoryRef,
    RepositoryServerTableCache,
    RepositoryTableCatalog,
    RepositoryTableCatalogTable,
)
from .._paths import resolve_benchmark_path
from ..flow_journey.runner import (
    _count_diagnostics as _journey_count_diagnostics,
    _count_native_routes as _journey_count_native_routes,
    _default_machine_profile_id as _journey_default_machine_profile_id,
    _build_run_id as _journey_build_run_id,
    _elapsed_ms as _journey_elapsed_ms,
    _failure_diagnostic as _journey_failure_diagnostic,
    _operation_id as _journey_operation_id,
    _utc_now_iso as _journey_utc_now_iso,
)
from ..repository_import import (
    RepositoryImportBenchmarkMachineProfile,
    RepositoryImportBenchmarkDatasetSpec,
    RepositoryImportDatasetManifestBuilder,
    RepositoryImportDatasetResolver,
    detect_local_machine_profile,
)
from .models import (
    HistoryCompareBenchmarkProfile,
    HistoryCompareBenchmarkResult,
    HistoryCompareBenchmarkStageResult,
    HistoryCompareBenchmarkStatus,
    HistoryCompareRepositoryBackedDatasetInput,
    HistoryCompareBenchmarkSummary,
)
from .report import MarkdownReportWriter, SummaryJsonWriter


DEFAULT_DATASET_ROOT = Path("/home/issac/test-dir/business-benchmark-data")
DEFAULT_DATASET_IDS: tuple[str, ...] = ("business_small_cut", "business_large")
DEFAULT_PROFILES: tuple[HistoryCompareBenchmarkProfile, ...] = (
    HistoryCompareBenchmarkProfile.REPO_BACKED_COLD,
    HistoryCompareBenchmarkProfile.REPO_BACKED_WARM,
)
DEFAULT_PROVIDER = RepositoryImportProvider.SERVER_SESSION_BULK_LOAD


@dataclass(frozen=True, slots=True)
class _HistoryCompareCacheBundle:
    repository_ref_cache: RepositoryServerTableCache
    comparison_core_cache: ComparisonCoreCache
    projection_table_cache: ProjectionTableCache


@dataclass(frozen=True, slots=True)
class _HistoryCompareMaterializationPlan:
    baseline_context: RepositoryBackedComparisonContext
    current_context: RepositoryBackedComparisonContext
    baseline_materialized_tables: tuple[str, ...]
    planned_row_table_count: int
    planned_native_route_count: int
    planned_summary_early_exit_count: int


class HistoryCompareBenchmarkRunner:
    """Benchmark entry for repo-backed history compare.

    The runner measures compare/risk/surface from the open stages onward and no
    longer records a separate preparation phase.
    """

    def __init__(
        self,
        *,
        dataset_root: Path = DEFAULT_DATASET_ROOT,
        run_root: Path,
        result_out: Path | None = None,
        dolt_bin: str = "dolt",
        mysql_bin: str = "mysql",
        machine_profile: RepositoryImportBenchmarkMachineProfile | None = None,
        repository_ref_cache: RepositoryServerTableCache | None = None,
        comparison_core_cache: ComparisonCoreCache | None = None,
        projection_table_cache: ProjectionTableCache | None = None,
    ) -> None:
        self.dataset_root = resolve_benchmark_path(dataset_root)
        self.run_root = resolve_benchmark_path(run_root)
        self.result_out = result_out if result_out is not None else self.run_root / "report.md"
        self.dolt_bin = dolt_bin
        self.mysql_bin = mysql_bin
        self.machine_profile = machine_profile or detect_local_machine_profile(
            machine_profile_id=_journey_default_machine_profile_id(),
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
        )
        self.dataset_resolver = RepositoryImportDatasetResolver(self.dataset_root)
        self.dataset_manifest_builder = RepositoryImportDatasetManifestBuilder()
        self.provider_runner = RepositoryImportProviderRunner(
            self.run_root / "repos",
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
        )
        self.comparison_engine = ComparisonEngine()
        self.table_rule_registry = default_table_rule_registry()
        self.repository_ref_cache = repository_ref_cache or RepositoryServerTableCache(self.run_root / "repository-ref-cache")
        self.comparison_core_cache = comparison_core_cache or FilesystemComparisonCoreCache(
            self.run_root / "comparison-core-cache"
        )
        self.projection_table_cache = projection_table_cache or FilesystemProjectionTableCache(
            self.run_root / "projection-table-cache"
        )
        self.summary_path = self.run_root / "summary.json"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.result_out.parent.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        profiles: Sequence[HistoryCompareBenchmarkProfile | str] = DEFAULT_PROFILES,
        datasets: Sequence[str] | None = DEFAULT_DATASET_IDS,
        validation_policy: RepositoryImportValidationPolicy | str = RepositoryImportValidationPolicy.DISABLED,
        repository_backed_inputs: Mapping[str, HistoryCompareRepositoryBackedDatasetInput],
    ) -> HistoryCompareBenchmarkSummary:
        self.run_root.mkdir(parents=True, exist_ok=True)
        del validation_policy
        selected_profiles = tuple(_coerce_profile(profile) for profile in profiles)
        selected_dataset_ids = DEFAULT_DATASET_IDS if datasets is None else datasets
        selected_dataset_specs = self.dataset_resolver.resolve(selected_dataset_ids)
        dataset_resolutions = {
            spec.dataset_id: self.dataset_manifest_builder.build(spec)
            for spec in selected_dataset_specs
        }

        diagnostics: list[DiagnosticRecord] = []
        selected_providers: list[str] = []
        repository_backed_input_map = dict(repository_backed_inputs)
        for dataset_spec in selected_dataset_specs:
            if dataset_spec.dataset_id not in repository_backed_input_map:
                raise KeyError(
                    f"repository_backed_inputs missing required dataset_id: {dataset_spec.dataset_id}"
                )

        results: list[HistoryCompareBenchmarkResult] = []

        for profile in selected_profiles:
            self._reset_caches_for_profile(profile)
            cache_bundle = self._build_cache_bundle(profile)
            for dataset_spec in selected_dataset_specs:
                resolution = dataset_resolutions[dataset_spec.dataset_id]
                repository_backed_input = repository_backed_input_map[dataset_spec.dataset_id]
                result = self._run_compare_for_dataset_profile(
                    dataset_spec=dataset_spec,
                    resolution=resolution,
                    profile=profile,
                    repository_backed_input=repository_backed_input,
                    cache_bundle=cache_bundle,
                )
                diagnostics.extend(result.diagnostics)
                results.append(result)
                selected_providers.append(result.provider.value)

        summary = HistoryCompareBenchmarkSummary(
            run_id=_journey_build_run_id(),
            created_at=datetime.now(timezone.utc),
            machine_profile=self.machine_profile,
            datasets=tuple(dataset_resolutions[spec.dataset_id].manifest for spec in selected_dataset_specs),
            profiles=tuple(profile.value for profile in selected_profiles),
            providers=tuple(_unique_preserve_order(selected_providers)),
            results=tuple(results),
            diagnostics=tuple(diagnostics),
        )
        SummaryJsonWriter().write(self.summary_path, summary)
        MarkdownReportWriter().write(summary, self.result_out)
        return summary

    def _reset_caches_for_profile(self, profile: HistoryCompareBenchmarkProfile) -> None:
        if profile is HistoryCompareBenchmarkProfile.REPO_BACKED_COLD:
            self.repository_ref_cache.clear()
            self.comparison_core_cache.clear()
            self.projection_table_cache.clear()
        elif profile is HistoryCompareBenchmarkProfile.REPO_BACKED_WARM_PARTIAL:
            self.comparison_core_cache.clear()

    def _plan_history_compare_materialization(
        self,
        *,
        before_repository_path: Path,
        current_repository_path: Path,
        dataset_id: str,
        before_snapshot: Snapshot,
        current_snapshot: Snapshot,
        before_repository_ref: str,
        current_repository_ref: str,
        requested_tables: tuple[str, ...],
        cache: RepositoryServerTableCache,
    ) -> _HistoryCompareMaterializationPlan:
        baseline_backend = _RepositoryImportRepositoryBackend(
            repo_dir=before_repository_path,
            dolt=self.provider_runner.dolt,
        )
        baseline_provider = LocalRepositoryTableAccessProvider(backend=baseline_backend, cache=cache)
        current_provider = LocalRepositoryTableAccessProvider(
            backend=_RepositoryImportRepositoryBackend(
                repo_dir=current_repository_path,
                dolt=self.provider_runner.dolt,
            ),
            cache=cache,
        )
        baseline_context = RepositoryBackedComparisonContext(
            repository_id=dataset_id,
            resolved_commit_hash=before_repository_ref,
            repository_server_contract_version=LOCAL_REPOSITORY_SERVER_CONTRACT_VERSION,
            repository_ref=before_repository_ref,
            repository_table_access_provider=baseline_provider,
            dolt_version=None,
        )
        current_context = RepositoryBackedComparisonContext(
            repository_id=dataset_id,
            resolved_commit_hash=current_repository_ref,
            repository_server_contract_version=LOCAL_REPOSITORY_SERVER_CONTRACT_VERSION,
            repository_ref=current_repository_ref,
            repository_table_access_provider=current_provider,
            dolt_version=None,
        )
        plan = self.comparison_engine.plan(
            DirectedComparisonInput(
                before=ComparisonInput(
                    role=ComparisonRole.BEFORE,
                    snapshot=before_snapshot,
                    summary=before_snapshot.summary,
                    repository_backed_context=baseline_context,
                ),
                current=ComparisonInput(
                    role=ComparisonRole.CURRENT,
                    snapshot=current_snapshot,
                    summary=current_snapshot.summary,
                    repository_backed_context=current_context,
                ),
                table_ruleset_version=current_snapshot.summary.table_ruleset_version,
                requested_tables=requested_tables,
            )
        )
        baseline_materialized_tables = tuple(
            table_name
            for table_name, provider in plan.provider_routes
            if provider in {SNAPSHOT_TABLE_COMPARE_PROVIDER, ORDERED_TABLE_COMPARE_PROVIDER}
        )
        planned_native_route_count = sum(1 for _, provider in plan.provider_routes if provider == DOLT_NATIVE_PROVIDER)
        planned_summary_early_exit_count = sum(
            1 for _, provider in plan.provider_routes if provider == SUMMARY_EARLY_EXIT_PROVIDER
        )
        return _HistoryCompareMaterializationPlan(
            baseline_context=baseline_context,
            current_context=current_context,
            baseline_materialized_tables=baseline_materialized_tables,
            planned_row_table_count=len(baseline_materialized_tables),
            planned_native_route_count=planned_native_route_count,
            planned_summary_early_exit_count=planned_summary_early_exit_count,
        )

    def _run_compare_for_dataset_profile(
        self,
        *,
        dataset_spec: RepositoryImportBenchmarkDatasetSpec,
        resolution: object,
        profile: HistoryCompareBenchmarkProfile,
        repository_backed_input: HistoryCompareRepositoryBackedDatasetInput,
        cache_bundle: _HistoryCompareCacheBundle,
    ) -> HistoryCompareBenchmarkResult:
        run_dir = self.run_root / dataset_spec.dataset_id / profile.value
        run_dir.mkdir(parents=True, exist_ok=True)
        repository_id = repository_backed_input.repository_id or dataset_spec.dataset_id
        requested_tables = repository_backed_input.requested_tables
        current_semantic_snapshot_holder: dict[str, Snapshot] = {}

        def _open_baseline_repository_snapshot() -> tuple[Mapping[str, object], _OpenedRepositorySnapshot]:
            baseline_semantic_snapshot = self._read_repository_ref_summary_snapshot(
                repository_path=repository_backed_input.before_repository_path,
                repository_id=repository_id,
                repository_ref=repository_backed_input.before_repository_ref,
            )
            current_semantic_snapshot = self._read_repository_ref_summary_snapshot(
                repository_path=repository_backed_input.current_repository_path,
                repository_id=repository_id,
                repository_ref=repository_backed_input.current_repository_ref,
            )
            baseline_semantic_snapshot = replace(
                baseline_semantic_snapshot,
                repository_id=repository_id,
                repository_ref=repository_backed_input.before_repository_ref,
            )
            current_semantic_snapshot = replace(
                current_semantic_snapshot,
                repository_id=repository_id,
                repository_ref=repository_backed_input.current_repository_ref,
            )
            current_semantic_snapshot_holder["snapshot"] = current_semantic_snapshot
            materialization_plan = self._plan_history_compare_materialization(
                before_repository_path=repository_backed_input.before_repository_path,
                current_repository_path=repository_backed_input.current_repository_path,
                dataset_id=repository_id,
                before_snapshot=baseline_semantic_snapshot,
                current_snapshot=current_semantic_snapshot,
                before_repository_ref=repository_backed_input.before_repository_ref,
                current_repository_ref=repository_backed_input.current_repository_ref,
                requested_tables=requested_tables,
                cache=cache_bundle.repository_ref_cache,
            )
            return self._open_repository_snapshot(
                repository_path=repository_backed_input.before_repository_path,
                repository_id=repository_id,
                repository_ref=repository_backed_input.before_repository_ref,
                semantic_snapshot=baseline_semantic_snapshot,
                materialized_tables=materialization_plan.baseline_materialized_tables,
                cache=cache_bundle.repository_ref_cache,
                requested_tables=requested_tables,
                planned_native_route_count=materialization_plan.planned_native_route_count,
                planned_row_table_count=materialization_plan.planned_row_table_count,
                planned_summary_early_exit_count=materialization_plan.planned_summary_early_exit_count,
            )

        open_baseline_stage, baseline_opened, exc = self._run_stage(
            "OPEN_BASELINE_REPOSITORY_REF",
            _open_baseline_repository_snapshot,
        )
        stages: list[HistoryCompareBenchmarkStageResult] = [open_baseline_stage]
        diagnostics: list[DiagnosticRecord] = list(resolution.diagnostics)
        if exc is not None:
            diagnostics.append(
                _journey_failure_diagnostic("history-compare-open-baseline", exc, open_baseline_stage.stage_name)
            )
            return self._build_failed_result(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                stages=tuple(stages),
                failure_stage=open_baseline_stage.stage_name,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
            )
        assert baseline_opened is not None

        current_semantic_snapshot = current_semantic_snapshot_holder.get("snapshot")
        if current_semantic_snapshot is None:
            raise RuntimeError("current repository summary snapshot was not loaded")
        open_current_stage, current_opened, exc = self._run_stage(
            "OPEN_CURRENT_REPOSITORY_REF",
            lambda: self._open_repository_snapshot(
                repository_path=repository_backed_input.current_repository_path,
                repository_id=repository_id,
                repository_ref=repository_backed_input.current_repository_ref,
                semantic_snapshot=current_semantic_snapshot,
                materialized_tables=(),
                cache=cache_bundle.repository_ref_cache,
                requested_tables=requested_tables,
            ),
        )
        stages.append(open_current_stage)
        if exc is not None:
            diagnostics.append(
                _journey_failure_diagnostic("history-compare-open-current", exc, open_current_stage.stage_name)
            )
            return self._build_failed_result(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                stages=tuple(stages),
                failure_stage=open_current_stage.stage_name,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
                repository_id=repository_id,
                before_repository_ref=repository_backed_input.before_repository_ref,
                current_repository_ref=repository_backed_input.current_repository_ref,
            )
        assert current_opened is not None

        compare_stage, compare_result, exc = self._run_stage(
            "HISTORY_COMPARE",
            lambda: self._run_history_compare_operation(
                dataset_spec=dataset_spec,
                profile=profile,
                baseline_opened=baseline_opened,
                current_opened=current_opened,
                run_dir=run_dir,
                cache_bundle=cache_bundle,
            ),
        )
        stages.append(compare_stage)
        if exc is not None:
            diagnostics.append(
                _journey_failure_diagnostic("history-compare", exc, compare_stage.stage_name)
            )
            return self._build_failed_result(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                stages=tuple(stages),
                failure_stage=compare_stage.stage_name,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
                repository_id=repository_id,
                before_repository_ref=repository_backed_input.before_repository_ref,
                current_repository_ref=repository_backed_input.current_repository_ref,
            )
        assert compare_result is not None

        compare_summary = compare_result.pair_results[0].comparison_result.summary
        pair_result = compare_result.pair_results[0]
        comparison_risk_result = pair_result.comparison_risk_result
        comparison_duration_ms = (
            None if comparison_risk_result is None else comparison_risk_result.comparison_duration_ms
        )
        risk_duration_ms = None if comparison_risk_result is None else comparison_risk_result.risk_duration_ms
        surface_duration_ms = pair_result.surface_duration_ms
        native_route_count = _journey_count_native_routes(
            pair_result.comparison_result.plan.provider_routes
        )
        cache_hit_count = _journey_count_diagnostics(
            pair_result.comparison_result.cache_diagnostics,
            "comparison.projection-cache.hit",
        )
        cache_miss_count = _journey_count_diagnostics(
            pair_result.comparison_result.cache_diagnostics,
            "comparison.projection-cache.miss",
        )
        comparison_core_cache_hit_count = _journey_count_diagnostics(
            pair_result.comparison_result.cache_diagnostics,
            "comparison.core-cache.hit",
        )
        comparison_core_cache_miss_count = _journey_count_diagnostics(
            pair_result.comparison_result.cache_diagnostics,
            "comparison.core-cache.miss",
        )
        comparison_core_cache_completion_ms = compare_stage.details.get(
            "comparison_core_cache_completion_ms"
        )
        diagnostics.extend(compare_result.operation.diagnostics)
        diagnostics.extend(compare_result.bundle_result.diagnostics)
        async_cache_completion_step = _operation_step(
            compare_result.operation,
            "ASYNC_COMPARISON_CORE_CACHE_COMPLETION",
        )
        if async_cache_completion_step is not None:
            diagnostics.extend(async_cache_completion_step.diagnostics)
        diagnostics.extend(compare_result.pair_results[0].comparison_result.diagnostics)
        diagnostics.extend(compare_result.pair_results[0].risk_result.diagnostics)
        diagnostics.extend(compare_result.pair_results[0].surface_result.diagnostics)

        return HistoryCompareBenchmarkResult(
            dataset_id=dataset_spec.dataset_id,
            dataset_kind=dataset_spec.dataset_kind,
            profile=profile,
            provider=DEFAULT_PROVIDER,
            status=HistoryCompareBenchmarkStatus.PASSED,
            source_sql_digest=resolution.manifest.source_sql_digest,
            source_sql_bytes=resolution.manifest.source_sql_bytes,
            table_count=resolution.manifest.table_count,
            row_count_total=resolution.manifest.row_count_total,
            repository_id=repository_id,
            before_repository_ref=repository_backed_input.before_repository_ref,
            current_repository_ref=repository_backed_input.current_repository_ref,
            comparison_mode="DOLT_TO_DOLT",
            pair_count=len(compare_result.pair_results),
            stages=tuple(stages),
            comparison_status=compare_summary.status.value,
            comparison_duration_ms=comparison_duration_ms,
            risk_duration_ms=risk_duration_ms,
            surface_duration_ms=surface_duration_ms,
            bundle_duration_ms=compare_result.bundle_duration_ms,
            native_route_count=native_route_count,
            cache_hit_count=cache_hit_count,
            cache_miss_count=cache_miss_count,
            comparison_core_cache_hit_count=comparison_core_cache_hit_count,
            comparison_core_cache_miss_count=comparison_core_cache_miss_count,
            comparison_core_cache_completion_ms=comparison_core_cache_completion_ms,
            diagnostics=tuple(diagnostics),
        )

    def _run_history_compare_operation(
        self,
        *,
        dataset_spec: RepositoryImportBenchmarkDatasetSpec,
        profile: HistoryCompareBenchmarkProfile,
        baseline_opened: _OpenedRepositorySnapshot,
        current_opened: _OpenedRepositorySnapshot,
        run_dir: Path,
        cache_bundle: _HistoryCompareCacheBundle,
    ):
        del dataset_spec, profile
        requested_tables = baseline_opened.requested_tables
        before_input = ComparisonInput(
            role=ComparisonRole.BEFORE,
            snapshot=baseline_opened.snapshot.snapshot,
            summary=baseline_opened.snapshot.summary,
            table_set_ref=baseline_opened.snapshot.table_set,
            repository_backed_context=baseline_opened.context,
        )
        current_input = ComparisonInput(
            role=ComparisonRole.CURRENT,
            snapshot=current_opened.snapshot.snapshot,
            summary=current_opened.snapshot.summary,
            table_set_ref=current_opened.snapshot.table_set,
            repository_backed_context=current_opened.context,
        )
        comparison_input = DirectedComparisonInput(
            before=before_input,
            current=current_input,
            table_ruleset_version=current_opened.snapshot.summary.table_ruleset_version,
            requested_tables=requested_tables,
        )
        comparison_flow_input = ComparisonRiskFlowInput(
            comparison_input=comparison_input,
            records_store=LocalArtifactStore(run_dir / "comparison-records"),
            comparison_engine=self.comparison_engine,
            comparison_core_cache=cache_bundle.comparison_core_cache,
            projection_table_cache=cache_bundle.projection_table_cache,
            risk_engine=RiskEngine(),
        )
        pair_input = build_history_compare_pair_input(
            pair_id="pair-0",
            before_input_index=0,
            current_input_index=1,
            comparison_flow_input=comparison_flow_input,
            before_repository_backed_context=baseline_opened.context,
            current_repository_backed_context=current_opened.context,
        )
        history_compare_input = HistoryCompareFlowInput(
            bundle_root=run_dir / "bundle",
            bundle_inputs=(
                BundleInput(
                    input_index=0,
                    role=ComparisonRole.BEFORE,
                    snapshot_digest=baseline_opened.snapshot.summary.snapshot_digest,
                ),
                BundleInput(
                    input_index=1,
                    role=ComparisonRole.CURRENT,
                    snapshot_digest=current_opened.snapshot.summary.snapshot_digest,
                ),
            ),
            pair_inputs=(pair_input,),
            projection_table_cache=cache_bundle.projection_table_cache,
            operation_id=_journey_operation_id(
                "history-compare",
                baseline_opened.snapshot.summary.snapshot_id,
                current_opened.snapshot.summary.snapshot_id,
            ),
        )
        history_compare_result = run_history_compare(history_compare_input)
        completion_output = history_compare_result.run_result.outputs.get(
            "ASYNC_COMPARISON_CORE_CACHE_COMPLETION"
        )
        if not isinstance(completion_output, Mapping):
            completion_output = {}
        comparison_core_cache_hit_count = _journey_count_diagnostics(
            history_compare_result.pair_results[0].comparison_result.cache_diagnostics,
            "comparison.core-cache.hit",
        )
        comparison_core_cache_miss_count = _journey_count_diagnostics(
            history_compare_result.pair_results[0].comparison_result.cache_diagnostics,
            "comparison.core-cache.miss",
        )
        return (
            {
                "pair_count": len(history_compare_result.pair_results),
                "bundle_duration_ms": history_compare_result.bundle_duration_ms,
                "comparison_core_cache_hit_count": comparison_core_cache_hit_count,
                "comparison_core_cache_miss_count": comparison_core_cache_miss_count,
                "comparison_core_cache_completion_ms": completion_output.get(
                    "comparison_core_cache_completion_ms"
                ),
                "comparison_core_cache_completion_pair_count": completion_output.get(
                    "comparison_core_cache_completion_pair_count"
                ),
                "comparison_core_cache_completion_write_count": completion_output.get(
                    "comparison_core_cache_completion_write_count"
                ),
                "comparison_core_cache_completion_hit_count": completion_output.get(
                    "comparison_core_cache_completion_hit_count"
                ),
                "comparison_core_cache_completion_skip_count": completion_output.get(
                    "comparison_core_cache_completion_skip_count"
                ),
                "comparison_core_cache_completion_statuses": completion_output.get(
                    "comparison_core_cache_completion_statuses"
                ),
            },
            history_compare_result,
        )

    def _open_repository_snapshot(
        self,
        *,
        repository_path: Path,
        repository_id: str,
        repository_ref: str,
        semantic_snapshot: Snapshot,
        materialized_tables: tuple[str, ...],
        cache: RepositoryServerTableCache,
        requested_tables: tuple[str, ...] | None = None,
        planned_native_route_count: int | None = None,
        planned_row_table_count: int | None = None,
        planned_summary_early_exit_count: int | None = None,
        reused_snapshot: SnapshotMaterializationResult | None = None,
    ) -> tuple[Mapping[str, object], "_OpenedRepositorySnapshot"]:
        materialize_start = perf_counter()
        backend = _RepositoryImportRepositoryBackend(
            repo_dir=repository_path,
            dolt=self.provider_runner.dolt,
        )
        provider = LocalRepositoryTableAccessProvider(backend=backend, cache=cache)
        repository_ref_input = RepositoryRef(
            repository_id=repository_id,
            repository_ref=repository_ref,
        )
        session = provider.open_ref(repository_ref_input)
        try:
            catalog = session.get_catalog()
        finally:
            session.close()
        if semantic_snapshot.summary is None:
            raise ValueError("semantic_snapshot must include a summary")
        if reused_snapshot is not None and materialized_tables:
            raise ValueError("reused_snapshot cannot be combined with materialized_tables")
        if reused_snapshot is not None:
            table_set = reused_snapshot.table_set
            if table_set is None:
                raise RuntimeError("reused snapshot did not produce a table set")
            snapshot = replace(reused_snapshot, snapshot=semantic_snapshot)
            open_ref_materialize_ms = _journey_elapsed_ms(materialize_start)
            materialized_table_count = 0
            resolved_commit_hash = semantic_snapshot.repository_ref or repository_ref
        elif materialized_tables:
            materialized_result = materialize_repository_ref(
                RepositoryRefMaterializationInput(
                    repository_ref=repository_ref_input,
                    repository_table_access_provider=provider,
                    requested_tables=materialized_tables,
                )
            )
            if materialized_result.table_set is None:
                raise RuntimeError("repository ref materialization did not produce a table set")
            table_set = _build_repository_ref_open_table_set(
                semantic_snapshot=semantic_snapshot,
                catalog=catalog,
                provider=provider,
                repository_ref=repository_ref_input,
                requested_tables=(
                    requested_tables
                    if requested_tables is not None
                    else materialized_tables
                ),
                eager_tables=materialized_result.table_set.tables,
            )
            snapshot = SnapshotMaterializationResult(
                snapshot=semantic_snapshot,
                summary=semantic_snapshot.summary,
                table_set=table_set,
                table_artifact_refs=materialized_result.table_artifact_refs,
                materialization_input=materialized_result.materialization_input,
                cache_diagnostics=materialized_result.cache_diagnostics,
                diagnostics=tuple(semantic_snapshot.diagnostics) + tuple(materialized_result.diagnostics),
            )
            open_ref_materialize_ms = _journey_elapsed_ms(materialize_start)
            materialized_table_count = 0 if materialized_result.table_set is None else materialized_result.table_set.table_count
            resolved_commit_hash = semantic_snapshot.repository_ref or repository_ref
        else:
            table_set = _build_repository_ref_open_table_set(
                semantic_snapshot=semantic_snapshot,
                catalog=catalog,
                provider=provider,
                repository_ref=repository_ref_input,
                requested_tables=(
                    requested_tables
                    if requested_tables is not None
                    else materialized_tables
                ),
            )
            snapshot = SnapshotMaterializationResult(
                snapshot=semantic_snapshot,
                summary=semantic_snapshot.summary,
                table_set=table_set,
                cache_diagnostics=tuple(),
                diagnostics=tuple(semantic_snapshot.diagnostics),
            )
            open_ref_materialize_ms = _journey_elapsed_ms(materialize_start)
            materialized_table_count = 0
            resolved_commit_hash = semantic_snapshot.repository_ref or repository_ref
        context = _build_repository_backed_context(
            snapshot=snapshot,
            repository_id=repository_id,
            repository_ref=repository_ref,
            provider=provider,
        )
        details = {
            "repository_path": repository_path,
            "repository_ref": repository_ref,
            "resolved_commit_hash": resolved_commit_hash,
            "table_count": snapshot.summary.table_count,
            "row_count_total": snapshot.summary.row_count_total,
            "requested_tables": (
                requested_tables if requested_tables is not None else materialized_tables
            ),
            "materialized_table_count": materialized_table_count,
            "reader_table_count": 0 if snapshot.table_set is None else snapshot.table_set.table_count,
            "planned_row_table_count": planned_row_table_count,
            "planned_native_route_count": planned_native_route_count,
            "planned_summary_early_exit_count": planned_summary_early_exit_count,
            "open_ref_materialize_ms": open_ref_materialize_ms,
        }
        return details, _OpenedRepositorySnapshot(
            snapshot=snapshot,
            context=context,
            details=details,
            requested_tables=requested_tables if requested_tables is not None else materialized_tables,
        )

    def _read_repository_ref_summary_snapshot(
        self,
        *,
        repository_path: Path,
        repository_id: str,
        repository_ref: str,
    ) -> Snapshot:
        backend = _RepositoryImportRepositoryBackend(
            repo_dir=repository_path,
            dolt=self.provider_runner.dolt,
        )
        provider = LocalRepositoryTableAccessProvider(backend=backend, cache=self.repository_ref_cache)
        return read_repository_ref_summary_snapshot(
            RepositoryRefMaterializationInput(
                repository_ref=RepositoryRef(
                    repository_id=repository_id,
                    repository_ref=repository_ref,
                ),
                repository_table_access_provider=provider,
            )
        )

    def _build_cache_bundle(self, profile: HistoryCompareBenchmarkProfile) -> _HistoryCompareCacheBundle:
        return _HistoryCompareCacheBundle(
            repository_ref_cache=self.repository_ref_cache,
            comparison_core_cache=self.comparison_core_cache,
            projection_table_cache=self.projection_table_cache,
        )

    def _run_stage(
        self,
        stage_name: str,
        callback,
    ) -> tuple[HistoryCompareBenchmarkStageResult, object | None, Exception | None]:
        start = perf_counter()
        try:
            details, value = callback()
            return (
                HistoryCompareBenchmarkStageResult(
                    stage_name=stage_name,
                    status="SUCCEEDED",
                    duration_ms=_journey_elapsed_ms(start),
                    details=details,
                ),
                value,
                None,
            )
        except Exception as exc:  # pragma: no cover - stage-level failure path
            return (
                HistoryCompareBenchmarkStageResult(
                    stage_name=stage_name,
                    status="FAILED",
                    duration_ms=_journey_elapsed_ms(start),
                    details={"error": str(exc)},
                ),
                None,
                exc,
            )

    def _build_failed_result(
        self,
        *,
        dataset_spec: RepositoryImportBenchmarkDatasetSpec,
        resolution: object,
        profile: HistoryCompareBenchmarkProfile,
        stages: tuple[HistoryCompareBenchmarkStageResult, ...],
        failure_stage: str,
        failure_reason: str,
        diagnostics: tuple[DiagnosticRecord, ...],
        repository_id: str | None = None,
        before_repository_ref: str | None = None,
        current_repository_ref: str | None = None,
    ) -> HistoryCompareBenchmarkResult:
        return HistoryCompareBenchmarkResult(
            dataset_id=dataset_spec.dataset_id,
            dataset_kind=dataset_spec.dataset_kind,
            profile=profile,
            provider=DEFAULT_PROVIDER,
            status=HistoryCompareBenchmarkStatus.FAILED,
            source_sql_digest=resolution.manifest.source_sql_digest,
            source_sql_bytes=resolution.manifest.source_sql_bytes,
            table_count=resolution.manifest.table_count,
            row_count_total=resolution.manifest.row_count_total,
            repository_id=repository_id or dataset_spec.dataset_id,
            before_repository_ref=before_repository_ref or "UNAVAILABLE",
            current_repository_ref=current_repository_ref or "UNAVAILABLE",
            stages=stages,
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            diagnostics=diagnostics,
        )

@dataclass(frozen=True, slots=True)
class _OpenedRepositorySnapshot:
    snapshot: SnapshotMaterializationResult
    context: RepositoryBackedComparisonContext
    details: Mapping[str, object]
    requested_tables: tuple[str, ...]


def _build_repository_backed_context(
    *,
    snapshot: SnapshotMaterializationResult,
    repository_id: str,
    repository_ref: str,
    provider: LocalRepositoryTableAccessProvider,
) -> RepositoryBackedComparisonContext:
    del snapshot
    return RepositoryBackedComparisonContext(
        repository_id=repository_id,
        resolved_commit_hash=repository_ref,
        repository_server_contract_version=LOCAL_REPOSITORY_SERVER_CONTRACT_VERSION,
        repository_ref=repository_ref,
        repository_table_access_provider=provider,
        dolt_version=None,
    )


def _build_repository_ref_lazy_snapshot_table(
    *,
    summary_descriptor: SnapshotTableDescriptor,
    catalog_table: RepositoryTableCatalogTable,
    provider: LocalRepositoryTableAccessProvider,
    repository_ref: RepositoryRef,
) -> SnapshotTable:
    reader = RepositoryRefLazySnapshotTableReader(
        _descriptor=summary_descriptor,
        _repository_table_access_provider=provider,
        _repository_ref=repository_ref,
        _table_name=summary_descriptor.table_name,
    )
    return SnapshotTable(
        descriptor=summary_descriptor,
        reader=reader,
        raw_create_sql=_render_repository_table_create_sql(catalog_table),
    )


def _build_repository_ref_open_table_set(
    *,
    semantic_snapshot: Snapshot,
    catalog: RepositoryTableCatalog,
    provider: LocalRepositoryTableAccessProvider,
    repository_ref: RepositoryRef,
    requested_tables: Sequence[str],
    eager_tables: Mapping[str, SnapshotTable] | None = None,
) -> SnapshotTableSet:
    if semantic_snapshot.summary is None:
        raise ValueError("semantic_snapshot must include a summary")
    summary_table_map = {
        table.table_name: table for table in semantic_snapshot.summary.tables
    }
    effective_requested_tables = tuple(
        canonical_identifier(table_name) for table_name in requested_tables
    ) or tuple(summary_table_map)
    prepared_tables: dict[str, SnapshotTable] = {}
    for table_name in effective_requested_tables:
        eager_table = eager_tables.get(table_name) if eager_tables is not None else None
        if eager_table is not None:
            prepared_tables[table_name] = eager_table
            continue
        summary_descriptor = summary_table_map.get(table_name)
        if summary_descriptor is None:
            continue
        prepared_tables[table_name] = _build_repository_ref_lazy_snapshot_table(
            summary_descriptor=summary_descriptor,
            catalog_table=catalog.table(table_name),
            provider=provider,
            repository_ref=repository_ref,
        )
    return SnapshotTableSet(
        snapshot_id=semantic_snapshot.snapshot_id,
        snapshot_digest=semantic_snapshot.snapshot_digest,
        table_ruleset_version=semantic_snapshot.table_ruleset_version,
        tables=prepared_tables,
        resolution_plan="repository_ref:SUMMARY_FIRST_SELECTIVE_LAZY",
        diagnostics=tuple(semantic_snapshot.diagnostics),
    )

def _coerce_profile(profile: HistoryCompareBenchmarkProfile | str) -> HistoryCompareBenchmarkProfile:
    return HistoryCompareBenchmarkProfile(profile)


def _unique_preserve_order(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _operation_step(operation, step_name: str):
    for step in operation.steps:
        if step.step_name == step_name:
            return step
    return None
