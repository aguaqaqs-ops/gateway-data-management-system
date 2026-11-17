"""Operation, submit attempt, and submission read authorization use cases."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gateway_backend.application.history.contracts import (
    HISTORY_COMPARE_JOB_KIND,
    PERMISSION_READ_PROJECT_HISTORY,
    HistoryCompareAcceptanceRecord,
)
from gateway_backend.application.history.ports import HistoryControlUnitOfWorkFactory
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND
from gateway_backend.application.submission.ports import SubmissionReaderPort
from gateway_backend.domain.submission.models import SubmitAttempt, Submission
from gateway_backend.domain.workspace.errors import PermissionDenied, ScopeForbidden, ScopeNotFound
from gateway_backend.domain.workspace.models import IdentityContext, ResolvedScope, Workspace
from gateway_backend.domain.workspace.policies import assert_exact_scope, assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.operations.store import RecordNotFound

PERMISSION_WORKSPACE_READ = "workspace_read"


@runtime_checkable
class OperationReaderPort(Protocol):
    def get_operation(self, operation_id: str) -> OperationRecord:
        """Return an operation or raise RecordNotFound."""

    def get_step(self, step_id: str) -> StepRecord:
        """Return a step or raise RecordNotFound."""


def assert_workspace_read_permission(context: IdentityContext) -> None:
    assert_permission(context, PERMISSION_WORKSPACE_READ)


def history_compare_acceptance_id_from_operation(operation: OperationRecord) -> str | None:
    for ref in operation.business_refs:
        if ref.kind == "history_compare":
            return ref.value
    return None


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
        raise ScopeForbidden
    assert_exact_scope(workspace, context)
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
    resolved = scope_resolution.resolve(context)
    if resolved.repository_id != workspace.repository_id:
        raise ScopeForbidden
    if frozen_repository_id is not None and frozen_repository_id != resolved.repository_id:
        raise ScopeForbidden
    return resolved


def authorize_history_compare_operation_read(
    *,
    context: IdentityContext,
    operation: OperationRecord,
    unit_of_work_factory: HistoryControlUnitOfWorkFactory,
) -> HistoryCompareAcceptanceRecord:
    assert_permission(context, PERMISSION_READ_PROJECT_HISTORY)
    if operation.job_kind != HISTORY_COMPARE_JOB_KIND:
        raise ScopeForbidden
    acceptance_id = history_compare_acceptance_id_from_operation(operation)
    if acceptance_id is None:
        raise ScopeForbidden
    with unit_of_work_factory(read_only=True) as unit_of_work:
        acceptance = unit_of_work.history_compare.get_acceptance_by_operation_id(
            operation.operation_id
        )
        if acceptance is None or acceptance.acceptance_id != acceptance_id:
            raise ScopeForbidden
        if (
            acceptance.gateway_device_external_key != context.gateway_device_external_key
            or acceptance.business_project_id != context.business_project_id
        ):
            raise ScopeForbidden
        try:
            resolved = unit_of_work.resolve_provisioned_scope(
                gateway_device_external_key=context.gateway_device_external_key,
                business_project_id=context.business_project_id,
            )
        except ScopeNotFound as exc:
            raise PermissionDenied(PERMISSION_READ_PROJECT_HISTORY) from exc
        if resolved.repository_id != acceptance.repository_id:
            raise ScopeForbidden
    return acceptance


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
        raise ScopeForbidden
    workspace = _authorize_workspace_scope(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
        scope_resolution=scope_resolution,
    )
    if operation.job_kind == SUBMIT_JOB_KIND:
        submit_attempt_id = submit_attempt_id_from_operation(operation)
        if submit_attempt_id is None:
            raise ScopeForbidden
        attempt = submission_reader.get_submit_attempt(
            submit_attempt_id, workspace_id=workspace_id, repository_id=workspace.repository_id
        )
        if attempt is None:
            raise ScopeForbidden
    return workspace


def read_authorized_operation(
    *,
    context: IdentityContext,
    operation_id: str,
    operation_reader: OperationReaderPort,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
    scope_resolution: ScopeResolutionPort,
    history_unit_of_work_factory: HistoryControlUnitOfWorkFactory,
) -> OperationRecord:
    try:
        operation = operation_reader.get_operation(operation_id)
    except RecordNotFound:
        assert_workspace_read_permission(context)
        raise ScopeForbidden from None
    if operation.job_kind == HISTORY_COMPARE_JOB_KIND:
        authorize_history_compare_operation_read(
            context=context,
            operation=operation,
            unit_of_work_factory=history_unit_of_work_factory,
        )
        return operation
    assert_workspace_read_permission(context)
    authorize_operation_read(
        context=context,
        operation=operation,
        workspace_repository=workspace_repository,
        submission_reader=submission_reader,
        scope_resolution=scope_resolution,
        permission_checked=True,
    )
    return operation


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
    workspace = _authorize_workspace_scope(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
        scope_resolution=scope_resolution,
    )
    attempt = submission_reader.get_submit_attempt(
        submit_attempt_id, workspace_id=workspace_id, repository_id=workspace.repository_id
    )
    if attempt is None:
        raise ScopeForbidden
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
    workspace = _authorize_workspace_scope(
        context=context,
        workspace_id=workspace_id,
        workspace_repository=workspace_repository,
        scope_resolution=scope_resolution,
    )
    submission = submission_reader.get_submission(
        submission_id, workspace_id=workspace_id, repository_id=workspace.repository_id
    )
    if submission is None:
        raise ScopeForbidden
    return submission
