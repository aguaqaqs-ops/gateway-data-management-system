"""History compare step 3: atomic history comparison result publication."""

from __future__ import annotations

import dataclasses

from datetime import (
    datetime,
    timedelta,
)
from gateway_backend.application.checkpoints import (
    definition_matches_checkpoint,
    load_checkpoint_envelope,
    load_ready_closure,
)
from gateway_backend.application.comparison_audit import verify_structure_audit_bindings
from gateway_backend.application.job_steps import terminal_step
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.artifacts.store import ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
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

from gateway_backend.application.history.compare_jobs.checkpoint import (
    _active_history_compare_transaction,
    _assert_history_bundle_binding,
    _load_step,
    _release_history_compare_checkpoint_protection,
    _unique_refs,
    history_compare_assemble_state_from_checkpoint,
    history_compare_ready_ref,
)
from gateway_backend.application.history.compare_jobs.failures import (
    _assert_runtime_ruleset,
    _make_cancelled_terminal_builder,
    _publish_ruleset_mismatch_failure,
    _with_resource_failure_terminal,
)
from gateway_backend.application.history.compare_jobs.payload import (
    HISTORY_COMPARE_STEP_ASSEMBLE,
    HistoryCompareJobError,
    HistoryCompareRulesetVersionMismatch,
    HistoryCompareRuntimeDependencies,
    _load_history_compare_payload,
    history_compare_assemble_job_definition,
    history_compare_step_id,
)


def build_publish_result_handler(deps: HistoryCompareRuntimeDependencies) -> ClaimedExecutor:
    assemble_definition = history_compare_assemble_job_definition()

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

        payload = _load_history_compare_payload(operation, deps.artifact_store)
        bind_scope(payload.repository_id, rules_digest=payload.comparison_ruleset_digest)
        try:
            _assert_runtime_ruleset(payload)
        except HistoryCompareRulesetVersionMismatch as exc:
            _publish_ruleset_mismatch_failure(
                lease_session=lease_session,
                operation=operation,
                step=step,
                message=str(exc),
                control=control,
            )
            return ExecutorAcknowledgment.PUBLISHED

        assemble_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=history_compare_step_id(operation.operation_id, HISTORY_COMPARE_STEP_ASSEMBLE),
        )
        if assemble_step.checkpoint_ref is None:
            raise HistoryCompareJobError("assemble checkpoint is missing")
        assemble_checkpoint_ref: ArtifactRef = assemble_step.checkpoint_ref
        assemble_envelope = load_checkpoint_envelope(
            deps.artifact_store,
            assemble_checkpoint_ref,
        )
        if not definition_matches_checkpoint(assemble_definition, assemble_envelope):
            raise CheckpointDecodeError(
                "assemble checkpoint does not match the history compare JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        ready_closure_ref = history_compare_ready_ref(assemble_envelope.job_state)
        try:
            deps.artifact_store.locate(ready_closure_ref)
        except ManifestVerificationError as exc:
            raise CheckpointDecodeError(str(exc), code="CHECKPOINT_REF_UNREADABLE") from exc

        def builder(
            current_operation: OperationRecord,
            current_step: StepRecord,
            transaction_now: datetime,
        ) -> tuple[StepRecord, OperationRecord]:
            transaction = _active_history_compare_transaction.get()
            if transaction is None:
                raise HistoryCompareJobError("history compare publication transaction is not bound")
            closure_output_refs = load_ready_closure(
                deps.artifact_store,
                ready_closure_ref,
            ).artifact_refs()
            _assert_history_bundle_binding(assemble_envelope.job_state, closure_output_refs)
            assemble_state_ref, assemble_state = history_compare_assemble_state_from_checkpoint(
                assemble_envelope.job_state, deps.artifact_store
            )
            verify_structure_audit_bindings(
                deps.artifact_store,
                assemble_state.get("structure_audit_bindings"),
                closure_output_refs,
                assemble_state.get("pair_ids"),
            )
            acceptance = transaction.history_compare.get_acceptance_by_operation_id(
                current_operation.operation_id
            )
            if acceptance is None:
                raise HistoryCompareJobError("history compare acceptance is missing")
            expires_at = transaction_now + timedelta(seconds=acceptance.result_retention_seconds)
            completed_step = terminal_step(
                current_step, transaction_now, status=StepStatus.SUCCEEDED
            )
            terminal_operation = dataclasses.replace(
                current_operation,
                status=OperationStatus.SUCCEEDED,
                ready_closure_ref=ready_closure_ref,
                updated_at=transaction_now,
                completed_at=transaction_now,
                optimistic_version=current_operation.optimistic_version + 1,
            )
            transaction.set_artifact_protection(
                _unique_refs(
                    (
                        ready_closure_ref,
                        assemble_checkpoint_ref,
                        assemble_state_ref,
                        *closure_output_refs,
                    )
                ),
                owner_kind="history-compare-operation",
                owner_id=current_operation.operation_id,
                intent="history-compare-result",
                expires_at=expires_at,
            )
            _release_history_compare_checkpoint_protection(
                transaction, operation_id=current_operation.operation_id
            )
            return completed_step, terminal_operation

        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED
        lease_session.publish_operation(builder)
        return ExecutorAcknowledgment.PUBLISHED

    return _with_resource_failure_terminal(cast(ClaimedExecutor, execute))


__all__ = [
    "build_publish_result_handler",
]
