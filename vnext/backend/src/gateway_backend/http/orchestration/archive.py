"""Archive orchestration for HTTP routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from gateway_backend.application.archive.audit import (
    AppendArchiveAnomalyResolutionCommand,
    AppendArchiveConfirmationCommand,
    append_archive_anomaly_resolution,
    append_archive_confirmation,
)
from gateway_backend.application.archive.errors import ArchiveRequestValidation
from gateway_backend.application.archive.ports import ArchiveControlUnitOfWorkFactory
from gateway_backend.application.archive.queries import (
    get_archive_candidates,
    get_archive_result,
    list_archive_audit_events,
    preview_archive_plan,
)
from gateway_backend.application.archive.start import StartArchiveCommand, start_archive
from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionAction,
    ArchiveConfirmationAction,
)
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.archive import (
    AppendArchiveAnomalyResolutionRequest,
    AppendArchiveConfirmationRequest,
    ArchiveAuditAppendResponse,
    ArchiveAuditEventsResponse,
    ArchiveCandidatesResponse,
    ArchiveResultResponse,
    ArchiveStartedResponse,
    PreviewArchivePlanRequest,
    PreviewArchivePlanResponse,
    StartArchiveRequest,
    audit_append_to_response,
    audit_events_to_response,
    archive_candidates_to_response,
    archive_result_to_response,
    audit_reference_from_request,
    parse_archive_subject_kind,
    preview_plan_to_response,
    selected_ref_from_request,
    start_archive_to_response,
    validate_utf8_id_field,
)


@dataclass(frozen=True, slots=True)
class ArchiveMutationOperationResult:
    response: ArchiveAuditAppendResponse | ArchiveStartedResponse
    replay: bool


def _validation_failed() -> ApiError:
    return ApiError(
        code="REQUEST_VALIDATION_FAILED",
        message="request validation failed",
        status_code=422,
    )


def parse_archive_idempotency_key(raw_header: str | None) -> str:
    if raw_header is None:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="Idempotency-Key header is required",
            status_code=422,
        )
    try:
        return validate_utf8_id_field(raw_header, field_name="idempotency_key")
    except ValueError:
        raise _validation_failed() from None


def list_candidates_operation(
    *,
    context: IdentityContext,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
) -> ArchiveCandidatesResponse:
    result = get_archive_candidates(
        context=context,
        unit_of_work_factory=unit_of_work_factory,
    )
    return archive_candidates_to_response(result)


def preview_plan_operation(
    *,
    context: IdentityContext,
    body: PreviewArchivePlanRequest,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
) -> PreviewArchivePlanResponse:
    selected_ref = None
    if body.selected is not None:
        selected_ref = selected_ref_from_request(body.selected)
    result = preview_archive_plan(
        context=context,
        selected_ref=selected_ref,
        unit_of_work_factory=unit_of_work_factory,
    )
    return preview_plan_to_response(result)


def build_append_confirmation_command(
    *,
    context: IdentityContext,
    body: AppendArchiveConfirmationRequest,
    idempotency_key: str,
) -> AppendArchiveConfirmationCommand:
    return AppendArchiveConfirmationCommand(
        context=context,
        idempotency_key=idempotency_key,
        expected_baseline_node_id=body.expected_baseline_node_id,
        expected_baseline_head_version=body.expected_baseline_head_version,
        selected=selected_ref_from_request(body.selected),
        candidate_set_digest=body.candidate_set_digest,
        subject_digest=body.subject_digest,
        expected_sequence=body.expected_sequence,
        action=ArchiveConfirmationAction(body.action),
        reason=body.reason,
    )


def append_confirmation_operation(
    *,
    command: AppendArchiveConfirmationCommand,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
    now: datetime,
) -> ArchiveMutationOperationResult:
    result = append_archive_confirmation(
        command=command,
        unit_of_work_factory=unit_of_work_factory,
        now=now,
    )
    return ArchiveMutationOperationResult(
        response=audit_append_to_response(result),
        replay=result.replay,
    )


def build_append_resolution_command(
    *,
    context: IdentityContext,
    body: AppendArchiveAnomalyResolutionRequest,
    idempotency_key: str,
) -> AppendArchiveAnomalyResolutionCommand:
    return AppendArchiveAnomalyResolutionCommand(
        context=context,
        idempotency_key=idempotency_key,
        expected_baseline_node_id=body.expected_baseline_node_id,
        expected_baseline_head_version=body.expected_baseline_head_version,
        selected=selected_ref_from_request(body.selected),
        candidate_set_digest=body.candidate_set_digest,
        subject_digest=body.subject_digest,
        expected_sequence=body.expected_sequence,
        action=ArchiveAnomalyResolutionAction(body.action),
        reason=body.reason,
        issue_code=body.issue_code,
        sibling_submission_id=body.sibling_submission_id,
        sibling_candidate_digest=body.sibling_candidate_digest,
    )


def append_resolution_operation(
    *,
    command: AppendArchiveAnomalyResolutionCommand,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
    now: datetime,
) -> ArchiveMutationOperationResult:
    result = append_archive_anomaly_resolution(
        command=command,
        unit_of_work_factory=unit_of_work_factory,
        now=now,
    )
    return ArchiveMutationOperationResult(
        response=audit_append_to_response(result),
        replay=result.replay,
    )


def build_start_archive_command(
    *,
    context: IdentityContext,
    body: StartArchiveRequest,
    idempotency_key: str,
) -> StartArchiveCommand:
    return StartArchiveCommand(
        context=context,
        idempotency_key=idempotency_key,
        expected_baseline_node_id=body.expected_baseline_node_id,
        expected_baseline_head_version=body.expected_baseline_head_version,
        candidate_set_digest=body.candidate_set_digest,
        selected_ref=selected_ref_from_request(body.selected),
        confirmation_refs=tuple(
            audit_reference_from_request(ref) for ref in body.confirmation_refs
        ),
        anomaly_resolution_refs=tuple(
            audit_reference_from_request(ref) for ref in body.anomaly_resolution_refs
        ),
    )


def start_archive_operation(
    *,
    command: StartArchiveCommand,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
    now: datetime,
) -> ArchiveMutationOperationResult:
    result = start_archive(
        command=command,
        unit_of_work_factory=unit_of_work_factory,
        now=now,
    )
    return ArchiveMutationOperationResult(
        response=start_archive_to_response(result),
        replay=result.replay,
    )


def list_audit_events_operation(
    *,
    context: IdentityContext,
    subject_kind: str,
    subject_digest: str,
    after_sequence: int,
    limit: int,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
) -> ArchiveAuditEventsResponse:
    try:
        parsed_subject_kind = parse_archive_subject_kind(subject_kind)
    except ValueError:
        raise _validation_failed() from None
    try:
        result = list_archive_audit_events(
            context=context,
            subject_kind=parsed_subject_kind,
            subject_digest=subject_digest,
            after_sequence=after_sequence,
            limit=limit,
            unit_of_work_factory=unit_of_work_factory,
        )
    except ArchiveRequestValidation:
        raise _validation_failed() from None
    return audit_events_to_response(result)


def get_archive_result_operation(
    *,
    context: IdentityContext,
    archive_result_id: str,
    unit_of_work_factory: ArchiveControlUnitOfWorkFactory,
) -> ArchiveResultResponse:
    result = get_archive_result(
        context=context,
        archive_result_id=archive_result_id,
        unit_of_work_factory=unit_of_work_factory,
    )
    return archive_result_to_response(result)
