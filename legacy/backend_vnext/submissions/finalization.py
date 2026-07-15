from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..capabilities.repository_import import RepositoryImportResult
from ..operations import OperationRecord
from ..workspaces.models import WorkspaceRecord
from .models import SubmissionArchiveStatus, SubmissionRecord, SubmissionStatus
from .store import SubmissionStore


@runtime_checkable
class SubmitFinalizeResultPort(Protocol):
    operation: OperationRecord
    repository_import_result: RepositoryImportResult
    submission_id: str


def _is_submit_finalize_result(value: object) -> bool:
    return isinstance(value, SubmitFinalizeResultPort)


@dataclass(frozen=True, slots=True)
class SubmissionFinalizeInput:
    flow_result: SubmitFinalizeResultPort
    workspace: WorkspaceRecord

    def __post_init__(self) -> None:
        if not _is_submit_finalize_result(self.flow_result):
            raise TypeError("flow_result must be a SubmitFinalizeFlowResult")
        if not isinstance(self.workspace, WorkspaceRecord):
            raise TypeError("workspace must be a WorkspaceRecord")


@dataclass(frozen=True, slots=True)
class SubmissionFinalizeService:
    submission_store: SubmissionStore

    def __post_init__(self) -> None:
        if not hasattr(self.submission_store, "create") or not hasattr(self.submission_store, "get") or not hasattr(self.submission_store, "save") or not hasattr(self.submission_store, "delete"):
            raise TypeError("submission_store must implement the SubmissionStore protocol")

    def finalize_submission(self, command: SubmissionFinalizeInput) -> SubmissionRecord:
        if not isinstance(command, SubmissionFinalizeInput):
            raise TypeError("command must be a SubmissionFinalizeInput")

        flow_result = command.flow_result
        workspace = command.workspace
        repository_import_result = flow_result.repository_import_result
        existing = self.submission_store.get(flow_result.submission_id)
        if existing is not None:
            if (
                existing.workspace_id != workspace.workspace_id
                or existing.batch_id != workspace.batch_id
                or existing.repository_id != repository_import_result.repository_id
                or existing.repository_target_ref != repository_import_result.target_ref
                or existing.repository_commit_hash != repository_import_result.commit_hash
            ):
                raise ValueError("submission already exists with a conflicting finalize payload")
            return existing

        preview_binding = workspace.latest_preview_input_binding
        record = SubmissionRecord(
            submission_id=flow_result.submission_id,
            workspace_id=workspace.workspace_id,
            batch_id=workspace.batch_id,
            status=SubmissionStatus.PENDING_REVIEW,
            archive_status=SubmissionArchiveStatus.NOT_ARCHIVED,
            source_package_id=None,
            preview_binding_id=None if preview_binding is None else preview_binding.binding_id,
            preview_revision_id=None if preview_binding is None else preview_binding.upload_generation,
            preview_source_digest=None if preview_binding is None else preview_binding.preview_source_digest,
            repository_id=repository_import_result.repository_id,
            repository_target_ref=repository_import_result.target_ref,
            repository_commit_hash=repository_import_result.commit_hash,
            submitted_at=flow_result.operation.created_at,
            created_at=flow_result.operation.created_at,
            updated_at=flow_result.operation.updated_at,
        )
        self.submission_store.create(record)
        return record


def finalize_submission(
    *,
    submission_store: SubmissionStore,
    command: SubmissionFinalizeInput,
) -> SubmissionRecord:
    service = SubmissionFinalizeService(submission_store=submission_store)
    return service.finalize_submission(command)
