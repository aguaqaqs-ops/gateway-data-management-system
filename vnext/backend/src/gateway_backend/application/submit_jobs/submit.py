"""Submit step 2: send repository import external effect."""

from __future__ import annotations

import dataclasses

from datetime import (
    UTC,
    datetime,
)
from gateway_backend.application.checkpoints import (
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    prepare_step_checkpoint,
)
from gateway_backend.application.job_definitions import JobDefinition
from gateway_backend.application.job_steps import (
    checkpoint_generation,
    make_successor_builder,
    pinned_checkpoint_builder,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.recovery import compute_request_fingerprint
from gateway_backend.application.submission.contracts import PrepareImportCheckpoint
from gateway_backend.application.submission.effect_pending_transaction import (
    BindRepositoryOperationRequest,
    EffectPendingTransactionRequest,
    bind_repository_operation_identity,
    mark_submit_attempt_effect_pending,
)
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
    submit_successor_step_id as _successor_step_id,
)
from gateway_backend.artifacts.location import (
    ArtifactLocation,
    build_artifact_id,
)
from gateway_backend.artifacts.store import put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    SubmitAttempt,
    SubmitAttemptState,
)
from gateway_backend.operations.contracts import (
    OperationRecord,
    StepRecord,
)
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
)
from gateway_backend.statistics.metrics import bind_scope
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.application.submit_jobs.checkpoint import (
    _SubmitCheckpointState,
    _active_submit_transaction,
    _job_state_for_submit_request,
    _job_state_for_submit_sent,
    _load_step,
    _prepare_checkpoint_from_job_state,
    _submit_state_from_job_state,
)
from gateway_backend.application.submit_jobs.failures import _make_cancelled_terminal_builder
from gateway_backend.application.submit_jobs.payload import (
    SubmitJobError,
    SubmitJobPayload,
    SubmitRuntimeDependencies,
    _JCS_MEDIA_TYPE,
    _assert_payload_matches_attempt,
    _definition_for_step,
    _load_submit_attempt,
    _load_submit_payload,
)


def build_submit_import_handler(deps: SubmitRuntimeDependencies) -> ClaimedExecutor:
    prepare_definition = _definition_for_step(SUBMIT_STEP_PREPARE)
    submit_definition = _definition_for_step(SUBMIT_STEP_SUBMIT)

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        lease_session.refresh_control()
        if step.checkpoint_ref is None and control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        payload = _load_submit_payload(operation, deps.artifact_store)
        bind_scope(payload.repository_id, payload.submit_attempt_id)
        attempt = _load_submit_attempt(deps, payload.submit_attempt_id)
        _assert_payload_matches_attempt(payload, attempt)

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
        if not definition_matches_checkpoint(prepare_definition, prepare_envelope):
            raise CheckpointDecodeError(
                "prepare checkpoint does not match the prepare_import JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        prepare_checkpoint = _prepare_checkpoint_from_job_state(
            prepare_envelope.job_state,
            expected_attempt_id=payload.submit_attempt_id,
        )

        request_state: _SubmitCheckpointState
        last_checkpoint_generation = None

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(submit_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the submit_import JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            request_state = _submit_state_from_job_state(
                deps.artifact_store,
                envelope.job_state,
                repository_write=deps.repository_write,
                expected_payload=payload,
                prepare_checkpoint_ref=prepare_step.checkpoint_ref,
                checkpoint_ref=step.checkpoint_ref,
            )
        else:
            request_state, last_checkpoint_generation = _materialize_submit_checkpoint_state(
                deps=deps,
                submit_definition=submit_definition,
                operation=operation,
                step=step,
                lease_session=lease_session,
                payload=payload,
                attempt=attempt,
                prepare_checkpoint=prepare_checkpoint,
                prepare_checkpoint_ref=prepare_step.checkpoint_ref,
            )

        if not request_state.request_sent:
            lease_session.refresh_control()
            if control.cancel_requested:
                # unreachable until submit cancel source exists (effect boundary crossed)
                lease_session.publish_operation(_make_cancelled_terminal_builder())
                return ExecutorAcknowledgment.PUBLISHED
            repository_operation_id = deps.repository_write.submit_versioned_import(
                repository_id=payload.repository_id,
                idempotency_key=payload.repository_import_idempotency_key,
                artifact_ref=request_state.repository_artifact_ref,
                expected_commit_id=payload.repository_expected_commit_id,
            )
            with deps.control_transaction_factory() as unit_of_work:
                fresh_attempt = unit_of_work.submission.get_submit_attempt(
                    payload.submit_attempt_id
                )
                if fresh_attempt is None:
                    raise SubmitJobError("submit attempt is missing")
                bind_repository_operation_identity(
                    request=BindRepositoryOperationRequest(
                        submit_attempt_id=payload.submit_attempt_id,
                        repository_operation_id=repository_operation_id,
                        expected_attempt_version=fresh_attempt.optimistic_version,
                    ),
                    unit_of_work=unit_of_work,
                )
            sent_envelope = envelope_for_step(
                key=submit_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=checkpoint_generation(step),
                job_state=_job_state_for_submit_sent(
                    prepare_checkpoint_ref=request_state.prepare_checkpoint_ref,
                    repository_artifact_ref=request_state.repository_artifact_ref,
                    payload=payload,
                    request_artifact_ref=request_state.request_artifact_ref,
                    request_fingerprint=request_state.request_fingerprint,
                    repository_operation_id=repository_operation_id,
                ),
            )
            sent_checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, sent_envelope)
            last_checkpoint_generation = lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=sent_checkpoint_ref,
                    extra_refs=(
                        request_state.prepare_checkpoint_ref,
                        request_state.request_artifact_ref,
                    ),
                    owner_kind="submit-checkpoint",
                    active_transaction=_active_submit_transaction.get,
                    transaction_missing=lambda: SubmitJobError(
                        "submit checkpoint transaction is not bound"
                    ),
                    deduplicate_refs=False,
                    intent="submit-import-checkpoint",
                )
            )
            request_state = dataclasses.replace(
                request_state,
                request_sent=True,
                repository_operation_id=repository_operation_id,
                checkpoint_ref=sent_checkpoint_ref,
            )

        lease_session.refresh_control()
        if control.cancel_requested:
            # unreachable until submit cancel source exists (post-effect publish path)
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        lease_session.publish_successor(
            make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=SUBMIT_STEP_AWAIT,
                successor_step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_AWAIT),
            )
        )
        if last_checkpoint_generation is not None:
            del last_checkpoint_generation
        return ExecutorAcknowledgment.PUBLISHED

    return execute


