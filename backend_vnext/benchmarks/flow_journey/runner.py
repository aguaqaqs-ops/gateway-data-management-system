from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from platform import platform, python_version
import os
from time import perf_counter
from uuid import uuid4

from ...artifacts import ArtifactRef, LocalArtifactStore
from ...cache import (
    FilesystemComparisonCoreCache,
    FilesystemProjectionTableCache,
    InMemoryComparisonCoreCache,
    InMemoryProjectionTableCache,
    ProjectionTableCache,
)
from ...cache.comparison_core import (
    COMPARISON_CORE_CACHE_PROVENANCE_SUBMIT_FINALIZE_PROMOTION,
    ComparisonCoreCache,
)
from ...capabilities.comparison import (
    ComparisonComputeInput,
    ComparisonEngine,
    ComparisonInput,
    ComparisonRole,
    DirectedComparisonInput,
    RepositoryBackedComparisonContext,
)
from ...capabilities.comparison.planner import DOLT_NATIVE_PROVIDER
from ...capabilities.repository_import import (
    RepositoryImportArtifactBuilder,
    RepositoryImportArtifactLayout,
    RepositoryImportCallerPolicy,
    RepositoryImportExecutionContext,
    RepositoryImportPlan,
    RepositoryImportProvider,
    RepositoryImportProviderRunner,
    RepositoryImportServerMode,
    RepositoryImportStatus,
    RepositoryImportValidationPolicy,
    RepositoryImportValidationResult,
    RepositoryImportWorktreeContext,
    REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,
    build_physical_repository_import_plan_tables,
)
from ...capabilities.repository_import.repository_ref_readback import _RepositoryImportRepositoryBackend
from ...capabilities.risk_evaluation import RiskEngine
from ...capabilities.snapshot_materialization import (
    RepositoryRefMaterializationInput,
    SnapshotMaterializationResult,
    materialize_repository_ref,
)
from ...capabilities.surface_assembly import SurfaceAssembler
from ...contracts import (
    CacheValidationStatus,
    PreviewInputBinding,
    PreviewInputBindingEntry,
    SubmitSourcePackage,
)
from ...core import DigestRef, DiagnosticRecord
from ...core.row_digests import stable_rows_digest
from ...core.scalar_encoding import normalize_snapshot_rows
from ...flows import (
    ComparisonRiskFlowInput,
    SubmitFinalizeFlowInput,
    UploadPreviewFlowInput,
    run_upload_preview,
)
from ...operations import OperationRuntime, OperationStatus
from ...repository_server import (
    InMemoryRepositoryBackend,
    LocalRepositoryTableAccessProvider,
    RepositoryRef,
    RepositoryTableCatalog,
    RepositoryTableCatalogTable,
    RepositoryTableColumn,
)
from ...submissions import InMemorySubmissionStore
from ...submissions.store import InMemorySubmissionIdentityStore
from ...workspaces import InMemoryWorkspaceStore, WorkspaceRecord, WorkspaceStatus
from ...workspaces.acceptance import (
    WorkspaceSubmitAcceptanceCommand,
    WorkspaceSubmitAcceptanceService,
)
from ...workspaces.finalization import (
    WorkspaceSubmitFinalizeCommand,
    WorkspaceSubmitFinalizeWorkflowCommand,
    finalize_workspace_submit,
)
from .._paths import resolve_benchmark_path
from ..repository_import import (
    RepositoryImportBenchmarkMachineProfile,
    RepositoryImportDatasetManifestBuilder,
    RepositoryImportDatasetResolver,
    detect_local_machine_profile,
)
from .models import (
    FlowJourneyBenchmarkProfile,
    FlowJourneyBenchmarkResult,
    FlowJourneyBenchmarkStageResult,
    FlowJourneyBenchmarkStatus,
    FlowJourneyBenchmarkSummary,
    FlowJourneyBenchmarkSubmissionKind,
)
from .report import MarkdownReportWriter, SummaryJsonWriter


DEFAULT_DATASET_ROOT = Path("/home/issac/test-dir/business-benchmark-data")
DEFAULT_DATASET_IDS: tuple[str, ...] = ("business_small_cut", "business_large")
DEFAULT_PROFILES: tuple[FlowJourneyBenchmarkProfile, ...] = (
    FlowJourneyBenchmarkProfile.FULL_JOURNEY_COLD,
    FlowJourneyBenchmarkProfile.FULL_JOURNEY_WARM,
)


@dataclass(frozen=True, slots=True)
class _PreparedCompareInputs:
    baseline_snapshot: SnapshotMaterializationResult
    current_snapshot: SnapshotMaterializationResult
    baseline_context: RepositoryBackedComparisonContext
    current_context: RepositoryBackedComparisonContext
    mutation_details: Mapping[str, object]
    requested_tables: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _JourneyCacheBundle:
    baseline_preview_cache: ProjectionTableCache
    modified_preview_cache: ProjectionTableCache
    baseline_preview_comparison_core_cache: ComparisonCoreCache
    modified_preview_comparison_core_cache: ComparisonCoreCache


@dataclass(frozen=True, slots=True)
class _OpenedRepositorySnapshot:
    snapshot: SnapshotMaterializationResult
    context: RepositoryBackedComparisonContext
    details: Mapping[str, object]


