from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..contracts.repository import (
    MutableRefReleaseConflict,
    MutableRefReleaseRejected,
    RefPurpose,
    RefReleaseRequest,
    RefRetentionOwnerKind,
    RepositoryOperationContext,
    RepositoryRefPort,
)

from ..workspaces.models import WorkspaceRecord
from ..workspaces.store import WorkspaceStore
from .models import SubmissionRecord
from .store import SubmissionStore


@dataclass(frozen=True, slots=True)
class SubmissionReviewCommand:
    submission_id: str
    actor_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.submission_id, str) or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if not isinstance(self.actor_id, str) or not self.actor_id:
            raise ValueError("actor_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SubmissionReviewResult:
    submission: SubmissionRecord
    workspace: WorkspaceRecord

    def __post_init__(self) -> None:
        if not isinstance(self.submission, SubmissionRecord):
            raise TypeError("submission must be a SubmissionRecord")
        if not isinstance(self.workspace, WorkspaceRecord):
            raise TypeError("workspace must be a WorkspaceRecord")


@dataclass(frozen=True, slots=True)
class SubmissionReviewService:
    submission_store: SubmissionStore
    workspace_store: WorkspaceStore
    repository_ref_port: RepositoryRefPort | None = None

    def __post_init__(self) -> None:
        if not hasattr(self.submission_store, "create") or not hasattr(self.submission_store, "get") or not hasattr(self.submission_store, "save") or not hasattr(self.submission_store, "delete"):
            raise TypeError("submission_store must implement the SubmissionStore protocol")
        if not hasattr(self.workspace_store, "create") or not hasattr(self.workspace_store, "get") or not hasattr(self.workspace_store, "save") or not hasattr(self.workspace_store, "delete"):
            raise TypeError("workspace_store must implement the WorkspaceStore protocol")
        if self.repository_ref_port is not None and not hasattr(self.repository_ref_port, "release_mutable_ref"):
            raise TypeError("repository_ref_port must implement release_mutable_ref() or be None")

    def start_review(self, command: SubmissionReviewCommand) -> SubmissionReviewResult:
        return self._mutate(command, action="start_review")

    def approve(self, command: SubmissionReviewCommand) -> SubmissionReviewResult:
        return self._mutate(command, action="approve")

    def reject(self, command: SubmissionReviewCommand) -> SubmissionReviewResult:
        return self._mutate(command, action="reject", reopen_workspace=True)

    def withdraw(self, command: SubmissionReviewCommand) -> SubmissionReviewResult:
        return self._mutate(command, action="withdraw", reopen_workspace=True)

    def _mutate(
        self,
        command: SubmissionReviewCommand,
        *,
        action: str,
        reopen_workspace: bool = False,
    ) -> SubmissionReviewResult:
        if not isinstance(command, SubmissionReviewCommand):
            raise TypeError("command must be a SubmissionReviewCommand")

        submission = self.submission_store.get(command.submission_id)
        if submission is None:
            raise KeyError(f"submission not found: {command.submission_id}")
        workspace = self.workspace_store.get(submission.workspace_id)
        if workspace is None:
            raise KeyError(f"workspace not found: {submission.workspace_id}")

        if action == "start_review":
            updated_submission = submission.start_review(
                reviewer_actor_id=command.actor_id,
                reviewed_at=datetime.now(timezone.utc),
            )
        elif action == "approve":
            updated_submission = submission.approve(
                reviewer_actor_id=command.actor_id,
                reviewed_at=datetime.now(timezone.utc),
            )
        elif action == "reject":
            updated_submission = submission.reject(
                reviewer_actor_id=command.actor_id,
                reviewed_at=datetime.now(timezone.utc),
            )
        elif action == "withdraw":
            updated_submission = submission.withdraw(
                actor_id=command.actor_id,
                withdrawn_at=datetime.now(timezone.utc),
            )
        else:
            raise ValueError(f"unsupported review action: {action}")

        self.submission_store.save(updated_submission, expected_version=submission.version)

        updated_workspace = workspace
        if reopen_workspace:
            reopened = workspace.reopen_after_terminal_submission(
                updated_submission.submission_id,
                updated_at=datetime.now(timezone.utc),
            )
            if reopened is not workspace:
                self.workspace_store.save(reopened, expected_version=workspace.version)
                updated_workspace = reopened
            self._release_mutable_ref(submission=updated_submission, workspace=workspace)

        return SubmissionReviewResult(submission=updated_submission, workspace=updated_workspace)

    def _release_mutable_ref(
        self,
        *,
        submission: SubmissionRecord,
        workspace: WorkspaceRecord,
    ) -> None:
        if self.repository_ref_port is None:
            return
        if submission.repository_id is None or submission.repository_target_ref is None or submission.repository_commit_hash is None:
            return
        try:
            self.repository_ref_port.release_mutable_ref(
                RefReleaseRequest(
                    repository_id=submission.repository_id,
                    ref=submission.repository_target_ref,
                    purpose=RefPurpose.WORKSPACE_DRAFT,
                    expected_commit_hash=submission.repository_commit_hash,
                    owner_kind=RefRetentionOwnerKind.WORKSPACE,
                    owner_id=workspace.workspace_id,
                    reason=f"submission_{submission.status.value.lower()}",
                    idempotency_key=(
                        f"submission-review-release:"
                        f"{workspace.workspace_id}:{submission.submission_id}:{submission.status.value}"
                    ),
                ),
                context=RepositoryOperationContext(
                    operation_id=(
                        f"submission-review-release-{workspace.workspace_id}-{submission.submission_id}"
                    ),
                    caller_service="backend_vnext.submissions.review",
                    actor_id=submission.reviewed_by_actor_id or submission.withdrawn_by_actor_id or "system",
                ),
            )
        except (MutableRefReleaseConflict, MutableRefReleaseRejected):
            raise
