"""Submit step 3: await and finalize repository import operation."""

from __future__ import annotations

import dataclasses

from collections.abc import Callable
from dataclasses import dataclass
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from gateway_backend.application.checkpoints import (
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    load_ready_closure,
    prepare_step_checkpoint,
)
from gateway_backend.application.job_steps import (
    checkpoint_generation,
    pinned_checkpoint_builder,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.recovery import (
    DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
)
from gateway_backend.application.submission.abort import (
    ALLOWED_ABORT_CODES,
    validate_abort_proof,
)
from gateway_backend.application.submission.abort_transaction import (
    AbortSubmitTransactionRequest,
    abort_submit_in_control_transaction,
)
from gateway_backend.application.submission.contracts import (
    MatchingAbortProof,
    MatchingFinalizeFacts,
    PrepareImportCheckpoint,
    RepositoryImportOperation,
    RepositoryImportOperationStatus as RepositoryOperationStatus,
    RepositoryOperationTerminalStatus,
)
from gateway_backend.application.submission.errors import (
    FinalizeBindingMismatch,
    RepositoryWriteTimeoutError,
    RepositoryWriteTransportError,
)
from gateway_backend.application.submission.finalize_transaction import (
    FinalizeSubmitTransactionRequest,
    finalize_submit_transaction,
)
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
    submit_successor_step_id as _successor_step_id,
)
from gateway_backend.application.submission.ports import RepositoryAbortEvidencePort
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    SubmitAttempt,
    SubmitAttemptState,
)
from gateway_backend.operations.contracts import (
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.recovery import DIAGNOSTIC_RETRY_SCHEDULED
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
)
from gateway_backend.statistics.metrics import bind_scope

from gateway_backend.application.submit_jobs.checkpoint import (
    _AwaitCheckpointState,
    _JOB_STATE_PREPARE_CHECKPOINT_REF,
    _active_submit_transaction,
    _await_checkpoint_from_job_state,
    _job_state_for_await_reconcile,
    _job_state_for_await_terminal,
    _load_step,
    _load_terminal_repository_evidence,
    _persist_terminal_repository_evidence,
    _prepare_checkpoint_from_job_state,
    _submit_state_from_job_state,
)
from gateway_backend.application.submit_jobs.failures import (
    _make_cancelled_terminal_builder,
    _make_manual_recovery_terminal_builder,
    _publish_counted_reconcile_pending,
    _publish_manual_recovery,
    _publish_wait_upper_bound_exceeded,
)
from gateway_backend.application.submit_jobs.payload import (
    SUBMIT_IMPORT_POLL_DEADLINE_SECONDS,
    SUBMIT_IMPORT_WAIT_UPPER_BOUND_SECONDS,
    SubmitJobError,
    SubmitJobPayload,
    SubmitRuntimeDependencies,
    _assert_payload_matches_attempt,
    _definition_for_step,
    _load_submit_payload,
    _require_artifact_ref_dict,
    _submit_now,
    _target_ref_from_repository,
    _unknown_type_policy_from_repository,
    _verification_policy_from_repository,
)

