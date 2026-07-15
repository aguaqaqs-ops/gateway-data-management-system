from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from ...contracts.repository import (
    MainlinePromotionConflict,
    OperationStatus as RepositoryOperationStatus,
    PromoteMainlineResult,
    RepositoryOperationContext,
    RepositoryOperationRecord,
    RepositoryOperationType,
)

from ...artifacts import LocalArtifactStore
from ...cache import (
    ComparisonCoreCache,
    FilesystemComparisonCoreCache,
    FilesystemProjectionTableCache,
    ProjectionTableCache,
)
from ...capabilities.comparison import (
    ComparisonEngine,
    ComparisonInput,
    ComparisonRole,
    DirectedComparisonInput,
    RepositoryBackedComparisonContext,
)
from ...capabilities.bundle_assembly import BundleInput
from ...capabilities.risk_evaluation import RiskEngine
from ...capabilities.repository_import import RepositoryImportProvider, RepositoryImportValidationPolicy
from ...capabilities.repository_import import RepositoryImportWorktreeContext
from ...capabilities.repository_import.dolt_cli import DoltCli
from ...capabilities.repository_import.repository_ref_readback import (
    _RepositoryImportRepositoryBackend,
)
from ...capabilities.snapshot_materialization import (
    SnapshotMaterializationResult,
    materialize_repository_ref,
    read_repository_ref_summary_snapshot,
)
from ...core import DigestRef, DiagnosticRecord
from ...archive import (
    ArchiveCandidateRole,
    ArchiveCandidateSourceKind,
    ArchiveCandidateUpsertCommand,
    ArchiveConfirmWorkspaceCommand,
    ArchiveDryRunCommand,
    ArchiveExecuteCommand,
    ArchiveOpenBatchCommand,
    ArchiveSelectCandidatesCommand,
    ArchiveService,
)
from ...flows import (
    ComparisonRiskFlowInput,
    HistoryCompareFlowInput,
    HistoryComparePairInput,
    SubmissionReviewAction,
    SubmissionReviewFlowInput,
    build_history_compare_pair_input,
    run_history_compare,
    run_submission_review,
)
from ...operations import OperationRuntime
from ...repository_server import (
    LocalRepositoryTableAccessProvider,
    RepositoryRef,
    RepositoryServerTableCache,
)
from ...submissions.review import SubmissionReviewCommand, SubmissionReviewService
from ...submissions import (
    InMemorySubmissionIdentityStore,
    InMemorySubmissionStore,
)
from ...workspaces import InMemoryWorkspaceStore
from .._paths import resolve_benchmark_path
from ..flow_journey import FlowJourneyBenchmarkProfile, FlowJourneyBenchmarkRunner
from ..flow_journey.runner import (
    _count_diagnostics as _journey_count_diagnostics,
    _default_machine_profile_id as _journey_default_machine_profile_id,
    _elapsed_ms as _journey_elapsed_ms,
    _failure_diagnostic as _journey_failure_diagnostic,
    _operation_id as _journey_operation_id,
)
from ..history_compare import HistoryCompareBenchmarkRunner
from ..history_compare.models import HistoryCompareBenchmarkStageResult
from ..repository_import import (
    RepositoryImportBenchmarkDatasetManifest,
    RepositoryImportBenchmarkDatasetResolution,
    RepositoryImportBenchmarkMachineProfile,
    RepositoryImportBenchmarkDatasetSpec,
    RepositoryImportDatasetManifestBuilder,
    RepositoryImportDatasetResolver,
    detect_local_machine_profile,
)
from .models import (
    WorkflowLadderBenchmarkCompareResult,
    WorkflowLadderBenchmarkNodeResult,
    WorkflowLadderBenchmarkStageResult,
    WorkflowLadderBenchmarkStatus,
    WorkflowLadderBenchmarkSummary,
)
from .report import MarkdownReportWriter, SummaryJsonWriter


DEFAULT_DATASET_ROOT = Path("/home/issac/test-dir/business-benchmark-data")
DEFAULT_DATASET_IDS: tuple[str, ...] = (
    "business_small_cut/small_cut",
    "business_small_cut/small_cut-1",
    "business_small_cut/small_cut-2",
)
DEFAULT_FLOW_PROFILE = FlowJourneyBenchmarkProfile.FULL_JOURNEY_WARM
DEFAULT_VALIDATION_POLICY = RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY
DEFAULT_COMPARE_SCENARIO_NAMES: tuple[str, ...] = (
    "TWO_NODE_COMPARE",
    "THREE_NODE_DUAL_PAIR_COMPARE",
)


@dataclass(frozen=True, slots=True)
class _LadderFlowDatasetSpec:
    dataset_id: str
    dataset_kind: str


@dataclass(frozen=True, slots=True)
class _LadderRepositoryContext:
    repository_id: str
    run_dir: Path
    repo_dir: Path


@dataclass(frozen=True, slots=True)
class _RecordedRepositoryRefSession:
    delegate: object
    recorder: "_RepositoryRefMaterializationRecorder"

    def get_catalog(self):  # type: ignore[no-untyped-def]
        start = perf_counter()
        try:
            return self.delegate.get_catalog()
        finally:
            self.recorder.catalog_duration_ms += _journey_elapsed_ms(start)

    def open_table_reader(self, table_name: str):  # type: ignore[no-untyped-def]
        start = perf_counter()
        try:
            return self.delegate.open_table_reader(table_name)
        finally:
            self.recorder.table_reader_duration_ms += _journey_elapsed_ms(start)

    def export_table_artifact(self, table_name: str, export_format: str):  # type: ignore[no-untyped-def]
        start = perf_counter()
        try:
            return self.delegate.export_table_artifact(table_name, export_format)
        finally:
            self.recorder.table_export_duration_ms += _journey_elapsed_ms(start)

    def close(self) -> None:
        self.delegate.close()

    def __enter__(self) -> "_RecordedRepositoryRefSession":
        self.delegate.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.delegate.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return getattr(self.delegate, name)


@dataclass(slots=True)
class _RepositoryRefMaterializationRecorder:
    open_ref_duration_ms: int = 0
    catalog_duration_ms: int = 0
    table_reader_duration_ms: int = 0
    table_export_duration_ms: int = 0

    def to_payload(self) -> dict[str, object]:
        return {
            "open_ref_duration_ms": self.open_ref_duration_ms,
            "catalog_duration_ms": self.catalog_duration_ms,
            "table_reader_duration_ms": self.table_reader_duration_ms,
            "table_export_duration_ms": self.table_export_duration_ms,
        }


