"""Archive HTTP DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from gateway_backend.application.archive.audit import AppendArchiveAuditResult
from gateway_backend.application.archive.contracts import (
    ARCHIVE_MAX_AUDIT_REFS,
    ArchiveAuditReferenceInput,
    ArchiveSelectedRef,
    validate_archive_confirmation_reason,
    validate_archive_digest,
    validate_utf8_id,
)
from gateway_backend.application.archive.errors import ArchiveRequestValidation
from gateway_backend.application.archive.queries import (
    ArchiveCandidatesResult,
    ArchivePreviewAnomaly,
    ArchivePreviewDisposition,
    GetArchiveResultResult,
    ListArchiveAuditEventsResult,
    PreviewArchivePlanResult,
)
from gateway_backend.application.archive.start import StartArchiveResult
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionEvent,
    ArchiveConfirmationAction,
    ArchiveConfirmationEvent,
    ArchiveDisposition,
    ArchiveSubjectKind,
)
from gateway_backend.domain.workspace.models import BaselineHead
from gateway_backend.http.schemas.constraints import (
    BoundedDiagnosticReason,
    BoundedOpaqueId,
    NonNegativeIJsonInt,
)

ArchiveConfirmationActionLiteral = Literal["CONFIRM", "REVOKE"]
ArchiveAnomalyResolutionActionLiteral = Literal["ACKNOWLEDGE_EXCLUSION", "REVOKE"]
ArchiveSubjectKindLiteral = Literal["CONFIRM_SELECTION", "APPROVED_SIBLING_EXCLUDED"]
ArchiveDispositionLiteral = Literal["ARCHIVED_BASELINE", "CLOSED_NOT_ARCHIVED"]


def _validation_value_error(exc: ArchiveRequestValidation) -> ValueError:
    return ValueError(str(exc))


def _validate_archive_digest_field(value: object, *, field_name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a string")
    try:
        return validate_archive_digest(value, field_name=field_name)
    except ArchiveRequestValidation as exc:
        raise _validation_value_error(exc) from exc


ArchiveDigest = Annotated[
    str,
    BeforeValidator(lambda value: _validate_archive_digest_field(value, field_name="digest")),
]


class BaselineHeadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_baseline_node_id: BoundedOpaqueId
    business_baseline_commit_id: BoundedOpaqueId
    baseline_head_version: NonNegativeIJsonInt


class ArchiveSelectedRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: BoundedOpaqueId
    expected_candidate_digest: ArchiveDigest


class ArchiveAuditReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_digest: ArchiveDigest
    sequence: NonNegativeIJsonInt


class PreviewArchivePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected: ArchiveSelectedRefRequest | None = None


class AppendArchiveConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_baseline_node_id: BoundedOpaqueId
    expected_baseline_head_version: NonNegativeIJsonInt
    selected: ArchiveSelectedRefRequest
    candidate_set_digest: ArchiveDigest
    subject_digest: ArchiveDigest
    expected_sequence: NonNegativeIJsonInt
    action: ArchiveConfirmationActionLiteral
    reason: BoundedDiagnosticReason | None = None

    @model_validator(mode="after")
    def validate_reason_for_action(self) -> Self:
        validate_confirmation_reason_field(self.action, self.reason)
        return self


class AppendArchiveAnomalyResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_baseline_node_id: BoundedOpaqueId
    expected_baseline_head_version: NonNegativeIJsonInt
    selected: ArchiveSelectedRefRequest
    candidate_set_digest: ArchiveDigest
    subject_digest: ArchiveDigest
    expected_sequence: NonNegativeIJsonInt
    action: ArchiveAnomalyResolutionActionLiteral
    reason: BoundedDiagnosticReason
    issue_code: BoundedOpaqueId
    sibling_submission_id: BoundedOpaqueId
    sibling_candidate_digest: ArchiveDigest


class StartArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_baseline_node_id: BoundedOpaqueId
    expected_baseline_head_version: NonNegativeIJsonInt
    candidate_set_digest: ArchiveDigest
    selected: ArchiveSelectedRefRequest
    confirmation_refs: list[ArchiveAuditReferenceRequest] = Field(
        default_factory=list,
        max_length=ARCHIVE_MAX_AUDIT_REFS,
    )
    anomaly_resolution_refs: list[ArchiveAuditReferenceRequest] = Field(
        default_factory=list,
        max_length=ARCHIVE_MAX_AUDIT_REFS,
    )

    @model_validator(mode="after")
    def validate_unique_audit_refs(self) -> Self:
        _assert_unique_audit_refs(self.confirmation_refs, field_name="confirmation_refs")
        _assert_unique_audit_refs(
            self.anomaly_resolution_refs,
            field_name="anomaly_resolution_refs",
        )
        return self


class ArchiveCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str
    expected_candidate_digest: str


class ArchiveCandidatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    head: BaselineHeadResponse
    candidates: list[ArchiveCandidateResponse]
    candidate_set_digest: str
    blockers: list[str]


class ArchivePreviewAnomalyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_code: str
    sibling_submission_id: str
    sibling_candidate_digest: str
    subject_digest: str


class ArchivePreviewDispositionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str
    disposition: ArchiveDispositionLiteral


class ArchivePreviewWorkspaceReleaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    submission_id: str


class PreviewArchivePlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    head: BaselineHeadResponse
    candidate_set_digest: str
    selected: ArchiveSelectedRefRequest | None = None
    selection_subject_digest: str | None = None
    confirmation_requirements: list[str]
    anomalies: list[ArchivePreviewAnomalyResponse]
    audit_validity: bool
    dispositions: list[ArchivePreviewDispositionResponse]
    workspace_releases: list[ArchivePreviewWorkspaceReleaseResponse]
    can_start: bool
    blockers: list[str]


class ArchiveAuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    subject_kind: ArchiveSubjectKindLiteral
    subject_digest: str
    sequence: int
    action: str
    reason: str | None = None
    actor_id: str
    occurred_at: datetime
    issue_code: str | None = None
    sibling_submission_id: str | None = None
    sibling_candidate_digest: str | None = None


class ArchiveAuditAppendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    sequence: int


class ArchiveAuditEventsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[ArchiveAuditEventResponse]
    next_after_sequence: int | None = None


class ArchiveDispositionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str
    disposition: ArchiveDispositionLiteral


class ArchiveStartedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archive_plan_id: str
    archive_result_id: str
    baseline_node_id: str
    baseline_commit_id: str
    baseline_head_version: int
    selected_submission_id: str
    dispositions: list[ArchiveDispositionResponse]
    released_workspace_ids: list[str]
    archived_by: str
    archived_at: datetime


class ArchiveAuditReferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_digest: str
    sequence: int


class ArchiveResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archive_result_id: str
    archive_plan_id: str
    baseline_node_id: str
    baseline_commit_id: str
    baseline_head_version: int
    selected_submission_id: str
    selected_repository_commit_id: str
    candidate_set_digest: str
    confirmation_refs: list[ArchiveAuditReferenceResponse]
    anomaly_resolution_refs: list[ArchiveAuditReferenceResponse]
    dispositions: list[ArchiveDispositionResponse]
    archived_by: str
    archived_at: datetime


def baseline_head_to_response(head: BaselineHead) -> BaselineHeadResponse:
    return BaselineHeadResponse(
        business_baseline_node_id=head.business_baseline_node_id,
        business_baseline_commit_id=head.business_baseline_commit_id,
        baseline_head_version=head.baseline_head_version,
    )


def selected_ref_from_request(body: ArchiveSelectedRefRequest) -> ArchiveSelectedRef:
    return ArchiveSelectedRef(
        submission_id=body.submission_id,
        expected_candidate_digest=body.expected_candidate_digest,
    )


def audit_reference_from_request(body: ArchiveAuditReferenceRequest) -> ArchiveAuditReferenceInput:
    return ArchiveAuditReferenceInput(
        subject_digest=body.subject_digest,
        sequence=body.sequence,
    )


def archive_candidates_to_response(result: ArchiveCandidatesResult) -> ArchiveCandidatesResponse:
    return ArchiveCandidatesResponse(
        head=baseline_head_to_response(result.head),
        candidates=[
            ArchiveCandidateResponse(
                submission_id=candidate.submission_id,
                expected_candidate_digest=candidate.expected_candidate_digest,
            )
            for candidate in result.candidates
        ],
        candidate_set_digest=result.candidate_set_digest,
        blockers=list(result.blockers),
    )


def preview_plan_to_response(result: PreviewArchivePlanResult) -> PreviewArchivePlanResponse:
    selected = None
    if result.selected is not None:
        selected = ArchiveSelectedRefRequest(
            submission_id=result.selected.submission_id,
            expected_candidate_digest=result.selected.expected_candidate_digest,
        )
    return PreviewArchivePlanResponse(
        head=baseline_head_to_response(result.head),
        candidate_set_digest=result.candidate_set_digest,
        selected=selected,
        selection_subject_digest=result.selection_subject_digest,
        confirmation_requirements=list(result.confirmation_requirements),
        anomalies=[_anomaly_to_response(anomaly) for anomaly in result.anomalies],
        audit_validity=result.audit_valid,
        dispositions=[_disposition_to_response(item) for item in result.dispositions],
        workspace_releases=[
            ArchivePreviewWorkspaceReleaseResponse(
                workspace_id=item.workspace_id,
                submission_id=item.submission_id,
            )
            for item in result.workspace_releases
        ],
        can_start=result.can_start,
        blockers=list(result.blockers),
    )


def audit_append_to_response(result: AppendArchiveAuditResult) -> ArchiveAuditAppendResponse:
    return ArchiveAuditAppendResponse(
        event_id=result.event_id,
        sequence=result.sequence,
    )


def audit_events_to_response(result: ListArchiveAuditEventsResult) -> ArchiveAuditEventsResponse:
    return ArchiveAuditEventsResponse(
        events=[_audit_event_to_response(event) for event in result.events],
        next_after_sequence=result.next_after_sequence,
    )


def start_archive_to_response(result: StartArchiveResult) -> ArchiveStartedResponse:
    return ArchiveStartedResponse(
        archive_plan_id=result.archive_plan_id,
        archive_result_id=result.archive_result_id,
        baseline_node_id=result.baseline_node_id,
        baseline_commit_id=result.baseline_commit_id,
        baseline_head_version=result.baseline_head_version,
        selected_submission_id=result.selected_submission_id,
        dispositions=[_disposition_record_to_response(item) for item in result.dispositions],
        released_workspace_ids=list(result.released_workspace_ids),
        archived_by=result.archived_by,
        archived_at=result.archived_at,
    )


def archive_result_to_response(result: GetArchiveResultResult) -> ArchiveResultResponse:
    plan = result.plan
    archive_result = result.archive_result
    return ArchiveResultResponse(
        archive_result_id=archive_result.result_id,
        archive_plan_id=plan.plan_id,
        baseline_node_id=archive_result.baseline_node_id,
        baseline_commit_id=plan.selected_repository_commit_id,
        baseline_head_version=plan.old_baseline_head_version + 1,
        selected_submission_id=plan.selected_submission_id,
        selected_repository_commit_id=result.selected_repository_commit_id,
        candidate_set_digest=plan.candidate_set_digest,
        confirmation_refs=[
            ArchiveAuditReferenceResponse(
                subject_digest=ref.subject_digest,
                sequence=ref.sequence,
            )
            for ref in plan.confirmation_refs
        ],
        anomaly_resolution_refs=[
            ArchiveAuditReferenceResponse(
                subject_digest=ref.subject_digest,
                sequence=ref.sequence,
            )
            for ref in plan.anomaly_resolution_refs
        ],
        dispositions=[
            _disposition_record_to_response(item) for item in archive_result.dispositions
        ],
        archived_by=plan.accepted_by,
        archived_at=archive_result.archived_at,
    )


def validate_utf8_id_field(value: object, *, field_name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a string")
    return validate_utf8_id(value, field_name=field_name)


def _assert_unique_audit_refs(
    refs: list[ArchiveAuditReferenceRequest],
    *,
    field_name: str,
) -> None:
    seen: set[tuple[str, int]] = set()
    for ref in refs:
        key = (ref.subject_digest, int(ref.sequence))
        if key in seen:
            raise ValueError(f"duplicate reference in {field_name}")
        seen.add(key)


def validate_confirmation_reason_field(
    action: ArchiveConfirmationActionLiteral,
    reason: object,
) -> str | None:
    parsed_action = ArchiveConfirmationAction(action)
    if reason is None:
        try:
            return validate_archive_confirmation_reason(parsed_action, None)
        except ArchiveRequestValidation as exc:
            raise _validation_value_error(exc) from exc
    if type(reason) is not str:
        raise ValueError("reason must be a string")
    try:
        return validate_archive_confirmation_reason(parsed_action, reason)
    except ArchiveRequestValidation as exc:
        raise _validation_value_error(exc) from exc


def _anomaly_to_response(anomaly: ArchivePreviewAnomaly) -> ArchivePreviewAnomalyResponse:
    return ArchivePreviewAnomalyResponse(
        issue_code=anomaly.issue_code,
        sibling_submission_id=anomaly.sibling_submission_id,
        sibling_candidate_digest=anomaly.sibling_candidate_digest,
        subject_digest=anomaly.subject_digest,
    )


def _disposition_to_response(
    item: ArchivePreviewDisposition,
) -> ArchivePreviewDispositionResponse:
    return ArchivePreviewDispositionResponse(
        submission_id=item.submission_id,
        disposition=item.disposition,
    )


def _disposition_record_to_response(disposition: ArchiveDisposition) -> ArchiveDispositionResponse:
    return ArchiveDispositionResponse(
        submission_id=disposition.submission_id,
        disposition=disposition.disposition.value,
    )


def _audit_event_to_response(
    event: ArchiveConfirmationEvent | ArchiveAnomalyResolutionEvent,
) -> ArchiveAuditEventResponse:
    if isinstance(event, ArchiveConfirmationEvent):
        return ArchiveAuditEventResponse(
            event_id=event.event_id,
            subject_kind=event.subject_kind.value,
            subject_digest=event.subject_digest,
            sequence=event.sequence,
            action=event.action.value,
            reason=event.reason,
            actor_id=event.actor_id,
            occurred_at=event.occurred_at,
        )
    return ArchiveAuditEventResponse(
        event_id=event.event_id,
        subject_kind=event.subject_kind.value,
        subject_digest=event.subject_digest,
        sequence=event.sequence,
        action=event.action.value,
        reason=event.reason,
        actor_id=event.actor_id,
        occurred_at=event.occurred_at,
        issue_code=event.issue_code,
        sibling_submission_id=event.sibling_submission_id,
        sibling_candidate_digest=event.sibling_candidate_digest,
    )


def parse_archive_subject_kind(raw_value: str) -> ArchiveSubjectKind:
    try:
        return ArchiveSubjectKind(raw_value)
    except ValueError:
        raise ValueError("subject_kind is not supported") from None
