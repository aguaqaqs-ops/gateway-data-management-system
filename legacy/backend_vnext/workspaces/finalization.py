from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..operations import OperationRecord, OperationStatus
from ..submissions.finalization import (
    SubmissionFinalizeInput,
    SubmissionFinalizeService,
    SubmitFinalizeResultPort,
)
from ..submissions.models import SubmissionRecord
from ..submissions.store import SubmissionStore
from .models import WorkspaceRecord, WorkspaceStatus
from .store import WorkspaceStore

if TYPE_CHECKING:
    from ..flows.submit_finalize import (
        SubmitFinalizeFlowInput,
        SubmitFinalizeWorkerProtocol,
    )


def _default_submit_finalize_worker() -> "SubmitFinalizeWorkerProtocol":
    from ..flows.submit_finalize import SubmitFinalizeWorker

    return SubmitFinalizeWorker()


def _is_submit_finalize_flow_input(value: object) -> bool:
    from ..flows.submit_finalize import SubmitFinalizeFlowInput

    return isinstance(value, SubmitFinalizeFlowInput)


def _is_submit_finalize_worker(value: object) -> bool:
    from ..flows.submit_finalize import SubmitFinalizeWorkerProtocol

    return isinstance(value, SubmitFinalizeWorkerProtocol)


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitFinalizeCommand:
    workspace_id: str
    operation_id: str
    submission_id: str
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or not self.workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if not isinstance(self.operation_id, str) or not self.operation_id:
            raise ValueError("operation_id must be a non-empty string")
        if not isinstance(self.submission_id, str) or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if self.updated_at is not None and not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be a datetime or None")
        if self.updated_at is not None and self.updated_at.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitFinalizeResult:
    workspace: WorkspaceRecord

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, WorkspaceRecord):
            raise TypeError("workspace must be a WorkspaceRecord")


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitFinalizeWorkflowCommand:
    workspace_finalize_command: WorkspaceSubmitFinalizeCommand
    submit_finalize_flow_input: "SubmitFinalizeFlowInput"
    submit_finalize_worker: "SubmitFinalizeWorkerProtocol" = field(default_factory=_default_submit_finalize_worker)

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_finalize_command, WorkspaceSubmitFinalizeCommand):
            raise TypeError("workspace_finalize_command must be a WorkspaceSubmitFinalizeCommand")
        if not _is_submit_finalize_flow_input(self.submit_finalize_flow_input):
            raise TypeError("submit_finalize_flow_input must be a SubmitFinalizeFlowInput")
        if not _is_submit_finalize_worker(self.submit_finalize_worker):
            raise TypeError("submit_finalize_worker must implement the submit finalize worker protocol")


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitFinalizeWorkflowResult:
    flow_result: SubmitFinalizeResultPort
    submission_record: SubmissionRecord | None = None
    workspace_result: WorkspaceSubmitFinalizeResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.flow_result, SubmitFinalizeResultPort):
            raise TypeError("flow_result must be a SubmitFinalizeFlowResult")
        if self.submission_record is not None and not isinstance(self.submission_record, SubmissionRecord):
            raise TypeError("submission_record must be a SubmissionRecord or None")
        if self.workspace_result is not None and not isinstance(
            self.workspace_result,
            WorkspaceSubmitFinalizeResult,
        ):
            raise TypeError("workspace_result must be a WorkspaceSubmitFinalizeResult or None")

    @property
    def submission_id(self) -> str:
        return self.flow_result.submission_id

    @property
    def operation(self) -> OperationRecord:
        return self.flow_result.operation

    @property
    def workspace(self) -> WorkspaceRecord | None:
        if self.workspace_result is None:
            return None
        return self.workspace_result.workspace

    @property
    def workspace_updated(self) -> bool:
        return self.workspace_result is not None


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitFinalizeService:
    workspace_store: WorkspaceStore

    def __post_init__(self) -> None:
        if not hasattr(self.workspace_store, "create") or not hasattr(self.workspace_store, "get") or not hasattr(self.workspace_store, "save") or not hasattr(self.workspace_store, "delete"):
            raise TypeError("workspace_store must implement the WorkspaceStore protocol")

    def finalize_submit(
        self,
        command: WorkspaceSubmitFinalizeCommand,
    ) -> WorkspaceSubmitFinalizeResult:
        if not isinstance(command, WorkspaceSubmitFinalizeCommand):
            raise TypeError("command must be a WorkspaceSubmitFinalizeCommand")

        workspace = self.workspace_store.get(command.workspace_id)
        if workspace is None:
            raise KeyError(f"workspace not found: {command.workspace_id}")

        if (
            workspace.status is WorkspaceStatus.SUBMITTED
            and workspace.submitted_submission_id == command.submission_id
            and workspace.active_submit_operation_id is None
        ):
            return WorkspaceSubmitFinalizeResult(workspace=workspace)

        updated_workspace = workspace.complete_submit(
            command.operation_id,
            command.submission_id,
            updated_at=command.updated_at or datetime.now(timezone.utc),
        )
        self.workspace_store.save(
            updated_workspace,
            expected_version=workspace.version,
        )
        return WorkspaceSubmitFinalizeResult(workspace=updated_workspace)


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitFinalizeWorkflowService:
    workspace_store: WorkspaceStore
    submission_store: SubmissionStore

    def __post_init__(self) -> None:
        if not hasattr(self.workspace_store, "create") or not hasattr(self.workspace_store, "get") or not hasattr(self.workspace_store, "save") or not hasattr(self.workspace_store, "delete"):
            raise TypeError("workspace_store must implement the WorkspaceStore protocol")
        if not hasattr(self.submission_store, "create") or not hasattr(self.submission_store, "get") or not hasattr(self.submission_store, "save") or not hasattr(self.submission_store, "delete"):
            raise TypeError("submission_store must implement the SubmissionStore protocol")

    def finalize_submit(
        self,
        command: WorkspaceSubmitFinalizeWorkflowCommand,
    ) -> WorkspaceSubmitFinalizeWorkflowResult:
        if not isinstance(command, WorkspaceSubmitFinalizeWorkflowCommand):
            raise TypeError("command must be a WorkspaceSubmitFinalizeWorkflowCommand")

        flow_result = command.submit_finalize_worker.start_or_resume(
            command.submit_finalize_flow_input,
        )
        if flow_result.submission_id != command.workspace_finalize_command.submission_id:
            raise ValueError("submission_id must match between submit finalize flow and workspace command")
        if flow_result.operation.operation_id != command.workspace_finalize_command.operation_id:
            raise ValueError("operation_id must match between submit finalize flow and workspace command")
        if flow_result.operation.status is not OperationStatus.READY:
            return WorkspaceSubmitFinalizeWorkflowResult(flow_result=flow_result)

        workspace = self.workspace_store.get(command.workspace_finalize_command.workspace_id)
        if workspace is None:
            raise KeyError(f"workspace not found: {command.workspace_finalize_command.workspace_id}")
        existing_submission = self.submission_store.get(flow_result.submission_id)
        submission_result = SubmissionFinalizeService(
            submission_store=self.submission_store,
        ).finalize_submission(
            SubmissionFinalizeInput(
                flow_result=flow_result,
                workspace=workspace,
            )
        )
        try:
            workspace_result = WorkspaceSubmitFinalizeService(
                workspace_store=self.workspace_store,
            ).finalize_submit(command.workspace_finalize_command)
        except Exception:
            if existing_submission is None:
                try:
                    self.submission_store.delete(submission_result.submission_id)
                except Exception:
                    pass
            raise
        return WorkspaceSubmitFinalizeWorkflowResult(
            flow_result=flow_result,
            submission_record=submission_result,
            workspace_result=workspace_result,
        )


def finalize_workspace_submit(
    *,
    workspace_store: WorkspaceStore,
    submission_store: SubmissionStore,
    command: WorkspaceSubmitFinalizeWorkflowCommand,
) -> WorkspaceSubmitFinalizeWorkflowResult:
    service = WorkspaceSubmitFinalizeWorkflowService(
        workspace_store=workspace_store,
        submission_store=submission_store,
    )
    return service.finalize_submit(command)