def build_await_import_result_handler(deps: SubmitRuntimeDependencies) -> ClaimedExecutor:
    submit_definition = _definition_for_step(SUBMIT_STEP_SUBMIT)
    await_definition = _definition_for_step(SUBMIT_STEP_AWAIT)

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        payload = _load_submit_payload(operation, deps.artifact_store)
        bind_scope(payload.repository_id, payload.submit_attempt_id)
        with deps.control_transaction_factory() as unit_of_work:
            fresh_attempt = unit_of_work.submission.get_submit_attempt(payload.submit_attempt_id)
        if fresh_attempt is None:
            raise SubmitJobError("submit attempt is missing")
        _assert_payload_matches_attempt(payload, fresh_attempt)

        lease_session.refresh_control()
        if step.checkpoint_ref is None and control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        attempt = fresh_attempt
        if attempt.state is not SubmitAttemptState.EFFECT_PENDING:
            raise SubmitJobError("await_import_result requires EFFECT_PENDING attempt")

        submit_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_SUBMIT),
        )
        if submit_step.checkpoint_ref is None:
            raise SubmitJobError("submit_import checkpoint is missing")
        submit_envelope = load_checkpoint_envelope(deps.artifact_store, submit_step.checkpoint_ref)
        if not definition_matches_checkpoint(submit_definition, submit_envelope):
            raise CheckpointDecodeError(
                "submit checkpoint does not match the submit_import JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        submit_state = _submit_state_from_job_state(
            deps.artifact_store,
            submit_envelope.job_state,
            repository_write=deps.repository_write,
            expected_payload=payload,
            prepare_checkpoint_ref=artifact_ref_from_dict(
                _require_artifact_ref_dict(
                    submit_envelope.job_state.get(_JOB_STATE_PREPARE_CHECKPOINT_REF),
                    label="prepare_checkpoint_ref",
                )
            ),
            checkpoint_ref=submit_step.checkpoint_ref,
        )
        if not submit_state.request_sent or submit_state.repository_operation_id is None:
            raise SubmitJobError(
                "submit_import checkpoint is missing durable repository operation identity"
            )

        prepare_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_PREPARE),
        )
        if prepare_step.checkpoint_ref is None:
            raise SubmitJobError("prepare_import checkpoint is missing")
        prepare_envelope = load_checkpoint_envelope(
            deps.artifact_store, prepare_step.checkpoint_ref
        )
        prepare_checkpoint = _prepare_checkpoint_from_job_state(
            prepare_envelope.job_state,
            expected_attempt_id=payload.submit_attempt_id,
        )

        await_checkpoint_ref = step.checkpoint_ref
        await_checkpoint_state: _AwaitCheckpointState | None = None
        if await_checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, await_checkpoint_ref)
            if not definition_matches_checkpoint(await_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the await_import_result JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            await_checkpoint_state = _await_checkpoint_from_job_state(
                envelope.job_state,
                expected_submit_checkpoint_ref=submit_step.checkpoint_ref,
                expected_repository_operation_id=submit_state.repository_operation_id,
            )
        else:
            envelope = envelope_for_step(
                key=await_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=checkpoint_generation(step),
                job_state=_job_state_for_await_reconcile(
                    submit_checkpoint_ref=submit_step.checkpoint_ref,
                    repository_operation_id=submit_state.repository_operation_id,
                ),
            )
            await_checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
            lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=await_checkpoint_ref,
                    extra_refs=(),
                    owner_kind="submit-checkpoint",
                    active_transaction=_active_submit_transaction.get,
                    transaction_missing=lambda: SubmitJobError(
                        "submit checkpoint transaction is not bound"
                    ),
                    deduplicate_refs=False,
                    intent="await-import-reconcile-checkpoint",
                )
            )
            await_checkpoint_state = _AwaitCheckpointState(
                submit_checkpoint_ref=submit_step.checkpoint_ref,
                repository_operation_id=submit_state.repository_operation_id,
                last_observed_repository_status=None,
                terminal_result_evidence_ref=None,
            )

        repository_operation: RepositoryImportOperation | None = None
        if (
            await_checkpoint_state is not None
            and await_checkpoint_state.terminal_result_evidence_ref is not None
        ):
            repository_operation = _load_terminal_repository_evidence(
                deps.artifact_store,
                await_checkpoint_state.terminal_result_evidence_ref,
                terminal_evidence_decode=deps.terminal_evidence_decode,
                expected_operation_id=submit_state.repository_operation_id,
                expected_status=await_checkpoint_state.last_observed_repository_status,
            )
        else:
            if step.started_at is None:
                raise SubmitJobError("await_import_result is missing started_at")
            wait_upper_bound_at = step.started_at + timedelta(
                seconds=SUBMIT_IMPORT_WAIT_UPPER_BOUND_SECONDS
            )
            now = _submit_now(deps)
            remaining_wait_seconds = (wait_upper_bound_at - now).total_seconds()
            poll_deadline_seconds = min(
                SUBMIT_IMPORT_POLL_DEADLINE_SECONDS,
                max(remaining_wait_seconds, 5.0),
            )
            try:
                repository_operation = deps.repository_write.wait_operation(
                    repository_id=payload.repository_id,
                    operation_id=submit_state.repository_operation_id,
                    deadline_seconds=poll_deadline_seconds,
                )
            except (
                TimeoutError,
                RepositoryWriteTimeoutError,
                RepositoryWriteTransportError,
            ) as exc:
                now = _submit_now(deps)
                if now >= wait_upper_bound_at:
                    return _publish_wait_upper_bound_exceeded(
                        step=step,
                        lease_session=lease_session,
                        now=now,
                    )
                return _publish_counted_reconcile_pending(
                    step=step,
                    control=control,
                    lease_session=lease_session,
                    now=now,
                    diagnostic_code=DIAGNOSTIC_RETRY_SCHEDULED,
                    reason=(
                        "repository import poll transport failed; outcome remains unknown"
                        if isinstance(exc, RepositoryWriteTransportError)
                        else "repository import poll timed out; outcome remains unknown"
                    ),
                )

            now = _submit_now(deps)
            if repository_operation.operation_id != submit_state.repository_operation_id:
                return _publish_manual_recovery(
                    step=step,
                    lease_session=lease_session,
                    now=now,
                    diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
                    reason="Repository operation identity does not match the Submit checkpoint",
                )
            if (
                repository_operation.status
                in {
                    RepositoryOperationStatus.QUEUED,
                    RepositoryOperationStatus.RUNNING,
                }
                and now >= wait_upper_bound_at
            ):
                return _publish_wait_upper_bound_exceeded(
                    step=step,
                    lease_session=lease_session,
                    now=now,
                )

        if repository_operation.status in {
            RepositoryOperationStatus.QUEUED,
            RepositoryOperationStatus.RUNNING,
        }:
            if await_checkpoint_ref is None:
                raise SubmitJobError(
                    "await_import_result checkpoint is missing for reconcile handoff"
                )
            published_generation = lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=await_checkpoint_ref,
                    extra_refs=(),
                    owner_kind="submit-checkpoint",
                    active_transaction=_active_submit_transaction.get,
                    transaction_missing=lambda: SubmitJobError(
                        "submit checkpoint transaction is not bound"
                    ),
                    deduplicate_refs=False,
                    intent="await-import-reconcile-checkpoint",
                )
            )
            return lease_session.acknowledge_safe_handoff(
                published_generation,
                healthy_external_operation_wait=True,
            )

        if (
            await_checkpoint_state is not None
            and await_checkpoint_state.terminal_result_evidence_ref is None
            and await_checkpoint_ref is not None
        ):
            evidence_ref = _persist_terminal_repository_evidence(
                deps.artifact_store,
                repository_operation,
            )
            terminal_envelope = envelope_for_step(
                key=await_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=checkpoint_generation(step),
                job_state=_job_state_for_await_terminal(
                    submit_checkpoint_ref=submit_step.checkpoint_ref,
                    repository_operation_id=submit_state.repository_operation_id,
                    last_observed_repository_status=repository_operation.status.value,
                    terminal_result_evidence_ref=evidence_ref,
                ),
            )
            await_checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, terminal_envelope)
            lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=await_checkpoint_ref,
                    extra_refs=(evidence_ref,),
                    owner_kind="submit-checkpoint",
                    active_transaction=_active_submit_transaction.get,
                    transaction_missing=lambda: SubmitJobError(
                        "submit checkpoint transaction is not bound"
                    ),
                    deduplicate_refs=False,
                    intent="await-import-terminal-checkpoint",
                )
            )
            await_checkpoint_state = _AwaitCheckpointState(
                submit_checkpoint_ref=submit_step.checkpoint_ref,
                repository_operation_id=submit_state.repository_operation_id,
                last_observed_repository_status=repository_operation.status.value,
                terminal_result_evidence_ref=evidence_ref,
            )

        if repository_operation.status is RepositoryOperationStatus.SUCCEEDED:
            try:
                facts = _matching_finalize_facts(
                    payload=payload,
                    prepare_checkpoint=prepare_checkpoint,
                    repository_operation=repository_operation,
                    repository_operation_id=submit_state.repository_operation_id,
                )
            except FinalizeBindingMismatch as exc:
                lease_session.publish_operation(
                    _make_manual_recovery_terminal_builder(
                        submit_state.repository_operation_id,
                        diagnostic=OperationDiagnostic(
                            code=FinalizeBindingMismatch.stable_code,
                            message=str(exc),
                        ),
                    )
                )
                return ExecutorAcknowledgment.PUBLISHED
            ready_ref = next(
                ref
                for ref in operation.artifact_refs
                if ref.artifact_id == attempt.preview_ready_closure_ref
            )
            review_artifact_refs = (
                ready_ref,
                *load_ready_closure(deps.artifact_store, ready_ref).artifact_refs(),
            )
            lease_session.publish_operation(
                _make_finalize_success_builder(
                    submit_attempt_id=payload.submit_attempt_id,
                    facts=facts,
                    submission_id_factory=deps.submission_id_factory,
                    review_artifact_refs=review_artifact_refs,
                )
            )
            return ExecutorAcknowledgment.PUBLISHED

        if repository_operation.status is RepositoryOperationStatus.FAILED:
            if repository_operation.error is None:
                raise SubmitJobError("repository FAILED operation is missing error evidence")
            if repository_operation.error.code not in ALLOWED_ABORT_CODES:
                lease_session.publish_operation(
                    _make_manual_recovery_terminal_builder(
                        submit_state.repository_operation_id,
                        diagnostic=OperationDiagnostic(
                            code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED.upper(),
                            message=(
                                "repository failure code is not an allowed stable abort: "
                                f"{repository_operation.error.code}"
                            ),
                        ),
                    )
                )
                return ExecutorAcknowledgment.PUBLISHED
            proof = MatchingAbortProof(
                repository_id=payload.repository_id,
                repository_operation_id=submit_state.repository_operation_id,
                terminal_status=RepositoryOperationTerminalStatus.FAILED,
                stable_failure_code=repository_operation.error.code,
            )
            lease_session.publish_operation(
                _make_stable_abort_builder(
                    request=AbortSubmitTransactionRequest(
                        submit_attempt_id=payload.submit_attempt_id,
                        proof=proof,
                        aborted_at=datetime.now(UTC),
                        worker_id=step.worker_id,
                        lease_token=step.lease_token,
                    ),
                    evidence=_StaticAbortEvidence(repository_operation),
                )
            )
            return ExecutorAcknowledgment.PUBLISHED

        raise SubmitJobError("repository operation returned an unsupported terminal status")

    return execute

