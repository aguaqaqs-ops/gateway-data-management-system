from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..capabilities.repository_import import (
    RepositoryImportExecutionContext,
    RepositoryImportFailurePhase,
    RepositoryImportPlan,
    RepositoryImportProvider,
    RepositoryImportResult,
    RepositoryImportStatus,
    RepositoryImportValidationResult,
)
from ..capabilities.repository_import.import_artifacts import RepositoryImportArtifact
from ..capabilities.snapshot_materialization import SnapshotMaterializationResult
from ..artifacts import ArtifactRef
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


@runtime_checkable
class RepositoryImportRunnerProtocol(Protocol):
    def run(
        self,
        plan: RepositoryImportPlan,
        source_snapshot: SnapshotMaterializationResult,
        import_artifact: RepositoryImportArtifact,
        *,
        server_session: object | None = None,
        execution_context: RepositoryImportExecutionContext | None = None,
    ) -> RepositoryImportResult: ...


@runtime_checkable
class SubmitFinalizeWorkerProtocol(Protocol):
    def start_or_resume(self, flow_input: "SubmitFinalizeFlowInput") -> "SubmitFinalizeFlowResult": ...


@dataclass(frozen=True, slots=True)
class SubmitFinalizeFlowInput:
    repository_import_plan: RepositoryImportPlan
    source_snapshot: SnapshotMaterializationResult
    import_artifact: RepositoryImportArtifact
    runner: RepositoryImportRunnerProtocol
    submission_id: str
    operation_id: str
    server_session: object | None = None
    execution_context: RepositoryImportExecutionContext = field(default_factory=RepositoryImportExecutionContext)
    operation_runtime: OperationRuntime = field(default_factory=OperationRuntime)
    worker_id: str = "submit-finalize-worker"
    snapshot_rows_artifact_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.repository_import_plan, RepositoryImportPlan):
            raise TypeError("repository_import_plan must be a RepositoryImportPlan")
        if not isinstance(self.source_snapshot, SnapshotMaterializationResult):
            raise TypeError("source_snapshot must be a SnapshotMaterializationResult")
        if not isinstance(self.import_artifact, RepositoryImportArtifact):
            raise TypeError("import_artifact must be a RepositoryImportArtifact")
        if self.snapshot_rows_artifact_ref is not None and not isinstance(
            self.snapshot_rows_artifact_ref,
            ArtifactRef,
        ):
            raise TypeError("snapshot_rows_artifact_ref must be an ArtifactRef or None")
        if not isinstance(self.runner, RepositoryImportRunnerProtocol):
            raise TypeError("runner must implement the repository import runner protocol")
        if self.server_session is not None and not hasattr(self.server_session, "start"):
            raise TypeError("server_session must be a Dolt server session-like object or None")
        if not isinstance(self.execution_context, RepositoryImportExecutionContext):
            raise TypeError("execution_context must be a RepositoryImportExecutionContext")
        if not isinstance(self.operation_runtime, OperationRuntime):
            raise TypeError("operation_runtime must be an OperationRuntime")
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("worker_id must be a non-empty string")
        if not isinstance(self.submission_id, str) or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("operation_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SubmitFinalizeFlowResult:
    operation: OperationRecord
    run_result: OperationRunResult
    repository_import_result: RepositoryImportResult
    source_snapshot: SnapshotMaterializationResult
    submission_id: str
    snapshot_rows_artifact_ref: ArtifactRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation, OperationRecord):
            raise TypeError("operation must be an OperationRecord")
        if not isinstance(self.run_result, OperationRunResult):
            raise TypeError("run_result must be an OperationRunResult")
        if not isinstance(self.repository_import_result, RepositoryImportResult):
            raise TypeError("repository_import_result must be a RepositoryImportResult")
        if not isinstance(self.source_snapshot, SnapshotMaterializationResult):
            raise TypeError("source_snapshot must be a SnapshotMaterializationResult")
        if not isinstance(self.submission_id, str) or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if self.snapshot_rows_artifact_ref is not None and not isinstance(
            self.snapshot_rows_artifact_ref,
            ArtifactRef,
        ):
            raise TypeError("snapshot_rows_artifact_ref must be an ArtifactRef or None")