class _RecordingRepositoryTableAccessProvider:
    def __init__(self, delegate: LocalRepositoryTableAccessProvider) -> None:
        self.delegate = delegate
        self.recorder = _RepositoryRefMaterializationRecorder()

    def open_ref(self, repository_ref: RepositoryRef, timeout_policy=None):  # type: ignore[no-untyped-def]
        start = perf_counter()
        session = self.delegate.open_ref(repository_ref, timeout_policy=timeout_policy)
        self.recorder.open_ref_duration_ms += _journey_elapsed_ms(start)
        return _RecordedRepositoryRefSession(session, self.recorder)


@dataclass(frozen=True, slots=True)
class _BenchmarkRepositoryServicePort:
    repository_id: str
    repo_dir: Path
    dolt: DoltCli

    def promote_mainline(self, request, *, context):  # type: ignore[no-untyped-def]
        current_main = self.dolt.resolve_ref_commit(
            repository_id=self.repository_id,
            ref="refs/heads/main",
            repo_dir=self.repo_dir,
        )
        if current_main != request.expected_base_main_hash:
            raise MainlinePromotionConflict(
                repository_id=request.repository_id,
                expected_base_main_hash=request.expected_base_main_hash,
                actual_main_hash=current_main,
                target_main_hash=request.selected_modified_commit_hash,
            )
        self.dolt.branch_force(self.repo_dir, "main", request.selected_modified_commit_hash)
        new_main = self.dolt.resolve_ref_commit(
            repository_id=self.repository_id,
            ref="refs/heads/main",
            repo_dir=self.repo_dir,
        )
        if new_main is None:
            raise RuntimeError("main branch promotion did not produce a commit hash")
        operation_record = RepositoryOperationRecord(
            operation_id=context.operation_id,
            idempotency_key=request.idempotency_key,
            request_hash=request.request_hash,
            repository_id=request.repository_id,
            operation_type=RepositoryOperationType.PROMOTE_MAINLINE,
            status=RepositoryOperationStatus.SUCCEEDED,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            before_ref="refs/heads/main",
            before_commit=current_main,
            after_ref="refs/heads/main",
            after_commit=new_main,
            message_summary="mainline promoted",
        )
        return PromoteMainlineResult(
            repository_id=request.repository_id,
            batch_id=request.batch_id,
            old_main_hash=request.expected_base_main_hash,
            new_main_hash=new_main,
            selected_modified_candidate_id=request.selected_modified_candidate_id,
            selected_initial_history_candidate_ids=tuple(
                candidate.candidate_id for candidate in request.selected_initial_history_candidates
            ),
            repository_operation_id=context.operation_id,
            request_hash=request.request_hash,
            idempotent_replay=False,
            operation_record=operation_record,
        )


