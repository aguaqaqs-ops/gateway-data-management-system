"""Operation read routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from gateway_backend.application.operation_reads import read_authorized_operation
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import (
    HistoryHttpDependencies,
    WorkspaceHttpDependencies,
    get_history_http,
    get_workspace_http,
)
from gateway_backend.http.mappers import operation_to_response
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
    history_deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
) -> OperationResponse:
    operation = read_authorized_operation(
        context=context,
        operation_id=operation_id,
        operation_reader=deps.operation_reader,
        workspace_repository=deps.workspace_repository,
        submission_reader=deps.submission_reader,
        scope_resolution=deps.scope_resolution,
        history_unit_of_work_factory=history_deps.unit_of_work_factory,
    )
    return operation_to_response(operation)
