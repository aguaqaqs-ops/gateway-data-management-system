from __future__ import annotations

from dataclasses import dataclass, field

from ..archive import (
    ArchiveAnomalyResolutionCommand,
    ArchiveAnomalyResolutionResult,
    ArchiveCandidateUpsertCommand,
    ArchiveCandidateUpsertResult,
    ArchiveConfirmWorkspaceCommand,
    ArchiveConfirmWorkspaceResult,
    ArchiveDryRunCommand,
    ArchiveDryRunResult,
    ArchiveExecuteCommand,
    ArchiveExecuteResult,
    ArchiveOpenBatchCommand,
    ArchiveOpenBatchResult,
    ArchiveSelectCandidatesCommand,
    ArchiveSelectCandidatesResult,
    ArchiveService,
)
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
from ..repository_server import RepositoryRefTimeoutPolicy


@dataclass(frozen=True, slots=True)
class ArchivePromoteFlowInput:
    archive_service: ArchiveService
    open_batch_command: ArchiveOpenBatchCommand
    select_archive_candidates_command: ArchiveSelectCandidatesCommand
    requested_by_actor_id: str
    idempotency_key: str
    confirm_workspace_commands: tuple[ArchiveConfirmWorkspaceCommand, ...] = field(default_factory=tuple)
    candidate_upsert_commands: tuple[ArchiveCandidateUpsertCommand, ...] = field(default_factory=tuple)
    anomaly_resolution_commands: tuple[ArchiveAnomalyResolutionCommand, ...] = field(default_factory=tuple)
    open_ref_requested_tables: tuple[str, ...] = field(default_factory=tuple)
    open_ref_timeout_policy: RepositoryRefTimeoutPolicy | None = None
    operation_runtime: OperationRuntime = field(default_factory=OperationRuntime)
    worker_id: str = "archive-promote-worker"
    operation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.archive_service, ArchiveService):
            raise TypeError("archive_service must be an ArchiveService")
        if not isinstance(self.open_batch_command, ArchiveOpenBatchCommand):
            raise TypeError("open_batch_command must be an ArchiveOpenBatchCommand")
        if not isinstance(self.select_archive_candidates_command, ArchiveSelectCandidatesCommand):
            raise TypeError("select_archive_candidates_command must be an ArchiveSelectCandidatesCommand")
        if self.select_archive_candidates_command.batch_id != self.open_batch_command.batch_id:
            raise ValueError("select_archive_candidates_command batch_id must match open_batch_command batch_id")
        for field_name in ("requested_by_actor_id", "idempotency_key"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.confirm_workspace_commands, tuple):
            object.__setattr__(self, "confirm_workspace_commands", tuple(self.confirm_workspace_commands))
        if not isinstance(self.candidate_upsert_commands, tuple):
            object.__setattr__(self, "candidate_upsert_commands", tuple(self.candidate_upsert_commands))
        if not isinstance(self.anomaly_resolution_commands, tuple):
            object.__setattr__(self, "anomaly_resolution_commands", tuple(self.anomaly_resolution_commands))
        if not isinstance(self.open_ref_requested_tables, tuple):
            object.__setattr__(self, "open_ref_requested_tables", tuple(self.open_ref_requested_tables))
        for command in self.confirm_workspace_commands:
            if not isinstance(command, ArchiveConfirmWorkspaceCommand):
                raise TypeError("confirm_workspace_commands must contain ArchiveConfirmWorkspaceCommand values")
            if command.batch_id != self.open_batch_command.batch_id:
                raise ValueError("confirm_workspace_commands batch_id must match open_batch_command batch_id")
        for command in self.candidate_upsert_commands:
            if not isinstance(command, ArchiveCandidateUpsertCommand):
                raise TypeError("candidate_upsert_commands must contain ArchiveCandidateUpsertCommand values")
            if command.batch_id != self.open_batch_command.batch_id:
                raise ValueError("candidate_upsert_commands batch_id must match open_batch_command batch_id")
        for command in self.anomaly_resolution_commands:
            if not isinstance(command, ArchiveAnomalyResolutionCommand):
                raise TypeError("anomaly_resolution_commands must contain ArchiveAnomalyResolutionCommand values")
            if command.batch_id != self.open_batch_command.batch_id:
                raise ValueError("anomaly_resolution_commands batch_id must match open_batch_command batch_id")
        for table_name in self.open_ref_requested_tables:
            if not isinstance(table_name, str) or not table_name:
                raise ValueError("open_ref_requested_tables must contain non-empty strings")
        if self.open_ref_timeout_policy is not None and not isinstance(
            self.open_ref_timeout_policy,
            RepositoryRefTimeoutPolicy,
        ):
            raise TypeError("open_ref_timeout_policy must be a RepositoryRefTimeoutPolicy or None")
        if not isinstance(self.operation_runtime, OperationRuntime):
            raise TypeError("operation_runtime must be an OperationRuntime")
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("worker_id must be a non-empty string")
        if self.operation_id is not None and not isinstance(self.operation_id, str):
            raise TypeError("operation_id must be a string or None")


