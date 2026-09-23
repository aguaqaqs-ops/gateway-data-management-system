"""History bounded read queries."""

from __future__ import annotations

from gateway_backend.application.history.contracts import (
    DEFAULT_HISTORY_PAGE_LIMIT,
    MAX_HISTORY_PAGE_LIMIT,
    PERMISSION_READ_PROJECT_HISTORY,
    HistoryTreeProjection,
)
from gateway_backend.application.history.errors import HistoryIntegrityFailure, HistoryRequestValidation
from gateway_backend.application.history.ports import HistoryControlUnitOfWorkFactory, HistorySnapshotLoaderPort
from gateway_backend.application.history.projection import _decode_cursor, project_history_page
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeResolutionError
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission


def get_project_history(
    *,
    context: IdentityContext,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    snapshot_loader: HistorySnapshotLoaderPort,
    limit: int | None = None,
    cursor: str | None = None,
) -> HistoryTreeProjection:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    resolved_limit = DEFAULT_HISTORY_PAGE_LIMIT if limit is None else limit
    if type(resolved_limit) is not int or resolved_limit < 1 or resolved_limit > MAX_HISTORY_PAGE_LIMIT:
        raise HistoryRequestValidation("limit must be an integer between 1 and 500")
    cursor_order_key = _decode_cursor(cursor)
    try:
        with unit_of_work_factory(read_only=True) as unit_of_work:
            fresh_scope = unit_of_work.resolve_provisioned_scope(
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id,
            )
            page = snapshot_loader.load_page_in_transaction(
                unit_of_work,
                repository_id=fresh_scope.repository_id,
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id,
                limit=resolved_limit,
                after_order_key=cursor_order_key,
            )
    except ScopeResolutionError as exc:
        raise PermissionDenied(PERMISSION_READ_PROJECT_HISTORY) from exc
    except ValueError as exc:
        raise HistoryIntegrityFailure("history fact rows are inconsistent") from exc
    return project_history_page(page=page)