class FlowJourneyBenchmarkRunner:
    def __init__(
        self,
        *,
        dataset_root: Path = DEFAULT_DATASET_ROOT,
        run_root: Path,
        result_out: Path | None = None,
        dolt_bin: str = "dolt",
        mysql_bin: str = "mysql",
        machine_profile: RepositoryImportBenchmarkMachineProfile | None = None,
        comparison_core_cache: ComparisonCoreCache | None = None,
        projection_table_cache: ProjectionTableCache | None = None,
    ) -> None:
        self.dataset_root = resolve_benchmark_path(dataset_root)
        self.run_root = resolve_benchmark_path(run_root)
        self.result_out = result_out if result_out is not None else self.run_root / "report.md"
        self.dolt_bin = dolt_bin
        self.mysql_bin = mysql_bin
        self.machine_profile = machine_profile or detect_local_machine_profile(
            machine_profile_id=_default_machine_profile_id(),
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
        self.surface_assembler = SurfaceAssembler()
        self.shared_comparison_core_cache = comparison_core_cache or FilesystemComparisonCoreCache(
            self.run_root / "comparison-core-cache"
        )
        self.shared_projection_table_cache = projection_table_cache or FilesystemProjectionTableCache(
            self.run_root / "projection-table-cache"
        )
        self.summary_path = self.run_root / "summary.json"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.result_out.parent.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        profiles: Sequence[FlowJourneyBenchmarkProfile | str] = DEFAULT_PROFILES,
        datasets: Sequence[str] | None = DEFAULT_DATASET_IDS,
        providers: Mapping[str, RepositoryImportProvider | str] | None = None,
        validation_policy: RepositoryImportValidationPolicy | str = (
            RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY
        ),
    ) -> FlowJourneyBenchmarkSummary:
        self.run_root.mkdir(parents=True, exist_ok=True)
        selected_profiles = tuple(_coerce_profile(profile) for profile in profiles)
        selected_dataset_ids = DEFAULT_DATASET_IDS if datasets is None else datasets
        selected_dataset_specs = self.dataset_resolver.resolve(selected_dataset_ids)
        dataset_resolutions = {
            spec.dataset_id: self.dataset_manifest_builder.build(spec)
            for spec in selected_dataset_specs
        }
        submission_identity_store = InMemorySubmissionIdentityStore()

        results: list[FlowJourneyBenchmarkResult] = []
        diagnostics: list[DiagnosticRecord] = []
        selected_providers: list[str] = []

        for dataset_spec in selected_dataset_specs:
            resolution = dataset_resolutions[dataset_spec.dataset_id]
            diagnostics.extend(resolution.diagnostics)
            provider = _select_provider(dataset_spec, providers)
            selected_providers.append(provider.value)
            for profile in selected_profiles:
                journey_caches = self._build_journey_cache_bundle(profile)
                baseline_result, _baseline_open_result = self._run_baseline_submission_for_dataset_profile(
                    dataset_spec=dataset_spec,
                    resolution=resolution,
                    profile=profile,
                    provider=provider,
                    validation_policy=validation_policy,
                    journey_caches=journey_caches,
                    submission_identity_store=submission_identity_store,
                )
                diagnostics.extend(baseline_result.diagnostics)
                results.append(baseline_result)
                if baseline_result.status is FlowJourneyBenchmarkStatus.FAILED:
                    continue
                result = self._run_modified_submission_for_dataset_profile(
                    dataset_spec=dataset_spec,
                    resolution=resolution,
                    profile=profile,
                    provider=provider,
                    validation_policy=validation_policy,
                    journey_caches=journey_caches,
                    baseline_result=baseline_result,
                    submission_identity_store=submission_identity_store,
                )
                diagnostics.extend(result.diagnostics)
                results.append(result)

        summary = FlowJourneyBenchmarkSummary(
            run_id=_build_run_id(),
            created_at=_utc_now_iso(),
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

    def _run_baseline_submission_for_dataset_profile(
        self,
        *,
        dataset_spec,
        resolution: object,
        profile: FlowJourneyBenchmarkProfile,
        provider: RepositoryImportProvider,
        validation_policy: RepositoryImportValidationPolicy | str,
        journey_caches: _JourneyCacheBundle,
        submission_identity_store: InMemorySubmissionIdentityStore,
    ) -> tuple[FlowJourneyBenchmarkResult, _OpenedRepositorySnapshot | None]:
        run_dir = self.run_root / dataset_spec.dataset_id / profile.value / "baseline-init"
        run_dir.mkdir(parents=True, exist_ok=True)
        requested_tables = _requested_tables_for_resolution(resolution)
        source_snapshot = resolution.source_snapshot
        if source_snapshot.table_set is None:
            raise ValueError("dataset resolution must include a table_set")

        stage_results: list[FlowJourneyBenchmarkStageResult] = []
        diagnostics: list[DiagnosticRecord] = list(resolution.diagnostics)

        prepare_stage, prepared, exc = self._run_stage(
            "PREPARE_BASELINE_INPUTS",
            lambda: self._prepare_baseline_submission_inputs(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                requested_tables=requested_tables,
            ),
        )
        stage_results.append(prepare_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("baseline-prepare", exc, prepare_stage.stage_name))
            return (
                self._build_failed_result(
                    dataset_spec=dataset_spec,
                    resolution=resolution,
                    profile=profile,
                    provider=provider,
                    requested_tables=requested_tables,
                    run_dir=run_dir,
                    stages=tuple(stage_results),
                    failure_stage=prepare_stage.stage_name,
                    failure_reason=str(exc),
                    diagnostics=tuple(diagnostics),
                    submission_kind=FlowJourneyBenchmarkSubmissionKind.BASELINE_INIT_SUBMISSION,
                ),
                None,
            )
        assert prepared is not None

        preview_stage, preview_result, exc = self._run_stage(
            "UPLOAD_PREVIEW",
            lambda: self._run_preview_stage(
                dataset_spec=dataset_spec,
                resolution=resolution,
                prepared=prepared,
                run_dir=run_dir,
                cache=journey_caches.baseline_preview_cache,
                comparison_core_cache=journey_caches.baseline_preview_comparison_core_cache,
            ),
        )
        stage_results.append(preview_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("baseline-upload-preview", exc, preview_stage.stage_name))
            return (
                self._build_failed_result(
                    dataset_spec=dataset_spec,
                    resolution=resolution,
                    profile=profile,
                    provider=provider,
                    requested_tables=requested_tables,
                    run_dir=run_dir,
                    stages=tuple(stage_results),
                    failure_stage=preview_stage.stage_name,
                    failure_reason=str(exc),
                    diagnostics=tuple(diagnostics),
                    submission_kind=FlowJourneyBenchmarkSubmissionKind.BASELINE_INIT_SUBMISSION,
                ),
                None,
            )
        assert preview_result is not None

        binding = self._build_preview_binding(
            dataset_spec=dataset_spec,
            resolution=resolution,
            prepared=prepared,
            preview_result=preview_result,
            workspace_id=f"workspace-{dataset_spec.dataset_id}-baseline-{profile.value.lower()}",
        )
        submit_source_package = self._build_submit_source_package(
            dataset_spec=dataset_spec,
            resolution=resolution,
            preview_binding=binding,
            current_snapshot=prepared.current_snapshot,
        )
        workspace_store = InMemoryWorkspaceStore()
        submission_store = InMemorySubmissionStore()
        operation_runtime = OperationRuntime()

        acceptance_stage, acceptance_result, exc = self._run_stage(
            "SUBMIT_ACCEPTANCE",
            lambda: self._run_submit_acceptance_stage(
                dataset_spec=dataset_spec,
                profile=profile,
                binding=binding,
                submit_source_package=submit_source_package,
                workspace_store=workspace_store,
                submission_identity_store=submission_identity_store,
                operation_runtime=operation_runtime,
            ),
        )
        stage_results.append(acceptance_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("baseline-submit-acceptance", exc, acceptance_stage.stage_name))
            return (
                self._build_failed_result(
                    dataset_spec=dataset_spec,
                    resolution=resolution,
                    profile=profile,
                    provider=provider,
                    requested_tables=requested_tables,
                    run_dir=run_dir,
                    stages=tuple(stage_results),
                    workspace_id=binding.workspace_id,
                    failure_stage=acceptance_stage.stage_name,
                    failure_reason=str(exc),
                    diagnostics=tuple(diagnostics),
                    submission_kind=FlowJourneyBenchmarkSubmissionKind.BASELINE_INIT_SUBMISSION,
                ),
                None,
            )
        assert acceptance_result is not None

        finalize_stage, finalize_result, exc = self._run_stage(
            "SUBMIT_FINALIZE",
            lambda: self._run_submit_finalize_stage(
                dataset_spec=dataset_spec,
                profile=profile,
                resolution=resolution,
                prepared=prepared,
                submit_source_package=submit_source_package,
                acceptance_result=acceptance_result,
                provider=provider,
                validation_policy=validation_policy,
                workspace_store=workspace_store,
                submission_store=submission_store,
                operation_runtime=operation_runtime,
                run_dir=run_dir,
                comparison_core_cache=journey_caches.baseline_preview_comparison_core_cache,
            ),
        )
        stage_results.append(finalize_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("baseline-submit-finalize", exc, finalize_stage.stage_name))
            return (
                self._build_failed_result(
                    dataset_spec=dataset_spec,
                    resolution=resolution,
                    profile=profile,
                    provider=provider,
                    requested_tables=requested_tables,
                    run_dir=run_dir,
                    stages=tuple(stage_results),
                    workspace_id=binding.workspace_id,
                    submission_id=acceptance_result.submission_id,
                    failure_stage=finalize_stage.stage_name,
                    failure_reason=str(exc),
                    diagnostics=tuple(diagnostics),
                    submission_kind=FlowJourneyBenchmarkSubmissionKind.BASELINE_INIT_SUBMISSION,
                ),
                None,
            )
        assert finalize_result is not None

        open_stage, open_result, exc = self._run_stage(
            "OPEN_BASELINE_REF",
            lambda: self._open_final_repository_snapshot(
                dataset_spec=dataset_spec,
                profile=profile,
                finalize_result=finalize_result,
                requested_tables=requested_tables,
                run_dir=run_dir,
            ),
        )
        stage_results.append(open_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("baseline-open-ref", exc, open_stage.stage_name))
            return (
                self._build_failed_result(
                    dataset_spec=dataset_spec,
                    resolution=resolution,
                    profile=profile,
                    provider=provider,
                    requested_tables=requested_tables,
                    run_dir=run_dir,
                    stages=tuple(stage_results),
                    workspace_id=binding.workspace_id,
                    submission_id=acceptance_result.submission_id,
                    repository_id=finalize_result.flow_result.repository_import_result.repository_id,
                    repository_path=finalize_result.flow_result.repository_import_result.repository_path,
                    repository_commit_hash=finalize_result.flow_result.repository_import_result.commit_hash,
                    failure_stage=open_stage.stage_name,
                    failure_reason=str(exc),
                    diagnostics=tuple(diagnostics),
                    submission_kind=FlowJourneyBenchmarkSubmissionKind.BASELINE_INIT_SUBMISSION,
                ),
                None,
            )
        assert open_result is not None

        result = self._build_result(
            dataset_spec=dataset_spec,
            resolution=resolution,
            profile=profile,
            provider=provider,
            requested_tables=requested_tables,
            stages=tuple(stage_results),
            workspace_id=binding.workspace_id,
            submission_id=acceptance_result.submission_id,
            repository_id=finalize_result.flow_result.repository_import_result.repository_id,
            repository_path=finalize_result.flow_result.repository_import_result.repository_path,
            repository_commit_hash=finalize_result.flow_result.repository_import_result.commit_hash,
            diagnostics=tuple(diagnostics),
            submission_kind=FlowJourneyBenchmarkSubmissionKind.BASELINE_INIT_SUBMISSION,
        )
        return result, open_result

    def _run_modified_submission_for_dataset_profile(
        self,
        *,
        dataset_spec,
        resolution: object,
        profile: FlowJourneyBenchmarkProfile,
        provider: RepositoryImportProvider,
        validation_policy: RepositoryImportValidationPolicy | str,
        journey_caches: _JourneyCacheBundle,
        baseline_result: FlowJourneyBenchmarkResult,
        submission_identity_store: InMemorySubmissionIdentityStore,
    ) -> FlowJourneyBenchmarkResult:
        run_dir = self.run_root / dataset_spec.dataset_id / profile.value
        run_dir.mkdir(parents=True, exist_ok=True)
        requested_tables = _requested_tables_for_resolution(resolution)
        source_snapshot = resolution.source_snapshot
        if source_snapshot.table_set is None:
            raise ValueError("dataset resolution must include a table_set")

        stage_results: list[FlowJourneyBenchmarkStageResult] = []
        diagnostics: list[DiagnosticRecord] = list(resolution.diagnostics)
        stage, value, exc = self._run_stage(
            "PREPARE_COMPARE_INPUTS",
            lambda: self._prepare_compare_inputs(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                requested_tables=requested_tables,
                run_dir=run_dir,
            ),
        )
        stage_results.append(stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("prepare-compare-inputs", exc, stage.stage_name))
            return self._build_failed_result(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                provider=provider,
                requested_tables=requested_tables,
                run_dir=run_dir,
                stages=tuple(stage_results),
                failure_stage=stage.stage_name,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
            )
        prepared = value
        assert isinstance(prepared, _PreparedCompareInputs)

        preview_cache = journey_caches.modified_preview_cache

        preview_stage, preview_result, exc = self._run_stage(
            "UPLOAD_PREVIEW",
            lambda: self._run_preview_stage(
                dataset_spec=dataset_spec,
                resolution=resolution,
                prepared=prepared,
                run_dir=run_dir,
                cache=preview_cache,
                comparison_core_cache=journey_caches.modified_preview_comparison_core_cache,
            ),
        )
        stage_results.append(preview_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("upload-preview", exc, preview_stage.stage_name))
            return self._build_failed_result(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                provider=provider,
                requested_tables=requested_tables,
                run_dir=run_dir,
                stages=tuple(stage_results),
                failure_stage=preview_stage.stage_name,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
            )
        assert preview_result is not None

        binding = self._build_preview_binding(
            dataset_spec=dataset_spec,
            resolution=resolution,
            prepared=prepared,
            preview_result=preview_result,
            workspace_id=f"workspace-{dataset_spec.dataset_id}-modified-{profile.value.lower()}",
        )
        submit_source_package = self._build_submit_source_package(
            dataset_spec=dataset_spec,
            resolution=resolution,
            preview_binding=binding,
            current_snapshot=prepared.current_snapshot,
        )
        workspace_store = InMemoryWorkspaceStore()
        submission_store = InMemorySubmissionStore()
        operation_runtime = OperationRuntime()

        acceptance_stage, acceptance_result, exc = self._run_stage(
            "SUBMIT_ACCEPTANCE",
            lambda: self._run_submit_acceptance_stage(
                dataset_spec=dataset_spec,
                profile=profile,
                binding=binding,
                submit_source_package=submit_source_package,
                workspace_store=workspace_store,
                submission_identity_store=submission_identity_store,
                operation_runtime=operation_runtime,
            ),
        )
        stage_results.append(acceptance_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("submit-acceptance", exc, acceptance_stage.stage_name))
            return self._build_failed_result(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                provider=provider,
                requested_tables=requested_tables,
                run_dir=run_dir,
                stages=tuple(stage_results),
                workspace_id=binding.workspace_id,
                failure_stage=acceptance_stage.stage_name,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
            )
        assert acceptance_result is not None

        finalize_stage, finalize_result, exc = self._run_stage(
            "SUBMIT_FINALIZE",
            lambda: self._run_submit_finalize_stage(
                dataset_spec=dataset_spec,
                profile=profile,
                resolution=resolution,
                prepared=prepared,
                submit_source_package=submit_source_package,
                acceptance_result=acceptance_result,
                provider=provider,
                validation_policy=validation_policy,
                workspace_store=workspace_store,
                submission_store=submission_store,
                operation_runtime=operation_runtime,
                run_dir=run_dir,
                comparison_core_cache=journey_caches.modified_preview_comparison_core_cache,
                promotion_before_commit_hash=baseline_result.repository_commit_hash,
            ),
        )
        stage_results.append(finalize_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("submit-finalize", exc, finalize_stage.stage_name))
            return self._build_failed_result(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                provider=provider,
                requested_tables=requested_tables,
                run_dir=run_dir,
                stages=tuple(stage_results),
                workspace_id=binding.workspace_id,
                submission_id=acceptance_result.submission_id,
                failure_stage=finalize_stage.stage_name,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
            )
        assert finalize_result is not None

        open_stage, open_result, exc = self._run_stage(
            "OPEN_NEW_BASELINE_REF",
            lambda: self._open_final_repository_snapshot(
                dataset_spec=dataset_spec,
                profile=profile,
                finalize_result=finalize_result,
                requested_tables=requested_tables,
                run_dir=run_dir,
            ),
        )
        stage_results.append(open_stage)
        if exc is not None:
            diagnostics.append(_failure_diagnostic("open-new-baseline-ref", exc, open_stage.stage_name))
            return self._build_failed_result(
                dataset_spec=dataset_spec,
                resolution=resolution,
                profile=profile,
                provider=provider,
                requested_tables=requested_tables,
                run_dir=run_dir,
                stages=tuple(stage_results),
                workspace_id=binding.workspace_id,
                submission_id=acceptance_result.submission_id,
                repository_id=finalize_result.flow_result.repository_import_result.repository_id,
                repository_path=finalize_result.flow_result.repository_import_result.repository_path,
                repository_commit_hash=finalize_result.flow_result.repository_import_result.commit_hash,
                failure_stage=open_stage.stage_name,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
            )
        assert open_result is not None

        result = self._build_result(
            dataset_spec=dataset_spec,
            resolution=resolution,
            profile=profile,
            provider=provider,
            requested_tables=requested_tables,
            stages=tuple(stage_results),
            workspace_id=binding.workspace_id,
            submission_id=acceptance_result.submission_id,
            repository_id=finalize_result.flow_result.repository_import_result.repository_id,
            repository_path=finalize_result.flow_result.repository_import_result.repository_path,
            repository_commit_hash=finalize_result.flow_result.repository_import_result.commit_hash,
            diagnostics=tuple(diagnostics),
        )
        return result

    def _prepare_compare_inputs(
        self,
        *,
        dataset_spec,
        resolution: object,
        profile: FlowJourneyBenchmarkProfile,
        requested_tables: tuple[str, ...],
        run_dir: Path,
    ) -> tuple[Mapping[str, object], _PreparedCompareInputs]:
        del run_dir
        source_snapshot = resolution.source_snapshot
        source_sql_materialization_ms = getattr(resolution, "source_sql_materialization_ms", None)
        rows_extract_start = perf_counter()
        rows_by_table = _snapshot_rows_by_table(source_snapshot)
        rows_extract_ms = _elapsed_ms(rows_extract_start)
        mutation_start = perf_counter()
        mutated_rows_by_table, mutation_details = _mutate_rows_by_table(
            rows_by_table,
            preferred_tables=requested_tables or tuple(rows_by_table),
        )
        mutation_ms = _elapsed_ms(mutation_start)

        baseline_repository_ref = f"refs/heads/{dataset_spec.dataset_id}/baseline"
        current_repository_ref = f"refs/heads/{dataset_spec.dataset_id}/current"
        baseline_commit_hash = _stable_commit_hash(
            dataset_spec.dataset_id,
            profile.value,
            "baseline",
            resolution.manifest.source_sql_digest.to_payload(),
        )
        current_commit_hash = _stable_commit_hash(
            dataset_spec.dataset_id,
            profile.value,
            "current",
            resolution.manifest.source_sql_digest.to_payload(),
        )
        baseline_materialize_start = perf_counter()
        baseline_snapshot = self._materialize_snapshot_from_rows(
            dataset_spec=dataset_spec,
            source_snapshot=source_snapshot,
            rows_by_table=rows_by_table,
            repository_ref=baseline_repository_ref,
            resolved_commit_hash=baseline_commit_hash,
            requested_tables=requested_tables,
        )
        baseline_materialize_ms = _elapsed_ms(baseline_materialize_start)
        current_materialize_start = perf_counter()
        current_snapshot = self._materialize_snapshot_from_rows(
            dataset_spec=dataset_spec,
            source_snapshot=source_snapshot,
            rows_by_table=mutated_rows_by_table,
            repository_ref=current_repository_ref,
            resolved_commit_hash=current_commit_hash,
            requested_tables=requested_tables,
        )
        current_materialize_ms = _elapsed_ms(current_materialize_start)
        context_build_start = perf_counter()
        baseline_context = _build_repository_backed_context(
            snapshot=baseline_snapshot,
            repository_id=dataset_spec.dataset_id,
            repository_ref=baseline_repository_ref,
            resolved_commit_hash=baseline_commit_hash,
            provider=self._repository_table_access_provider_for_snapshot(
                snapshot=baseline_snapshot,
                repository_id=dataset_spec.dataset_id,
                repository_ref=baseline_repository_ref,
                resolved_commit_hash=baseline_commit_hash,
                rows_by_table=rows_by_table,
            ),
        )
        current_context = _build_repository_backed_context(
            snapshot=current_snapshot,
            repository_id=dataset_spec.dataset_id,
            repository_ref=current_repository_ref,
            resolved_commit_hash=current_commit_hash,
            provider=self._repository_table_access_provider_for_snapshot(
                snapshot=current_snapshot,
                repository_id=dataset_spec.dataset_id,
                repository_ref=current_repository_ref,
                resolved_commit_hash=current_commit_hash,
                rows_by_table=mutated_rows_by_table,
            ),
        )
        context_build_ms = _elapsed_ms(context_build_start)
        details = {
            "source_sql_materialization_ms": source_sql_materialization_ms,
            "rows_extract_ms": rows_extract_ms,
            "rows_mutate_ms": mutation_ms,
            "baseline_materialize_ms": baseline_materialize_ms,
            "current_materialize_ms": current_materialize_ms,
            "context_build_ms": context_build_ms,
            "baseline_repository_ref": baseline_repository_ref,
            "current_repository_ref": current_repository_ref,
            "mutated_table_name": mutation_details.get("table_name"),
            "mutated_column_index": mutation_details.get("column_index"),
            "mutated_before_value": mutation_details.get("before_value"),
            "mutated_after_value": mutation_details.get("after_value"),
            "table_count": source_snapshot.summary.table_count,
        }
        prepared = _PreparedCompareInputs(
            baseline_snapshot=baseline_snapshot,
            current_snapshot=current_snapshot,
            baseline_context=baseline_context,
            current_context=current_context,
            mutation_details=details,
            requested_tables=requested_tables,
        )
        return details, prepared

    def _run_preview_stage(
        self,
        *,
        dataset_spec,
        resolution: object,
        prepared: _PreparedCompareInputs,
        run_dir: Path,
        cache: ProjectionTableCache,
        comparison_core_cache: ComparisonCoreCache,
    ) -> tuple[Mapping[str, object], object]:
        preview_input = _comparison_risk_input(
            before_snapshot=prepared.baseline_snapshot,
            current_snapshot=prepared.current_snapshot,
            before_context=prepared.baseline_context,
            current_context=prepared.current_context,
            requested_tables=prepared.requested_tables,
            records_store=LocalArtifactStore(run_dir / "preview-records"),
            projection_table_cache=cache,
            comparison_engine=self.comparison_engine,
        )
        preview_flow_input = _build_upload_preview_input(
            comparison_input=preview_input.comparison_input,
            records_store=preview_input.records_store,
            comparison_engine=preview_input.comparison_engine,
            comparison_core_cache=comparison_core_cache,
            projection_table_cache=preview_input.projection_table_cache,
            risk_engine=preview_input.risk_engine,
        )
        preview_result = run_upload_preview(preview_flow_input)
        if preview_result.operation.status is not OperationStatus.READY:
            raise RuntimeError(
                f"upload preview operation did not complete successfully: {preview_result.operation.status.value}"
            )
        comparison_result = preview_result.comparison_result
        comparison_risk_result = getattr(preview_result, "comparison_risk_result", None)
        completion_output = preview_result.run_result.outputs.get("ASYNC_COMPARISON_CORE_CACHE_COMPLETION")
        details = {
            "comparison_digest": comparison_result.facts.comparison_digest.to_payload(),
            "comparison_status": comparison_result.summary.status.value,
            "comparison_duration_ms": (
                None
                if comparison_risk_result is None
                else getattr(comparison_risk_result, "comparison_duration_ms", None)
            ),
            "risk_duration_ms": (
                None
                if comparison_risk_result is None
                else getattr(comparison_risk_result, "risk_duration_ms", None)
            ),
            "surface_duration_ms": getattr(preview_result, "surface_duration_ms", None),
            "comparison_core_cache_hit_count": _count_diagnostics(
                comparison_result.cache_diagnostics,
                "comparison.core-cache.hit",
            ),
            "comparison_core_cache_miss_count": _count_diagnostics(
                comparison_result.cache_diagnostics,
                "comparison.core-cache.miss",
            ),
            "native_route_count": _count_native_routes(comparison_result.plan.provider_routes),
            "cache_hit_count": _count_diagnostics(comparison_result.cache_diagnostics, "comparison.projection-cache.hit"),
            "cache_miss_count": _count_diagnostics(comparison_result.cache_diagnostics, "comparison.projection-cache.miss"),
            "comparison_core_cache_completion_ms": (
                None
                if not isinstance(completion_output, Mapping)
                else completion_output.get("comparison_core_cache_completion_ms")
            ),
            "comparison_core_cache_completion_write_count": (
                None
                if not isinstance(completion_output, Mapping)
                else completion_output.get("comparison_core_cache_completion_write_count")
            ),
            "comparison_core_cache_completion_hit_count": (
                None
                if not isinstance(completion_output, Mapping)
                else completion_output.get("comparison_core_cache_completion_hit_count")
            ),
            "comparison_core_cache_completion_skip_count": (
                None
                if not isinstance(completion_output, Mapping)
                else completion_output.get("comparison_core_cache_completion_skip_count")
            ),
            "table_count": comparison_result.summary.table_count,
        }
        return details, preview_result

    def _build_preview_binding(
        self,
        *,
        dataset_spec,
        resolution: object,
        prepared: _PreparedCompareInputs,
        preview_result,
        workspace_id: str | None = None,
    ) -> PreviewInputBinding:
        sql_entry = PreviewInputBindingEntry(
            entry_name=f"/datasets/{dataset_spec.dataset_id}/dbcfg.sql",
            content_digest=resolution.manifest.source_sql_digest,
            normalized_path="/sql/dbcfg.sql",
            entry_kind="FILE",
        )
        manifest_entry = PreviewInputBindingEntry(
            entry_name=f"{dataset_spec.dataset_id}-required-entries",
            content_digest=DigestRef.from_payload(
                {
                    "dataset_id": dataset_spec.dataset_id,
                    "operation_id": preview_result.operation.operation_id,
                    "comparison_digest": preview_result.comparison_result.facts.comparison_digest.to_payload(),
                }
            ),
            normalized_path=None,
            entry_kind="DIRECTORY_MANIFEST",
        )
        return PreviewInputBinding(
            binding_id=f"binding-{dataset_spec.dataset_id}-{preview_result.operation.operation_id}",
            workspace_id=workspace_id or f"workspace-{dataset_spec.dataset_id}",
            upload_generation=f"journey-{dataset_spec.dataset_id}-{preview_result.operation.operation_id}",
            preview_source_digest=DigestRef.from_payload(
                {
                    "dataset_id": dataset_spec.dataset_id,
                    "operation_id": preview_result.operation.operation_id,
                    "source_digest": resolution.manifest.source_sql_digest.to_payload(),
                }
            ),
            required_entries=(manifest_entry, sql_entry),
            parser_version=resolution.source_snapshot.summary.parser_version,
            table_ruleset_version=resolution.source_snapshot.summary.table_ruleset_version,
            before_snapshot_digest=prepared.baseline_snapshot.summary.snapshot_digest,
            current_snapshot_digest=prepared.current_snapshot.summary.snapshot_digest,
            comparison_digest=preview_result.comparison_result.facts.comparison_digest,
            generated_at=datetime.now(timezone.utc),
        )

    def _prepare_baseline_submission_inputs(
        self,
        *,
        dataset_spec,
        resolution: object,
        profile: FlowJourneyBenchmarkProfile,
        requested_tables: tuple[str, ...],
    ) -> tuple[Mapping[str, object], _PreparedCompareInputs]:
        del profile
        source_snapshot = resolution.source_snapshot
        if source_snapshot.table_set is None:
            raise ValueError("resolution.source_snapshot must include a table_set")

        source_sql_materialization_ms = getattr(resolution, "source_sql_materialization_ms", None)
        rows_extract_start = perf_counter()
        rows_by_table = _snapshot_rows_by_table(source_snapshot)
        rows_extract_ms = _elapsed_ms(rows_extract_start)
        context_build_start = perf_counter()
        repository_ref = f"refs/heads/{dataset_spec.dataset_id}/baseline-init"
        context = _build_repository_backed_context(
            snapshot=source_snapshot,
            repository_id=dataset_spec.dataset_id,
            repository_ref=repository_ref,
            resolved_commit_hash=source_snapshot.summary.snapshot_digest.to_payload(),
            provider=self._repository_table_access_provider_for_snapshot(
                snapshot=source_snapshot,
                repository_id=dataset_spec.dataset_id,
                repository_ref=repository_ref,
                resolved_commit_hash=source_snapshot.summary.snapshot_digest.to_payload(),
                rows_by_table=rows_by_table,
            ),
        )
        context_build_ms = _elapsed_ms(context_build_start)
        details = {
            "source_sql_materialization_ms": source_sql_materialization_ms,
            "rows_extract_ms": rows_extract_ms,
            "rows_mutate_ms": 0,
            "baseline_materialize_ms": 0,
            "current_materialize_ms": 0,
            "context_build_ms": context_build_ms,
            "baseline_repository_ref": repository_ref,
            "current_repository_ref": repository_ref,
            "table_count": source_snapshot.summary.table_count,
        }
        prepared = _PreparedCompareInputs(
            baseline_snapshot=source_snapshot,
            current_snapshot=source_snapshot,
            baseline_context=context,
            current_context=context,
            mutation_details=details,
            requested_tables=requested_tables,
        )
        return details, prepared

    def _build_submit_source_package(
        self,
        *,
        dataset_spec,
        resolution: object,
        preview_binding: PreviewInputBinding,
        current_snapshot: SnapshotMaterializationResult,
    ) -> SubmitSourcePackage:
        artifact_ref = ArtifactRef(
            artifact_kind="flow-journey-submit-source-package",
            artifact_contract_version="backend-vnext/flow-journey/v1",
            manifest_digest=DigestRef.from_payload(
                {
                    "dataset_id": dataset_spec.dataset_id,
                    "binding_id": preview_binding.binding_id,
                    "snapshot_digest": current_snapshot.summary.snapshot_digest.to_payload(),
                }
            ),
            content_digest=DigestRef.from_payload(
                {
                    "dataset_id": dataset_spec.dataset_id,
                    "source_sql_digest": resolution.manifest.source_sql_digest.to_payload(),
                    "snapshot_digest": current_snapshot.summary.snapshot_digest.to_payload(),
                }
            ),
        )
        return SubmitSourcePackage(
            source_package_id=f"submit-source-{dataset_spec.dataset_id}-{preview_binding.binding_id}",
            source_kind="SUBMIT_FULL",
            package_kind="DIRECTORY",
            source_package_digest=DigestRef.from_payload(
                {
                    "dataset_id": dataset_spec.dataset_id,
                    "binding_id": preview_binding.binding_id,
                    "source_sql_digest": resolution.manifest.source_sql_digest.to_payload(),
                }
            ),
            package_manifest_digest=DigestRef.from_payload(
                {
                    "dataset_id": dataset_spec.dataset_id,
                    "binding_id": preview_binding.binding_id,
                    "required_entries_manifest_digest": preview_binding.required_entries_manifest_digest.to_payload(),
                }
            ),
            required_entries_manifest_digest=preview_binding.required_entries_manifest_digest,
            parser_version=preview_binding.parser_version,
            table_ruleset_version=preview_binding.table_ruleset_version,
            artifact_ref=artifact_ref,
            size_bytes=resolution.manifest.source_sql_bytes,
            created_by="flow-journey-benchmark",
            created_at=datetime.now(timezone.utc),
        )

    def _run_submit_acceptance_stage(
        self,
        *,
        dataset_spec,
        profile: FlowJourneyBenchmarkProfile,
        binding: PreviewInputBinding,
        submit_source_package: SubmitSourcePackage,
        workspace_store: InMemoryWorkspaceStore,
        submission_identity_store: InMemorySubmissionIdentityStore,
        operation_runtime: OperationRuntime,
        workspace_batch_id: str | None = None,
    ):
        workspace = WorkspaceRecord(
            workspace_id=binding.workspace_id,
            batch_id=workspace_batch_id,
        ).record_preview_input_binding(
            binding,
            updated_at=datetime.now(timezone.utc),
        )
        workspace_store.create(workspace)
        service = WorkspaceSubmitAcceptanceService(
            workspace_store=workspace_store,
            submission_identity_store=submission_identity_store,
        )
        operation_id = _operation_id("accept", dataset_spec.dataset_id, profile.value)
        result = service.accept_submit(
            WorkspaceSubmitAcceptanceCommand(
                workspace_id=binding.workspace_id,
                submit_source_package=submit_source_package,
                preview_input_binding=binding,
                operation_runtime=operation_runtime,
                worker_id=f"journey-acceptance-{dataset_spec.dataset_id}",
                operation_id=operation_id,
            )
        )
        if result.workspace.status is not WorkspaceStatus.PREVIEW_READY:
            raise RuntimeError("workspace did not remain PREVIEW_READY after acceptance")
        details = {
            "workspace_status": result.workspace.status.value,
            "operation_id": result.accepted.operation_id,
            "submission_id": result.submission_id,
        }
        return details, result

    def _run_submit_finalize_stage(
        self,
        *,
        dataset_spec,
        profile: FlowJourneyBenchmarkProfile,
        resolution: object,
        prepared: _PreparedCompareInputs,
        submit_source_package: SubmitSourcePackage,
        acceptance_result,
        provider: RepositoryImportProvider,
        validation_policy: RepositoryImportValidationPolicy | str,
        workspace_store: InMemoryWorkspaceStore,
        submission_store: InMemorySubmissionStore,
        operation_runtime: OperationRuntime,
        run_dir: Path,
        comparison_core_cache: ComparisonCoreCache | None,
        promotion_before_commit_hash: str | None = None,
        base_ref_or_commit: str = "main",
        target_branch_ref: str | None = None,
        worktree_context: RepositoryImportWorktreeContext | None = None,
    ):
        import_artifact = RepositoryImportArtifactBuilder(
            run_dir / "import-artifacts",
            export_formats=(REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,),
            artifact_layout=RepositoryImportArtifactLayout.REPLAY_ONLY_MINIMAL,
        ).build(
            prepared.current_snapshot,
            requested_tables=prepared.requested_tables or None,
        )
        import_plan = _build_repository_import_plan(
            dataset_spec=dataset_spec,
            current_snapshot=prepared.current_snapshot,
            provider=provider,
            validation_policy=validation_policy,
            requested_tables=prepared.requested_tables,
            base_ref_or_commit=base_ref_or_commit,
            target_branch_ref=target_branch_ref,
        )
        flow_input = SubmitFinalizeFlowInput(
            repository_import_plan=import_plan,
            source_snapshot=prepared.current_snapshot,
            import_artifact=import_artifact,
            runner=self.provider_runner,
            submission_id=acceptance_result.submission_id,
            operation_id=acceptance_result.accepted.operation_id,
            execution_context=RepositoryImportExecutionContext(
                caller_policy=RepositoryImportCallerPolicy.FINALIZE_WRITE_CALLER,
                worktree_context=worktree_context,
            ),
            operation_runtime=operation_runtime,
            worker_id=f"journey-finalize-{dataset_spec.dataset_id}",
        )
        finalize_result = finalize_workspace_submit(
            workspace_store=workspace_store,
            submission_store=submission_store,
            command=WorkspaceSubmitFinalizeWorkflowCommand(
                workspace_finalize_command=WorkspaceSubmitFinalizeCommand(
                    workspace_id=acceptance_result.workspace.workspace_id,
                    operation_id=acceptance_result.accepted.operation_id,
                    submission_id=acceptance_result.submission_id,
                ),
                submit_finalize_flow_input=flow_input,
            ),
        )
        if not finalize_result.workspace_updated:
            raise RuntimeError("workspace was not updated after submit finalize")
        if finalize_result.flow_result.operation.status is not OperationStatus.READY:
            raise RuntimeError("submit finalize flow did not reach READY")
        repository_import_result = finalize_result.flow_result.repository_import_result
        if repository_import_result.status is not RepositoryImportStatus.PASSED:
            raise RuntimeError(
                f"repository import did not pass: {repository_import_result.status.value}"
            )
        if repository_import_result.validation_result is not RepositoryImportValidationResult.PASSED:
            raise RuntimeError(
                f"repository import validation did not pass: {repository_import_result.validation_result.value}"
            )
        if repository_import_result.repository_path is None:
            raise RuntimeError("repository import did not return a repository_path")

        details = {
            "workspace_status": finalize_result.workspace.status.value if finalize_result.workspace is not None else None,
            "operation_id": finalize_result.flow_result.operation.operation_id,
            "repository_path": repository_import_result.repository_path,
            "repository_commit_hash": repository_import_result.commit_hash,
            "provider": repository_import_result.import_provider.value,
            "server_mode": repository_import_result.server_mode.value if repository_import_result.server_mode is not None else None,
            "imported_table_count": repository_import_result.imported_table_count,
            "validation_result": repository_import_result.validation_result.value,
            "parse_duration_ms": repository_import_result.parse_duration_ms,
            "staging_duration_ms": repository_import_result.staging_duration_ms,
            "server_start_ms": repository_import_result.server_start_ms,
            "import_duration_ms": repository_import_result.import_duration_ms,
            "commit_duration_ms": repository_import_result.commit_duration_ms,
            "validation_duration_ms": repository_import_result.validation_duration_ms,
            "cleanup_duration_ms": repository_import_result.cleanup_duration_ms,
            "total_duration_ms": repository_import_result.total_duration_ms,
            "comparison_core_cache_promotion_enabled": comparison_core_cache is not None,
            "comparison_core_cache_promotion_status": None,
            "comparison_core_cache_promotion_lookup_hit": None,
            "comparison_core_cache_promotion_write_applied": None,
            "comparison_core_cache_promotion_key_digest": None,
            "comparison_core_cache_promotion_ms": None,
        }
        if comparison_core_cache is not None:
            canonical_current_commit_hash = repository_import_result.commit_hash or repository_import_result.target_ref
            if canonical_current_commit_hash is None:
                raise RuntimeError("submit finalize did not expose a canonical current commit hash")
            canonical_before_commit_hash = promotion_before_commit_hash or canonical_current_commit_hash
            canonical_provider = self._repository_table_access_provider_for_repo_dir(
                repo_dir=repository_import_result.repository_path,
                repository_id=repository_import_result.repository_id,
                repository_ref=canonical_current_commit_hash,
                resolved_commit_hash=canonical_current_commit_hash,
            )
            canonical_flow_input = ComparisonRiskFlowInput(
                comparison_input=DirectedComparisonInput(
                    before=ComparisonInput(
                        role=ComparisonRole.BEFORE,
                        snapshot=prepared.baseline_snapshot.snapshot,
                        summary=prepared.baseline_snapshot.summary,
                        table_set_ref=prepared.baseline_snapshot.table_set,
                        repository_backed_context=_build_repository_backed_context(
                            snapshot=prepared.baseline_snapshot,
                            repository_id=repository_import_result.repository_id,
                            repository_ref=canonical_before_commit_hash,
                            resolved_commit_hash=canonical_before_commit_hash,
                            provider=canonical_provider,
                        ),
                    ),
                    current=ComparisonInput(
                        role=ComparisonRole.CURRENT,
                        snapshot=prepared.current_snapshot.snapshot,
                        summary=prepared.current_snapshot.summary,
                        table_set_ref=prepared.current_snapshot.table_set,
                        repository_backed_context=_build_repository_backed_context(
                            snapshot=prepared.current_snapshot,
                            repository_id=repository_import_result.repository_id,
                            repository_ref=canonical_current_commit_hash,
                            resolved_commit_hash=canonical_current_commit_hash,
                            provider=canonical_provider,
                        ),
                    ),
                    table_ruleset_version=prepared.current_snapshot.summary.table_ruleset_version,
                    requested_tables=prepared.requested_tables,
                ),
                comparison_core_cache=comparison_core_cache,
                comparison_engine=self.comparison_engine,
            )
            promotion_start = perf_counter()
            promotion_status = "WRITE_SKIPPED"
            promotion_write_applied = False
            promotion_lookup_hit = False
            promotion_error: str | None = None
            promotion_key_digest: DigestRef | None = None
            source_flow_input = ComparisonRiskFlowInput(
                comparison_input=DirectedComparisonInput(
                    before=ComparisonInput(
                        role=ComparisonRole.BEFORE,
                        snapshot=prepared.baseline_snapshot.snapshot,
                        summary=prepared.baseline_snapshot.summary,
                        table_set_ref=prepared.baseline_snapshot.table_set,
                        repository_backed_context=prepared.baseline_context,
                    ),
                    current=ComparisonInput(
                        role=ComparisonRole.CURRENT,
                        snapshot=prepared.current_snapshot.snapshot,
                        summary=prepared.current_snapshot.summary,
                        table_set_ref=prepared.current_snapshot.table_set,
                        repository_backed_context=prepared.current_context,
                    ),
                    table_ruleset_version=prepared.current_snapshot.summary.table_ruleset_version,
                    requested_tables=prepared.requested_tables,
                ),
                comparison_core_cache=comparison_core_cache,
                comparison_engine=self.comparison_engine,
            )
            try:
                promotion_lookup = comparison_core_cache.rekey(
                    source_key=source_flow_input.comparison_core_cache_key(),
                    target_key=canonical_flow_input.comparison_core_cache_key(),
                    validation_status=CacheValidationStatus.COMMIT_VALIDATED,
                    provenance=COMPARISON_CORE_CACHE_PROVENANCE_SUBMIT_FINALIZE_PROMOTION,
                )
            except Exception as exc:  # pragma: no cover - defensive cache promotion path
                promotion_status = "REKEY_FAILED"
                promotion_error = str(exc)
            else:
                promotion_lookup_hit = promotion_lookup.hit
                promotion_key_digest = promotion_lookup.cache_key_digest
                if promotion_lookup.hit:
                    promotion_status = "REKEYED"
                    promotion_write_applied = True
                else:
                    promotion_status = "REKEY_SKIPPED"
            promotion_elapsed_ms = _elapsed_ms(promotion_start)
            details["comparison_core_cache_promotion_ms"] = promotion_elapsed_ms
            details["comparison_core_cache_promotion_status"] = promotion_status
            details["comparison_core_cache_promotion_lookup_hit"] = promotion_lookup_hit
            details["comparison_core_cache_promotion_write_applied"] = promotion_write_applied
            details["comparison_core_cache_promotion_key_digest"] = promotion_key_digest
            details["comparison_core_cache_promotion_write_count"] = 1 if promotion_write_applied else 0
            details["comparison_core_cache_promotion_hit_count"] = 1 if promotion_lookup_hit else 0
            details["comparison_core_cache_promotion_skip_count"] = 0 if promotion_write_applied else 1
            details["comparison_core_cache_promotion_enabled"] = True
            details["comparison_core_cache_promotion_error"] = promotion_error
        return details, finalize_result

    def _open_final_repository_snapshot(
        self,
        *,
        dataset_spec,
        profile: FlowJourneyBenchmarkProfile,
        finalize_result,
        requested_tables: tuple[str, ...],
        run_dir: Path,
    ) -> tuple[Mapping[str, object], _OpenedRepositorySnapshot]:
        del run_dir, profile
        repository_import_result = finalize_result.flow_result.repository_import_result
        if repository_import_result.repository_path is None:
            raise RuntimeError("repository_path must exist before opening the final repository ref")
        repository_ref = repository_import_result.commit_hash or repository_import_result.target_ref
        materialize_start = perf_counter()
        final_snapshot = self._materialize_repository_path_snapshot(
            repo_dir=repository_import_result.repository_path,
            repository_id=repository_import_result.repository_id,
            repository_ref=repository_ref,
            requested_tables=requested_tables,
        )
        materialize_ms = _elapsed_ms(materialize_start)
        provider = self._repository_table_access_provider_for_repo_dir(
            repo_dir=repository_import_result.repository_path,
            repository_id=repository_import_result.repository_id,
            repository_ref=repository_ref,
            resolved_commit_hash=repository_ref,
        )
        current_context = _build_repository_backed_context(
            snapshot=final_snapshot,
            repository_id=repository_import_result.repository_id,
            repository_ref=repository_ref,
            resolved_commit_hash=repository_ref,
            provider=provider,
        )
        details = {
            "repository_path": repository_import_result.repository_path,
            "repository_ref": repository_ref,
            "resolved_commit_hash": final_snapshot.snapshot.repository_ref,
            "table_count": final_snapshot.summary.table_count,
            "row_count_total": final_snapshot.summary.row_count_total,
            "open_ref_materialize_ms": materialize_ms,
        }
        opened = _OpenedRepositorySnapshot(
            snapshot=final_snapshot,
            context=current_context,
            details=details,
        )
        return details, opened

    def _materialize_snapshot_from_rows(
        self,
        *,
        dataset_spec,
        source_snapshot: SnapshotMaterializationResult,
        rows_by_table: Mapping[str, tuple[tuple[object | None, ...], ...]],
        repository_ref: str,
        resolved_commit_hash: str,
        requested_tables: tuple[str, ...],
    ) -> SnapshotMaterializationResult:
        del dataset_spec, repository_ref, resolved_commit_hash
        if source_snapshot.table_set is None:
            raise ValueError("source_snapshot must include a table_set")

        source_tables = source_snapshot.table_set.tables
        requested_table_names = set(requested_tables)
        selected_table_names = tuple(
            table_name
            for table_name in sorted(source_tables)
            if not requested_table_names or table_name in requested_table_names
        )
        missing_requested_tables = sorted(requested_table_names - set(source_tables))
        if missing_requested_tables:
            raise ValueError(
                f"requested_tables are not present in source snapshot: {missing_requested_tables}"
            )

        updated_tables: dict[str, object] = {}
        updated_descriptors = []
        for table_name in selected_table_names:
            source_table = source_tables[table_name]
            rows = rows_by_table.get(table_name)
            if rows is None:
                raise KeyError(f"missing rows for table: {table_name}")
            normalized_rows = normalize_snapshot_rows(rows, source_table.descriptor.columns)
            raw_content_digest = stable_rows_digest(
                normalized_rows,
                tuple(column.name for column in source_table.descriptor.columns),
            )
            updated_descriptor = replace(
                source_table.descriptor,
                row_count=len(normalized_rows),
                raw_content_digest=raw_content_digest,
                business_content_digest=raw_content_digest,
            )
            updated_reader = replace(
                source_table.reader,
                _descriptor=updated_descriptor,
                _rows=normalized_rows,
            )
            updated_table = replace(
                source_table,
                descriptor=updated_descriptor,
                reader=updated_reader,
                raw_create_sql=source_table.raw_create_sql,
            )
            updated_tables[table_name] = updated_table
            updated_descriptors.append(updated_descriptor)

        updated_descriptors = tuple(updated_descriptors)
        row_count_total = sum(descriptor.row_count for descriptor in updated_descriptors)
        source_digest = source_snapshot.snapshot.source_digest
        if source_digest is None:
            raise ValueError("source_snapshot must include a source_digest")
        raw_state_digest = DigestRef.from_payload(
            {
                "materialization_stage": source_snapshot.summary.materialization_stage,
                "table_count": len(updated_descriptors),
                "row_count_total": row_count_total,
                "tables": [
                    {
                        "table_name": descriptor.table_name,
                        "row_count": descriptor.row_count,
                        "raw_content_digest": descriptor.materialization_digest.to_payload(),
                    }
                    for descriptor in updated_descriptors
                ],
            }
        )
        snapshot_digest = DigestRef.from_payload(
            {
                "materialization_stage": source_snapshot.summary.materialization_stage,
                "source_kind": source_snapshot.snapshot.source_kind,
                "source_digest": source_digest.to_payload(),
                "parser_version": source_snapshot.snapshot.parser_version,
                "table_ruleset_version": source_snapshot.snapshot.table_ruleset_version,
                "scalar_encoding_version": source_snapshot.snapshot.scalar_encoding_version,
                "row_materialization_profile": source_snapshot.snapshot.row_materialization_profile,
                "requested_tables": sorted(requested_tables),
                "tables": [
                    {
                        "table_name": descriptor.table_name,
                        "compare_schema_digest": descriptor.compare_schema_digest.to_payload(),
                        "raw_content_digest": descriptor.materialization_digest.to_payload(),
                        "row_count": descriptor.row_count,
                    }
                    for descriptor in updated_descriptors
                ],
            }
        )
        snapshot_id = f"snapshot:{snapshot_digest.hex_digest}"
        source_context = source_snapshot.summary.source_context or source_snapshot.snapshot.source_context
        summary = replace(
            source_snapshot.summary,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            raw_state_digest=raw_state_digest,
            business_state_digest=raw_state_digest,
            table_count=len(updated_descriptors),
            row_count_total=row_count_total,
            tables=updated_descriptors,
            source_context=source_context,
        )
        snapshot = replace(
            source_snapshot.snapshot,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            raw_state_digest=raw_state_digest,
            business_state_digest=raw_state_digest,
            summary=summary,
            source_context=source_context,
        )
        table_set = replace(
            source_snapshot.table_set,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            tables=updated_tables,
        )
        return replace(
            source_snapshot,
            snapshot=snapshot,
            summary=summary,
            table_set=table_set,
        )

    def _materialize_repository_path_snapshot(
        self,
        *,
        repo_dir: Path,
        repository_id: str,
        repository_ref: str,
        requested_tables: tuple[str, ...],
    ) -> SnapshotMaterializationResult:
        backend = _RepositoryImportRepositoryBackend(
            repo_dir=repo_dir,
            dolt=self.provider_runner.dolt,
        )
        provider = LocalRepositoryTableAccessProvider(backend=backend)
        return materialize_repository_ref(
            RepositoryRefMaterializationInput(
                repository_ref=RepositoryRef(
                    repository_id=repository_id,
                    repository_ref=repository_ref,
                ),
                repository_table_access_provider=provider,
                requested_tables=requested_tables,
            )
        )

    def _repository_table_access_provider_for_snapshot(
        self,
        *,
        snapshot: SnapshotMaterializationResult,
        repository_id: str,
        repository_ref: str,
        resolved_commit_hash: str,
        rows_by_table: Mapping[str, tuple[tuple[object | None, ...], ...]],
    ) -> LocalRepositoryTableAccessProvider:
        backend = InMemoryRepositoryBackend(
            catalog=_build_catalog_from_snapshot(
                source_snapshot=snapshot,
                repository_id=repository_id,
                repository_ref=repository_ref,
                resolved_commit_hash=resolved_commit_hash,
                rows_by_table=rows_by_table,
            ),
            rows_by_table=rows_by_table,
        )
        return LocalRepositoryTableAccessProvider(backend=backend)

    def _repository_table_access_provider_for_repo_dir(
        self,
        *,
        repo_dir: Path,
        repository_id: str,
        repository_ref: str,
        resolved_commit_hash: str,
    ) -> LocalRepositoryTableAccessProvider:
        backend = _RepositoryImportRepositoryBackend(
            repo_dir=repo_dir,
            dolt=self.provider_runner.dolt,
        )
        return LocalRepositoryTableAccessProvider(backend=backend)

    def _build_journey_cache_bundle(self, profile: FlowJourneyBenchmarkProfile) -> _JourneyCacheBundle:
        if profile is FlowJourneyBenchmarkProfile.FULL_JOURNEY_WARM:
            cache = self.shared_projection_table_cache or InMemoryProjectionTableCache()
            comparison_core_cache = self.shared_comparison_core_cache or InMemoryComparisonCoreCache()
            return _JourneyCacheBundle(
                baseline_preview_cache=cache,
                modified_preview_cache=cache,
                baseline_preview_comparison_core_cache=comparison_core_cache,
                modified_preview_comparison_core_cache=comparison_core_cache,
            )
        return _JourneyCacheBundle(
            baseline_preview_cache=InMemoryProjectionTableCache(),
            modified_preview_cache=InMemoryProjectionTableCache(),
            baseline_preview_comparison_core_cache=InMemoryComparisonCoreCache(),
            modified_preview_comparison_core_cache=InMemoryComparisonCoreCache(),
        )

    def _run_stage(
        self,
        stage_name: str,
        callback,
    ) -> tuple[FlowJourneyBenchmarkStageResult, object | None, Exception | None]:
        start = perf_counter()
        try:
            details, value = callback()
            return (
                FlowJourneyBenchmarkStageResult(
                    stage_name=stage_name,
                    status="SUCCEEDED",
                    duration_ms=_elapsed_ms(start),
                    details=details,
                ),
                value,
                None,
            )
        except Exception as exc:  # pragma: no cover - stage-level failure path
            return (
                FlowJourneyBenchmarkStageResult(
                    stage_name=stage_name,
                    status="FAILED",
                    duration_ms=_elapsed_ms(start),
                    details={"error": str(exc)},
                ),
                None,
                exc,
            )

    def _build_result(
        self,
        *,
        dataset_spec,
        resolution: object,
        profile: FlowJourneyBenchmarkProfile,
        provider: RepositoryImportProvider,
        requested_tables: tuple[str, ...],
        stages: tuple[FlowJourneyBenchmarkStageResult, ...],
        workspace_id: str | None = None,
        submission_id: str | None = None,
        repository_id: str | None = None,
        repository_path: Path | None = None,
        repository_commit_hash: str | None = None,
        diagnostics: tuple[DiagnosticRecord, ...] = (),
        submission_kind: FlowJourneyBenchmarkSubmissionKind = FlowJourneyBenchmarkSubmissionKind.INITIAL_MODIFIED_SUBMISSION,
    ) -> FlowJourneyBenchmarkResult:
        return FlowJourneyBenchmarkResult(
            dataset_id=dataset_spec.dataset_id,
            dataset_kind=dataset_spec.dataset_kind,
            profile=profile,
            provider=provider,
            status=FlowJourneyBenchmarkStatus.PASSED,
            source_sql_digest=resolution.manifest.source_sql_digest,
            source_sql_bytes=resolution.manifest.source_sql_bytes,
            table_count=resolution.manifest.table_count,
            row_count_total=resolution.manifest.row_count_total,
            requested_tables=requested_tables,
            workspace_id=workspace_id,
            submission_id=submission_id,
            repository_id=repository_id,
            repository_path=repository_path,
            repository_commit_hash=repository_commit_hash,
            stages=stages,
            diagnostics=diagnostics,
            submission_kind=submission_kind,
        )

    def _build_failed_result(
        self,
        *,
        dataset_spec,
        resolution: object,
        profile: FlowJourneyBenchmarkProfile,
        provider: RepositoryImportProvider,
        requested_tables: tuple[str, ...],
        run_dir: Path,
        stages: tuple[FlowJourneyBenchmarkStageResult, ...],
        failure_stage: str,
        failure_reason: str,
        diagnostics: tuple[DiagnosticRecord, ...],
        workspace_id: str | None = None,
        submission_id: str | None = None,
        repository_id: str | None = None,
        repository_path: Path | None = None,
        repository_commit_hash: str | None = None,
        submission_kind: FlowJourneyBenchmarkSubmissionKind = FlowJourneyBenchmarkSubmissionKind.INITIAL_MODIFIED_SUBMISSION,
    ) -> FlowJourneyBenchmarkResult:
        del run_dir
        return FlowJourneyBenchmarkResult(
            dataset_id=dataset_spec.dataset_id,
            dataset_kind=dataset_spec.dataset_kind,
            profile=profile,
            provider=provider,
            status=FlowJourneyBenchmarkStatus.FAILED,
            source_sql_digest=resolution.manifest.source_sql_digest,
            source_sql_bytes=resolution.manifest.source_sql_bytes,
            table_count=resolution.manifest.table_count,
            row_count_total=resolution.manifest.row_count_total,
            requested_tables=requested_tables,
            workspace_id=workspace_id,
            submission_id=submission_id,
            repository_id=repository_id,
            repository_path=repository_path,
            repository_commit_hash=repository_commit_hash,
            stages=stages,
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            diagnostics=diagnostics,
            submission_kind=submission_kind,
        )


def _build_upload_preview_input(
    *,
    comparison_input: ComparisonComputeInput,
    records_store: LocalArtifactStore,
    comparison_engine: ComparisonEngine,
    comparison_core_cache: ComparisonCoreCache,
    projection_table_cache: ProjectionTableCache,
    risk_engine: RiskEngine,
) -> UploadPreviewFlowInput:
    return UploadPreviewFlowInput(
        comparison_input=comparison_input,
        records_store=records_store,
        comparison_engine=comparison_engine,
        comparison_core_cache=comparison_core_cache,
        projection_table_cache=projection_table_cache,
        risk_engine=risk_engine,
        surface_assembler=SurfaceAssembler(),
        operation_runtime=OperationRuntime(),
        worker_id="journey-upload-preview-worker",
        operation_id=_operation_id("preview", comparison_input.before.snapshot.repository_id or "dataset", "journey"),
    )


def _comparison_risk_input(
    *,
    before_snapshot: SnapshotMaterializationResult,
    current_snapshot: SnapshotMaterializationResult,
    before_context: RepositoryBackedComparisonContext,
    current_context: RepositoryBackedComparisonContext,
    requested_tables: tuple[str, ...],
    records_store: LocalArtifactStore,
    projection_table_cache: ProjectionTableCache,
    comparison_engine: ComparisonEngine,
    risk_engine: RiskEngine | None = None,
) -> ComparisonRiskFlowInput:
    before_input = ComparisonInput(
        role=ComparisonRole.BEFORE,
        snapshot=before_snapshot.snapshot,
        summary=before_snapshot.summary,
        table_set_ref=before_snapshot.table_set,
        repository_backed_context=before_context,
    )
    current_input = ComparisonInput(
        role=ComparisonRole.CURRENT,
        snapshot=current_snapshot.snapshot,
        summary=current_snapshot.summary,
        table_set_ref=current_snapshot.table_set,
        repository_backed_context=current_context,
    )
    directed_input = DirectedComparisonInput(
        before=before_input,
        current=current_input,
        table_ruleset_version=current_snapshot.summary.table_ruleset_version,
        requested_tables=requested_tables,
    )
    return ComparisonRiskFlowInput(
        comparison_input=directed_input,
        records_store=records_store,
        comparison_engine=comparison_engine,
        projection_table_cache=projection_table_cache,
        risk_engine=risk_engine or RiskEngine(),
    )


def _build_repository_import_plan(
    *,
    dataset_spec,
    current_snapshot: SnapshotMaterializationResult,
    provider: RepositoryImportProvider,
    validation_policy: RepositoryImportValidationPolicy | str,
    requested_tables: tuple[str, ...],
    base_ref_or_commit: str = "main",
    target_branch_ref: str | None = None,
) -> RepositoryImportPlan:
    assert current_snapshot.table_set is not None
    plan_tables = build_physical_repository_import_plan_tables(current_snapshot)
    physical_table_names = {table.table_name for table in plan_tables}
    validation_table_names = tuple(
        table_name for table_name in requested_tables if table_name in physical_table_names
    )
    server_mode = _provider_server_mode(provider)
    return RepositoryImportPlan(
        repository_id=dataset_spec.dataset_id,
        base_ref_or_commit=base_ref_or_commit,
        target_branch_ref=target_branch_ref or f"refs/heads/{dataset_spec.dataset_id}-journey",
        source_snapshot_id=current_snapshot.summary.snapshot_id,
        source_snapshot_digest=current_snapshot.summary.snapshot_digest,
        table_ruleset_version=current_snapshot.summary.table_ruleset_version,
        provider_preference=provider,
        server_mode=server_mode,
        tables=plan_tables,
        validation_policy=RepositoryImportValidationPolicy(validation_policy),
        validation_table_names=validation_table_names,
    )


def _provider_server_mode(provider: RepositoryImportProvider) -> RepositoryImportServerMode:
    if provider == RepositoryImportProvider.LOAD_DATA:
        return RepositoryImportServerMode.PER_IMPORT
    if provider == RepositoryImportProvider.DOLT_SERVER_BULK_LOAD:
        return RepositoryImportServerMode.PER_IMPORT
    if provider == RepositoryImportProvider.SERVER_SESSION_BULK_LOAD:
        return RepositoryImportServerMode.WARM_SESSION
    return RepositoryImportServerMode.DISABLED


def _build_catalog_from_snapshot(
    *,
    source_snapshot: SnapshotMaterializationResult,
    repository_id: str,
    repository_ref: str,
    resolved_commit_hash: str,
    rows_by_table: Mapping[str, tuple[tuple[object | None, ...], ...]],
) -> RepositoryTableCatalog:
    assert source_snapshot.table_set is not None
    tables: dict[str, RepositoryTableCatalogTable] = {}
    for table_name, table in source_snapshot.table_set.tables.items():
        descriptor = table.descriptor
        columns = tuple(
            RepositoryTableColumn(
                name=column.name,
                ordinal=index,
                display_name=column.display_name,
                scalar_type=column.scalar_type,
                nullable=column.nullable,
                raw_type=column.scalar_type,
            )
            for index, column in enumerate(descriptor.columns)
        )
        tables[descriptor.table_name] = RepositoryTableCatalogTable(
            table_name=descriptor.table_name,
            display_table_name=descriptor.display_table_name,
            columns=columns,
            primary_key_columns=descriptor.compare_key_columns,
            row_count=len(rows_by_table[descriptor.table_name]),
            repository_table_version=descriptor.table_ruleset_version,
            table_root_hash=_stable_commit_hash(
                repository_id,
                repository_ref,
                resolved_commit_hash,
                descriptor.table_name,
            ),
        )
    return RepositoryTableCatalog(
        repository_id=repository_id,
        repository_ref=repository_ref,
        resolved_commit_hash=resolved_commit_hash,
        repository_server_contract_version="backend-vnext/flow-journey/repository-server/v1",
        tables=tables,
    )


def _build_repository_backed_context(
    *,
    snapshot: SnapshotMaterializationResult,
    repository_id: str,
    repository_ref: str,
    resolved_commit_hash: str,
    provider: LocalRepositoryTableAccessProvider,
) -> RepositoryBackedComparisonContext:
    return RepositoryBackedComparisonContext(
        repository_id=repository_id,
        resolved_commit_hash=resolved_commit_hash,
        repository_server_contract_version="backend-vnext/flow-journey/repository-server/v1",
        repository_ref=repository_ref,
        repository_table_access_provider=provider,
        dolt_version=None,
    )


def _snapshot_rows_by_table(
    snapshot: SnapshotMaterializationResult,
) -> dict[str, tuple[tuple[object | None, ...], ...]]:
    if snapshot.table_set is None:
        raise ValueError("snapshot must include a table_set")
    rows_by_table: dict[str, tuple[tuple[object | None, ...], ...]] = {}
    for table_name, table in snapshot.table_set.tables.items():
        rows = tuple(tuple(row) for row in table.reader.iter_rows())
        rows_by_table[table_name] = rows
    return rows_by_table


def _mutate_rows_by_table(
    rows_by_table: Mapping[str, tuple[tuple[object | None, ...], ...]],
    *,
    preferred_tables: Sequence[str],
) -> tuple[dict[str, tuple[tuple[object | None, ...], ...]], dict[str, object]]:
    ordered_tables = list(dict.fromkeys([table for table in preferred_tables if table in rows_by_table]))
    for table_name in rows_by_table:
        if table_name not in ordered_tables:
            ordered_tables.append(table_name)
    for table_name in ordered_tables:
        rows = rows_by_table.get(table_name) or ()
        if not rows:
            continue
        first_row = list(rows[0])
        if not first_row:
            continue
        mutated_index = 0
        original_value = first_row[mutated_index]
        mutated_value = _mutate_scalar(original_value)
        if mutated_value == original_value:
            mutated_index = min(len(first_row) - 1, 0)
            mutated_value = _mutate_scalar(first_row[mutated_index])
        first_row[mutated_index] = mutated_value
        mutated_rows = list(rows)
        mutated_rows[0] = tuple(first_row)
        mutated_rows_by_table = dict(rows_by_table)
        mutated_rows_by_table[table_name] = tuple(mutated_rows)
        return (
            mutated_rows_by_table,
            {
                "table_name": table_name,
                "column_index": mutated_index,
                "before_value": original_value,
                "after_value": mutated_value,
            },
        )
    return dict(rows_by_table), {}


def _mutate_scalar(value: object | None) -> object:
    if value is None:
        return "bench"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1_000_000
    if isinstance(value, float):
        return value + 1_000.0
    if isinstance(value, bytes):
        return value + b"__bench"
    if isinstance(value, str):
        return f"{value}__bench"
    if isinstance(value, datetime):
        return value.replace(microsecond=(value.microsecond + 1) % 1_000_000)
    return f"{value}__bench"


def _requested_tables_for_resolution(resolution: object) -> tuple[str, ...]:
    source_snapshot = resolution.source_snapshot
    if source_snapshot.table_set is None:
        return ()
    return tuple(source_snapshot.table_set.tables)


def _coerce_profile(profile: FlowJourneyBenchmarkProfile | str) -> FlowJourneyBenchmarkProfile:
    return FlowJourneyBenchmarkProfile(profile)


def _select_provider(
    dataset_spec,
    providers: Mapping[str, RepositoryImportProvider | str] | None,
) -> RepositoryImportProvider:
    # Flow-level submit finalize is currently pinned to replay-only.
    del dataset_spec, providers
    return RepositoryImportProvider.SQL_DUMP_REPLAY


def _count_native_routes(provider_routes: Sequence[tuple[str, str]]) -> int:
    return sum(1 for _, provider in provider_routes if provider == DOLT_NATIVE_PROVIDER)


def _count_diagnostics(diagnostics: Sequence[DiagnosticRecord], code: str) -> int:
    return sum(1 for diagnostic in diagnostics if diagnostic.code == code)


def _operation_id(prefix: str, dataset_id: str, profile: str) -> str:
    return f"{prefix}-{dataset_id}-{profile}-{uuid4().hex[:8]}"


def _build_run_id() -> str:
    return f"flow-journey-benchmark-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:8]}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_machine_profile_id() -> str:
    hostname = os.uname().nodename if hasattr(os, "uname") else None
    if not hostname:
        hostname = os.environ.get("HOSTNAME") or "local"
    return f"local-{hostname}"


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


def _stable_commit_hash(*parts: object) -> str:
    return DigestRef.from_payload({"parts": parts}).to_payload()


def _unique_preserve_order(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _failure_diagnostic(stage_key: str, exc: Exception, stage_name: str) -> DiagnosticRecord:
    return DiagnosticRecord(
        code=f"benchmark.flow.{stage_key}.failed",
        message=f"flow journey stage failed: {stage_name}",
        phase="benchmark",
        severity="ERROR",
        details={"stage_name": stage_name, "error": str(exc)},
    )
