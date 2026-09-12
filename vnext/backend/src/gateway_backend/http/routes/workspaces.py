"""Workspace routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from gateway_backend.application.workspace.services import create_or_get_workspace
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, get_workspace_http
from gateway_backend.http.errors import ApiError
from gateway_backend.http.mappers import workspace_to_response
from gateway_backend.http.schemas.workspace import CreateWorkspaceRequest, WorkspaceResponse

router = APIRouter(tags=["workspaces"])


@router.post(
    "/v1/workspaces",
    response_model=WorkspaceResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def create_or_get_workspace_route(
    body: CreateWorkspaceRequest,
    request: Request,
    response: Response,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> WorkspaceResponse:
    if request.headers.get("Idempotency-Key"):
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message="CreateOrGetWorkspace does not accept Idempotency-Key",
            status_code=422,
        )
    if not deps.admission_gate.allows_new_work():
        raise ApiError(
            code="ADMISSION_LIMIT_REACHED",
            message="gateway admission is closed for new work",
            status_code=429,
        )
    result = create_or_get_workspace(
        context=context,
        scope_resolution=deps.scope_resolution,
        repository=deps.workspace_repository,
        created_at=deps.now(),
    )
    response.status_code = status.HTTP_200_OK if result.replay else status.HTTP_201_CREATED
    return workspace_to_response(result.workspace)
