"""Preview step 3: atomic preview business result publication."""

from __future__ import annotations

import dataclasses

from datetime import (
    UTC,
    datetime,
)
from gateway_backend.application.checkpoints import (
    definition_matches_checkpoint,
    load_checkpoint_envelope,
    load_ready_closure,
)
from gateway_backend.application.comparison_audit import verify_structure_audit_bindings
from gateway_backend.application.job_steps import terminal_step
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.workspace.ports import (
    WorkspaceControlTransaction as PreviewControlTransaction,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.workspace.models import (
    PreviewResult,
    Workspace,
)
from gateway_backend.operations.contracts import (
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
)
from gateway_backend.statistics.metrics import bind_scope
from typing import cast

from gateway_backend.application.preview_jobs.assemble import _build_preview_result
from gateway_backend.application.preview_jobs.checkpoint import (
    _JOB_STATE_BUNDLE_ARTIFACT,
    _JOB_STATE_BUNDLE_DIGEST,
    _JOB_STATE_READY_CLOSURE,
    _JOB_STATE_READY_CLOSURE_REF,
    _active_preview_transaction,
    _assemble_state_from_checkpoint,
    _assert_preview_bundle_binding,
    _load_step,
    _payload_source_refs,
    _preview_ready_ref,
    _release_preview_step_protection,
    _unique_refs,
)
from gateway_backend.application.preview_jobs.failures import (
    _make_cancelled_terminal_builder,
    _publish_preview_ruleset_mismatch_if_needed,
    _with_resource_failure_terminal,
)
from gateway_backend.application.preview_jobs.payload import (
    PREVIEW_STEP_ASSEMBLE,
    PreviewJobError,
    PreviewJobPayload,
    PreviewRuntimeDependencies,
    _load_preview_payload,
    _successor_step_id,
    preview_assemble_job_definition,
)


def build_publish_preview_handler(deps: PreviewRuntimeDependencies) -> ClaimedExecutor:
    assemble_definition = preview_assemble_job_definition()

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        payload = _load_preview_payload(operation, deps.artifact_store)
        bind_scope(payload.repository_id, rules_digest=payload.comparison_ruleset_digest)
        if _publish_preview_ruleset_mismatch_if_needed(
            payload=payload,
            operation=operation,
            step=step,
            lease_session=lease_session,
            control=control,
        ):
            return ExecutorAcknowledgment.PUBLISHED
        assemble_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=_successor_step_id(operation.operation_id, PREVIEW_STEP_ASSEMBLE),
        )
        if assemble_step.checkpoint_ref is None:
            raise PreviewJobError("assemble checkpoint is missing")
        assemble_envelope = load_checkpoint_envelope(
            deps.artifact_store,
            assemble_step.checkpoint_ref,
        )
        if not definition_matches_checkpoint(assemble_definition, assemble_envelope):
            raise CheckpointDecodeError(
                "assemble checkpoint does not match the preview JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        _assemble_state_ref, assemble_state = _assemble_state_from_checkpoint(
            assemble_envelope.job_state,
            deps.artifact_store,
        )
        ready_closure_id = assemble_envelope.job_state.get(_JOB_STATE_READY_CLOSURE)
        ready_closure_ref_raw = assemble_envelope.job_state.get(_JOB_STATE_READY_CLOSURE_REF)
        bundle_artifact_id = assemble_envelope.job_state.get(_JOB_STATE_BUNDLE_ARTIFACT)
        bundle_digest = assemble_envelope.job_state.get(_JOB_STATE_BUNDLE_DIGEST)
        if (
            type(ready_closure_id) is not str
            or not ready_closure_id
            or type(ready_closure_ref_raw) is not dict
            or type(bundle_artifact_id) is not str
            or not bundle_artifact_id
            or type(bundle_digest) is not str
            or not bundle_digest
        ):
            raise CheckpointDecodeError(
                "assemble checkpoint is incomplete for preview publication",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )

        ready_closure_ref = _preview_ready_ref(assemble_envelope.job_state)
        ready_closure = load_ready_closure(deps.artifact_store, ready_closure_ref)
        _assert_preview_bundle_binding(assemble_envelope.job_state, ready_closure.artifact_refs())
        verify_structure_audit_bindings(
            deps.artifact_store,
            assemble_state.get("structure_audit_bindings"),
            ready_closure.artifact_refs(),
            assemble_state.get("pair_ids"),
        )

        preview_result = _build_preview_result(
            payload=payload,
            operation=operation,
            assemble_state=assemble_state,
            bundle_artifact_id=bundle_artifact_id,
            bundle_digest=bundle_digest,
            ready_closure_artifact_id=ready_closure_id,
            transaction_now=datetime.now(UTC),
        )

        _atomic_publish_preview(
            lease_session=lease_session,
            deps=deps,
            payload=payload,
            preview_result=preview_result,
            ready_closure_ref=ready_closure_ref,
            control=control,
        )
        return ExecutorAcknowledgment.PUBLISHED

    return _with_resource_failure_terminal(cast(ClaimedExecutor, execute))


