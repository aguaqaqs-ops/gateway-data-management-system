"""History bounded read queries."""

from __future__ import annotations

from gateway_backend.application.history.contracts import (
    PERMISSION_READ_PROJECT_HISTORY,
    HistoryTreeProjection,
)
from gateway_backend.application.history.errors import HistoryIntegrityFailure
from gateway_backend.application.history.projection import project_history_tree
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeResolutionError
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort
from gateway_backend.application.history.ports import HistoryReadPort


def get_project_history(
    *,
    context: IdentityContext,
    scope_resolution: ScopeResolutionPort,
    history_reader: HistoryReadPort,
    limit: int | None = None,
    cursor: str | None = None,
) -> HistoryTreeProjection:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    try:
        resolved = scope_resolution.resolve(context)
    except ScopeResolutionError as exc:
        raise PermissionDenied(PERMISSION_READ_PROJECT_HISTORY) from exc
    try:
        facts = history_reader.load_facts(
            repository_id=resolved.repository_id,
            gateway_device_external_key=context.gateway_device_external_key,
            business_project_id=context.business_project_id,
        )
    except ValueError as exc:
        raise HistoryIntegrityFailure("history fact rows are inconsistent") from exc
    return project_history_tree(facts=facts, limit=limit, cursor=cursor)