@dataclass(frozen=True, slots=True)
class SubmitFinalizeWorker:
    def start_or_resume(self, flow_input: SubmitFinalizeFlowInput) -> SubmitFinalizeFlowResult:
        return run_submit_finalize(flow_input)


def run_submit_finalize(flow_input: SubmitFinalizeFlowInput) -> SubmitFinalizeFlowResult:
    if not isinstance(flow_input, SubmitFinalizeFlowInput):
        raise TypeError("flow_input must be a SubmitFinalizeFlowInput")
    if flow_input.repository_import_plan.provider_preference is not RepositoryImportProvider.SQL_DUMP_REPLAY:
        raise ValueError("submit finalize only supports SQL_DUMP_REPLAY provider preference")

    repository_import_result: RepositoryImportResult | None = None

    plan = OperationPlan(
        operation_kind=OperationKind.SUBMIT_FINALIZE,
        caller_type=OperationCallerType.FINALIZE_WRITE_CALLER,
        parallel_policy=OperationParallelPolicy.SERIAL,
        request_payload=_submit_finalize_request_payload(flow_input),
        steps=(
            OperationStepPlan(step_name="LOAD_INPUT"),
            OperationStepPlan(step_name="RUN_REPOSITORY_IMPORT", retryable=True),
            OperationStepPlan(step_name="PUBLISH_RESULT"),
            OperationStepPlan(step_name="CLEANUP"),
        ),
    )
    operation = flow_input.operation_runtime.get_operation(flow_input.operation_id)
    if operation is None:
        raise KeyError(f"submit finalize operation not found: {flow_input.operation_id}")
    _validate_submit_finalize_operation(operation, plan)

    def load_input(context: OperationStepContext) -> OperationStepOutcome:
        return OperationStepOutcome.success(
            value={
                "repository_id": flow_input.repository_import_plan.repository_id,
                "target_ref": flow_input.repository_import_plan.target_branch_ref,
                "source_snapshot_digest": flow_input.source_snapshot.snapshot.snapshot_digest.to_payload(),
                "submission_id": flow_input.submission_id,
            }
        )

    def run_repository_import(context: OperationStepContext) -> OperationStepOutcome:
        nonlocal repository_import_result
        try:
            repository_import_result = flow_input.runner.run(
                flow_input.repository_import_plan,
                flow_input.source_snapshot,
                flow_input.import_artifact,
                server_session=flow_input.server_session,
                execution_context=flow_input.execution_context,
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            repository_import_result = _build_failed_repository_import_result(
                plan=flow_input.repository_import_plan,
                source_snapshot=flow_input.source_snapshot,
                failure_phase=RepositoryImportFailurePhase.IMPORT_FAILED,
                failure_reason=str(exc),
            )
            return OperationStepOutcome.failure(
                code="submit.finalize.import-exception",
                message=str(exc),
                retryable=True,
                value=_repository_import_result_payload(repository_import_result),
            )

        if repository_import_result.status is RepositoryImportStatus.SKIPPED:
            return OperationStepOutcome.failure(
                code="submit.finalize.import-skipped",
                message="repository import was skipped",
                retryable=False,
                value=_repository_import_result_payload(repository_import_result),
            )
        if repository_import_result.status is RepositoryImportStatus.FAILED:
            return OperationStepOutcome.failure(
                code="submit.finalize.import-failed",
                message=repository_import_result.failure_reason or "repository import failed",
                retryable=_repository_import_result_retryable(repository_import_result),
                value=_repository_import_result_payload(repository_import_result),
            )
        if repository_import_result.validation_result is RepositoryImportValidationResult.FAILED:
            return OperationStepOutcome.failure(
                code="submit.finalize.validation-failed",
                message=repository_import_result.failure_reason or "repository import validation failed",
                retryable=False,
                value=_repository_import_result_payload(repository_import_result),
            )
        return OperationStepOutcome.success(
            value=_repository_import_result_payload(repository_import_result)
        )

    def publish_result(context: OperationStepContext) -> OperationStepOutcome:
        if repository_import_result is None:
            raise RuntimeError("repository import result must be available before publish")
        if repository_import_result.status is not RepositoryImportStatus.PASSED:
            raise RuntimeError("repository import must pass before publish")
        ready_payload = _submit_finalize_ready_payload(
            flow_input=flow_input,
            repository_import_result=repository_import_result,
        )
        return OperationStepOutcome.success(
            value=ready_payload,
            ready_closure_digest=DigestRef.from_payload(ready_payload),
        )

    def cleanup(context: OperationStepContext) -> OperationStepOutcome:
        # Cleanup only releases transient resources; durable repository outputs are retained by policy.
        return OperationStepOutcome.success(value={"cleanup": "noop"})

    run_result = flow_input.operation_runtime.run_operation(
        operation.operation_id,
        handlers={
            "LOAD_INPUT": load_input,
            "RUN_REPOSITORY_IMPORT": run_repository_import,
            "PUBLISH_RESULT": publish_result,
            "CLEANUP": cleanup,
        },
        worker_id=flow_input.worker_id,
    )

    if repository_import_result is None:
        raise RuntimeError("submit finalize operation completed without repository import result")

    return SubmitFinalizeFlowResult(
        operation=run_result.operation,
        run_result=run_result,
        repository_import_result=repository_import_result,
        source_snapshot=flow_input.source_snapshot,
        submission_id=flow_input.submission_id,
        snapshot_rows_artifact_ref=flow_input.snapshot_rows_artifact_ref,
    )


def _submit_finalize_request_payload(flow_input: SubmitFinalizeFlowInput) -> Mapping[str, object]:
    plan = flow_input.repository_import_plan
    payload: dict[str, object] = {
        "operation_kind": OperationKind.SUBMIT_FINALIZE.value,
        "caller_type": OperationCallerType.FINALIZE_WRITE_CALLER.value,
        "submission_id": flow_input.submission_id,
        "repository_id": plan.repository_id,
        "target_branch_ref": plan.target_branch_ref,
        "base_ref_or_commit": plan.base_ref_or_commit,
        "source_snapshot_digest": plan.source_snapshot_digest.to_payload(),
        "validation_policy": plan.validation_policy.value,
        "provider_preference": plan.provider_preference.value,
        "server_mode": plan.server_mode.value,
        "table_ruleset_version": plan.table_ruleset_version,
        "table_count": len(plan.tables),
        "snapshot_rows_artifact_ref": (
            None
            if flow_input.snapshot_rows_artifact_ref is None
            else flow_input.snapshot_rows_artifact_ref.to_payload()
        ),
    }
    if plan.commit_message:
        payload["commit_message"] = plan.commit_message
    if plan.validation_table_names:
        payload["validation_table_names"] = list(plan.validation_table_names)
    return payload


def _submit_finalize_ready_payload(
    *,
    flow_input: SubmitFinalizeFlowInput,
    repository_import_result: RepositoryImportResult,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "submission_id": flow_input.submission_id,
        "repository_id": repository_import_result.repository_id,
        "target_ref": repository_import_result.target_ref,
        "commit_hash": repository_import_result.commit_hash,
        "import_provider": repository_import_result.import_provider.value,
        "status": repository_import_result.status.value,
        "validation_result": repository_import_result.validation_result.value,
        "source_snapshot_digest": repository_import_result.source_snapshot_digest.to_payload(),
        "readback_snapshot_digest": (
            None
            if repository_import_result.readback_snapshot_digest is None
            else repository_import_result.readback_snapshot_digest.to_payload()
        ),
        "import_artifact_manifest_digest": (
            None
            if repository_import_result.import_artifact_manifest_digest is None
            else repository_import_result.import_artifact_manifest_digest.to_payload()
        ),
        "snapshot_rows_artifact_ref": (
            None
            if flow_input.snapshot_rows_artifact_ref is None
            else flow_input.snapshot_rows_artifact_ref.to_payload()
        ),
        "failure_phase": (
            None
            if repository_import_result.failure_phase is None
            else repository_import_result.failure_phase.value
        ),
    }
    if flow_input.execution_context.idempotency_key is not None:
        payload["idempotency_key"] = flow_input.execution_context.idempotency_key
    return payload


def _repository_import_result_payload(
    repository_import_result: RepositoryImportResult,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "repository_id": repository_import_result.repository_id,
        "target_ref": repository_import_result.target_ref,
        "commit_hash": repository_import_result.commit_hash,
        "import_provider": repository_import_result.import_provider.value,
        "status": repository_import_result.status.value,
        "validation_result": repository_import_result.validation_result.value,
        "imported_table_count": repository_import_result.imported_table_count,
        "source_snapshot_digest": repository_import_result.source_snapshot_digest.to_payload(),
    }
    if repository_import_result.readback_snapshot_digest is not None:
        payload["readback_snapshot_digest"] = repository_import_result.readback_snapshot_digest.to_payload()
    if repository_import_result.failure_phase is not None:
        payload["failure_phase"] = repository_import_result.failure_phase.value
    if repository_import_result.failure_reason is not None:
        payload["failure_reason"] = repository_import_result.failure_reason
    return payload


def _repository_import_result_retryable(
    repository_import_result: RepositoryImportResult,
) -> bool:
    failure_phase = repository_import_result.failure_phase
    if failure_phase is None:
        return False
    return failure_phase in {
        RepositoryImportFailurePhase.STAGING_FAILED,
        RepositoryImportFailurePhase.IMPORT_FAILED,
        RepositoryImportFailurePhase.COMMIT_FAILED,
        RepositoryImportFailurePhase.READBACK_FAILED,
        RepositoryImportFailurePhase.CLEANUP_FAILED,
        RepositoryImportFailurePhase.SERVER_START_FAILED,
        RepositoryImportFailurePhase.SERVER_HEALTH_CHECK_FAILED,
        RepositoryImportFailurePhase.SERVER_SHUTDOWN_FAILED,
        RepositoryImportFailurePhase.TIMEOUT,
    }


def _build_failed_repository_import_result(
    *,
    plan: RepositoryImportPlan,
    source_snapshot: SnapshotMaterializationResult,
    failure_phase: RepositoryImportFailurePhase,
    failure_reason: str,
) -> RepositoryImportResult:
    return RepositoryImportResult(
        repository_id=plan.repository_id,
        target_ref=plan.target_branch_ref,
        commit_hash=None,
        import_provider=plan.effective_provider,
        status=RepositoryImportStatus.FAILED,
        validation_result=RepositoryImportValidationResult.FAILED,
        imported_table_count=0,
        source_snapshot_digest=source_snapshot.snapshot.snapshot_digest,
        readback_snapshot_digest=None,
        server_mode=plan.server_mode,
        failure_phase=failure_phase,
        failure_reason=failure_reason,
        diagnostics=tuple(source_snapshot.diagnostics),
    )


def _validate_submit_finalize_operation(
    operation: OperationRecord,
    plan: OperationPlan,
) -> None:
    if operation.operation_kind is not OperationKind.SUBMIT_FINALIZE:
        raise ValueError("submit finalize operation kind mismatch")
    if operation.caller_type is not OperationCallerType.FINALIZE_WRITE_CALLER:
        raise ValueError("submit finalize caller type mismatch")
    if operation.parallel_policy is not plan.parallel_policy:
        raise ValueError("submit finalize parallel policy mismatch")
    if operation.request_payload.get("submission_id") != plan.request_payload.get("submission_id"):
        raise ValueError("submit finalize submission_id mismatch")
    if len(operation.steps) != len(plan.steps):
        raise ValueError("submit finalize step count mismatch")
    for operation_step, plan_step in zip(operation.steps, plan.steps, strict=True):
        if operation_step.step_name != plan_step.step_name:
            raise ValueError("submit finalize step name mismatch")
        if operation_step.retryable != plan_step.retryable:
            raise ValueError("submit finalize step retryable mismatch")
        if operation_step.allow_parallel != plan_step.allow_parallel:
            raise ValueError("submit finalize step allow_parallel mismatch")