class WorkflowLadderBenchmarkRunner:
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
        self.repository_ref_cache = repository_ref_cache or RepositoryServerTableCache(
            self.run_root / "repository-ref-cache"
        )
        self.comparison_core_cache = comparison_core_cache or FilesystemComparisonCoreCache(
            self.run_root / "comparison-core-cache"
        )
        self.projection_table_cache = projection_table_cache or FilesystemProjectionTableCache(
            self.run_root / "projection-table-cache"
        )
        self.flow_journey_bridge = FlowJourneyBenchmarkRunner(
            dataset_root=self.dataset_root,
            run_root=self.run_root / "_journey_bridge",
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
            machine_profile=self.machine_profile,
            comparison_core_cache=self.comparison_core_cache,
            projection_table_cache=self.projection_table_cache,
        )
        self.history_compare_bridge = HistoryCompareBenchmarkRunner(
            dataset_root=self.dataset_root,
            run_root=self.run_root / "_history_compare_bridge",
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
            machine_profile=self.machine_profile,
            repository_ref_cache=self.repository_ref_cache,
            comparison_core_cache=self.comparison_core_cache,
            projection_table_cache=self.projection_table_cache,
        )
        self.dataset_resolver = RepositoryImportDatasetResolver(self.dataset_root)
        self.dataset_manifest_builder = RepositoryImportDatasetManifestBuilder()
        self.summary_path = self.run_root / "summary.json"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.result_out.parent.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        datasets: Sequence[str] | None = DEFAULT_DATASET_IDS,
        validation_policy: RepositoryImportValidationPolicy | str = DEFAULT_VALIDATION_POLICY,
    ) -> WorkflowLadderBenchmarkSummary:
        self.run_root.mkdir(parents=True, exist_ok=True)
        selected_dataset_ids = DEFAULT_DATASET_IDS if datasets is None else tuple(datasets)
        if len(selected_dataset_ids) < 3:
            raise ValueError("workflow ladder benchmark requires at least three datasets")
        selected_specs = self.dataset_resolver.resolve(selected_dataset_ids)
        selected_resolutions = {
            spec.dataset_id: self.dataset_manifest_builder.build(spec)
            for spec in selected_specs
        }
        ladder_repository_context = self._build_ladder_repository_context(selected_dataset_ids)

        diagnostics: list[DiagnosticRecord] = []
        node_results: list[WorkflowLadderBenchmarkNodeResult] = []
        compare_results: list[WorkflowLadderBenchmarkCompareResult] = []
        execution_order: list[str] = []

        for index, spec in enumerate(selected_specs):
            resolution = selected_resolutions[spec.dataset_id]
            node_result = self._run_node_lifecycle(
                node_index=index,
                spec=spec,
                resolution=resolution,
                validation_policy=validation_policy,
                ladder_repository_context=ladder_repository_context,
            )
            diagnostics.extend(node_result.diagnostics)
            if node_result.status is WorkflowLadderBenchmarkStatus.FAILED:
                summary = self._build_summary(
                    status=WorkflowLadderBenchmarkStatus.FAILED,
                    dataset_ids=selected_dataset_ids,
                    node_results=tuple(node_results + [node_result]),
                    compare_results=tuple(compare_results),
                    execution_order=tuple(execution_order + [f"NODE[{spec.dataset_id}]"]),
                    failure_stage=node_result.failure_stage or "NODE",
                    failure_reason=node_result.failure_reason or "workflow ladder node failed",
                    diagnostics=tuple(diagnostics),
                )
                self._write_outputs(summary)
                return summary
            node_results.append(node_result)
            execution_order.append(f"NODE[{spec.dataset_id}]")

        compare_plans: list[tuple[str, tuple[tuple[int, int], ...]]] = [
            (DEFAULT_COMPARE_SCENARIO_NAMES[0], ((0, 1),)),
            (DEFAULT_COMPARE_SCENARIO_NAMES[1], ((0, 1), (1, 2))),
        ]
        for scenario_name, pair_indexes in compare_plans:
            compare_result = self._run_compare_scenario(
                scenario_name=scenario_name,
                pair_indexes=pair_indexes,
                node_results=tuple(node_results),
            )
            diagnostics.extend(compare_result.diagnostics)
            if compare_result.status is WorkflowLadderBenchmarkStatus.FAILED:
                summary = self._build_summary(
                    status=WorkflowLadderBenchmarkStatus.FAILED,
                    dataset_ids=selected_dataset_ids,
                    node_results=tuple(node_results),
                    compare_results=tuple(compare_results + [compare_result]),
                    execution_order=tuple(execution_order + [f"COMPARE[{scenario_name}]"]),
                    failure_stage=compare_result.failure_stage or "HISTORY_COMPARE",
                    failure_reason=compare_result.failure_reason or "workflow ladder compare failed",
                    diagnostics=tuple(diagnostics),
                )
                self._write_outputs(summary)
                return summary
            compare_results.append(compare_result)
            execution_order.append(f"COMPARE[{scenario_name}]")

        summary = self._build_summary(
            status=WorkflowLadderBenchmarkStatus.PASSED,
            dataset_ids=selected_dataset_ids,
            node_results=tuple(node_results),
            compare_results=tuple(compare_results),
            execution_order=tuple(execution_order),
            failure_stage=None,
            failure_reason=None,
            diagnostics=tuple(diagnostics),
        )
        self._write_outputs(summary)
        return summary

    def _build_ladder_repository_context(
        self,
        dataset_ids: Sequence[str],
    ) -> _LadderRepositoryContext:
        repository_id = _ladder_repository_id_from_dataset_ids(dataset_ids)
        run_dir = self.run_root / "ladder-repository"
        repo_dir = run_dir / "repos" / _path_fragment(repository_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        repo_dir.mkdir(parents=True, exist_ok=True)
        provider_runner = self.flow_journey_bridge.provider_runner
        provider_runner.dolt.init_repo(
            repo_dir,
            name=provider_runner.init_name,
            email=provider_runner.init_email,
        )
        return _LadderRepositoryContext(
            repository_id=repository_id,
            run_dir=run_dir,
            repo_dir=repo_dir,
        )

    def _run_node_lifecycle(
        self,
        *,
        node_index: int,
        spec: RepositoryImportBenchmarkDatasetSpec,
        resolution: RepositoryImportBenchmarkDatasetResolution,
        validation_policy: RepositoryImportValidationPolicy | str,
        ladder_repository_context: _LadderRepositoryContext,
    ) -> WorkflowLadderBenchmarkNodeResult:
        repository_id = ladder_repository_context.repository_id
        flow_spec = _LadderFlowDatasetSpec(
            dataset_id=repository_id,
            dataset_kind=spec.dataset_kind,
        )
        run_dir = self.run_root / "nodes" / _path_fragment(spec.dataset_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        requested_tables = _requested_tables_for_resolution(resolution)
        diagnostics: list[DiagnosticRecord] = list(resolution.diagnostics)
        stages: list[WorkflowLadderBenchmarkStageResult] = []
        submission_kind = (
            "BASELINE_INIT_SUBMISSION" if node_index == 0 else "INITIAL_MODIFIED_SUBMISSION"
        )
        profile = DEFAULT_FLOW_PROFILE

        open_stage_start = perf_counter()
        try:
            open_stage_details, prepared = self.flow_journey_bridge._prepare_baseline_submission_inputs(
                dataset_spec=flow_spec,
                resolution=resolution,
                profile=profile,
                requested_tables=requested_tables,
            )
        except Exception as exc:
            failure_stage = "OPEN_NEW_BASELINE"
            diagnostics.append(_journey_failure_diagnostic("workflow-ladder-open", exc, failure_stage))
            stages.append(
                WorkflowLadderBenchmarkStageResult(
                    stage_name=failure_stage,
                    status="FAILED",
                    duration_ms=_journey_elapsed_ms(open_stage_start),
                    details={"error": str(exc)},
                )
            )
            return self._build_failed_node_result(
                spec=spec,
                resolution=resolution,
                repository_id=repository_id,
                stage_results=tuple(stages),
                failure_stage=failure_stage,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
                submission_kind=submission_kind,
            )
        stages.append(
            WorkflowLadderBenchmarkStageResult(
                stage_name="OPEN_NEW_BASELINE",
                status="SUCCEEDED",
                duration_ms=_journey_elapsed_ms(open_stage_start),
                details=dict(open_stage_details),
            )
        )

        upload_stage_start = perf_counter()
        try:
            upload_stage_details, preview_result = self.flow_journey_bridge._run_preview_stage(
                dataset_spec=flow_spec,
                resolution=resolution,
                prepared=prepared,
                run_dir=run_dir,
                cache=self.projection_table_cache,
                comparison_core_cache=self.comparison_core_cache,
            )
        except Exception as exc:
            failure_stage = "UPLOAD"
            diagnostics.append(_journey_failure_diagnostic("workflow-ladder-upload", exc, failure_stage))
            stages.append(
                WorkflowLadderBenchmarkStageResult(
                    stage_name=failure_stage,
                    status="FAILED",
                    duration_ms=_journey_elapsed_ms(upload_stage_start),
                    details={"error": str(exc)},
                )
            )
            return self._build_failed_node_result(
                spec=spec,
                resolution=resolution,
                repository_id=repository_id,
                stage_results=tuple(stages),
                failure_stage=failure_stage,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
                submission_kind=submission_kind,
            )
        stages.append(
            WorkflowLadderBenchmarkStageResult(
                stage_name="UPLOAD",
                status="SUCCEEDED",
                duration_ms=_journey_elapsed_ms(upload_stage_start),
                details=dict(upload_stage_details),
            )
        )

        preview_binding = self.flow_journey_bridge._build_preview_binding(
            dataset_spec=flow_spec,
            resolution=resolution,
            prepared=prepared,
            preview_result=preview_result,
            workspace_id=f"workspace-{repository_id}-{_path_fragment(spec.dataset_id)}",
        )
        submit_source_package = self.flow_journey_bridge._build_submit_source_package(
            dataset_spec=flow_spec,
            resolution=resolution,
            preview_binding=preview_binding,
            current_snapshot=prepared.current_snapshot,
        )
        workspace_store = InMemoryWorkspaceStore()
        submission_store = InMemorySubmissionStore()
        submission_identity_store = InMemorySubmissionIdentityStore()
        operation_runtime = OperationRuntime()
        archive_batch_id = f"archive-{repository_id}-{_path_fragment(spec.dataset_id)}"

        submit_stage_start = perf_counter()
        try:
            acceptance_start = perf_counter()
            acceptance_details, acceptance_result = self.flow_journey_bridge._run_submit_acceptance_stage(
                dataset_spec=flow_spec,
                profile=profile,
                binding=preview_binding,
                submit_source_package=submit_source_package,
                workspace_store=workspace_store,
                submission_identity_store=submission_identity_store,
                operation_runtime=operation_runtime,
                workspace_batch_id=archive_batch_id,
            )
            acceptance_ms = _journey_elapsed_ms(acceptance_start)

            finalize_start = perf_counter()
            base_ref_or_commit = _current_main_or_symbolic(
                dolt=self.flow_journey_bridge.provider_runner.dolt,
                repo_dir=ladder_repository_context.repo_dir,
            )
            target_branch_ref = (
                f"refs/heads/workflow-ladder/{_path_fragment(spec.dataset_id)}"
            )
            finalize_details, finalize_result = self.flow_journey_bridge._run_submit_finalize_stage(
                dataset_spec=flow_spec,
                profile=profile,
                resolution=resolution,
                prepared=prepared,
                submit_source_package=submit_source_package,
                acceptance_result=acceptance_result,
                provider=RepositoryImportProvider.SQL_DUMP_REPLAY,
                validation_policy=validation_policy,
                workspace_store=workspace_store,
                submission_store=submission_store,
                operation_runtime=operation_runtime,
                run_dir=run_dir,
                comparison_core_cache=self.comparison_core_cache,
                promotion_before_commit_hash=base_ref_or_commit,
                base_ref_or_commit=base_ref_or_commit,
                target_branch_ref=target_branch_ref,
                worktree_context=RepositoryImportWorktreeContext(
                    run_dir=ladder_repository_context.run_dir,
                    repo_dir=ladder_repository_context.repo_dir,
                ),
            )
            finalize_ms = _journey_elapsed_ms(finalize_start)
        except Exception as exc:
            failure_stage = "SUBMIT"
            diagnostics.append(_journey_failure_diagnostic("workflow-ladder-submit", exc, failure_stage))
            stages.append(
                WorkflowLadderBenchmarkStageResult(
                    stage_name=failure_stage,
                    status="FAILED",
                    duration_ms=_journey_elapsed_ms(submit_stage_start),
                    details={"error": str(exc)},
                )
            )
            return self._build_failed_node_result(
                spec=spec,
                resolution=resolution,
                repository_id=repository_id,
                stage_results=tuple(stages),
                failure_stage=failure_stage,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
                submission_kind=submission_kind,
            )

        submit_details = dict(finalize_details)
        submit_details.update(
            {
                "acceptance_duration_ms": acceptance_ms,
                "finalize_duration_ms": finalize_ms,
                "submission_id": acceptance_result.submission_id,
                "workspace_id": preview_binding.workspace_id,
                "repository_id": finalize_result.flow_result.repository_import_result.repository_id,
                "base_ref_or_commit": base_ref_or_commit,
                "target_branch_ref": target_branch_ref,
                "repository_path": (
                    None
                    if finalize_result.flow_result.repository_import_result.repository_path is None
                    else str(finalize_result.flow_result.repository_import_result.repository_path)
                ),
                "repository_commit_hash": finalize_result.flow_result.repository_import_result.commit_hash,
            }
        )
        stages.append(
            WorkflowLadderBenchmarkStageResult(
                stage_name="SUBMIT",
                status="SUCCEEDED",
                duration_ms=_journey_elapsed_ms(submit_stage_start),
                details=submit_details,
            )
        )

        review_service = SubmissionReviewService(
            submission_store=submission_store,
            workspace_store=workspace_store,
        )
        review_actor_id = f"workflow-ladder-reviewer-{repository_id}"
        review_operation_runtime = OperationRuntime()
        start_review_start = perf_counter()
        try:
            start_review_result = run_submission_review(
                SubmissionReviewFlowInput(
                    submission_review_service=review_service,
                    review_command=SubmissionReviewCommand(
                        submission_id=acceptance_result.submission_id,
                        actor_id=review_actor_id,
                    ),
                    review_action=SubmissionReviewAction.START_REVIEW,
                    operation_runtime=review_operation_runtime,
                    worker_id=f"workflow-ladder-review-start-{repository_id}",
                )
            )
            start_review_ms = _journey_elapsed_ms(start_review_start)

            approve_start = perf_counter()
            approve_result = run_submission_review(
                SubmissionReviewFlowInput(
                    submission_review_service=review_service,
                    review_command=SubmissionReviewCommand(
                        submission_id=acceptance_result.submission_id,
                        actor_id=review_actor_id,
                    ),
                    review_action=SubmissionReviewAction.APPROVE,
                    operation_runtime=review_operation_runtime,
                    worker_id=f"workflow-ladder-review-approve-{repository_id}",
                )
            )
            approve_ms = _journey_elapsed_ms(approve_start)
        except Exception as exc:
            failure_stage = "APPROVE"
            diagnostics.append(_journey_failure_diagnostic("workflow-ladder-approve", exc, failure_stage))
            stages.append(
                WorkflowLadderBenchmarkStageResult(
                    stage_name=failure_stage,
                    status="FAILED",
                    duration_ms=_journey_elapsed_ms(start_review_start),
                    details={"error": str(exc)},
                )
            )
            return self._build_failed_node_result(
                spec=spec,
                resolution=resolution,
                repository_id=repository_id,
                stage_results=tuple(stages),
                failure_stage=failure_stage,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
                submission_kind=submission_kind,
            )

        approve_details = {
            "start_review_duration_ms": start_review_ms,
            "approve_duration_ms": approve_ms,
            "submission_status": approve_result.review_result.submission.status.value,
            "workspace_status": approve_result.review_result.workspace.status.value,
            "submission_id": approve_result.review_result.submission.submission_id,
            "workspace_id": approve_result.review_result.workspace.workspace_id,
        }
        stages.append(
            WorkflowLadderBenchmarkStageResult(
                stage_name="APPROVE",
                status="SUCCEEDED",
                duration_ms=_journey_elapsed_ms(start_review_start),
                details=approve_details,
            )
        )

        repository_import_result = finalize_result.flow_result.repository_import_result
        if repository_import_result.repository_path is None:
            raise RuntimeError("finalize did not return a repository path")
        archive_repository_id = repository_import_result.repository_id
        archive_repo_dir = repository_import_result.repository_path
        if archive_repository_id != ladder_repository_context.repository_id:
            raise RuntimeError("finalize returned an unexpected repository_id")
        if archive_repo_dir != ladder_repository_context.repo_dir:
            raise RuntimeError("finalize returned an unexpected repository_path")
        dolt = self.flow_journey_bridge.provider_runner.dolt
        archive_repo_service = _BenchmarkRepositoryServicePort(
            repository_id=archive_repository_id,
            repo_dir=archive_repo_dir,
            dolt=dolt,
        )
        archive_backend = _RepositoryImportRepositoryBackend(repo_dir=archive_repo_dir, dolt=dolt)
        archive_table_provider = _RecordingRepositoryTableAccessProvider(
            LocalRepositoryTableAccessProvider(
                backend=archive_backend,
                cache=self.repository_ref_cache,
            )
        )
        archive_service = ArchiveService(
            archive_store=_make_archive_store(),
            submission_store=submission_store,
            workspace_store=workspace_store,
            repository_service=archive_repo_service,
            repository_table_access_provider=archive_table_provider,
        )
        current_main_hash = dolt.resolve_ref_commit(
            repository_id=archive_repository_id,
            ref="refs/heads/main",
            repo_dir=archive_repo_dir,
        )
        if current_main_hash is None:
            raise RuntimeError("archive repository did not expose a main ref")

        archive_open_batch = ArchiveOpenBatchCommand(
            batch_id=archive_batch_id,
            repository_id=archive_repository_id,
            base_main_hash=current_main_hash,
            opened_by_actor_id=f"workflow-ladder-archive-{repository_id}",
            open_reason="workflow ladder archive",
            workspace_ids=(preview_binding.workspace_id,),
        )
        candidate_id = f"candidate-{repository_id}-{_path_fragment(spec.dataset_id)}"
        archive_candidate_command = ArchiveCandidateUpsertCommand(
            batch_id=archive_open_batch.batch_id,
            workspace_id=preview_binding.workspace_id,
            candidate_id=candidate_id,
            source_kind=ArchiveCandidateSourceKind.APPROVED_SUBMISSION,
            role=ArchiveCandidateRole.MAINLINE_MODIFIED,
            source_submission_id=acceptance_result.submission_id,
            selected_for_archive=False,
            created_by_actor_id=f"workflow-ladder-archive-{repository_id}",
        )
        archive_confirm_command = ArchiveConfirmWorkspaceCommand(
            batch_id=archive_open_batch.batch_id,
            workspace_id=preview_binding.workspace_id,
            actor_id=f"workflow-ladder-archive-{repository_id}",
            archive_candidate_id=candidate_id,
        )
        archive_select_command = ArchiveSelectCandidatesCommand(
            batch_id=archive_open_batch.batch_id,
            selected_modified_candidate_id=candidate_id,
            selected_initial_candidate_ids=(),
            actor_id=f"workflow-ladder-archive-{repository_id}",
        )

        archive_stage_start = perf_counter()
        try:
            open_batch_start = perf_counter()
            open_batch_result = archive_service.open_batch(archive_open_batch)
            open_batch_ms = _journey_elapsed_ms(open_batch_start)

            upsert_start = perf_counter()
            candidate_upsert_result = archive_service.upsert_archive_candidate(archive_candidate_command)
            candidate_upsert_ms = _journey_elapsed_ms(upsert_start)

            confirm_start = perf_counter()
            confirm_result = archive_service.confirm_workspace_archive(archive_confirm_command)
            confirm_ms = _journey_elapsed_ms(confirm_start)

            select_start = perf_counter()
            select_result = archive_service.select_archive_candidates(archive_select_command)
            select_ms = _journey_elapsed_ms(select_start)

            dry_run_start = perf_counter()
            dry_run_result = archive_service.dry_run_archive_mainline(
                ArchiveDryRunCommand(batch_id=archive_open_batch.batch_id)
            )
            dry_run_ms = _journey_elapsed_ms(dry_run_start)

            execute_start = perf_counter()
            execute_result = archive_service.execute_archive_mainline(
                ArchiveExecuteCommand(
                    batch_id=archive_open_batch.batch_id,
                    expected_base_main_hash=archive_open_batch.base_main_hash,
                    selected_modified_candidate_id=select_result.selected_modified_candidate_id,
                    selected_initial_candidate_ids=select_result.selected_initial_candidate_ids,
                    requested_by_actor_id=f"workflow-ladder-archive-{repository_id}",
                    idempotency_key=f"workflow-ladder-archive-{repository_id}",
                    workspace_confirmation_set_hash=dry_run_result.snapshot.workspace_confirmation_set_hash,
                    candidate_set_hash=dry_run_result.snapshot.candidate_set_hash,
                    override_reason=archive_select_command.override_reason,
                    open_ref_requested_tables=requested_tables,
                    open_ref_timeout_policy=None,
                )
            )
            execute_ms = _journey_elapsed_ms(execute_start)
            if execute_result.open_ref_result is None:
                raise RuntimeError(
                    execute_result.execution_record.failure_reason
                    or "archive open ref closeout failed"
                )
            promoted_main_hash = dolt.resolve_ref_commit(
                repository_id=archive_repository_id,
                ref="refs/heads/main",
                repo_dir=archive_repo_dir,
            )
            if promoted_main_hash != execute_result.execution_record.new_main_hash:
                raise RuntimeError("archive did not promote main to the selected commit")
        except Exception as exc:
            failure_stage = "ARCHIVE"
            diagnostics.append(_journey_failure_diagnostic("workflow-ladder-archive", exc, failure_stage))
            stages.append(
                WorkflowLadderBenchmarkStageResult(
                    stage_name=failure_stage,
                    status="FAILED",
                    duration_ms=_journey_elapsed_ms(archive_stage_start),
                    details={"error": str(exc)},
                )
            )
            return self._build_failed_node_result(
                spec=spec,
                resolution=resolution,
                repository_id=repository_id,
                stage_results=tuple(stages),
                failure_stage=failure_stage,
                failure_reason=str(exc),
                diagnostics=tuple(diagnostics),
                submission_kind=submission_kind,
            )

        archive_details = {
            "batch_id": open_batch_result.batch.batch_id,
            "archive_gate_status": open_batch_result.batch.archive_gate_status.value,
            "open_batch_duration_ms": open_batch_ms,
            "confirm_duration_ms": confirm_ms,
            "candidate_upsert_duration_ms": candidate_upsert_ms,
            "select_duration_ms": select_ms,
            "dry_run_duration_ms": dry_run_ms,
            "execute_duration_ms": execute_ms,
            "open_ref_duration_ms": archive_table_provider.recorder.open_ref_duration_ms,
            "open_ref_catalog_duration_ms": archive_table_provider.recorder.catalog_duration_ms,
            "open_ref_table_reader_duration_ms": archive_table_provider.recorder.table_reader_duration_ms,
            "open_ref_table_export_duration_ms": archive_table_provider.recorder.table_export_duration_ms,
            "selected_modified_candidate_id": select_result.selected_modified_candidate_id,
            "selected_initial_candidate_ids": list(select_result.selected_initial_candidate_ids),
            "candidate_set_hash": select_result.candidate_set_hash,
            "workspace_confirmation_set_hash": dry_run_result.snapshot.workspace_confirmation_set_hash,
            "execute_status": execute_result.execution_record.status.value,
            "transfer_status": execute_result.execution_record.transfer_status.value,
            "base_main_hash": archive_open_batch.base_main_hash,
            "repository_id": archive_repository_id,
            "repository_path": str(archive_repo_dir),
            "repository_commit_hash": execute_result.execution_record.new_main_hash,
            "promoted_main_hash": promoted_main_hash,
            "open_ref_repository_ref": execute_result.execution_record.open_ref_repository_ref,
            "open_ref_snapshot_id": execute_result.execution_record.open_ref_snapshot_id,
            "open_ref_snapshot_digest": execute_result.execution_record.open_ref_snapshot_digest,
            "open_ref_table_count": (
                None
                if execute_result.open_ref_result is None
                else execute_result.open_ref_result.summary.table_count
            ),
            "open_ref_row_count_total": (
                None
                if execute_result.open_ref_result is None
                else execute_result.open_ref_result.summary.row_count_total
            ),
        }
        stages.append(
            WorkflowLadderBenchmarkStageResult(
                stage_name="ARCHIVE",
                status="SUCCEEDED",
                duration_ms=_journey_elapsed_ms(archive_stage_start),
                details=archive_details,
            )
        )

        repository_commit_hash = execute_result.execution_record.new_main_hash
        if repository_commit_hash is None:
            raise RuntimeError("archive execution did not produce a new main hash")
        return WorkflowLadderBenchmarkNodeResult(
            node_id=spec.dataset_id,
            dataset_id=spec.dataset_id,
            dataset_kind=spec.dataset_kind,
            status=WorkflowLadderBenchmarkStatus.PASSED,
            source_sql_digest=resolution.manifest.source_sql_digest,
            source_sql_bytes=resolution.manifest.source_sql_bytes,
            table_count=resolution.manifest.table_count,
            row_count_total=resolution.manifest.row_count_total,
            stages=tuple(stages),
            submission_kind=submission_kind,
            workspace_id=preview_binding.workspace_id,
            submission_id=acceptance_result.submission_id,
            repository_id=archive_repository_id,
            repository_path=archive_repo_dir,
            repository_commit_hash=repository_commit_hash,
            baseline_repository_ref=archive_open_batch.base_main_hash,
            current_repository_ref=repository_commit_hash,
            diagnostics=tuple(diagnostics),
        )

    def _build_failed_node_result(
        self,
        *,
        spec: RepositoryImportBenchmarkDatasetSpec,
        resolution: RepositoryImportBenchmarkDatasetResolution,
        repository_id: str,
        stage_results: tuple[WorkflowLadderBenchmarkStageResult, ...],
        failure_stage: str,
        failure_reason: str,
        diagnostics: tuple[DiagnosticRecord, ...],
        submission_kind: str,
    ) -> WorkflowLadderBenchmarkNodeResult:
        return WorkflowLadderBenchmarkNodeResult(
            node_id=spec.dataset_id,
            dataset_id=spec.dataset_id,
            dataset_kind=spec.dataset_kind,
            status=WorkflowLadderBenchmarkStatus.FAILED,
            source_sql_digest=resolution.manifest.source_sql_digest,
            source_sql_bytes=resolution.manifest.source_sql_bytes,
            table_count=resolution.manifest.table_count,
            row_count_total=resolution.manifest.row_count_total,
            stages=tuple(stage_results),
            submission_kind=submission_kind,
            repository_id=repository_id,
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            diagnostics=diagnostics,
        )

    def _run_compare_scenario(
        self,
        *,
        scenario_name: str,
        pair_indexes: tuple[tuple[int, int], ...],
        node_results: tuple[WorkflowLadderBenchmarkNodeResult, ...],
    ) -> WorkflowLadderBenchmarkCompareResult:
        if not pair_indexes:
            raise ValueError("pair_indexes must not be empty")
        run_dir = self.run_root / "compare" / _path_fragment(scenario_name)
        run_dir.mkdir(parents=True, exist_ok=True)

        opened_nodes: dict[int, _OpenedNodeSnapshot] = {}
        for pair_index in pair_indexes:
            before_index, current_index = pair_index
            for node_index in (before_index, current_index):
                if node_index in opened_nodes:
                    continue
                node = node_results[node_index]
                if node.repository_path is None or node.repository_commit_hash is None or node.repository_id is None:
                    raise ValueError("node result is missing repository-backed compare inputs")
                semantic_snapshot = self.history_compare_bridge._read_repository_ref_summary_snapshot(
                    repository_path=node.repository_path,
                    repository_id=node.repository_id,
                    repository_ref=node.repository_commit_hash,
                )
                _, opened = self.history_compare_bridge._open_repository_snapshot(
                    repository_path=node.repository_path,
                    repository_id=node.repository_id,
                    repository_ref=node.repository_commit_hash,
                    semantic_snapshot=semantic_snapshot,
                    materialized_tables=(),
                    cache=self.repository_ref_cache,
                    requested_tables=(),
                )
                opened_nodes[node_index] = _OpenedNodeSnapshot(
                    node_result=node,
                    snapshot=opened.snapshot,
                    context=opened.context,
                    details=opened.details,
                )

        compare_pair_inputs: list[HistoryComparePairInput] = []
        bundle_inputs = tuple(
            BundleInput(
                input_index=index,
                role=ComparisonRole.BEFORE if index == 0 else ComparisonRole.CURRENT,
                display_name=node.node_id,
                display_metadata={
                    "dataset_id": node.dataset_id,
                    "repository_id": node.repository_id,
                },
                snapshot_digest=DigestRef.from_payload(
                    {
                        "dataset_id": node.dataset_id,
                        "repository_id": node.repository_id,
                        "repository_commit_hash": node.repository_commit_hash,
                    }
                ),
            )
            for index, node in enumerate(node_results)
        )

        for pair_number, (before_index, current_index) in enumerate(pair_indexes):
            before_opened = opened_nodes[before_index]
            current_opened = opened_nodes[current_index]
            comparison_flow_input = ComparisonRiskFlowInput(
                comparison_input=DirectedComparisonInput(
                    before=ComparisonInput(
                        role=ComparisonRole.BEFORE,
                        snapshot=before_opened.snapshot.snapshot,
                        summary=before_opened.snapshot.summary,
                        table_set_ref=before_opened.snapshot.table_set,
                        repository_backed_context=before_opened.context,
                    ),
                    current=ComparisonInput(
                        role=ComparisonRole.CURRENT,
                        snapshot=current_opened.snapshot.snapshot,
                        summary=current_opened.snapshot.summary,
                        table_set_ref=current_opened.snapshot.table_set,
                        repository_backed_context=current_opened.context,
                    ),
                    table_ruleset_version=current_opened.snapshot.summary.table_ruleset_version,
                    requested_tables=(),
                ),
                records_store=LocalArtifactStore(run_dir / f"pair-{pair_number}" / "comparison-records"),
                comparison_engine=ComparisonEngine(),
                comparison_core_cache=self.comparison_core_cache,
                projection_table_cache=self.projection_table_cache,
                risk_engine=RiskEngine(),
            )
            compare_pair_inputs.append(
                build_history_compare_pair_input(
                    pair_id=f"pair-{pair_number}",
                    before_input_index=before_index,
                    current_input_index=current_index,
                    comparison_flow_input=comparison_flow_input,
                    before_repository_backed_context=before_opened.context,
                    current_repository_backed_context=current_opened.context,
                )
            )

        history_compare_input = HistoryCompareFlowInput(
            bundle_root=run_dir / "bundle",
            bundle_inputs=bundle_inputs,
            pair_inputs=tuple(compare_pair_inputs),
            projection_table_cache=self.projection_table_cache,
            operation_id=_journey_operation_id(
                "workflow-ladder-compare",
                scenario_name,
                uuid4().hex[:8],
            ),
        )
        compare_stage_start = perf_counter()
        try:
            compare_result = run_history_compare(history_compare_input)
        except Exception as exc:
            return WorkflowLadderBenchmarkCompareResult(
                scenario_name=scenario_name,
                pair_ids=tuple(f"pair-{index}" for index in range(len(pair_indexes))),
                pair_refs=tuple(
                    (
                        node_results[before_index].repository_commit_hash or "UNAVAILABLE",
                        node_results[current_index].repository_commit_hash or "UNAVAILABLE",
                    )
                    for before_index, current_index in pair_indexes
                ),
                status=WorkflowLadderBenchmarkStatus.FAILED,
                source_sql_digest=DigestRef.from_payload(
                    {"scenario_name": scenario_name, "pair_indexes": pair_indexes}
                ),
                source_sql_bytes=sum(node.source_sql_bytes for node in node_results),
                table_count=max(node.table_count for node in node_results),
                row_count_total=sum(node.row_count_total for node in node_results),
                comparison_mode="DOLT_TO_DOLT",
                stages=(
                    WorkflowLadderBenchmarkStageResult(
                        stage_name="HISTORY_COMPARE",
                        status="FAILED",
                        duration_ms=_journey_elapsed_ms(compare_stage_start),
                        details={"error": str(exc)},
                    ),
                ),
                failure_stage="HISTORY_COMPARE",
                failure_reason=str(exc),
                diagnostics=(),
            )

        pair_results = compare_result.pair_results
        pair_ids = tuple(pair_result.pair_id for pair_result in pair_results)
        pair_refs = tuple(
            (
                node_results[pair_result.before_input_index].repository_commit_hash or "UNAVAILABLE",
                node_results[pair_result.current_input_index].repository_commit_hash or "UNAVAILABLE",
            )
            for pair_result in pair_results
        )
        comparison_statuses = tuple(
            pair_result.comparison_result.summary.status.value for pair_result in pair_results
        )
        compare_output = compare_result.run_result.outputs.get("ASYNC_COMPARISON_CORE_CACHE_COMPLETION", {})
        if not isinstance(compare_output, Mapping):
            compare_output = {}
        diagnostics: list[DiagnosticRecord] = []
        diagnostics.extend(compare_result.operation.diagnostics)
        diagnostics.extend(compare_result.bundle_result.diagnostics)
        for pair_result in pair_results:
            diagnostics.extend(pair_result.comparison_result.diagnostics)
            diagnostics.extend(pair_result.risk_result.diagnostics)
            diagnostics.extend(pair_result.surface_result.diagnostics)

        return WorkflowLadderBenchmarkCompareResult(
            scenario_name=scenario_name,
            pair_ids=pair_ids,
            pair_refs=pair_refs,
            status=WorkflowLadderBenchmarkStatus.PASSED,
            source_sql_digest=DigestRef.from_payload(
                {"scenario_name": scenario_name, "pair_ids": pair_ids, "pair_refs": pair_refs}
            ),
            source_sql_bytes=sum(node.source_sql_bytes for node in node_results),
            table_count=max(node.table_count for node in node_results),
            row_count_total=sum(node.row_count_total for node in node_results),
            comparison_mode="DOLT_TO_DOLT",
            stages=(
                WorkflowLadderBenchmarkStageResult(
                    stage_name="HISTORY_COMPARE",
                    status="SUCCEEDED",
                    duration_ms=_journey_elapsed_ms(compare_stage_start),
                    details={
                        "pair_count": len(pair_results),
                        "comparison_status": _summarize_statuses(comparison_statuses),
                        "comparison_duration_ms": sum(
                            _compare_duration(pair_result) for pair_result in pair_results
                        ),
                        "risk_duration_ms": sum(
                            None if pair_result.comparison_risk_result is None else pair_result.comparison_risk_result.risk_duration_ms or 0
                            for pair_result in pair_results
                        ),
                        "surface_duration_ms": sum(
                            pair_result.surface_duration_ms or 0 for pair_result in pair_results
                        ),
                        "bundle_duration_ms": compare_result.bundle_duration_ms,
                        "native_route_count": sum(
                            _journey_count_diagnostics(
                                pair_result.comparison_result.cache_diagnostics,
                                "comparison.native-route.hit",
                            )
                            for pair_result in pair_results
                        ),
                        "comparison_core_cache_hit_count": sum(
                            _journey_count_diagnostics(
                                pair_result.comparison_result.cache_diagnostics,
                                "comparison.core-cache.hit",
                            )
                            for pair_result in pair_results
                        ),
                        "comparison_core_cache_miss_count": sum(
                            _journey_count_diagnostics(
                                pair_result.comparison_result.cache_diagnostics,
                                "comparison.core-cache.miss",
                            )
                            for pair_result in pair_results
                        ),
                        "comparison_core_cache_completion_ms": compare_output.get(
                            "comparison_core_cache_completion_ms"
                        ),
                        "comparison_core_cache_completion_pair_count": compare_output.get(
                            "comparison_core_cache_completion_pair_count"
                        ),
                        "comparison_core_cache_completion_write_count": compare_output.get(
                            "comparison_core_cache_completion_write_count"
                        ),
                        "comparison_core_cache_completion_hit_count": compare_output.get(
                            "comparison_core_cache_completion_hit_count"
                        ),
                        "comparison_core_cache_completion_skip_count": compare_output.get(
                            "comparison_core_cache_completion_skip_count"
                        ),
                        "comparison_core_cache_completion_statuses": compare_output.get(
                            "comparison_core_cache_completion_statuses"
                        ),
                    },
                ),
            ),
            comparison_status=_summarize_statuses(comparison_statuses),
            comparison_duration_ms=sum(
                _compare_duration(pair_result) for pair_result in pair_results
            ),
            risk_duration_ms=sum(
                0 if pair_result.comparison_risk_result is None else pair_result.comparison_risk_result.risk_duration_ms or 0
                for pair_result in pair_results
            ),
            surface_duration_ms=sum(
                pair_result.surface_duration_ms or 0 for pair_result in pair_results
            ),
            bundle_duration_ms=compare_result.bundle_duration_ms,
            native_route_count=sum(
                _journey_count_diagnostics(
                    pair_result.comparison_result.cache_diagnostics,
                    "comparison.native-route.hit",
                )
                for pair_result in pair_results
            ),
            cache_hit_count=sum(
                _journey_count_diagnostics(
                    pair_result.comparison_result.cache_diagnostics,
                    "comparison.projection-cache.hit",
                )
                for pair_result in pair_results
            ),
            cache_miss_count=sum(
                _journey_count_diagnostics(
                    pair_result.comparison_result.cache_diagnostics,
                    "comparison.projection-cache.miss",
                )
                for pair_result in pair_results
            ),
            comparison_core_cache_hit_count=sum(
                _journey_count_diagnostics(
                    pair_result.comparison_result.cache_diagnostics,
                    "comparison.core-cache.hit",
                )
                for pair_result in pair_results
            ),
            comparison_core_cache_miss_count=sum(
                _journey_count_diagnostics(
                    pair_result.comparison_result.cache_diagnostics,
                    "comparison.core-cache.miss",
                )
                for pair_result in pair_results
            ),
            comparison_core_cache_completion_ms=compare_output.get(
                "comparison_core_cache_completion_ms"
            ),
            comparison_core_cache_completion_pair_count=compare_output.get(
                "comparison_core_cache_completion_pair_count"
            ),
            comparison_core_cache_completion_write_count=compare_output.get(
                "comparison_core_cache_completion_write_count"
            ),
            comparison_core_cache_completion_hit_count=compare_output.get(
                "comparison_core_cache_completion_hit_count"
            ),
            comparison_core_cache_completion_skip_count=compare_output.get(
                "comparison_core_cache_completion_skip_count"
            ),
            comparison_core_cache_completion_statuses=tuple(
                str(item)
                for item in (compare_output.get("comparison_core_cache_completion_statuses") or [])
            ),
            diagnostics=tuple(diagnostics),
        )

    def _build_summary(
        self,
        *,
        status: WorkflowLadderBenchmarkStatus,
        dataset_ids: Sequence[str],
        node_results: tuple[WorkflowLadderBenchmarkNodeResult, ...],
        compare_results: tuple[WorkflowLadderBenchmarkCompareResult, ...],
        execution_order: tuple[str, ...],
        failure_stage: str | None,
        failure_reason: str | None,
        diagnostics: tuple[DiagnosticRecord, ...],
    ) -> WorkflowLadderBenchmarkSummary:
        return WorkflowLadderBenchmarkSummary(
            run_id=_build_run_id(),
            created_at=datetime.now(timezone.utc),
            machine_profile=self.machine_profile,
            dataset_ids=tuple(dataset_ids),
            execution_order=execution_order,
            status=status,
            node_results=node_results,
            compare_results=compare_results,
            failure_stage=failure_stage,
            failure_reason=failure_reason,
            diagnostics=diagnostics,
        )

    def _write_outputs(self, summary: WorkflowLadderBenchmarkSummary) -> None:
        SummaryJsonWriter().write(self.summary_path, summary)
        MarkdownReportWriter().write(summary, self.result_out)


def _repository_id_from_dataset_id(dataset_id: str) -> str:
    text = dataset_id.strip().replace("/", "-").replace("\\", "-")
    text = text.replace(" ", "-")
    text = text.lower()
    if not text:
        raise ValueError("dataset_id must be non-empty")
    return text


def _ladder_repository_id_from_dataset_ids(dataset_ids: Sequence[str]) -> str:
    first_parts = []
    for dataset_id in dataset_ids:
        normalized = str(dataset_id).strip().replace("\\", "/")
        if not normalized:
            continue
        first_parts.append(normalized.split("/", 1)[0])
    if not first_parts:
        raise ValueError("dataset_ids must contain at least one non-empty id")
    first = first_parts[0]
    if all(part == first for part in first_parts):
        return _repository_id_from_dataset_id(first)
    return _repository_id_from_dataset_id(str(dataset_ids[0]))


def _path_fragment(value: str) -> str:
    return _repository_id_from_dataset_id(value)


def _current_main_or_symbolic(*, dolt: DoltCli, repo_dir: Path) -> str:
    if not (repo_dir / ".dolt").exists():
        return "main"
    current_main = dolt.resolve_ref_commit(
        repository_id=repo_dir.name,
        ref="refs/heads/main",
        repo_dir=repo_dir,
    )
    return current_main or "main"


def _requested_tables_for_resolution(resolution: RepositoryImportBenchmarkDatasetResolution) -> tuple[str, ...]:
    if resolution.source_snapshot.table_set is None:
        return tuple()
    return tuple(resolution.source_snapshot.table_set.tables.keys())


def _build_run_id() -> str:
    return f"workflow-ladder-benchmark-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:8]}"


def _summarize_statuses(statuses: Sequence[str]) -> str:
    normalized: list[str] = []
    seen: set[str] = set()
    for status in statuses:
        if status in seen:
            continue
        seen.add(status)
        normalized.append(status)
    if not normalized:
        return ""
    if len(normalized) == 1:
        return normalized[0]
    return " / ".join(normalized)


def _compare_duration(pair_result) -> int:
    comparison_risk_result = pair_result.comparison_risk_result
    if comparison_risk_result is None:
        return 0
    return comparison_risk_result.comparison_duration_ms or 0


@dataclass(frozen=True, slots=True)
class _OpenedNodeSnapshot:
    node_result: WorkflowLadderBenchmarkNodeResult
    snapshot: SnapshotMaterializationResult
    context: RepositoryBackedComparisonContext
    details: Mapping[str, object]


def _make_archive_store():
    from ...archive import InMemoryArchiveStore

    return InMemoryArchiveStore()