def _matching_finalize_facts(
    *,
    payload: SubmitJobPayload,
    prepare_checkpoint: PrepareImportCheckpoint,
    repository_operation: RepositoryImportOperation,
    repository_operation_id: str,
) -> MatchingFinalizeFacts:
    if repository_operation.operation_id != repository_operation_id:
        raise FinalizeBindingMismatch("repository operation identity does not match checkpoint")
    if repository_operation.result is None:
        raise SubmitJobError("repository SUCCEEDED operation is missing result")
    result = repository_operation.result
    manifest_digest = str(result.canonicalization_manifest_digest)
    if manifest_digest != prepare_checkpoint.canonicalization_manifest_digest:
        raise FinalizeBindingMismatch(
            "repository manifest digest does not match prepare checkpoint"
        )
    expected_commit_id = str(result.expected_commit_id)
    if expected_commit_id != payload.repository_expected_commit_id:
        raise FinalizeBindingMismatch("repository expected commit does not match payload")
    completed_verification_policy = _verification_policy_from_repository(
        result.completed_verification_policy
    )
    if completed_verification_policy is not payload.repository_policy.verification_policy:
        raise FinalizeBindingMismatch("completed verification policy does not match request")
    completed_unknown_type_policy = _unknown_type_policy_from_repository(result.unknown_type_policy)
    if completed_unknown_type_policy is not payload.repository_policy.unknown_type_policy:
        raise FinalizeBindingMismatch("completed unknown type policy does not match request")
    target_ref = _target_ref_from_repository(str(result.target_ref))
    if target_ref is not payload.repository_policy.target_ref:
        raise FinalizeBindingMismatch("completed target ref does not match request")
    return MatchingFinalizeFacts(
        repository_id=payload.repository_id,
        repository_operation_id=repository_operation_id,
        repository_commit_id=str(result.commit_id),
        repository_expected_parent_commit_id=expected_commit_id,
        repository_artifact_id=str(result.artifact_id),
        repository_import_artifact_raw_sha256=prepare_checkpoint.package_raw_sha256,
        canonicalization_manifest_ref=prepare_checkpoint.canonicalization_manifest_ref.artifact_id,
        canonicalization_manifest_digest=manifest_digest,
        completed_verification_policy=completed_verification_policy,
        completed_unknown_type_policy=completed_unknown_type_policy,
        target_ref=target_ref,
    )

