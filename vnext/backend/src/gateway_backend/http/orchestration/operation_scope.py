"""Operation scope re-authorization for HTTP reads."""

from __future__ import annotations

from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND
from gateway_backend.domain.submission.models import SubmitAttempt, Submission
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeForbidden, ScopeResolutionError
from gateway_backend.domain.workspace.models import IdentityContext, ResolvedScope, Workspace
from gateway_backend.domain.workspace.policies import assert_exact_scope, assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.http.dependencies import SubmissionReaderPort
from gateway_backend.http.errors import ApiError
from gateway_backend.operations.contracts import OperationRecord

PERMISSION_WORKSPACE_READ = "workspace_read"

_MAPPING_NOT_FOUND_REASONS = frozenset(
    {
        "provisioned mapping is missing",
        "provisioned mapping is disabled",
    }
)


def assert_workspace_read_permission(context: IdentityContext) -> None:
    assert_permission(context, PERMISSION_WORKSPACE_READ)


def workspace_id_from_operation(operation: OperationRecord) -> str | None:
    for ref in operation.business_refs:
        if ref.kind == "workspace":
            return ref.value
    return None


def submit_attempt_id_from_operation(operation: OperationRecord) -> str | None:
    for ref in operation.business_refs:
        if ref.kind == "submit_attempt":
            return ref.value
    return None


def _map_scope_resolution_error(exc: ScopeResolutionError) -> ApiError:
    if exc.reason in _MAPPING_NOT_FOUND_REASONS:
        return ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    return ApiError(
        code="DEPENDENCY_UNAVAILABLE",
        message=str(exc),
        status_code=503,
        details={"reason": exc.reason},
    )


def _authorize_workspace_scope(
    *,
    context: IdentityContext,
    workspace_id: str,
    workspace_repository: WorkspaceRepository,
    scope_resolution: ScopeResolutionPort,
    frozen_repository_id: str | None = None,
) -> Workspace:
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
    _authorize_current_mapping(
        context=context,
        workspace=workspace,
        scope_resolution=scope_resolution,
        frozen_repository_id=frozen_repository_id,
    )
    return workspace


def _authorize_current_mapping(
    *,
    context: IdentityContext,
    workspace: Workspace,
    scope_resolution: ScopeResolutionPort,
    frozen_repository_id: str | None = None,
) -> ResolvedScope:
    try:
        resolved = scope_resolution.resolve(context)
    except ScopeResolutionError as exc:
        raise _map_scope_resolution_error(exc) from exc
    if resolved.repository_id != workspace.repository_id:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    if frozen_repository_id is not None and frozen_repository_id != resolved.repository_id:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    return resolved


def authorize_operation_read(
    *,
    context: IdentityContext,
    operation: OperationRecord,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
    scope_resolution: ScopeResolutionPort,
    permission_checked: bool = False,
) -> Workspace:
    if not permission_checked:
        assert_workspace_read_permission(context)
    workspace_id = workspace_id_from_operation(operation)
    if workspace_id is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    frozen_repository_id: str | None = None
    if operation.job_kind == SUBMIT_JOB_KIND:
        submit_attempt_id = submit_attempt_id_from_operation(operation)
        if submit_attempt_id is None:
            raise ApiError(
                code="RESOURCE_NOT_FOUND",
                message="resource not found",
                status_code=404,
            )
        attempt = submission_reader.get_submit_attempt(submit_attempt_id)
        if attempt is None:
            raise ApiError(
                code="RESOURCE_NOT_FOUND",
                message="resource not found",
                status_code=404,
            )
        if attempt.workspace_id != workspace_id:
            raise ApiError(
                code="RESOURCE_NOT_FOUND",
                message="resource not found",
                status_code=404,
            )
        frozen_repository_id = attempt.repository_id
    return _authorize_workspace_scope(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
        scope_resolution=scope_resolution,
        frozen_repository_id=frozen_repository_id,
    )


def read_submit_attempt(
    *,
    context: IdentityContext,
    workspace_id: str,
    submit_attempt_id: str,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
    scope_resolution: ScopeResolutionPort,
) -> SubmitAttempt:
    assert_workspace_read_permission(context)
    attempt = submission_reader.get_submit_attempt(submit_attempt_id)
    if attempt is None or attempt.workspace_id != workspace_id:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    _authorize_workspace_scope(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
        scope_resolution=scope_resolution,
        frozen_repository_id=attempt.repository_id,
    )
    return attempt


def read_submission(
    *,
    context: IdentityContext,
    workspace_id: str,
    submission_id: str,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
    scope_resolution: ScopeResolutionPort,
) -> Submission:
    assert_workspace_read_permission(context)
    submission = submission_reader.get_submission(submission_id)
    if submission is None or submission.workspace_id != workspace_id:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    _authorize_workspace_scope(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
        scope_resolution=scope_resolution,
        frozen_repository_id=submission.repository_id,
    )
    return submission
