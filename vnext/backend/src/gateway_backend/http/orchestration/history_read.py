"""History read orchestration for HTTP routes."""

from __future__ import annotations

from gateway_backend.application.history.errors import HistoryIntegrityFailure, HistoryRequestValidation
from gateway_backend.application.history.queries import get_project_history
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.http.dependencies import HistoryHttpDependencies
from gateway_backend.http.errors import ApiError
from gateway_backend.http.schemas.history import HistoryListResponse, history_projection_to_response


def list_history_operation(
    *,
    context: IdentityContext,
    deps: HistoryHttpDependencies,
    limit: int | None,
    cursor: str | None,
) -> HistoryListResponse:
    try:
        projection = get_project_history(
            context=context,
            unit_of_work_factory=deps.unit_of_work_factory,
            snapshot_loader=deps.snapshot_loader,
            limit=limit,
            cursor=cursor,
        )
    except HistoryRequestValidation as exc:
        raise ApiError(
            code="REQUEST_VALIDATION_FAILED",
            message=str(exc),
            status_code=422,
        ) from exc
    except HistoryIntegrityFailure as exc:
        raise ApiError(
            code="HISTORY_INTEGRITY_FAILURE",
            message=str(exc),
            status_code=503,
        ) from exc
    return history_projection_to_response(projection)