def _make_stable_abort_builder(
    *,
    request: AbortSubmitTransactionRequest,
    evidence: RepositoryAbortEvidencePort,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_submit_transaction.get()
        if transaction is None:
            raise SubmitJobError("submit abort transaction is not bound")
        attempt = transaction.submission.get_submit_attempt(request.submit_attempt_id)
        if attempt is None:
            raise SubmitJobError("submit attempt is missing")
        validate_abort_proof(attempt=attempt, proof=request.proof, evidence=evidence)
        abort_submit_in_control_transaction(
            request=AbortSubmitTransactionRequest(
                submit_attempt_id=request.submit_attempt_id,
                proof=request.proof,
                aborted_at=transaction_now,
                worker_id=step.worker_id,
                lease_token=step.lease_token,
                expected_attempt_version=attempt.optimistic_version,
                expected_await_step_version=step.optimistic_version,
                expected_operation_version=operation.optimistic_version,
                defer_operation_terminal=True,
            ),
            unit_of_work=transaction,
        )
        abort_code = request.proof.stable_failure_code
        diagnostic = OperationDiagnostic(code=abort_code, message="submit attempt aborted")
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder

def _make_finalize_success_builder(
    *,
    submit_attempt_id: str,
    facts: MatchingFinalizeFacts,
    submission_id_factory: Callable[[], str],
    review_artifact_refs: tuple[ArtifactRef, ...],
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_submit_transaction.get()
        if transaction is None:
            raise SubmitJobError("submit finalize transaction is not bound")
        attempt = transaction.submission.get_submit_attempt(submit_attempt_id)
        if attempt is None:
            raise SubmitJobError("submit attempt is missing")
        finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=submit_attempt_id,
                facts=facts,
                submission_id=submission_id_factory(),
                created_at=transaction_now,
                expected_attempt_version=attempt.optimistic_version,
                expected_await_step_version=step.optimistic_version,
                expected_operation_version=operation.optimistic_version,
                worker_id=step.worker_id,
                lease_token=step.lease_token,
                defer_operation_terminal=True,
                review_artifact_refs=review_artifact_refs,
            ),
            unit_of_work=transaction,
        )
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.SUCCEEDED,
            diagnostic=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.SUCCEEDED,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder

@dataclass(frozen=True, slots=True)
class _StaticAbortEvidence:
    operation: RepositoryImportOperation

    def resolve_stable_failure_code(
        self,
        *,
        repository_id: str,
        repository_operation_id: str,
    ) -> str:
        del repository_id
        if str(self.operation.operation_id) != repository_operation_id:
            raise ValueError("repository operation identity does not match proof")
        if self.operation.status is not RepositoryOperationStatus.FAILED:
            raise ValueError("repository operation is not FAILED")
        if self.operation.error is None:
            raise ValueError("repository FAILED operation is missing error evidence")
        return self.operation.error.code

    def validate_matching_stable_failure(
        self,
        *,
        attempt: SubmitAttempt,
        proof: MatchingAbortProof,
    ) -> None:
        del attempt
        if str(self.operation.operation_id) != proof.repository_operation_id:
            raise ValueError("repository operation identity does not match proof")
        if self.operation.status is not RepositoryOperationStatus.FAILED:
            raise ValueError("repository operation is not FAILED")
        if self.operation.error is None or self.operation.error.code != proof.stable_failure_code:
            raise ValueError("abort proof stable failure code does not match repository")


__all__ = [
    "build_await_import_result_handler",
]
