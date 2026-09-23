"""History HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.auth import require_identity
from gateway_backend.http.dependencies import HistoryHttpDependencies, get_history_http
from gateway_backend.http.orchestration.history_read import list_history_operation
from gateway_backend.http.schemas.history import HistoryListResponse

router = APIRouter(tags=["history"])


@router.get(
    "/v1/history",
    response_model=HistoryListResponse,
    responses={
        401: {"description": "AUTHENTICATION_REQUIRED"},
        403: {"description": "SCOPE_FORBIDDEN"},
        422: {"description": "REQUEST_VALIDATION_FAILED"},
        503: {"description": "HISTORY_INTEGRITY_FAILURE, DEPENDENCY_UNAVAILABLE"},
    },
)
def list_history_route(
    deps: Annotated[HistoryHttpDependencies, Depends(get_history_http)],
    context: Annotated[IdentityContext, Depends(require_identity)],
    limit: Annotated[int | None, Query(ge=1, le=500)] = None,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
) -> HistoryListResponse:
    return list_history_operation(
        context=context,
        deps=deps,
        limit=limit,
        cursor=cursor,
    )
