"""Operation scope re-authorization for HTTP reads."""

from __future__ import annotations

from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND
from gateway_backend.domain.submission.models import SubmitAttempt, Submission
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeForbidden
from gateway_backend.domain.workspace.models import IdentityContext, Workspace
from gateway_backend.domain.workspace.policies import assert_exact_scope, assert_permission
from gateway_backend.domain.workspace.ports import WorkspaceRepository
from gateway_backend.http.dependencies import SubmissionReaderPort
from gateway_backend.http.errors import ApiError
from gateway_backend.operations.contracts import OperationRecord

PERMISSION_WORKSPACE_READ = "workspace_read"


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


def _authorize_workspace_read(
    *,
    context: IdentityContext,
    workspace_id: str,
    workspace_repository: WorkspaceRepository,
) -> Workspace:
    assert_permission(context, PERMISSION_WORKSPACE_READ)
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


def authorize_operation_read(
    *,
    context: IdentityContext,
    operation: OperationRecord,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
) -> Workspace:
    workspace_id = workspace_id_from_operation(operation)
    if workspace_id is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    workspace = _authorize_workspace_read(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
    )
    if operation.job_kind == SUBMIT_JOB_KIND:
        submit_attempt_id = submit_attempt_id_from_operation(operation)
        if submit_attempt_id is None:
            raise ApiError(
                code="RESOURCE_NOT_FOUND",
                message="resource not found",
                status_code=404,
            )
        attempt = submission_reader.get_submit_attempt(submit_attempt_id)
        if attempt is None or attempt.workspace_id != workspace.workspace_id:
            raise ApiError(
                code="RESOURCE_NOT_FOUND",
                message="resource not found",
                status_code=404,
            )
    return workspace


def read_submit_attempt(
    *,
    context: IdentityContext,
    workspace_id: str,
    submit_attempt_id: str,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
) -> SubmitAttempt:
    _authorize_workspace_read(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
    )
    attempt = submission_reader.get_submit_attempt(submit_attempt_id)
    if attempt is None or attempt.workspace_id != workspace_id:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    return attempt


def read_submission(
    *,
    context: IdentityContext,
    workspace_id: str,
    submission_id: str,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
) -> Submission:
    _authorize_workspace_read(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
    )
    submission = submission_reader.get_submission(submission_id)
    if submission is None or submission.workspace_id != workspace_id:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="resource not found",
            status_code=404,
        )
    return submission
