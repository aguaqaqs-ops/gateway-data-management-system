"""Preview operation routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, acquire_new_work, get_workspace_http
from gateway_backend.http.errors import ApiError
from gateway_backend.http.orchestration.preview_acceptance import (
    accept_preview_operation,
    build_start_preview_command,
)
from gateway_backend.http.schemas.preview import OperationAcceptedResponse, StartPreviewRequest

router = APIRouter(tags=["preview"])


@router.post(
    "/v1/workspaces/{workspace_id}/preview-operations",
    response_model=OperationAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        409: {
            "description": "IDEMPOTENCY_CONFLICT, WORKSPACE_VERSION_CONFLICT, PREVIEW_BINDING_CONFLICT"
        },
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        429: {"description": "ADMISSION_LIMIT_REACHED"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def start_preview_route(
    workspace_id: str,
    body: StartPreviewRequest,
    request: Request,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> OperationAcceptedResponse:
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
    command = build_start_preview_command(
        context=context,
        workspace_id=workspace_id,
        expected_workspace_version=body.expected_workspace_version,
        upload_revision_id=body.upload_revision_id,
        generation=body.generation,
        expected_baseline_node_id=body.expected_baseline_node_id,
        expected_baseline_head_version=body.expected_baseline_head_version,
        idempotency_key=resolved_key,
        request_fingerprint_seed=options,
    )
    with acquire_new_work(deps.admission_gate):
        result = accept_preview_operation(
            command=command,
            scope_resolution=deps.scope_resolution,
            workspace_repository=deps.workspace_repository,
            unit_of_work_factory=deps.unit_of_work_factory,
            job_registry=deps.job_registry,
            artifact_store=deps.artifact_store,
            now=deps.now(),
            options=options,
        )
    return result.response