@dataclass(frozen=True, slots=True)
class ArchivePromoteFlowResult:
    operation: OperationRecord
    run_result: OperationRunResult
    open_batch_result: ArchiveOpenBatchResult
    confirm_workspace_results: tuple[ArchiveConfirmWorkspaceResult, ...]
    candidate_upsert_results: tuple[ArchiveCandidateUpsertResult, ...]
    anomaly_resolution_results: tuple[ArchiveAnomalyResolutionResult, ...]
    select_result: ArchiveSelectCandidatesResult
    dry_run_result: ArchiveDryRunResult
    execute_result: ArchiveExecuteResult

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationRecord):
            raise TypeError("operation must be an OperationRecord")
        if not isinstance(self.run_result, OperationRunResult):
            raise TypeError("run_result must be an OperationRunResult")
        if not isinstance(self.open_batch_result, ArchiveOpenBatchResult):
            raise TypeError("open_batch_result must be an ArchiveOpenBatchResult")
        if not isinstance(self.confirm_workspace_results, tuple):
            object.__setattr__(self, "confirm_workspace_results", tuple(self.confirm_workspace_results))
        for result in self.confirm_workspace_results:
            if not isinstance(result, ArchiveConfirmWorkspaceResult):
                raise TypeError("confirm_workspace_results must contain ArchiveConfirmWorkspaceResult values")
        if not isinstance(self.candidate_upsert_results, tuple):
            object.__setattr__(self, "candidate_upsert_results", tuple(self.candidate_upsert_results))
        for result in self.candidate_upsert_results:
            if not isinstance(result, ArchiveCandidateUpsertResult):
                raise TypeError("candidate_upsert_results must contain ArchiveCandidateUpsertResult values")
        if not isinstance(self.anomaly_resolution_results, tuple):
            object.__setattr__(self, "anomaly_resolution_results", tuple(self.anomaly_resolution_results))
        for result in self.anomaly_resolution_results:
            if not isinstance(result, ArchiveAnomalyResolutionResult):
                raise TypeError("anomaly_resolution_results must contain ArchiveAnomalyResolutionResult values")
        if not isinstance(self.select_result, ArchiveSelectCandidatesResult):
            raise TypeError("select_result must be an ArchiveSelectCandidatesResult")
        if not isinstance(self.dry_run_result, ArchiveDryRunResult):
            raise TypeError("dry_run_result must be an ArchiveDryRunResult")
        if not isinstance(self.execute_result, ArchiveExecuteResult):
            raise TypeError("execute_result must be an ArchiveExecuteResult")


@dataclass(frozen=True, slots=True)
class ArchivePromoteWorker:
    def start_or_resume(self, flow_input: ArchivePromoteFlowInput) -> ArchivePromoteFlowResult:
        return run_archive_promote(flow_input)


