"""Submit attempt routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, acquire_new_work, get_workspace_http
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.operation_scope import read_submit_attempt
from gateway_backend.http.orchestration.submit_acceptance import (
    accept_submit_operation,
    build_accept_submit_command,
)
from gateway_backend.http.schemas.submit import (
    AcceptSubmitRequest,
    SubmitAcceptedResponse,
    SubmitAttemptResponse,
    submit_attempt_to_response,
)

router = APIRouter(tags=["submit"])


@router.post(
    "/v1/workspaces/{workspace_id}/submit-attempts",
    response_model=SubmitAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        409: {
            "description": "IDEMPOTENCY_CONFLICT, WORKSPACE_VERSION_CONFLICT, PREVIEW_BINDING_CONFLICT, "
            "PREVIEW_DERIVED_STALE, BASELINE_VERSION_CONFLICT, SUBMIT_OCCUPANCY_CONFLICT, NO_CANONICAL_CHANGE"
        },
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "ARTIFACT_UNAVAILABLE, DEPENDENCY_UNAVAILABLE, SERVICE_NOT_READY"},
    },
)
def accept_submit_route(
    workspace_id: str,
    body: AcceptSubmitRequest,
    request: Request,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> SubmitAcceptedResponse:
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key is None or not idempotency_key.strip():
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="Idempotency-Key header is required",
            status_code=422,
        )
    resolved_key = idempotency_key.strip()
    if len(resolved_key) > 255:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="Idempotency-Key must be 1..255 characters",
            status_code=422,
        )
    options = body.options.model_dump()
    command = build_accept_submit_command(
        context=context,
        workspace_id=workspace_id,
        expected_workspace_version=body.expected_workspace_version,
        upload_revision_id=body.upload_revision_id,
        preview_result_id=body.preview_result_id,
        generation=body.generation,
        expected_baseline_node_id=body.expected_baseline_node_id,
        expected_baseline_head_version=body.expected_baseline_head_version,
        idempotency_key=resolved_key,
        options=options,
    )
    with acquire_new_work(deps.admission_gate):
        result = accept_submit_operation(
            command=command,
            scope_resolution=deps.scope_resolution,
            workspace_repository=deps.workspace_repository,
            unit_of_work_factory=deps.unit_of_work_factory,
            job_registry=deps.job_registry,
            artifact_store=deps.artifact_store,
            artifact_ref_lookup=deps.artifact_ref_lookup,
            baseline_digest=deps.baseline_canonical_digest,
            main_resolve=deps.main_resolve,
            now=deps.now(),
        )
    return result.response


@router.get(
    "/v1/workspaces/{workspace_id}/submit-attempts/{submit_attempt_id}",
    response_model=SubmitAttemptResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def get_submit_attempt_route(
    workspace_id: str,
    submit_attempt_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> SubmitAttemptResponse:
    attempt = read_submit_attempt(
        context=context,
        workspace_id=workspace_id,
        submit_attempt_id=submit_attempt_id,
        workspace_repository=deps.workspace_repository,
        submission_reader=deps.submission_reader,
        scope_resolution=deps.scope_resolution,
    )
    return submit_attempt_to_response(attempt)