def _atomic_publish_preview(
    *,
    lease_session: LeaseSession,
    deps: PreviewRuntimeDependencies,
    payload: PreviewJobPayload,
    preview_result: PreviewResult,
    ready_closure_ref: ArtifactRef,
    control: ExecutionControl,
) -> None:
    pending_result = preview_result

    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_preview_transaction.get()
        if transaction is None:
            raise PreviewJobError("preview publication transaction is not bound")
        workspace = transaction.workspace.get_workspace(payload.workspace_id)
        if workspace is None:
            raise PreviewJobError("workspace is missing at preview publication")
        baseline_head = deps.baseline_head_read.get_current_head(payload.repository_id)
        if _publication_drift(payload, workspace, baseline_head):
            _release_preview_step_protection(
                transaction,
                operation_id=operation.operation_id,
                clear_operation_owner=True,
            )
            completed_step = terminal_step(step, transaction_now, status=StepStatus.SUCCEEDED)
            terminal_operation = dataclasses.replace(
                operation,
                status=OperationStatus.SUPERSEDED,
                updated_at=transaction_now,
                completed_at=transaction_now,
                optimistic_version=operation.optimistic_version + 1,
            )
            return completed_step, terminal_operation

        _persist_preview_business_state(
            transaction,
            workspace=workspace,
            payload=payload,
            preview_result=pending_result,
            ready_closure_ref=ready_closure_ref,
            closure_output_refs=closure_output_refs,
            transaction_now=transaction_now,
        )
        completed_step = terminal_step(step, transaction_now, status=StepStatus.SUCCEEDED)
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.SUCCEEDED,
            ready_closure_ref=ready_closure_ref,
            updated_at=transaction_now,
            completed_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return completed_step, terminal_operation

    lease_session.refresh_control()
    if control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
        return
    closure_output_refs = load_ready_closure(deps.artifact_store, ready_closure_ref).artifact_refs()
    lease_session.publish_operation(builder)


def _persist_preview_business_state(
    unit_of_work: PreviewControlTransaction,
    *,
    workspace: Workspace,
    payload: PreviewJobPayload,
    preview_result: PreviewResult,
    ready_closure_ref: ArtifactRef,
    closure_output_refs: tuple[ArtifactRef, ...],
    transaction_now: datetime,
) -> None:
    unit_of_work.workspace.save_preview_result(preview_result)
    updated_workspace = dataclasses.replace(
        workspace,
        current_preview_result_id=preview_result.preview_result_id,
        optimistic_version=workspace.optimistic_version + 1,
        updated_at=transaction_now,
    )
    unit_of_work.workspace.save_workspace(
        updated_workspace, expected_version=workspace.optimistic_version
    )
    unit_of_work.set_artifact_protection(
        _unique_refs((ready_closure_ref, *closure_output_refs, *_payload_source_refs(payload))),
        owner_kind="current-preview",
        owner_id=workspace.workspace_id,
        intent="current-preview",
    )
    _release_preview_step_protection(
        unit_of_work,
        operation_id=preview_result.operation_id,
        clear_operation_owner=False,
    )


def _publication_drift(
    payload: PreviewJobPayload,
    workspace: Workspace,
    baseline_head: object,
) -> bool:
    from gateway_backend.domain.workspace.models import BaselineHead

    if workspace.generation != payload.generation:
        return True
    if workspace.current_upload_revision_id != payload.upload_revision_id:
        return True
    if type(baseline_head) is not BaselineHead:
        return True
    if baseline_head.business_baseline_node_id != payload.business_baseline_node_id:
        return True
    if baseline_head.business_baseline_commit_id != payload.business_baseline_commit_id:
        return True
    if baseline_head.baseline_head_version != payload.baseline_head_version:
        return True
    return False


__all__ = [
    "build_publish_preview_handler",
]
