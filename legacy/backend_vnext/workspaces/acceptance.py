from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..contracts.submit import PreviewInputBinding, SubmitAccepted, SubmitSourcePackage
from ..flows.submit_acceptance import (
    SubmitAcceptanceFlowInput,
    SubmitAcceptanceFlowResult,
    run_submit_acceptance,
)
from ..operations import OperationRuntime
from ..submissions.store import SubmissionIdentityStore
from .models import WorkspaceRecord
from .store import WorkspaceStore


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitAcceptanceCommand:
    workspace_id: str
    submit_source_package: SubmitSourcePackage
    preview_input_binding: PreviewInputBinding
    operation_runtime: OperationRuntime
    worker_id: str = "workspace-submit-acceptance-worker"
    operation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or not self.workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if not isinstance(self.submit_source_package, SubmitSourcePackage):
            raise TypeError("submit_source_package must be a SubmitSourcePackage")
        if not isinstance(self.preview_input_binding, PreviewInputBinding):
            raise TypeError("preview_input_binding must be a PreviewInputBinding")
        if not isinstance(self.operation_runtime, OperationRuntime):
            raise TypeError("operation_runtime must be an OperationRuntime")
        if not isinstance(self.worker_id, str) or not self.worker_id:
            raise ValueError("worker_id must be a non-empty string")
        if self.operation_id is not None and not isinstance(self.operation_id, str):
            raise TypeError("operation_id must be a string or None")


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitAcceptanceResult:
    workspace: WorkspaceRecord
    acceptance: SubmitAcceptanceFlowResult

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, WorkspaceRecord):
            raise TypeError("workspace must be a WorkspaceRecord")
        if not isinstance(self.acceptance, SubmitAcceptanceFlowResult):
            raise TypeError("acceptance must be a SubmitAcceptanceFlowResult")

    @property
    def accepted(self) -> SubmitAccepted:
        return self.acceptance.accepted

    @property
    def submission_id(self) -> str:
        return self.acceptance.submission_id


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitAcceptanceService:
    workspace_store: WorkspaceStore
    submission_identity_store: SubmissionIdentityStore

    def __post_init__(self) -> None:
        if not hasattr(self.workspace_store, "create") or not hasattr(self.workspace_store, "get") or not hasattr(self.workspace_store, "save") or not hasattr(self.workspace_store, "delete"):
            raise TypeError("workspace_store must implement the WorkspaceStore protocol")
        if not hasattr(self.submission_identity_store, "next_identity"):
            raise TypeError("submission_identity_store must implement next_identity()")

    def accept_submit(self, command: WorkspaceSubmitAcceptanceCommand) -> WorkspaceSubmitAcceptanceResult:
        if not isinstance(command, WorkspaceSubmitAcceptanceCommand):
            raise TypeError("command must be a WorkspaceSubmitAcceptanceCommand")

        workspace = self.workspace_store.get(command.workspace_id)
        if workspace is None:
            raise KeyError(f"workspace not found: {command.workspace_id}")

        workspace.ensure_submit_acceptance_ready(command.preview_input_binding)
        acceptance = run_submit_acceptance(
            SubmitAcceptanceFlowInput(
                submit_source_package=command.submit_source_package,
                preview_input_binding=command.preview_input_binding,
                submission_identity_store=self.submission_identity_store,
                operation_runtime=command.operation_runtime,
                worker_id=command.worker_id,
                operation_id=command.operation_id,
            )
        )
        now = datetime.now(timezone.utc)
        updated_workspace = workspace.start_submit_acceptance(
            acceptance.operation.operation_id,
            updated_at=now,
        )
        try:
            self.workspace_store.save(
                updated_workspace,
                expected_version=workspace.version,
            )
        except Exception:
            try:
                command.operation_runtime.store.delete(acceptance.operation.operation_id)
            except Exception:
                pass
            raise

        return WorkspaceSubmitAcceptanceResult(
            workspace=updated_workspace,
            acceptance=acceptance,
        )


def submit_workspace(
    *,
    workspace_store: WorkspaceStore,
    submission_identity_store: SubmissionIdentityStore,
    command: WorkspaceSubmitAcceptanceCommand,
) -> WorkspaceSubmitAcceptanceResult:
    service = WorkspaceSubmitAcceptanceService(
        workspace_store=workspace_store,
        submission_identity_store=submission_identity_store,
    )
    return service.accept_submit(command)
