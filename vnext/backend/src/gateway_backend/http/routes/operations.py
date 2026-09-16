"""Operation read routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import WorkspaceHttpDependencies, get_workspace_http
from gateway_backend.http.mappers import operation_to_response
from gateway_backend.http.orchestration.operation_scope import (
    assert_workspace_read_permission,
    authorize_operation_read,
)
from gateway_backend.http.schemas.operation import OperationResponse

router = APIRouter(tags=["operations"])


@router.get(
    "/v1/operations/{operation_id}",
    response_model=OperationResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        404: {"description": "RESOURCE_NOT_FOUND"},
        503: {"description": "SERVICE_NOT_READY"},
    },
)
def get_operation_route(
    operation_id: str,
    deps: Annotated[WorkspaceHttpDependencies, Depends(get_workspace_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> OperationResponse:
    assert_workspace_read_permission(context)
    operation = deps.operation_reader.get_operation(operation_id)
    authorize_operation_read(
        context=context,
        operation=operation,
        workspace_repository=deps.workspace_repository,
        submission_reader=deps.submission_reader,
        scope_resolution=deps.scope_resolution,
        permission_checked=True,
    )
    return operation_to_response(operation)
