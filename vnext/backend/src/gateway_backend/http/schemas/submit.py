"""Submit HTTP DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gateway_backend.domain.submission.models import SubmitAttempt, Submission
from gateway_backend.http.schemas.constraints import BoundedOpaqueId, NonNegativeIJsonInt


class AcceptSubmitOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AcceptSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_workspace_version: NonNegativeIJsonInt
    preview_result_id: BoundedOpaqueId
    upload_revision_id: BoundedOpaqueId
    generation: NonNegativeIJsonInt
    expected_baseline_node_id: BoundedOpaqueId
    expected_baseline_head_version: NonNegativeIJsonInt
    options: AcceptSubmitOptions = Field(default_factory=AcceptSubmitOptions)


SubmitAttemptStateLiteral = Literal["PREPARED", "EFFECT_PENDING", "FINALIZED", "ABORTED"]


class SubmitAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submit_attempt_id: str
    operation_id: str
    workspace_id: str
    preview_result_id: str
    generation: int
    state: SubmitAttemptStateLiteral


class SubmitAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submit_attempt_id: str
    workspace_id: str
    upload_revision_id: str
    preview_result_id: str
    generation: int
    operation_id: str
    state: SubmitAttemptStateLiteral
    submission_id: str | None = None
    business_baseline_node_id: str
    business_baseline_commit_id: str
    canonical_business_digest: str
    created_at: datetime
    effect_pending_at: datetime | None = None
    finalized_at: datetime | None = None
    aborted_at: datetime | None = None
    abort_code: str | None = None


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str
    submit_attempt_id: str
    workspace_id: str
    upload_revision_id: str
    preview_result_id: str
    generation: int
    repository_id: str
    based_on_baseline_node_id: str
    business_baseline_commit_id: str
    repository_commit_id: str
    canonical_business_digest: str
    canonicalization_manifest_digest: str
    created_by: str
    created_at: datetime


def submit_attempt_to_response(attempt: SubmitAttempt) -> SubmitAttemptResponse:
    return SubmitAttemptResponse(
        submit_attempt_id=attempt.submit_attempt_id,
        workspace_id=attempt.workspace_id,
        upload_revision_id=attempt.upload_revision_id,
        preview_result_id=attempt.preview_result_id,
        generation=attempt.workspace_generation,
        operation_id=attempt.operation_id,
        state=attempt.state.value,
        submission_id=attempt.submission_id,
        business_baseline_node_id=attempt.business_baseline_node_id,
        business_baseline_commit_id=attempt.business_baseline_commit_id,
        canonical_business_digest=attempt.canonical_business_digest,
        created_at=attempt.created_at,
        effect_pending_at=attempt.effect_pending_at,
        finalized_at=attempt.finalized_at,
        aborted_at=attempt.aborted_at,
        abort_code=attempt.abort_code,
    )


def submission_to_response(submission: Submission) -> SubmissionResponse:
    return SubmissionResponse(
        submission_id=submission.submission_id,
        submit_attempt_id=submission.submit_attempt_id,
        workspace_id=submission.workspace_id,
        upload_revision_id=submission.upload_revision_id,
        preview_result_id=submission.preview_result_id,
        generation=submission.workspace_generation,
        repository_id=submission.repository_id,
        based_on_baseline_node_id=submission.based_on_baseline_node_id,
        business_baseline_commit_id=submission.business_baseline_commit_id,
        repository_commit_id=submission.repository_commit_id,
        canonical_business_digest=submission.canonical_business_digest,
        canonicalization_manifest_digest=submission.canonicalization_manifest_digest,
        created_by=submission.created_by,
        created_at=submission.created_at,
    )
