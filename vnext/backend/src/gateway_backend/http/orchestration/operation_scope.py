"""Operation scope re-authorization for HTTP reads."""

from __future__ import annotations

from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeForbidden
from gateway_backend.domain.workspace.models import IdentityContext, Workspace
from gateway_backend.domain.workspace.policies import assert_exact_scope, assert_permission
from gateway_backend.domain.workspace.ports import WorkspaceRepository
from gateway_backend.http.errors import ApiError
from gateway_backend.operations.contracts import OperationRecord


PERMISSION_WORKSPACE_READ = "workspace_read"


def workspace_id_from_operation(operation: OperationRecord) -> str | None:
    for ref in operation.business_refs:
        if ref.kind == "workspace":
            return ref.value
    return None


def authorize_operation_read(
    *,
    context: IdentityContext,
    operation: OperationRecord,
    workspace_repository: WorkspaceRepository,
) -> Workspace:
    assert_permission(context, PERMISSION_WORKSPACE_READ)
    workspace_id = workspace_id_from_operation(operation)
    if workspace_id is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    workspace = workspace_repository.get_workspace(workspace_id)
    if workspace is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    try:
        assert_exact_scope(workspace, context)
    except PermissionDenied:
        raise
    except ScopeForbidden:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        ) from None
    return workspace
