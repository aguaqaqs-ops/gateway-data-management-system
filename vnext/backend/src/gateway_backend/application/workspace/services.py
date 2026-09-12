"""Workspace create/get and upload acceptance application services."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from gateway_backend.application.workspace.contracts import (
    AcceptUploadCommand,
    AcceptUploadResult,
    CreateOrGetWorkspaceResult,
    compute_upload_request_fingerprint,
)
from gateway_backend.application.workspace.errors import IdempotencyConflict
from gateway_backend.domain.workspace.errors import ScopeForbidden
from gateway_backend.domain.workspace.models import (
    IdentityContext,
    PreviewAcceptanceRecord,
    UploadRevision,
    Workspace,
    WorkspaceState,
)
from gateway_backend.domain.workspace.policies import (
    assert_exact_scope,
    assert_open_uniqueness,
    assert_permission,
    assert_workspace_open,
    assert_workspace_version_cas,
    scope_from_context,
    validate_upload_role_closure,
)
from gateway_backend.domain.workspace.ports import ScopeResolutionPort, WorkspaceRepository
from gateway_backend.operations import (
    OperationStatus,
    StepStatus,
    WritePrecondition,
)
from gateway_backend.operations.store import OperationStore, RecordNotFound

PERMISSION_WORKSPACE_READ = "workspace_read"
PERMISSION_UPLOAD_SUBMIT = "upload_submit_workspace"


class ArtifactProtectionIntentPort(Protocol):
    def clear_artifact_protection(self, *, owner_kind: str, owner_id: str) -> int:
        """Delete protection rows for one owner."""


def create_or_get_workspace(
    *,
    context: IdentityContext,
    scope_resolution: ScopeResolutionPort,
    repository: WorkspaceRepository,
    created_at: datetime,
) -> CreateOrGetWorkspaceResult:
    assert_permission(context, PERMISSION_WORKSPACE_READ)
    resolved = scope_resolution.resolve(context)
    scope = scope_from_context(context)
    existing = repository.find_open_by_scope(scope)
    if existing is not None:
        assert_exact_scope(existing, context)
        return CreateOrGetWorkspaceResult(workspace=existing, replay=True)

    workspace_id = f"ws-{uuid4()}"
    workspace = Workspace(
        workspace_id=workspace_id,
        owner_actor_id=scope.owner_actor_id,
        gateway_device_external_key=scope.gateway_device_external_key,
        business_project_id=scope.business_project_id,
        repository_id=resolved.repository_id,
        state=WorkspaceState.OPEN,
        generation=0,
        optimistic_version=0,
        current_upload_revision_id=None,
        current_preview_result_id=None,
        created_at=created_at,
        updated_at=created_at,
    )
    assert_open_uniqueness(existing, scope=scope, workspace_id=workspace_id)
    saved = repository.save_workspace(workspace, expected_version=0)
    return CreateOrGetWorkspaceResult(workspace=saved, replay=False)


def accept_upload(
    *,
    command: AcceptUploadCommand,
    scope_resolution: ScopeResolutionPort,
    repository: WorkspaceRepository,
    operations: OperationStore | None = None,
    protection: ArtifactProtectionIntentPort | None = None,
) -> AcceptUploadResult:
    assert_permission(command.context, PERMISSION_UPLOAD_SUBMIT)
    scope_resolution.resolve(command.context)
    workspace = repository.get_workspace(command.workspace_id)
    if workspace is None:
        raise ScopeForbidden
    assert_exact_scope(workspace, command.context)
    assert_workspace_open(workspace)
    validate_upload_role_closure(command.input_completeness, command.source_artifacts)

    request_fingerprint = compute_upload_request_fingerprint(
        scope_owner_actor_id=workspace.owner_actor_id,
        scope_gateway_device_external_key=workspace.gateway_device_external_key,
        scope_business_project_id=workspace.business_project_id,
        expected_workspace_version=command.expected_workspace_version,
        input_completeness=command.input_completeness,
        source_artifacts=command.source_artifacts,
    )
    existing = repository.find_upload_idempotency(
        command.workspace_id,
        command.idempotency_key,
    )
    if existing is not None:
        if existing.request_fingerprint != request_fingerprint:
            raise IdempotencyConflict(idempotency_key=command.idempotency_key)
        current = repository.get_workspace(command.workspace_id)
        if current is None:
            raise ScopeForbidden
        return AcceptUploadResult(workspace=current, revision=existing, replay=True)

    assert_workspace_version_cas(workspace, command.expected_workspace_version)
    next_generation = workspace.generation + 1
    revision = UploadRevision(
        upload_revision_id=f"ur-{uuid4()}",
        workspace_id=workspace.workspace_id,
        generation=next_generation,
        input_completeness=command.input_completeness,
        source_artifacts=dict(command.source_artifacts),
        idempotency_key=command.idempotency_key,
        request_fingerprint=request_fingerprint,
        created_by=command.context.actor_id,
        created_at=command.now,
    )
    updated_workspace = replace(
        workspace,
        generation=next_generation,
        optimistic_version=workspace.optimistic_version + 1,
        current_upload_revision_id=revision.upload_revision_id,
        current_preview_result_id=None,
        updated_at=command.now,
    )
    saved_workspace = repository.save_workspace(
        updated_workspace,
        expected_version=command.expected_workspace_version,
    )
    repository.save_upload_revision(revision)
    if operations is not None:
        _supersede_or_cancel_prior_previews(
            repository=repository,
            operations=operations,
            protection=protection,
            workspace_id=workspace.workspace_id,
            next_generation=next_generation,
            now=operations.transaction_now,
        )
    return AcceptUploadResult(workspace=saved_workspace, revision=revision, replay=False)


def _supersede_or_cancel_prior_previews(
    *,
    repository: WorkspaceRepository,
    operations: OperationStore,
    protection: ArtifactProtectionIntentPort | None,
    workspace_id: str,
    next_generation: int,
    now: datetime,
) -> None:
    if protection is not None:
        protection.clear_artifact_protection(
            owner_kind="current-preview",
            owner_id=workspace_id,
        )
    for acceptance in repository.list_preview_acceptances(workspace_id):
        if acceptance.generation >= next_generation:
            continue
        try:
            operation = operations.get_operation(acceptance.operation_id)
        except RecordNotFound:
            continue
        steps, _cursor = operations.list_steps(acceptance.operation_id)
        live_steps = tuple(
            step
            for step in steps
            if step.status in {StepStatus.PENDING, StepStatus.RETRY_WAIT, StepStatus.RUNNING}
        )
        if operation.status is OperationStatus.QUEUED:
            for step in live_steps:
                cancelled = replace(
                    step,
                    status=StepStatus.CANCELLED,
                    worker_id=None,
                    lease_token=None,
                    lease_expires_at=None,
                    completed_at=now,
                    updated_at=now,
                    optimistic_version=step.optimistic_version + 1,
                )
                operations.compare_and_set_step(
                    cancelled,
                    WritePrecondition(
                        expected_optimistic_version=step.optimistic_version,
                        worker_id=None,
                        lease_token=None,
                    ),
                )
            superseded = replace(
                operation,
                status=OperationStatus.SUPERSEDED,
                completed_at=now,
                updated_at=now,
                optimistic_version=operation.optimistic_version + 1,
            )
            operations.compare_and_set_operation(
                superseded,
                WritePrecondition(
                    expected_optimistic_version=operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )
            _clear_preview_owner(protection, acceptance)
            continue
        if operation.status is OperationStatus.RUNNING and live_steps:
            live_step = live_steps[0]
            operations.compare_and_set_operation(
                replace(
                    operation,
                    cancel_requested=True,
                    updated_at=now,
                    optimistic_version=operation.optimistic_version + 1,
                ),
                WritePrecondition(
                    expected_optimistic_version=operation.optimistic_version,
                    worker_id=None,
                    lease_token=None,
                ),
            )
            operations.compare_and_set_step(
                replace(
                    live_step,
                    cancel_requested=True,
                    updated_at=now,
                    optimistic_version=live_step.optimistic_version + 1,
                ),
                WritePrecondition(
                    expected_optimistic_version=live_step.optimistic_version,
                    worker_id=live_step.worker_id,
                    lease_token=live_step.lease_token,
                ),
                require_live_lease=live_step.status is StepStatus.RUNNING,
            )
            continue
        if operation.status.is_final_terminal():
            _clear_preview_owner(protection, acceptance)


def _clear_preview_owner(
    protection: ArtifactProtectionIntentPort | None,
    acceptance: PreviewAcceptanceRecord,
) -> None:
    if protection is None:
        return
    protection.clear_artifact_protection(
        owner_kind="preview-operation",
        owner_id=acceptance.operation_id,
    )