def run_archive_promote(flow_input: ArchivePromoteFlowInput) -> ArchivePromoteFlowResult:
    if not isinstance(flow_input, ArchivePromoteFlowInput):
        raise TypeError("flow_input must be an ArchivePromoteFlowInput")

    open_batch_result: ArchiveOpenBatchResult | None = None
    confirm_workspace_results: list[ArchiveConfirmWorkspaceResult] = []
    candidate_upsert_results: list[ArchiveCandidateUpsertResult] = []
    anomaly_resolution_results: list[ArchiveAnomalyResolutionResult] = []
    select_result: ArchiveSelectCandidatesResult | None = None
    dry_run_result: ArchiveDryRunResult | None = None
    execute_result: ArchiveExecuteResult | None = None

    plan = OperationPlan(
        operation_kind=OperationKind.ARCHIVE_PROMOTE,
        caller_type=OperationCallerType.FINALIZE_WRITE_CALLER,
        parallel_policy=OperationParallelPolicy.SERIAL,
        request_payload=_archive_promote_request_payload(flow_input),
        steps=(
            OperationStepPlan(step_name="LOAD_INPUT"),
            OperationStepPlan(step_name="OPEN_BATCH", retryable=True),
            OperationStepPlan(step_name="UPSERT_CANDIDATES"),
            OperationStepPlan(step_name="RECORD_ANOMALY_RESOLUTIONS"),
            OperationStepPlan(step_name="CONFIRM_WORKSPACES", retryable=True),
            OperationStepPlan(step_name="SELECT_ARCHIVE_CANDIDATES"),
            OperationStepPlan(step_name="DRY_RUN_ARCHIVE_MAINLINE", retryable=True),
            OperationStepPlan(step_name="EXECUTE_ARCHIVE_MAINLINE", retryable=True),
            OperationStepPlan(step_name="PUBLISH_RESULT"),
            OperationStepPlan(step_name="CLEANUP"),
        ),
    )
    operation_record = flow_input.operation_runtime.create_operation(
        plan,
        operation_id=flow_input.operation_id,
    )

    def load_input(context: OperationStepContext) -> OperationStepOutcome:
        return OperationStepOutcome.success(
            value={
                "batch_id": flow_input.open_batch_command.batch_id,
                "repository_id": flow_input.open_batch_command.repository_id,
                "confirm_workspace_count": len(flow_input.confirm_workspace_commands),
                "candidate_upsert_count": len(flow_input.candidate_upsert_commands),
                "anomaly_resolution_count": len(flow_input.anomaly_resolution_commands),
                "selected_modified_candidate_id": flow_input.select_archive_candidates_command.selected_modified_candidate_id,
                "selected_initial_candidate_ids": list(
                    flow_input.select_archive_candidates_command.selected_initial_candidate_ids,
                ),
                "requested_by_actor_id": flow_input.requested_by_actor_id,
                "idempotency_key": flow_input.idempotency_key,
                "open_ref_requested_table_count": len(flow_input.open_ref_requested_tables),
            }
        )

    def open_batch(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal open_batch_result
        open_batch_result = flow_input.archive_service.open_batch(flow_input.open_batch_command)
        return OperationStepOutcome.success(
            value={
                "batch_id": open_batch_result.batch.batch_id,
                "workspace_count": len(open_batch_result.workspaces),
                "archive_gate_status": open_batch_result.batch.archive_gate_status.value,
            }
        )

    def confirm_workspaces(context: OperationStepContext) -> OperationStepOutcome:
        confirm_workspace_results.clear()
        for command in flow_input.confirm_workspace_commands:
            confirm_workspace_results.append(flow_input.archive_service.confirm_workspace_archive(command))
        return OperationStepOutcome.success(
            value={
                "confirmation_count": len(confirm_workspace_results),
                "workspace_ids": [
                    result.confirmation.workspace_id for result in confirm_workspace_results
                ],
            }
        )

    def upsert_candidates(context: OperationStepContext) -> OperationStepOutcome:
        candidate_upsert_results.clear()
        for command in flow_input.candidate_upsert_commands:
            candidate_upsert_results.append(flow_input.archive_service.upsert_archive_candidate(command))
        return OperationStepOutcome.success(
            value={
                "candidate_count": len(candidate_upsert_results),
                "candidate_ids": [result.candidate.candidate_id for result in candidate_upsert_results],
            }
        )

    def record_anomaly_resolutions(context: OperationStepContext) -> OperationStepOutcome:
        anomaly_resolution_results.clear()
        for command in flow_input.anomaly_resolution_commands:
            anomaly_resolution_results.append(flow_input.archive_service.record_anomaly_resolution(command))
        return OperationStepOutcome.success(
            value={
                "resolution_count": len(anomaly_resolution_results),
                "resolution_ids": [
                    result.resolution.resolution_id for result in anomaly_resolution_results
                ],
            }
        )

    def select_archive_candidates(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal select_result
        select_result = flow_input.archive_service.select_archive_candidates(
            flow_input.select_archive_candidates_command,
        )
        return OperationStepOutcome.success(
            value={
                "batch_id": select_result.batch.batch_id,
                "selected_modified_candidate_id": select_result.selected_modified_candidate_id,
                "selected_initial_candidate_ids": list(select_result.selected_initial_candidate_ids),
                "candidate_set_hash": select_result.candidate_set_hash,
            }
        )

    def dry_run_archive_mainline(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal dry_run_result
        if open_batch_result is None:
            raise RuntimeError("open batch result must be available before dry run")
        dry_run_result = flow_input.archive_service.dry_run_archive_mainline(
            ArchiveDryRunCommand(batch_id=open_batch_result.batch.batch_id)
        )
        return OperationStepOutcome.success(
            value={
                "eligible_for_execute": dry_run_result.snapshot.eligible_for_execute,
                "failure_reasons": list(dry_run_result.snapshot.failure_reasons),
                "workspace_confirmation_set_hash": dry_run_result.snapshot.workspace_confirmation_set_hash,
                "candidate_set_hash": dry_run_result.snapshot.candidate_set_hash,
            }
        )

    def execute_archive_mainline(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal execute_result
        if dry_run_result is None or select_result is None or open_batch_result is None:
            raise RuntimeError("dry run and selection results must be available before execute")
        execute_command = ArchiveExecuteCommand(
            batch_id=open_batch_result.batch.batch_id,
            expected_base_main_hash=open_batch_result.batch.base_main_hash,
            selected_modified_candidate_id=select_result.selected_modified_candidate_id,
            selected_initial_candidate_ids=select_result.selected_initial_candidate_ids,
            requested_by_actor_id=flow_input.requested_by_actor_id,
            idempotency_key=flow_input.idempotency_key,
            workspace_confirmation_set_hash=dry_run_result.snapshot.workspace_confirmation_set_hash,
            candidate_set_hash=dry_run_result.snapshot.candidate_set_hash,
            override_reason=flow_input.select_archive_candidates_command.override_reason,
            open_ref_requested_tables=flow_input.open_ref_requested_tables,
            open_ref_timeout_policy=flow_input.open_ref_timeout_policy,
        )
        execute_result = flow_input.archive_service.execute_archive_mainline(execute_command)
        execution_payload = execute_result.execution_record.to_payload()
        open_ref_payload = (
            None
            if execute_result.open_ref_result is None
            else {
                "snapshot_digest": execute_result.open_ref_result.snapshot.snapshot_digest.to_payload(),
                "snapshot_id": execute_result.open_ref_result.snapshot.snapshot_id,
                "table_count": execute_result.open_ref_result.summary.table_count,
            }
        )
        return OperationStepOutcome.success(
            value={
                "execution": execution_payload,
                "open_ref": open_ref_payload,
            }
        )

    def publish_result(context: OperationStepContext) -> OperationStepOutcome:
        if open_batch_result is None or select_result is None or dry_run_result is None or execute_result is None:
            raise RuntimeError("archive results must be available before publish")
        ready_payload = _archive_promote_ready_payload(
            open_batch_result=open_batch_result,
            select_result=select_result,
            dry_run_result=dry_run_result,
            execute_result=execute_result,
        )
        return OperationStepOutcome.success(
            value=ready_payload,
            ready_closure_digest=DigestRef.from_payload(ready_payload),
        )

    def cleanup(context: OperationStepContext) -> OperationStepOutcome:
        return OperationStepOutcome.success(value={"cleanup": "noop"})

    run_result = flow_input.operation_runtime.run_operation(
        operation_record.operation_id,
        handlers={
            "LOAD_INPUT": load_input,
            "OPEN_BATCH": open_batch,
            "UPSERT_CANDIDATES": upsert_candidates,
            "RECORD_ANOMALY_RESOLUTIONS": record_anomaly_resolutions,
            "CONFIRM_WORKSPACES": confirm_workspaces,
            "SELECT_ARCHIVE_CANDIDATES": select_archive_candidates,
            "DRY_RUN_ARCHIVE_MAINLINE": dry_run_archive_mainline,
            "EXECUTE_ARCHIVE_MAINLINE": execute_archive_mainline,
            "PUBLISH_RESULT": publish_result,
            "CLEANUP": cleanup,
        },
        worker_id=flow_input.worker_id,
    )

    if (
        open_batch_result is None
        or select_result is None
        or dry_run_result is None
        or execute_result is None
    ):
        raise RuntimeError("archive operation completed without required results")

    return ArchivePromoteFlowResult(
        operation=run_result.operation,
        run_result=run_result,
        open_batch_result=open_batch_result,
        confirm_workspace_results=tuple(confirm_workspace_results),
        candidate_upsert_results=tuple(candidate_upsert_results),
        anomaly_resolution_results=tuple(anomaly_resolution_results),
        select_result=select_result,
        dry_run_result=dry_run_result,
        execute_result=execute_result,
    )


def _archive_promote_request_payload(flow_input: ArchivePromoteFlowInput) -> dict[str, object]:
    payload: dict[str, object] = {
        "operation_kind": OperationKind.ARCHIVE_PROMOTE.value,
        "caller_type": OperationCallerType.FINALIZE_WRITE_CALLER.value,
        "batch_id": flow_input.open_batch_command.batch_id,
        "repository_id": flow_input.open_batch_command.repository_id,
        "base_main_hash": flow_input.open_batch_command.base_main_hash,
        "workspace_count": len(flow_input.open_batch_command.workspace_ids),
        "confirm_workspace_count": len(flow_input.confirm_workspace_commands),
        "candidate_upsert_count": len(flow_input.candidate_upsert_commands),
        "anomaly_resolution_count": len(flow_input.anomaly_resolution_commands),
        "selected_modified_candidate_id": flow_input.select_archive_candidates_command.selected_modified_candidate_id,
        "selected_initial_candidate_ids": list(
            flow_input.select_archive_candidates_command.selected_initial_candidate_ids,
        ),
        "requested_by_actor_id": flow_input.requested_by_actor_id,
        "idempotency_key": flow_input.idempotency_key,
    }
    if flow_input.select_archive_candidates_command.override_reason is not None:
        payload["override_reason"] = flow_input.select_archive_candidates_command.override_reason
    if flow_input.open_ref_requested_tables:
        payload["open_ref_requested_tables"] = list(flow_input.open_ref_requested_tables)
    return payload


def _archive_promote_ready_payload(
    *,
    open_batch_result: ArchiveOpenBatchResult,
    select_result: ArchiveSelectCandidatesResult,
    dry_run_result: ArchiveDryRunResult,
    execute_result: ArchiveExecuteResult,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "batch_id": open_batch_result.batch.batch_id,
        "repository_id": open_batch_result.batch.repository_id,
        "execution_id": execute_result.execution_record.execution_id,
        "execution_status": execute_result.execution_record.status.value,
        "transfer_status": execute_result.execution_record.transfer_status.value,
        "selected_modified_candidate_id": select_result.selected_modified_candidate_id,
        "selected_initial_candidate_ids": list(select_result.selected_initial_candidate_ids),
        "workspace_confirmation_set_hash": dry_run_result.snapshot.workspace_confirmation_set_hash,
        "candidate_set_hash": dry_run_result.snapshot.candidate_set_hash,
        "open_ref_snapshot_digest": execute_result.execution_record.open_ref_snapshot_digest,
        "open_ref_snapshot_id": execute_result.execution_record.open_ref_snapshot_id,
        "open_ref_repository_ref": execute_result.execution_record.open_ref_repository_ref,
        "new_main_hash": execute_result.execution_record.new_main_hash,
    }
    return payload
