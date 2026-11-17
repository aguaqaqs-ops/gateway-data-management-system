"""Authorized saved telemetry query use cases."""

from __future__ import annotations

from gateway_backend.application.history.ports import HistoryControlUnitOfWorkFactory
from gateway_backend.application.operation_reads import (
    OperationReaderPort,
    assert_workspace_read_permission,
    read_authorized_operation,
)
from gateway_backend.application.submission.ports import SubmissionReaderPort
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import IdentityContext, ResolvedScope
from gateway_backend.domain.workspace.policies import assert_permission
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.operations.contracts import OperationRecord
from gateway_backend.statistics.queries import (
    GroupRead,
    ReadPage,
    ReadRequest,
    ResourceRead,
    ResourceRequest,
    StatisticsReader,
)

PERMISSION_STATISTICS_READ_GROUP = "statistics_read_group"


def assert_statistics_group_permission(context: IdentityContext) -> None:
    """Authorize group telemetry only; grants no device or recovery access."""
    assert_permission(context, PERMISSION_STATISTICS_READ_GROUP)


def authorize_repository_statistics(
    *,
    context: IdentityContext,
    repository_id: str,
    scope_resolution: ScopeResolutionPort,
) -> ResolvedScope:
    assert_workspace_read_permission(context)
    resolved = scope_resolution.resolve(context)
    if resolved.repository_id != repository_id:
        raise ScopeForbidden
    return resolved


def read_repository_statistics(
    *,
    context: IdentityContext,
    repository_id: str,
    scope_resolution: ScopeResolutionPort,
    reader: StatisticsReader,
    request: ReadRequest,
) -> ReadPage:
    authorize_repository_statistics(
        context=context,
        repository_id=repository_id,
        scope_resolution=scope_resolution,
    )
    return reader.read(request)


def authorize_operation_statistics(
    *,
    context: IdentityContext,
    operation_id: str,
    operation_reader: OperationReaderPort,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
    scope_resolution: ScopeResolutionPort,
    history_unit_of_work_factory: HistoryControlUnitOfWorkFactory,
) -> OperationRecord:
    return read_authorized_operation(
        context=context,
        operation_id=operation_id,
        operation_reader=operation_reader,
        workspace_repository=workspace_repository,
        submission_reader=submission_reader,
        scope_resolution=scope_resolution,
        history_unit_of_work_factory=history_unit_of_work_factory,
    )


def read_operation_executions(
    *,
    context: IdentityContext,
    operation_id: str,
    operation_reader: OperationReaderPort,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
    scope_resolution: ScopeResolutionPort,
    history_unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    reader: StatisticsReader,
    request: ReadRequest,
) -> ReadPage:
    authorize_operation_statistics(
        context=context,
        operation_id=operation_id,
        operation_reader=operation_reader,
        workspace_repository=workspace_repository,
        submission_reader=submission_reader,
        scope_resolution=scope_resolution,
        history_unit_of_work_factory=history_unit_of_work_factory,
    )
    return reader.read(request)


def read_operation_resources(
    *,
    context: IdentityContext,
    operation_id: str,
    operation_reader: OperationReaderPort,
    workspace_repository: WorkspaceRepository,
    submission_reader: SubmissionReaderPort,
    scope_resolution: ScopeResolutionPort,
    history_unit_of_work_factory: HistoryControlUnitOfWorkFactory,
    reader: StatisticsReader,
    request: ResourceRequest,
) -> ResourceRead:
    authorize_operation_statistics(
        context=context,
        operation_id=operation_id,
        operation_reader=operation_reader,
        workspace_repository=workspace_repository,
        submission_reader=submission_reader,
        scope_resolution=scope_resolution,
        history_unit_of_work_factory=history_unit_of_work_factory,
    )
    return reader.resources(request)


def read_group_statistics(
    *,
    context: IdentityContext,
    reader: StatisticsReader,
    start_us: int,
    end_us: int,
) -> GroupRead:
    assert_statistics_group_permission(context)
    return reader.group(start_us, end_us)


def read_group_resources(
    *,
    context: IdentityContext,
    reader: StatisticsReader,
    request: ResourceRequest,
) -> ResourceRead:
    assert_statistics_group_permission(context)
    return reader.resources(request)