def _materialize_submit_checkpoint_state(
    *,
    deps: SubmitRuntimeDependencies,
    submit_definition: JobDefinition,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    payload: SubmitJobPayload,
    attempt: SubmitAttempt,
    prepare_checkpoint: PrepareImportCheckpoint,
    prepare_checkpoint_ref: ArtifactRef,
) -> tuple[_SubmitCheckpointState, object | None]:
    if (
        attempt.state is SubmitAttemptState.EFFECT_PENDING
        and attempt.repository_artifact_ref is not None
    ):
        repository_artifact_ref = attempt.repository_artifact_ref
        request_bytes = deps.repository_write.canonical_import_request_bytes(
            repository_id=payload.repository_id,
            artifact_ref=repository_artifact_ref,
            expected_commit_id=payload.repository_expected_commit_id,
        )
        request_ref = put_with_built_ref(
            deps.artifact_store,
            request_bytes,
            artifact_id=_import_request_artifact_id(request_bytes),
            media_type=_JCS_MEDIA_TYPE,
        )
        request_fingerprint = compute_request_fingerprint(request_bytes)
        if attempt.repository_operation_id is not None:
            envelope = envelope_for_step(
                key=submit_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=checkpoint_generation(step),
                job_state=_job_state_for_submit_sent(
                    prepare_checkpoint_ref=prepare_checkpoint_ref,
                    repository_artifact_ref=repository_artifact_ref,
                    payload=payload,
                    request_artifact_ref=request_ref,
                    request_fingerprint=request_fingerprint,
                    repository_operation_id=attempt.repository_operation_id,
                ),
            )
            request_sent = True
            repository_operation_id = attempt.repository_operation_id
        else:
            envelope = envelope_for_step(
                key=submit_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=checkpoint_generation(step),
                job_state=_job_state_for_submit_request(
                    prepare_checkpoint_ref=prepare_checkpoint_ref,
                    repository_artifact_ref=repository_artifact_ref,
                    payload=payload,
                    request_artifact_ref=request_ref,
                    request_fingerprint=request_fingerprint,
                ),
            )
            request_sent = False
            repository_operation_id = None
        checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
        published_generation = lease_session.publish_checkpoint(
            pinned_checkpoint_builder(
                checkpoint_ref=checkpoint_ref,
                extra_refs=(prepare_checkpoint_ref, request_ref),
                owner_kind="submit-checkpoint",
                active_transaction=_active_submit_transaction.get,
                transaction_missing=lambda: SubmitJobError(
                    "submit checkpoint transaction is not bound"
                ),
                deduplicate_refs=False,
                intent="submit-import-checkpoint",
            )
        )
        return (
            _SubmitCheckpointState(
                prepare_checkpoint_ref=prepare_checkpoint_ref,
                repository_artifact_ref=repository_artifact_ref,
                request_artifact_ref=request_ref,
                request_fingerprint=request_fingerprint,
                request_sent=request_sent,
                repository_operation_id=repository_operation_id,
                checkpoint_ref=checkpoint_ref,
            ),
            published_generation,
        )

    package_bytes = deps.publication.read_back_package(
        checkpoint=prepare_checkpoint,
        store=deps.artifact_store,
    )
    repository_artifact_ref = deps.repository_write.upload_artifact(
        repository_id=payload.repository_id,
        idempotency_key=payload.repository_upload_idempotency_key,
        media_type=prepare_checkpoint.backend_import_artifact_ref.media_type,
        raw_sha256=prepare_checkpoint.package_raw_sha256,
        body=package_bytes,
    )
    request_bytes = deps.repository_write.canonical_import_request_bytes(
        repository_id=payload.repository_id,
        artifact_ref=repository_artifact_ref,
        expected_commit_id=payload.repository_expected_commit_id,
    )
    request_ref = put_with_built_ref(
        deps.artifact_store,
        request_bytes,
        artifact_id=_import_request_artifact_id(request_bytes),
        media_type=_JCS_MEDIA_TYPE,
    )
    request_fingerprint = compute_request_fingerprint(request_bytes)
    effect_pending_at = datetime.now(UTC)
    with deps.control_transaction_factory() as unit_of_work:
        fresh_attempt = unit_of_work.submission.get_submit_attempt(payload.submit_attempt_id)
        if fresh_attempt is None:
            raise SubmitJobError("submit attempt is missing")
        mark_submit_attempt_effect_pending(
            request=EffectPendingTransactionRequest(
                submit_attempt_id=payload.submit_attempt_id,
                checkpoint=prepare_checkpoint,
                repository_artifact_ref=repository_artifact_ref,
                effect_pending_at=effect_pending_at,
                expected_attempt_version=fresh_attempt.optimistic_version,
            ),
            unit_of_work=unit_of_work,
        )
    envelope = envelope_for_step(
        key=submit_definition.key,
        operation=operation,
        step=step,
        checkpoint_generation=checkpoint_generation(step),
        job_state=_job_state_for_submit_request(
            prepare_checkpoint_ref=prepare_checkpoint_ref,
            repository_artifact_ref=repository_artifact_ref,
            payload=payload,
            request_artifact_ref=request_ref,
            request_fingerprint=request_fingerprint,
        ),
    )
    checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
    published_generation = lease_session.publish_checkpoint(
        pinned_checkpoint_builder(
            checkpoint_ref=checkpoint_ref,
            extra_refs=(prepare_checkpoint_ref, request_ref),
            owner_kind="submit-checkpoint",
            active_transaction=_active_submit_transaction.get,
            transaction_missing=lambda: SubmitJobError(
                "submit checkpoint transaction is not bound"
            ),
            deduplicate_refs=False,
            intent="submit-import-checkpoint",
        )
    )
    return (
        _SubmitCheckpointState(
            prepare_checkpoint_ref=prepare_checkpoint_ref,
            repository_artifact_ref=repository_artifact_ref,
            request_artifact_ref=request_ref,
            request_fingerprint=request_fingerprint,
            request_sent=False,
            repository_operation_id=None,
            checkpoint_ref=checkpoint_ref,
        ),
        published_generation,
    )


def _submit_may_invoke_handler_without_checkpoint(
    deps: SubmitRuntimeDependencies,
    operation: OperationRecord,
    step: StepRecord,
) -> bool:
    if step.step_name != SUBMIT_STEP_SUBMIT:
        return False
    try:
        payload = _load_submit_payload(operation, deps.artifact_store)
        bind_scope(payload.repository_id, payload.submit_attempt_id)
        attempt = _load_submit_attempt(deps, payload.submit_attempt_id)
    except Exception:
        return False
    if (
        attempt.state is SubmitAttemptState.EFFECT_PENDING
        and attempt.repository_artifact_ref is not None
    ):
        return True
    if attempt.state is SubmitAttemptState.PREPARED:
        try:
            prepare_step = _load_step(
                deps,
                operation_id=operation.operation_id,
                step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_PREPARE),
            )
        except Exception:
            return False
        return prepare_step.checkpoint_ref is not None
    return False


def _import_request_artifact_id(request_bytes: bytes) -> str:
    return build_artifact_id(
        ArtifactLocation.DURABLE, "submit-import-request", raw_blob_digest(request_bytes).value
    )


__all__ = [
    "build_submit_import_handler",
]
