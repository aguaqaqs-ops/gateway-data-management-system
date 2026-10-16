"""Archive HTTP routes."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, Response, status

from gateway_backend.application.archive.queries import ARCHIVE_AUDIT_EVENTS_MAX_LIMIT
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, acquire_new_work, get_workspace_http
from gateway_backend.http.orchestration.archive import (
    append_confirmation_operation,
    append_resolution_operation,
    build_append_confirmation_command,
    build_append_resolution_command,
    build_start_archive_command,
    get_archive_result_operation,
    list_audit_events_operation,
    list_candidates_operation,
    parse_archive_idempotency_key,
    preview_plan_operation,
    start_archive_operation,
)
from gateway_backend.http.schemas.archive import (
    AppendArchiveAnomalyResolutionRequest,
    AppendArchiveConfirmationRequest,
    ArchiveAuditAppendResponse,
    ArchiveAuditEventsResponse,
    ArchiveCandidatesResponse,
    ArchiveDigest,
    ArchiveResultResponse,
    ArchiveStartedResponse,
    ArchiveSubjectKindLiteral,
    PreviewArchivePlanRequest,
    PreviewArchivePlanResponse,
    StartArchiveRequest,
)

router = APIRouter(tags=["archives"])


@router.get(
    "/v1/archive-candidates",
    response_model=ArchiveCandidatesResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        409: {"description": "ARCHIVE_SCOPE_LIMIT_EXCEEDED"},
        503: {"description": "ARCHIVE_INTEGRITY_FAILURE, DEPENDENCY_UNAVAILABLE"},
    },
)
def list_archive_candidates_route(
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> ArchiveCandidatesResponse:
    return list_candidates_operation(
        context=context,
        unit_of_work_factory=deps.archive_unit_of_work_factory,
    )


@router.post(
    "/v1/archive-plan-preview",
    response_model=PreviewArchivePlanResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        409: {
            "description": "CANDIDATE_BINDING_CONFLICT, ARCHIVE_SCOPE_LIMIT_EXCEEDED"
        },
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        413: {"description": "REQUEST_TOO_LARGE"},
        503: {"description": "ARCHIVE_INTEGRITY_FAILURE, DEPENDENCY_UNAVAILABLE"},
    },
)
def preview_archive_plan_route(
    body: PreviewArchivePlanRequest,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> PreviewArchivePlanResponse:
    return preview_plan_operation(
        context=context,
        body=body,
        unit_of_work_factory=deps.archive_unit_of_work_factory,
    )


@router.post(
    "/v1/archive-confirmations",
    response_model=ArchiveAuditAppendResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Idempotent replay", "model": ArchiveAuditAppendResponse},
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        409: {
            "description": "IDEMPOTENCY_CONFLICT, BASELINE_VERSION_CONFLICT, "
            "CANDIDATE_SET_CONFLICT, CANDIDATE_BINDING_CONFLICT, "
            "ARCHIVE_AUDIT_VERSION_CONFLICT"
        },
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        413: {"description": "REQUEST_TOO_LARGE"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "ARCHIVE_INTEGRITY_FAILURE, DEPENDENCY_UNAVAILABLE"},
    },
)
def append_archive_confirmation_route(
    body: AppendArchiveConfirmationRequest,
    request: Request,
    response: Response,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> ArchiveAuditAppendResponse:
    idempotency_key = parse_archive_idempotency_key(request.headers.get("Idempotency-Key"))
    command = build_append_confirmation_command(
        context=context,
        body=body,
        idempotency_key=idempotency_key,
    )
    with acquire_new_work(deps.admission_gate):
        result = append_confirmation_operation(
            command=command,
            unit_of_work_factory=deps.archive_unit_of_work_factory,
            now=deps.now(),
        )
    if result.replay:
        response.status_code = status.HTTP_200_OK
    return cast(ArchiveAuditAppendResponse, result.response)


@router.post(
    "/v1/archive-anomaly-resolutions",
    response_model=ArchiveAuditAppendResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Idempotent replay", "model": ArchiveAuditAppendResponse},
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        409: {
            "description": "IDEMPOTENCY_CONFLICT, BASELINE_VERSION_CONFLICT, "
            "CANDIDATE_SET_CONFLICT, CANDIDATE_BINDING_CONFLICT, "
            "ARCHIVE_AUDIT_VERSION_CONFLICT"
        },
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        413: {"description": "REQUEST_TOO_LARGE"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "ARCHIVE_INTEGRITY_FAILURE, DEPENDENCY_UNAVAILABLE"},
    },
)
def append_archive_anomaly_resolution_route(
    body: AppendArchiveAnomalyResolutionRequest,
    request: Request,
    response: Response,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> ArchiveAuditAppendResponse:
    idempotency_key = parse_archive_idempotency_key(request.headers.get("Idempotency-Key"))
    command = build_append_resolution_command(
        context=context,
        body=body,
        idempotency_key=idempotency_key,
    )
    with acquire_new_work(deps.admission_gate):
        result = append_resolution_operation(
            command=command,
            unit_of_work_factory=deps.archive_unit_of_work_factory,
            now=deps.now(),
        )
    if result.replay:
        response.status_code = status.HTTP_200_OK
    return cast(ArchiveAuditAppendResponse, result.response)


@router.get(
    "/v1/archive-audit-events",
    response_model=ArchiveAuditEventsResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        503: {"description": "DEPENDENCY_UNAVAILABLE"},
    },
)
def list_archive_audit_events_route(
    subject_kind: Annotated[ArchiveSubjectKindLiteral, Query()],
    subject_digest: Annotated[ArchiveDigest, Query()],
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=ARCHIVE_AUDIT_EVENTS_MAX_LIMIT)] = 100,
) -> ArchiveAuditEventsResponse:
    return list_audit_events_operation(
        context=context,
        subject_kind=subject_kind,
        subject_digest=subject_digest,
        after_sequence=after_sequence,
        limit=limit,
        unit_of_work_factory=deps.archive_unit_of_work_factory,
    )


@router.post(
    "/v1/archives",
    response_model=ArchiveStartedResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Idempotent replay", "model": ArchiveStartedResponse},
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        409: {
            "description": "IDEMPOTENCY_CONFLICT, BASELINE_VERSION_CONFLICT, "
            "CANDIDATE_SET_CONFLICT, CANDIDATE_BINDING_CONFLICT, "
            "ARCHIVE_CONFIRMATION_REQUIRED, ARCHIVE_ANOMALY_UNRESOLVED, "
            "ARCHIVE_AUDIT_VERSION_CONFLICT, ACTIVE_SUBMIT_ATTEMPT, "
            "ARCHIVE_SCOPE_LIMIT_EXCEEDED, WORKSPACE_OCCUPANCY_CONFLICT"
        },
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        413: {"description": "REQUEST_TOO_LARGE"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "ARCHIVE_INTEGRITY_FAILURE, DEPENDENCY_UNAVAILABLE"},
    },
)
def start_archive_route(
    body: StartArchiveRequest,
    request: Request,
    response: Response,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> ArchiveStartedResponse:
    idempotency_key = parse_archive_idempotency_key(request.headers.get("Idempotency-Key"))
    command = build_start_archive_command(
        context=context,
        body=body,
        idempotency_key=idempotency_key,
    )
    with acquire_new_work(deps.admission_gate):
        result = start_archive_operation(
            command=command,
            unit_of_work_factory=deps.archive_unit_of_work_factory,
            now=deps.now(),
        )
    if result.replay:
        response.status_code = status.HTTP_200_OK
    return cast(ArchiveStartedResponse, result.response)


@router.get(
    "/v1/archives/{archive_result_id}",
    response_model=ArchiveResultResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        503: {"description": "DEPENDENCY_UNAVAILABLE"},
    },
)
def get_archive_result_route(
    archive_result_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> ArchiveResultResponse:
    return get_archive_result_operation(
        context=context,
        archive_result_id=archive_result_id,
        unit_of_work_factory=deps.archive_unit_of_work_factory,
    )
