"""Cross-boundary synthetic job reload and R5 fault-matrix tests (P4-R5-S3c owner).

R5 S3c fault matrix (one authoritative owner per invariant):

| Fault boundary | Authoritative owner |
|---|---|
| crash | ``test_cross_boundary_crash_preserves_durable_state`` (``CROSS_BOUNDARY_CRASH_CASES``) |
| response loss | ``test_cross_boundary_response_loss_preserves_original_identity``; stub before-checkpoint also in crash matrix; recovery-port indexed to S3b ``test_external_effect_recovery_port_accepted_polls_original_identity``; pure-compute N/A |
| lease expiry | ``test_operation_takeover`` (integration); ``test_process_startup_takeover_*`` (process); S3a ``test_pure_compute_lease_takeover_*`` (consumer E2E) |
| duplicate | ``test_duplicate_delivery_*``, ``test_terminal_publication_*``, ``test_stub_duplicate_*``; S3a ``test_pure_compute_recovery_port_duplicate_*``, ``test_pure_compute_retry_does_not_duplicate_*`` |
| stale writer | ``test_operation_takeover`` ``test_old_lease_token_*``, ``test_operator_command_stale_*``; R4 stale CAS in ``test_operation_worker_integration`` |
| corrupt checkpoint | ``test_reload_rejects_missing_or_corrupt_*`` (``RELOAD_ARTIFACT_FAULTS`` × ``PAYLOAD_RELOAD_CONSUMERS``); ``test_stub_reload_rejects_*`` (``STUB_REQUEST_ARTIFACT_FAULTS``) |
| retry exhaustion | ``test_operation_takeover`` ``test_session_budget_exhaustion_marks_manual_recovery`` |
| reconcile timeout | S3b ``test_external_effect_recovery_port_reconcile_budget_exhausted``; S2b ``test_operation_effect_reconcile`` |
| operator action | S2c ``test_operation_takeover`` ``test_operator_*`` |

R4 delegated (indexed, not duplicated): payload reload, checkpoint round-trip (S2a),
closure set-once, cancel before/after request (``test_operation_job_synthetic``),
process SIGKILL (``test_operation_worker_process``).

S3a/S3b consumer RecoveryPort proofs remain in ``test_pure_compute_recovery_port_*`` and
``test_external_effect_recovery_port_*``; S3c does not duplicate those invariants.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.application.checkpoints import (
    envelope_for_step,
    load_checkpoint_envelope,
    load_ready_closure,
    make_checkpoint_step_builder,
    prepare_step_checkpoint,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.external_effect_stub import (
    DeterministicExternalEffectStub,
    RecordingExternalEffectStub,
    StubOutcome,
    build_request_bytes,
    compute_operation_identity,
    request_artifact_id,
)
from gateway_backend.application.job_definitions import JobWorkerComposition, build_job_worker_composition
from gateway_backend.application.payloads import decode_job_payload
from gateway_backend.application.recovery import (
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    DIAGNOSTIC_RECONCILE_TIMEOUT,
    RECONCILE_SESSION_BUDGET_SECONDS,
    RecoveryOutcomeDisposition,
    compute_request_fingerprint,
)
from gateway_backend.application.synthetic_jobs import (
    EXTERNAL_EFFECT_STUB_JOB_KIND,
    EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION,
    EXTERNAL_EFFECT_STUB_STEP_NAME,
    ExternalEffectStubPayload,
    PURE_COMPUTE_JOB_KIND,
    PURE_COMPUTE_PAYLOAD_VERSION,
    PURE_COMPUTE_STEP_NAME,
    PureComputePayload,
    PollingExternalEffectStub,
    build_external_effect_stub_handler,
    build_external_effect_stub_recovery_port,
    build_pure_compute_recovery_port,
    compute_pure_compute_output_bytes,
    external_effect_stub_composition_bundle,
    external_effect_stub_job_key,
    pure_compute_composition_bundle,
    pure_compute_job_key,
)
from gateway_backend.artifacts import InMemoryArtifactStore, put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.operations.contracts import JobStepKey, OperationRecord, StepRecord
from gateway_backend.bootstrap.operation_worker import bootstrap_control_database
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.operations.recovery import RecoveryCapabilityValue, StartupRecovery, build_startup_recovery
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationStatus,
    StepStatus,
    TransitionDisposition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.state import WritePrecondition, validate_operation_transition
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    RecoveryHook,
    StartupDisposition,
)
from gateway_backend.operations.worker_startup import WorkerStartup
from gateway_backend.settings import OperationWorkerSettings

pytestmark = pytest.mark.integration

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
LEASE_EXPIRES_AT = BASE_TIME + timedelta(seconds=30)
SEED_ALPHA = "alpha"
IDEMPOTENCY_KEY_ALPHA = "idem-alpha"
REQUEST_BODY_ALPHA = "request-alpha"

PAYLOAD_RELOAD_CONSUMERS: tuple[tuple[str, str, str], ...] = (
    ("pure-compute", PURE_COMPUTE_JOB_KIND, PURE_COMPUTE_PAYLOAD_VERSION),
    ("external-effect-stub", EXTERNAL_EFFECT_STUB_JOB_KIND, EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION),
)


def _corrupt_stored_artifact_bytes(store: InMemoryArtifactStore, artifact_id: str) -> None:
    stored_ref, raw_bytes = store._artifacts[artifact_id]
    corrupted = raw_bytes[:-1] + (b"x" if raw_bytes[-1:] != b"x" else b"y")
    store._artifacts[artifact_id] = (stored_ref, corrupted)


def _delete_stored_artifact(store: InMemoryArtifactStore, artifact_id: str) -> None:
    store._artifacts.pop(artifact_id)


RELOAD_ARTIFACT_FAULTS: tuple[
    tuple[str, Callable[[InMemoryArtifactStore, str], None], type[Exception]],
    ...,
] = (
    (
        "missing-checkpoint",
        _delete_stored_artifact,
        CheckpointDecodeError,
    ),
    (
        "corrupt-checkpoint",
        _corrupt_stored_artifact_bytes,
        CheckpointDecodeError,
    ),
)

STUB_REQUEST_ARTIFACT_FAULTS: tuple[
    tuple[str, Callable[[InMemoryArtifactStore, str], None]],
    ...,
] = (
    ("missing-request", _delete_stored_artifact),
    ("corrupt-request", _corrupt_stored_artifact_bytes),
)

STUB_RELOAD_OUTCOMES: tuple[str, ...] = (
    StubOutcome.CONFIRMED.value,
    StubOutcome.UNKNOWN.value,
    StubOutcome.ACCEPTED.value,
)

CROSS_BOUNDARY_CRASH_CASES: tuple[tuple[str, str], ...] = (
    ("pure-compute", "before-checkpoint"),
    ("pure-compute", "after-checkpoint"),
    ("external-effect-stub", "before-request-checkpoint"),
    ("external-effect-stub", "after-request-checkpoint"),
)

RESPONSE_LOSS_HANDLER_SCENARIOS: tuple[str, ...] = (
    "handler-reload-after-request-checkpoint",
    "handler-reload-unknown-no-resubmit",
)


def _operation_document(operation_id: str) -> dict[str, object]:
    return {
        "artifact_refs": [],
        "business_refs": [],
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2026-08-24T12:00:00Z",
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": PURE_COMPUTE_PAYLOAD_VERSION,
        "job_kind": PURE_COMPUTE_JOB_KIND,
        "job_payload": {"seed": SEED_ALPHA},
        "job_payload_ref": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "ready_closure_ref": None,
        "repository_operation_id": None,
        "status": OperationStatus.QUEUED.value,
        "updated_at": "2026-08-24T12:00:00Z",
    }


def _step_document(operation_id: str, step_id: str) -> dict[str, object]:
    return {
        "attempt_count": 0,
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2026-08-24T12:00:00Z",
        "diagnostic": None,
        "document_type": "step",
        "lease_expires_at": None,
        "lease_token": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "prior_output_refs": [],
        "retry_not_before": None,
        "started_at": None,
        "status": StepStatus.PENDING.value,
        "step_id": step_id,
        "step_name": PURE_COMPUTE_STEP_NAME,
        "updated_at": "2026-08-24T12:00:00Z",
        "worker_id": None,
    }


def _bootstrap_claimed(
    db_path: Path,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str = "worker-recovery-1",
    lease_token: str = "lease-recovery-1",
) -> tuple[LeaseSession, ExecutionControl]:
    bootstrap_control_database(OperationWorkerSettings(control_db_path=db_path))
    operation = operation_record_from_document(_operation_document(operation_id))
    step = step_record_from_document(_step_document(operation.operation_id, step_id))
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        transaction_now = unit_of_work.operations.transaction_now
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=transaction_now,
        ).claim_one(worker_id, lease_token)
    assert claimed is not None
    claimed_operation, claimed_step = claimed

    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=claimed_operation.operation_id,
        step_id=claimed_step.step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    return session, control


def _wrapped_executor(store: InMemoryArtifactStore) -> ClaimedExecutor:
    definitions, handlers, decoders = pure_compute_composition_bundle(store)
    composition = build_job_worker_composition(
        definitions,
        handlers,
        artifact_store=store,
        decoders=decoders,
    )
    executor = composition.worker_registry.resolve(pure_compute_job_key())
    assert executor is not None
    return executor


def _publish_checkpoint_only(
    db_path: Path,
    artifact_store: InMemoryArtifactStore,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str,
    lease_token: str,
) -> ArtifactRef:
    session, _control = _bootstrap_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    output_bytes = compute_pure_compute_output_bytes(SEED_ALPHA)
    digest = raw_blob_digest(output_bytes).value
    output_ref = put_with_built_ref(
        artifact_store,
        output_bytes,
        artifact_id=f"pure-compute-output:{digest}",
        media_type="application/jcs",
    )
    envelope = envelope_for_step(
        key=pure_compute_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=step.attempt_count,
        job_state={
            "output_artifact_id": output_ref.artifact_id,
            "seed": SEED_ALPHA,
        },
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))
    return checkpoint_ref


def _composition_for_consumer(
    consumer: str,
    store: InMemoryArtifactStore,
) -> JobWorkerComposition:
    if consumer == "pure-compute":
        definitions, handlers, decoders = pure_compute_composition_bundle(store)
        key = pure_compute_job_key()
    else:
        definitions, handlers, decoders = external_effect_stub_composition_bundle(store)
        key = external_effect_stub_job_key()
    composition = build_job_worker_composition(
        definitions,
        handlers,
        artifact_store=store,
        decoders=decoders,
    )
    executor = composition.worker_registry.resolve(key)
    assert executor is not None
    return composition


def _restart_session(
    db_path: Path,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str,
    lease_token: str,
) -> tuple[LeaseSession, ExecutionControl, OperationRecord, StepRecord]:
    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    return session, control, operation, step


def test_checkpoint_reload_completes_after_simulated_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "reload.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-reload"
    step_id = "step-reload"
    worker_id = "worker-reload-1"
    lease_token = "lease-reload-1"

    _publish_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    assert step.checkpoint_ref is not None
    assert operation.ready_closure_ref is None

    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )

    executor = _wrapped_executor(artifact_store)
    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_step.status is StepStatus.SUCCEEDED
    assert persisted_operation.ready_closure_ref is not None
    expected_digest = raw_blob_digest(compute_pure_compute_output_bytes(SEED_ALPHA))
    checkpoint_ref = persisted_step.checkpoint_ref
    assert checkpoint_ref is not None
    envelope = load_checkpoint_envelope(artifact_store, checkpoint_ref)
    assert envelope.job_state["seed"] == SEED_ALPHA
    closure = load_ready_closure(artifact_store, persisted_operation.ready_closure_ref)
    assert closure.outputs[0].artifact_ref.raw_sha256 == expected_digest


def test_duplicate_delivery_preserves_output_digest(tmp_path: Path) -> None:
    db_path = tmp_path / "duplicate.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-duplicate"
    step_id = "step-duplicate"

    _publish_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id="worker-dup-1",
        lease_token="lease-dup-1",
    )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    expected_digest = raw_blob_digest(compute_pure_compute_output_bytes(SEED_ALPHA))

    control = ExecutionControl()
    session = LeaseSession(
        worker_id="worker-dup-1",
        lease_token="lease-dup-1",
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )

    executor = _wrapped_executor(artifact_store)
    executor(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    closure_ref = persisted_operation.ready_closure_ref
    assert closure_ref is not None
    closure = load_ready_closure(artifact_store, closure_ref)
    assert closure.outputs[0].artifact_ref.raw_sha256 == expected_digest


def test_terminal_publication_is_idempotent_on_duplicate(tmp_path: Path) -> None:
    db_path = tmp_path / "idempotent.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-idempotent"
    step_id = "step-idempotent"

    session, control = _bootstrap_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id="worker-idem-1",
        lease_token="lease-idem-1",
    )
    executor = _wrapped_executor(artifact_store)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    executor(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        terminal_operation = unit_of_work.operations.get_operation(operation_id)

    assert validate_operation_transition(terminal_operation, terminal_operation) is TransitionDisposition.IDEMPOTENT

    candidate_operation = dataclasses.replace(
        terminal_operation,
        optimistic_version=terminal_operation.optimistic_version + 1,
        updated_at=terminal_operation.updated_at + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="conflicting terminal duplicate"):
        validate_operation_transition(terminal_operation, candidate_operation)


def _stub_operation_document(
    operation_id: str,
    *,
    stub_outcome: str = StubOutcome.CONFIRMED.value,
) -> dict[str, object]:
    return {
        "artifact_refs": [],
        "business_refs": [],
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2026-08-24T12:00:00Z",
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION,
        "job_kind": EXTERNAL_EFFECT_STUB_JOB_KIND,
        "job_payload": {
            "idempotency_key": IDEMPOTENCY_KEY_ALPHA,
            "request_body": REQUEST_BODY_ALPHA,
            "stub_outcome": stub_outcome,
        },
        "job_payload_ref": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "ready_closure_ref": None,
        "repository_operation_id": None,
        "status": OperationStatus.QUEUED.value,
        "updated_at": "2026-08-24T12:00:00Z",
    }


def _stub_step_document(operation_id: str, step_id: str) -> dict[str, object]:
    return {
        "attempt_count": 0,
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2026-08-24T12:00:00Z",
        "diagnostic": None,
        "document_type": "step",
        "lease_expires_at": None,
        "lease_token": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "prior_output_refs": [],
        "retry_not_before": None,
        "started_at": None,
        "status": StepStatus.PENDING.value,
        "step_id": step_id,
        "step_name": EXTERNAL_EFFECT_STUB_STEP_NAME,
        "updated_at": "2026-08-24T12:00:00Z",
        "worker_id": None,
    }


def _bootstrap_stub_claimed(
    db_path: Path,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str = "worker-stub-recovery-1",
    lease_token: str = "lease-stub-recovery-1",
    stub_outcome: str = StubOutcome.CONFIRMED.value,
) -> tuple[LeaseSession, ExecutionControl]:
    bootstrap_control_database(OperationWorkerSettings(control_db_path=db_path))
    operation = operation_record_from_document(
        _stub_operation_document(operation_id, stub_outcome=stub_outcome)
    )
    step = step_record_from_document(_stub_step_document(operation.operation_id, step_id))
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
        transaction_now = unit_of_work.operations.transaction_now
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=transaction_now,
        ).claim_one(worker_id, lease_token)
    assert claimed is not None
    claimed_operation, claimed_step = claimed

    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=claimed_operation.operation_id,
        step_id=claimed_step.step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    return session, control


def _wrapped_stub_executor(
    store: InMemoryArtifactStore,
    *,
    recording_stub: RecordingExternalEffectStub | None = None,
) -> ClaimedExecutor:
    definitions, handlers, decoders = external_effect_stub_composition_bundle(
        store,
        external_stub=recording_stub,
    )
    composition = build_job_worker_composition(
        definitions,
        handlers,
        artifact_store=store,
        decoders=decoders,
    )
    executor = composition.worker_registry.resolve(external_effect_stub_job_key())
    assert executor is not None
    return executor


def _expected_stub_identity() -> str:
    request_bytes = build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)
    return compute_operation_identity(IDEMPOTENCY_KEY_ALPHA, request_bytes)


def _publish_stub_checkpoint_only(
    db_path: Path,
    artifact_store: InMemoryArtifactStore,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str,
    lease_token: str,
    stub_outcome: str = StubOutcome.CONFIRMED.value,
) -> ArtifactRef:
    session, _control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=stub_outcome,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    request_bytes = build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)
    request_ref = put_with_built_ref(
        artifact_store,
        request_bytes,
        artifact_id=request_artifact_id(request_bytes),
        media_type="application/jcs",
    )
    operation_identity = compute_operation_identity(IDEMPOTENCY_KEY_ALPHA, request_bytes)
    envelope = envelope_for_step(
        key=external_effect_stub_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=step.attempt_count,
        job_state={
            "idempotency_key": IDEMPOTENCY_KEY_ALPHA,
            "request_artifact_id": request_ref.artifact_id,
            "operation_identity": operation_identity,
            "request_sent": True,
        },
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))
    return checkpoint_ref


def _assert_response_loss_invariants(
    *,
    recording_stub: RecordingExternalEffectStub | None,
    expected_submit_count: int,
    persisted_operation: OperationRecord,
    persisted_step: StepRecord,
    expected_identity: str,
    artifact_store: InMemoryArtifactStore,
    terminal_success: bool,
    manual_recovery: bool,
) -> None:
    if recording_stub is not None:
        assert recording_stub.submit_count == expected_submit_count
    if manual_recovery:
        assert persisted_operation.repository_operation_id == expected_identity
    elif terminal_success:
        assert persisted_operation.repository_operation_id == expected_identity
    else:
        assert persisted_operation.repository_operation_id is None
    if terminal_success:
        assert persisted_operation.status is OperationStatus.SUCCEEDED
        assert persisted_step.status is StepStatus.SUCCEEDED
        assert persisted_operation.ready_closure_ref is not None
    elif manual_recovery:
        assert persisted_operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
        assert persisted_operation.ready_closure_ref is None
    assert persisted_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(artifact_store, persisted_step.checkpoint_ref)
    assert envelope.job_state["operation_identity"] == expected_identity


@pytest.mark.parametrize("scenario", RESPONSE_LOSS_HANDLER_SCENARIOS)
def test_cross_boundary_response_loss_preserves_original_identity(
    tmp_path: Path,
    scenario: str,
) -> None:
    """Post-request uncertainty: poll or reload original identity without resubmit."""
    artifact_store = InMemoryArtifactStore()
    operation_id = f"operation-response-loss-{scenario}"
    step_id = f"step-response-loss-{scenario}"
    worker_id = f"worker-response-loss-{scenario}"
    lease_token = f"lease-response-loss-{scenario}"
    db_path = tmp_path / f"response-loss-{scenario}.sqlite3"
    expected_identity = _expected_stub_identity()

    if scenario == "handler-reload-after-request-checkpoint":
        _publish_stub_checkpoint_only(
            db_path,
            artifact_store,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        session, control, operation, step = _restart_session(
            db_path,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        executor = _wrapped_stub_executor(artifact_store)
        acknowledgment = executor(operation, step, control, session)
        assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
        with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
            persisted_operation = unit_of_work.operations.get_operation(operation_id)
            persisted_step = unit_of_work.operations.get_step(step_id)
        _assert_response_loss_invariants(
            recording_stub=None,
            expected_submit_count=0,
            persisted_operation=persisted_operation,
            persisted_step=persisted_step,
            expected_identity=expected_identity,
            artifact_store=artifact_store,
            terminal_success=True,
            manual_recovery=False,
        )
        return

    assert scenario == "handler-reload-unknown-no-resubmit"
    _publish_stub_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.UNKNOWN.value,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    request_bytes = build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)
    recording_stub = RecordingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes)
    )
    executor = _wrapped_stub_executor(artifact_store, recording_stub=recording_stub)
    session, control, operation, step = _restart_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.SAFE_HANDOFF
    assert recording_stub.submit_count == 0
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    _assert_response_loss_invariants(
        recording_stub=recording_stub,
        expected_submit_count=0,
        persisted_operation=persisted_operation,
        persisted_step=persisted_step,
        expected_identity=expected_identity,
        artifact_store=artifact_store,
        terminal_success=False,
        manual_recovery=False,
    )


@pytest.mark.parametrize(("consumer", "crash_barrier"), CROSS_BOUNDARY_CRASH_CASES)
def test_cross_boundary_crash_preserves_durable_state(
    tmp_path: Path,
    consumer: str,
    crash_barrier: str,
) -> None:
    """Simulated crash/reload proves durable readback; not R5 takeover."""
    artifact_store = InMemoryArtifactStore()
    operation_id = f"operation-crash-{consumer}-{crash_barrier}"
    step_id = f"step-crash-{consumer}-{crash_barrier}"
    worker_id = f"worker-crash-{consumer}"
    lease_token = f"lease-crash-{consumer}"
    db_path = tmp_path / f"crash-{consumer}-{crash_barrier}.sqlite3"

    if consumer == "pure-compute":
        if crash_barrier == "before-checkpoint":
            session, control = _bootstrap_claimed(
                db_path,
                operation_id=operation_id,
                step_id=step_id,
                worker_id=worker_id,
                lease_token=lease_token,
            )
            output_bytes = compute_pure_compute_output_bytes(SEED_ALPHA)
            put_with_built_ref(
                artifact_store,
                output_bytes,
                artifact_id=f"pure-compute-output:{raw_blob_digest(output_bytes).value}",
                media_type="application/jcs",
            )
            with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
                operation = unit_of_work.operations.get_operation(operation_id)
                step = unit_of_work.operations.get_step(step_id)
            assert step.checkpoint_ref is None
            executor = _wrapped_executor(artifact_store)
            acknowledgment = executor(operation, step, control, session)
            assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
            expected_digest = raw_blob_digest(output_bytes)
            with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
                persisted_operation = unit_of_work.operations.get_operation(operation_id)
                persisted_step = unit_of_work.operations.get_step(step_id)
            assert persisted_step.checkpoint_ref is not None
            assert persisted_operation.ready_closure_ref is not None
            closure = load_ready_closure(artifact_store, persisted_operation.ready_closure_ref)
            assert closure.outputs[0].artifact_ref.raw_sha256 == expected_digest
            return

        assert crash_barrier == "after-checkpoint"
        checkpoint_ref = _publish_checkpoint_only(
            db_path,
            artifact_store,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        envelope_before = load_checkpoint_envelope(artifact_store, checkpoint_ref)
        session, control, operation, step = _restart_session(
            db_path,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        executor = _wrapped_executor(artifact_store)
        acknowledgment = executor(operation, step, control, session)
        assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
        envelope_after = load_checkpoint_envelope(artifact_store, checkpoint_ref)
        assert envelope_after.job_state == envelope_before.job_state
        with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
            persisted_operation = unit_of_work.operations.get_operation(operation_id)
            persisted_step = unit_of_work.operations.get_step(step_id)
        assert persisted_operation.status is OperationStatus.SUCCEEDED
        assert persisted_step.status is StepStatus.SUCCEEDED
        assert persisted_operation.ready_closure_ref is not None
        return

    assert consumer == "external-effect-stub"
    if crash_barrier == "before-request-checkpoint":
        request_bytes = build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)
        recording_stub = RecordingExternalEffectStub(
            DeterministicExternalEffectStub(request_bytes=request_bytes)
        )
        session, control = _bootstrap_stub_claimed(
            db_path,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
            stub_outcome=StubOutcome.ACCEPTED.value,
        )
        executor = _wrapped_stub_executor(artifact_store, recording_stub=recording_stub)
        with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
            operation = unit_of_work.operations.get_operation(operation_id)
            step = unit_of_work.operations.get_step(step_id)
        acknowledgment = executor(operation, step, control, session)
        assert acknowledgment is ExecutorAcknowledgment.SAFE_HANDOFF
        assert recording_stub.submit_count == 1
        with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
            persisted_step = unit_of_work.operations.get_step(step_id)
        first_checkpoint_ref = persisted_step.checkpoint_ref
        assert first_checkpoint_ref is not None
        session_after_restart, control_after_restart, operation, step = _restart_session(
            db_path,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        second_ack = executor(operation, step, control_after_restart, session_after_restart)
        assert second_ack is ExecutorAcknowledgment.SAFE_HANDOFF
        assert recording_stub.submit_count == 1
        envelope = load_checkpoint_envelope(artifact_store, first_checkpoint_ref)
        assert envelope.job_state["operation_identity"] == _expected_stub_identity()
        return

    assert crash_barrier == "after-request-checkpoint"
    checkpoint_ref = _publish_stub_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    envelope_before = load_checkpoint_envelope(artifact_store, checkpoint_ref)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    request_bytes = build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)
    recording_stub = RecordingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes)
    )
    executor = _wrapped_stub_executor(artifact_store, recording_stub=recording_stub)
    session, control, operation, step = _restart_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    executor(operation, step, control, session)
    envelope_after = load_checkpoint_envelope(artifact_store, checkpoint_ref)
    assert envelope_after.job_state == envelope_before.job_state
    assert recording_stub.submit_count == 0


def test_stub_duplicate_delivery_preserves_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-duplicate.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-duplicate"
    step_id = "step-stub-duplicate"

    checkpoint_ref = _publish_stub_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id="worker-stub-dup-1",
        lease_token="lease-stub-dup-1",
    )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    expected_identity = _expected_stub_identity()
    control = ExecutionControl()
    session = LeaseSession(
        worker_id="worker-stub-dup-1",
        lease_token="lease-stub-dup-1",
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    executor = _wrapped_stub_executor(artifact_store)
    executor(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.repository_operation_id == expected_identity
    envelope = load_checkpoint_envelope(artifact_store, checkpoint_ref)
    assert envelope.job_state["idempotency_key"] == IDEMPOTENCY_KEY_ALPHA
    assert envelope.job_state["operation_identity"] == expected_identity


@pytest.mark.parametrize(("consumer", "job_kind", "expected_version"), PAYLOAD_RELOAD_CONSUMERS)
def test_cross_boundary_payload_reload_resolves_version_and_semantic_input(
    tmp_path: Path,
    consumer: str,
    job_kind: str,
    expected_version: str,
) -> None:
    db_path = tmp_path / f"payload-reload-{consumer}.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = f"operation-payload-{consumer}"
    step_id = f"step-payload-{consumer}"
    worker_id = f"worker-payload-{consumer}"
    lease_token = f"lease-payload-{consumer}"

    if consumer == "pure-compute":
        _bootstrap_claimed(
            db_path,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        expected_key = pure_compute_job_key()
    else:
        _bootstrap_stub_claimed(
            db_path,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        expected_key = external_effect_stub_job_key()

    _session, _control, operation, step = _restart_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    composition = _composition_for_consumer(consumer, artifact_store)
    definition = composition.definition_registry.resolve_runnable(
        expected_key,
        operation.job_contract_version,
    )
    decoded = decode_job_payload(
        definition,
        operation,
        artifact_store,
        composition.decoder_registry,
    )

    assert operation.job_kind == job_kind
    assert operation.job_contract_version == expected_version
    assert step.step_name == expected_key.step_name
    if consumer == "pure-compute":
        assert isinstance(decoded, PureComputePayload)
        assert decoded.seed == SEED_ALPHA
    else:
        assert isinstance(decoded, ExternalEffectStubPayload)
        assert decoded.idempotency_key == IDEMPOTENCY_KEY_ALPHA
        assert decoded.request_body == REQUEST_BODY_ALPHA


@pytest.mark.parametrize(("consumer", "job_kind", "expected_version"), PAYLOAD_RELOAD_CONSUMERS)
@pytest.mark.parametrize(("fault_kind", "inject_fault", "expected_error"), RELOAD_ARTIFACT_FAULTS)
def test_reload_rejects_missing_or_corrupt_checkpoint_without_ready(
    tmp_path: Path,
    consumer: str,
    job_kind: str,
    expected_version: str,
    fault_kind: str,
    inject_fault: Callable[[InMemoryArtifactStore, str], None],
    expected_error: type[Exception],
) -> None:
    del job_kind, expected_version
    db_path = tmp_path / f"artifact-fault-{consumer}-{fault_kind}.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = f"operation-fault-{consumer}-{fault_kind}"
    step_id = f"step-fault-{consumer}-{fault_kind}"
    worker_id = f"worker-fault-{consumer}"
    lease_token = f"lease-fault-{consumer}"

    if consumer == "pure-compute":
        checkpoint_ref = _publish_checkpoint_only(
            db_path,
            artifact_store,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        executor = _wrapped_executor(artifact_store)
    else:
        checkpoint_ref = _publish_stub_checkpoint_only(
            db_path,
            artifact_store,
            operation_id=operation_id,
            step_id=step_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        executor = _wrapped_stub_executor(artifact_store)

    inject_fault(artifact_store, checkpoint_ref.artifact_id)

    session, control, operation, step = _restart_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with pytest.raises(expected_error):
        executor(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_operation.ready_closure_ref is None


@pytest.mark.parametrize("stub_outcome", STUB_RELOAD_OUTCOMES)
@pytest.mark.parametrize(("fault_kind", "inject_fault"), STUB_REQUEST_ARTIFACT_FAULTS)
def test_stub_reload_rejects_missing_or_corrupt_request_artifact_without_ready(
    tmp_path: Path,
    stub_outcome: str,
    fault_kind: str,
    inject_fault: Callable[[InMemoryArtifactStore, str], None],
) -> None:
    db_path = tmp_path / f"stub-request-fault-{stub_outcome}-{fault_kind}.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = f"operation-stub-request-{stub_outcome}-{fault_kind}"
    step_id = f"step-stub-request-{stub_outcome}-{fault_kind}"
    worker_id = f"worker-stub-request-{fault_kind}"
    lease_token = f"lease-stub-request-{fault_kind}"

    _publish_stub_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=stub_outcome,
    )

    request_bytes = build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)
    request_id = request_artifact_id(request_bytes)
    inject_fault(artifact_store, request_id)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    executor = _wrapped_stub_executor(artifact_store)
    with pytest.raises(CheckpointDecodeError):
        executor(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_operation.ready_closure_ref is None
    if fault_kind == "missing-request":
        assert request_id not in artifact_store._artifacts


def _deterministic_jitter(lower: float, _upper: float) -> float:
    return lower


class _MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _noop_pure_compute_executor(
    _operation: OperationRecord,
    _step: StepRecord,
    _control: ExecutionControl,
    _session: object,
) -> ExecutorAcknowledgment:
    return ExecutorAcknowledgment.PUBLISHED


def _ready_recovery(_operation: OperationRecord, _step: StepRecord) -> StartupDisposition:
    return StartupDisposition.READY


class _PureComputeRegistry:
    def resolve(self, key: JobStepKey) -> ClaimedExecutor | None:
        if key == pure_compute_job_key():
            return cast(ClaimedExecutor, _noop_pure_compute_executor)
        return None


@dataclasses.dataclass
class PureComputeRecoveryHarness:
    db_path: Path
    clock: _MutableClock
    capability: RecoveryCapabilityValue = RecoveryCapabilityValue.PURE_RECOMPUTE

    def read_uow(self) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(self.db_path, read_only=True, now=self.clock)

    def write_uow(self) -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(self.db_path, now=self.clock)

    def startup_recovery(self) -> StartupRecovery:
        return build_startup_recovery(
            write_uow_factory=self.write_uow,
            capability_lookup=lambda _job_kind, _step_name: self.capability,
            jitter=_deterministic_jitter,
            now_factory=self.clock,
        )

    def worker_startup(self, *, worker_id: str = "worker-pure-recovery") -> WorkerStartup:
        return WorkerStartup(
            read_uow_factory=self.read_uow,
            write_uow_factory=self.write_uow,
            registry=_PureComputeRegistry(),
            recovery_hook=cast(RecoveryHook, _ready_recovery),
            startup_recovery=self.startup_recovery(),
            observer=lambda _event: None,
            worker_id_factory=lambda: worker_id,
            lease_token_factory=lambda: f"lease-{worker_id}",
        )

    def seed_claimed_running(
        self,
        *,
        operation_id: str = "operation-pure-r5",
        step_id: str = "step-pure-r5",
        worker_id: str = "worker-pure-old",
        lease_token: str = "lease-pure-old",
    ) -> tuple[OperationRecord, StepRecord]:
        operation = operation_record_from_document(_operation_document(operation_id))
        step = step_record_from_document(_step_document(operation.operation_id, step_id))
        with self.write_uow() as unit_of_work:
            store = unit_of_work.operations
            assert (
                store.insert_operation_with_initial_step(operation, step)
                is TransitionDisposition.APPLY
            )
            claimed = OperationLifecycleActions(
                store,
                transaction_now=store.transaction_now,
            ).claim_one(worker_id, lease_token)
            assert claimed is not None
            return claimed

    def advance_past_lease(self, step: StepRecord) -> None:
        if step.lease_expires_at is None:
            raise ValueError("step must have lease_expires_at")
        self.clock.value = step.lease_expires_at + timedelta(seconds=1)

    def seed_running_with_attempt_count(
        self,
        attempt_count: int,
        *,
        operation_id: str = "operation-pure-r5",
        step_id: str = "step-pure-r5",
    ) -> tuple[OperationRecord, StepRecord]:
        operation, step = self.seed_claimed_running(
            operation_id=operation_id,
            step_id=step_id,
        )
        while step.attempt_count < attempt_count:
            self.advance_past_lease(step)
            recovery_startup = self.worker_startup(worker_id=f"worker-recover-{step.attempt_count}")
            assert recovery_startup.startup() is StartupDisposition.RETRYABLE_BLOCK
            with self.read_uow() as unit_of_work:
                retry_not_before = unit_of_work.operations.get_step(step.step_id).retry_not_before
            assert retry_not_before is not None
            self.clock.value = retry_not_before
            claim_startup = self.worker_startup(worker_id=f"worker-claim-{step.attempt_count + 1}")
            assert claim_startup.startup() is StartupDisposition.READY
            work = claim_startup.claim_one()
            assert work is not None
            operation, step = work.operation, work.step
        return operation, step


def _make_pure_compute_harness(tmp_path: Path) -> PureComputeRecoveryHarness:
    db_path = tmp_path / "pure-compute-r5.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    clock = _MutableClock(BASE_TIME)
    initialize_control_db(db_path, now=clock)
    return PureComputeRecoveryHarness(db_path=db_path, clock=clock)


def _apply_cancel_intent(
    db_path: Path,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str,
    lease_token: str,
) -> None:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        store = unit_of_work.operations
        current_operation = store.get_operation(operation_id)
        current_step = store.get_step(step_id)
        transaction_now = store.transaction_now
        operation_after = dataclasses.replace(
            current_operation,
            cancel_requested=True,
            optimistic_version=current_operation.optimistic_version + 1,
            updated_at=transaction_now,
        )
        step_after = dataclasses.replace(
            current_step,
            cancel_requested=True,
            optimistic_version=current_step.optimistic_version + 1,
            updated_at=transaction_now,
        )
        assert OperationLifecycleActions(
            store,
            transaction_now=transaction_now,
        ).cancel_intent(
            operation_after,
            WritePrecondition(
                expected_optimistic_version=current_operation.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
            step_after,
            WritePrecondition(
                expected_optimistic_version=current_step.optimistic_version,
                worker_id=worker_id,
                lease_token=lease_token,
            ),
        ) == (TransitionDisposition.APPLY, TransitionDisposition.APPLY)


def _recovery_session(
    db_path: Path,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str,
    lease_token: str,
    control: ExecutionControl | None = None,
    now: Callable[[], datetime] | None = None,
) -> tuple[LeaseSession, ExecutionControl]:
    session_control = control if control is not None else ExecutionControl()

    def write_uow_factory() -> ControlDbUnitOfWork:
        if now is not None:
            return ControlDbUnitOfWork(db_path, now=now)
        return ControlDbUnitOfWork(db_path)

    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=write_uow_factory,
        control=session_control,
        observer=lambda _event: None,
    )
    return session, session_control


def _publish_pure_compute_checkpoint_via_harness(
    harness: PureComputeRecoveryHarness,
    artifact_store: InMemoryArtifactStore,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str,
    lease_token: str,
) -> ArtifactRef:
    operation, step = harness.seed_claimed_running(
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    output_bytes = compute_pure_compute_output_bytes(SEED_ALPHA)
    digest = raw_blob_digest(output_bytes).value
    output_ref = put_with_built_ref(
        artifact_store,
        output_bytes,
        artifact_id=f"pure-compute-output:{digest}",
        media_type="application/jcs",
    )
    envelope = envelope_for_step(
        key=pure_compute_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=step.attempt_count,
        job_state={
            "output_artifact_id": output_ref.artifact_id,
            "seed": SEED_ALPHA,
        },
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    session, _control = _recovery_session(
        harness.db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        now=harness.clock,
    )
    session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))
    return checkpoint_ref


def test_pure_compute_recovery_port_completes_from_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "pure-recovery-port.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-pure-recovery-port"
    step_id = "step-pure-recovery-port"
    worker_id = "worker-pure-recovery-port"
    lease_token = "lease-pure-recovery-port"

    _publish_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )

    recovery_port = build_pure_compute_recovery_port(artifact_store)
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED

    expected_digest = raw_blob_digest(compute_pure_compute_output_bytes(SEED_ALPHA))
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_step.status is StepStatus.SUCCEEDED
    assert persisted_operation.ready_closure_ref is not None
    closure = load_ready_closure(artifact_store, persisted_operation.ready_closure_ref)
    assert closure.outputs[0].artifact_ref.raw_sha256 == expected_digest


def test_pure_compute_recovery_missing_output_enters_manual_without_recreation(tmp_path: Path) -> None:
    artifact_store = InMemoryArtifactStore()
    harness = _make_pure_compute_harness(tmp_path / "pure-missing-output")
    operation_id = "operation-pure-missing-output"
    step_id = "step-pure-missing-output"
    _publish_pure_compute_checkpoint_via_harness(
        harness,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id="worker-pure-missing-output",
        lease_token="lease-pure-missing-output",
    )
    with harness.read_uow() as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    checkpoint_ref = step.checkpoint_ref
    assert checkpoint_ref is not None
    envelope = load_checkpoint_envelope(artifact_store, checkpoint_ref)
    output_id = envelope.job_state["output_artifact_id"]
    assert isinstance(output_id, str)
    artifact_store._artifacts.pop(output_id)
    before = set(artifact_store._artifacts)

    session, control = _recovery_session(
        harness.db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id="worker-pure-missing-output",
        lease_token="lease-pure-missing-output",
        now=harness.clock,
    )
    outcome = build_pure_compute_recovery_port(artifact_store).recover(
        operation, step, control, session
    )
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert set(artifact_store._artifacts) == before
    with harness.read_uow() as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.ready_closure_ref is None


def test_pure_compute_recovery_port_cancel_before_effect(tmp_path: Path) -> None:
    db_path = tmp_path / "pure-cancel-before.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-pure-cancel-before"
    step_id = "step-pure-cancel-before"
    worker_id = "worker-pure-cancel"
    lease_token = "lease-pure-cancel"

    _bootstrap_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    _apply_cancel_intent(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )

    recovery_port = build_pure_compute_recovery_port(artifact_store)
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.CANCELLED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.CANCELLED
    assert persisted_step.status is StepStatus.CANCELLED
    assert persisted_operation.ready_closure_ref is None
    assert persisted_step.checkpoint_ref is None
    assert artifact_store._artifacts == {}


def test_pure_compute_recovery_port_duplicate_publish_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "pure-recovery-dup.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-pure-recovery-dup"
    step_id = "step-pure-recovery-dup"
    worker_id = "worker-pure-recovery-dup"
    lease_token = "lease-pure-recovery-dup"

    _publish_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )

    recovery_port = build_pure_compute_recovery_port(artifact_store)
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    first_outcome = recovery_port.recover(operation, step, control, session)
    assert first_outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        terminal_operation = unit_of_work.operations.get_operation(operation_id)
        terminal_step = unit_of_work.operations.get_step(step_id)
    closure_ref = terminal_operation.ready_closure_ref
    assert closure_ref is not None

    second_session, second_control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    second_outcome = recovery_port.recover(
        terminal_operation,
        terminal_step,
        second_control,
        second_session,
    )
    assert second_outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.ready_closure_ref == closure_ref


def test_pure_compute_lease_takeover_reclaim_preserves_started_at_and_checkpoint(
    tmp_path: Path,
) -> None:
    artifact_store = InMemoryArtifactStore()
    harness = _make_pure_compute_harness(tmp_path / "pure-takeover")
    db_path = harness.db_path

    operation_id = "operation-pure-takeover"
    step_id = "step-pure-takeover"
    worker_id = "worker-pure-takeover-old"
    lease_token = "lease-pure-takeover-old"

    _publish_pure_compute_checkpoint_via_harness(
        harness,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )

    with harness.read_uow() as unit_of_work:
        step = unit_of_work.operations.get_step(step_id)
        original_started_at = step.started_at
        checkpoint_ref = step.checkpoint_ref
    assert checkpoint_ref is not None

    harness.advance_past_lease(step)
    reclaim_startup = harness.worker_startup(worker_id="worker-pure-takeover-new")
    assert reclaim_startup.startup() is StartupDisposition.RETRYABLE_BLOCK

    with harness.read_uow() as unit_of_work:
        retry_not_before = unit_of_work.operations.get_step(step_id).retry_not_before
        persisted_checkpoint = unit_of_work.operations.get_step(step_id).checkpoint_ref
    assert retry_not_before is not None
    assert persisted_checkpoint == checkpoint_ref

    harness.clock.value = retry_not_before
    assert reclaim_startup.startup() is StartupDisposition.READY
    work = reclaim_startup.claim_one()
    assert work is not None
    assert work.step.attempt_count == step.attempt_count + 1
    assert work.step.started_at == original_started_at
    assert work.step.checkpoint_ref == checkpoint_ref

    recovery_port = build_pure_compute_recovery_port(artifact_store)
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=work.step.worker_id or "worker-pure-takeover-new",
        lease_token=work.step.lease_token or "lease-worker-pure-takeover-new",
        now=harness.clock,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step_after_claim = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step_after_claim, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_operation.ready_closure_ref is not None


def test_pure_compute_retry_does_not_duplicate_successor_or_closure(tmp_path: Path) -> None:
    artifact_store = InMemoryArtifactStore()
    harness = _make_pure_compute_harness(tmp_path / "pure-no-dup-successor")
    db_path = harness.db_path

    operation_id = "operation-pure-no-dup"
    step_id = "step-pure-no-dup"
    worker_id = "worker-pure-no-dup-1"
    lease_token = "lease-pure-no-dup-1"

    _publish_pure_compute_checkpoint_via_harness(
        harness,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )

    with harness.read_uow() as unit_of_work:
        running_step = unit_of_work.operations.get_step(step_id)
    harness.advance_past_lease(running_step)
    assert harness.worker_startup().startup() is StartupDisposition.RETRYABLE_BLOCK

    with harness.read_uow() as unit_of_work:
        retry_step = unit_of_work.operations.get_step(step_id)
    assert retry_step.status is StepStatus.RETRY_WAIT
    assert retry_step.retry_not_before is not None
    harness.clock.value = retry_step.retry_not_before

    reclaim_startup = harness.worker_startup(worker_id="worker-pure-no-dup-2")
    assert reclaim_startup.startup() is StartupDisposition.READY
    work = reclaim_startup.claim_one()
    assert work is not None

    recovery_port = build_pure_compute_recovery_port(artifact_store)
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=work.step.worker_id or "worker-pure-no-dup-2",
        lease_token=work.step.lease_token or "lease-worker-pure-no-dup-2",
        now=harness.clock,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        claimed_step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, claimed_step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED

    expected_digest = raw_blob_digest(compute_pure_compute_output_bytes(SEED_ALPHA))
    with harness.read_uow() as unit_of_work:
        store = unit_of_work.operations
        steps, next_cursor = store.list_steps(operation_id, limit=10)
        persisted_operation = store.get_operation(operation_id)
        persisted_step = store.get_step(step_id)
    assert next_cursor is None
    assert len(steps) == 1
    assert steps[0].step_id == step_id
    assert persisted_step.status is StepStatus.SUCCEEDED
    closure_ref = persisted_operation.ready_closure_ref
    assert closure_ref is not None
    closure = load_ready_closure(artifact_store, closure_ref)
    assert closure.outputs[0].artifact_ref.raw_sha256 == expected_digest

    duplicate_session, duplicate_control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=work.step.worker_id or "worker-pure-no-dup-2",
        lease_token=work.step.lease_token or "lease-worker-pure-no-dup-2",
        now=harness.clock,
    )
    duplicate_outcome = recovery_port.recover(
        persisted_operation,
        persisted_step,
        duplicate_control,
        duplicate_session,
    )
    assert duplicate_outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED
    with harness.read_uow() as unit_of_work:
        assert unit_of_work.operations.get_operation(operation_id).ready_closure_ref == closure_ref
        steps_after, cursor_after = unit_of_work.operations.list_steps(operation_id, limit=10)
    assert cursor_after is None
    assert len(steps_after) == 1


def _stub_request_bytes() -> bytes:
    return build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)


def _stub_job_state_for_identity(
    *,
    request_artifact_id: str,
    operation_identity: str,
    request_fingerprint: str | None = None,
    reconcile_started_at: str = "2026-08-24T12:00:00Z",
) -> dict[str, object]:
    fingerprint = request_fingerprint or compute_request_fingerprint(_stub_request_bytes())
    return {
        "idempotency_key": IDEMPOTENCY_KEY_ALPHA,
        "request_fingerprint": fingerprint,
        "request_artifact_id": request_artifact_id,
        "operation_identity": operation_identity,
        "request_sent": True,
        "reconcile_started_at": reconcile_started_at,
    }


def _artifact_ids(artifact_store: InMemoryArtifactStore) -> frozenset[str]:
    return frozenset(artifact_store._artifacts)


def _assert_external_effect_recovery_invariants(
    *,
    recording_stub: RecordingExternalEffectStub,
    expected_submit_count: int,
    persisted_operation: OperationRecord,
    persisted_step: StepRecord,
    expected_identity: str,
    allow_ready: bool,
    artifact_store: InMemoryArtifactStore | None = None,
    checkpoint_ref: ArtifactRef | None = None,
    preserve_occupancy: bool = True,
) -> None:
    assert recording_stub.submit_count == expected_submit_count
    if allow_ready:
        assert persisted_operation.ready_closure_ref is not None
    else:
        assert persisted_operation.ready_closure_ref is None
    if checkpoint_ref is not None and artifact_store is not None:
        envelope = load_checkpoint_envelope(artifact_store, checkpoint_ref)
        assert envelope.job_state["idempotency_key"] == IDEMPOTENCY_KEY_ALPHA
        assert envelope.job_state["operation_identity"] == expected_identity
    elif persisted_step.checkpoint_ref is not None and artifact_store is not None:
        envelope = load_checkpoint_envelope(artifact_store, persisted_step.checkpoint_ref)
        assert envelope.job_state["idempotency_key"] == IDEMPOTENCY_KEY_ALPHA
        assert envelope.job_state["operation_identity"] == expected_identity
    if preserve_occupancy:
        assert persisted_step.status is StepStatus.RUNNING
        assert persisted_step.worker_id is not None
        assert persisted_step.lease_token is not None


def _publish_stub_post_request_checkpoint(
    db_path: Path,
    artifact_store: InMemoryArtifactStore,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str,
    lease_token: str,
    stub_outcome: str = StubOutcome.ACCEPTED.value,
    reconcile_started_at: str = "2026-08-24T12:00:00Z",
) -> ArtifactRef:
    session, _control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=stub_outcome,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    request_bytes = _stub_request_bytes()
    request_ref = put_with_built_ref(
        artifact_store,
        request_bytes,
        artifact_id=request_artifact_id(request_bytes),
        media_type="application/jcs",
    )
    operation_identity = _expected_stub_identity()
    envelope = envelope_for_step(
        key=external_effect_stub_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=step.attempt_count,
        job_state=_stub_job_state_for_identity(
            request_artifact_id=request_ref.artifact_id,
            operation_identity=operation_identity,
            reconcile_started_at=reconcile_started_at,
        ),
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))
    return checkpoint_ref


def test_external_effect_recovery_port_cancel_before_request(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-recovery-cancel-before.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-recovery-cancel-before"
    step_id = "step-stub-recovery-cancel-before"
    worker_id = "worker-stub-recovery-cancel-before"
    lease_token = "lease-stub-recovery-cancel-before"

    _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    _apply_cancel_intent(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )

    request_bytes = _stub_request_bytes()
    recording_stub = RecordingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes)
    )
    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=recording_stub,
    )
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.CANCELLED
    assert recording_stub.submit_count == 0

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.CANCELLED
    assert persisted_step.status is StepStatus.CANCELLED
    assert persisted_operation.ready_closure_ref is None
    assert persisted_step.checkpoint_ref is None
    assert persisted_operation.repository_operation_id is None
    assert artifact_store._artifacts == {}


def test_external_effect_recovery_port_creates_request_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-recovery-pre-request.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-recovery-pre-request"
    step_id = "step-stub-recovery-pre-request"
    worker_id = "worker-stub-recovery-pre-request"
    lease_token = "lease-stub-recovery-pre-request"

    _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.ACCEPTED.value,
    )

    request_bytes = _stub_request_bytes()
    expected_identity = _expected_stub_identity()
    inner_stub = DeterministicExternalEffectStub(request_bytes=request_bytes)
    recording_stub = RecordingExternalEffectStub(inner_stub)
    polling_stub = PollingExternalEffectStub(recording_stub, default_poll_result=None)
    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=polling_stub,
        now_factory=lambda: BASE_TIME,
    )
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    assert step.checkpoint_ref is None

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.RECONCILE_PENDING
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_step.checkpoint_ref is not None
    _assert_external_effect_recovery_invariants(
        recording_stub=recording_stub,
        expected_submit_count=1,
        persisted_operation=persisted_operation,
        persisted_step=persisted_step,
        expected_identity=expected_identity,
        allow_ready=False,
        artifact_store=artifact_store,
    )


def test_external_effect_recovery_port_accepted_polls_original_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-recovery-accepted-poll.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-recovery-accepted-poll"
    step_id = "step-stub-recovery-accepted-poll"
    worker_id = "worker-stub-recovery-accepted-poll"
    lease_token = "lease-stub-recovery-accepted-poll"

    request_bytes = _stub_request_bytes()
    expected_identity = _expected_stub_identity()
    inner_stub = DeterministicExternalEffectStub(request_bytes=request_bytes)
    polling_stub = PollingExternalEffectStub(inner_stub, default_poll_result=None)
    polling_stub.configure_poll(expected_identity, [None, StubOutcome.CONFIRMED])
    recording_stub = RecordingExternalEffectStub(polling_stub)

    session, control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.ACCEPTED.value,
    )
    handler = build_external_effect_stub_handler(artifact_store, external_stub=recording_stub)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    assert handler(operation, step, control, session) is ExecutorAcknowledgment.SAFE_HANDOFF
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        step_after_handler = unit_of_work.operations.get_step(step_id)
    assert step_after_handler.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(artifact_store, step_after_handler.checkpoint_ref)
    started_at = envelope.job_state["reconcile_started_at"]
    assert isinstance(started_at, str)
    reconcile_started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=polling_stub,
        now_factory=lambda: reconcile_started_at + timedelta(seconds=1),
    )
    recovery_session, recovery_control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        control=control,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    first_outcome = recovery_port.recover(operation, step, recovery_control, recovery_session)
    assert first_outcome.disposition is RecoveryOutcomeDisposition.RECONCILE_PENDING
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        pending_operation = unit_of_work.operations.get_operation(operation_id)
        pending_step = unit_of_work.operations.get_step(step_id)
    _assert_external_effect_recovery_invariants(
        recording_stub=recording_stub,
        expected_submit_count=1,
        persisted_operation=pending_operation,
        persisted_step=pending_step,
        expected_identity=expected_identity,
        allow_ready=False,
        artifact_store=artifact_store,
    )

    second_outcome = recovery_port.recover(operation, step, recovery_control, recovery_session)
    assert second_outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_step.status is StepStatus.SUCCEEDED
    assert persisted_operation.repository_operation_id == expected_identity
    _assert_external_effect_recovery_invariants(
        recording_stub=recording_stub,
        expected_submit_count=1,
        persisted_operation=persisted_operation,
        persisted_step=persisted_step,
        expected_identity=expected_identity,
        allow_ready=True,
        artifact_store=artifact_store,
        preserve_occupancy=False,
    )


def test_external_effect_recovery_port_confirmed_from_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-recovery-confirmed-checkpoint.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-recovery-confirmed-checkpoint"
    step_id = "step-stub-recovery-confirmed-checkpoint"
    worker_id = "worker-stub-recovery-confirmed-checkpoint"
    lease_token = "lease-stub-recovery-confirmed-checkpoint"

    request_bytes = _stub_request_bytes()
    expected_identity = _expected_stub_identity()
    polling_stub = PollingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes),
        default_poll_result=StubOutcome.CONFIRMED,
    )
    recording_stub = RecordingExternalEffectStub(polling_stub)

    _publish_stub_post_request_checkpoint(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.CONFIRMED.value,
    )

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=recording_stub,
        now_factory=lambda: BASE_TIME,
    )
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED
    assert recording_stub.submit_count == 0

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.repository_operation_id == expected_identity
    _assert_external_effect_recovery_invariants(
        recording_stub=recording_stub,
        expected_submit_count=0,
        persisted_operation=persisted_operation,
        persisted_step=persisted_step,
        expected_identity=expected_identity,
        allow_ready=True,
        artifact_store=artifact_store,
        preserve_occupancy=False,
    )


def test_external_effect_recovery_port_unknown_manual_no_false_ready(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-recovery-unknown-manual.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-recovery-unknown-manual"
    step_id = "step-stub-recovery-unknown-manual"
    worker_id = "worker-stub-recovery-unknown-manual"
    lease_token = "lease-stub-recovery-unknown-manual"

    request_bytes = _stub_request_bytes()
    expected_identity = _expected_stub_identity()
    polling_stub = PollingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes),
        default_poll_result=StubOutcome.UNKNOWN,
    )

    _publish_stub_post_request_checkpoint(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.UNKNOWN.value,
    )

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=polling_stub,
        now_factory=lambda: BASE_TIME,
    )
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert outcome.diagnostic_code == DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.RUNNING
    _assert_external_effect_recovery_invariants(
        recording_stub=RecordingExternalEffectStub(polling_stub),
        expected_submit_count=0,
        persisted_operation=persisted_operation,
        persisted_step=persisted_step,
        expected_identity=expected_identity,
        allow_ready=False,
        artifact_store=artifact_store,
    )


def test_external_effect_recovery_port_reconcile_budget_exhausted(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-recovery-budget-exhausted.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-recovery-budget-exhausted"
    step_id = "step-stub-recovery-budget-exhausted"
    worker_id = "worker-stub-recovery-budget-exhausted"
    lease_token = "lease-stub-recovery-budget-exhausted"

    request_bytes = _stub_request_bytes()
    expected_identity = _expected_stub_identity()
    polling_stub = PollingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes),
        default_poll_result=None,
    )
    recording_stub = RecordingExternalEffectStub(polling_stub)
    started_at = BASE_TIME.isoformat().replace("+00:00", "Z")

    _publish_stub_post_request_checkpoint(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.ACCEPTED.value,
        reconcile_started_at=started_at,
    )

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=recording_stub,
        now_factory=lambda: BASE_TIME + timedelta(seconds=RECONCILE_SESSION_BUDGET_SECONDS),
    )
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert outcome.diagnostic_code == DIAGNOSTIC_RECONCILE_TIMEOUT
    assert recording_stub.submit_count == 0

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    _assert_external_effect_recovery_invariants(
        recording_stub=recording_stub,
        expected_submit_count=0,
        persisted_operation=persisted_operation,
        persisted_step=persisted_step,
        expected_identity=expected_identity,
        allow_ready=False,
        artifact_store=artifact_store,
    )


def test_external_effect_recovery_port_cancel_after_request_continues_reconcile(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stub-recovery-cancel-after.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-recovery-cancel-after"
    step_id = "step-stub-recovery-cancel-after"
    worker_id = "worker-stub-recovery-cancel-after"
    lease_token = "lease-stub-recovery-cancel-after"

    request_bytes = _stub_request_bytes()
    expected_identity = _expected_stub_identity()
    polling_stub = PollingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes),
        default_poll_result=None,
    )
    polling_stub.configure_poll(expected_identity, [None, StubOutcome.CONFIRMED])
    recording_stub = RecordingExternalEffectStub(polling_stub)

    session, control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.ACCEPTED.value,
    )
    handler = build_external_effect_stub_handler(artifact_store, external_stub=recording_stub)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    assert handler(operation, step, control, session) is ExecutorAcknowledgment.SAFE_HANDOFF
    assert recording_stub.submit_count == 1

    _apply_cancel_intent(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        step_after_cancel = unit_of_work.operations.get_step(step_id)
    assert step_after_cancel.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(artifact_store, step_after_cancel.checkpoint_ref)
    started_at = envelope.job_state["reconcile_started_at"]
    assert isinstance(started_at, str)
    reconcile_started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=polling_stub,
        now_factory=lambda: reconcile_started_at + timedelta(seconds=1),
    )
    recovery_session, recovery_control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        control=control,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    assert operation.cancel_requested is True
    assert step.cancel_requested is True

    first_outcome = recovery_port.recover(operation, step, recovery_control, recovery_session)
    assert first_outcome.disposition is RecoveryOutcomeDisposition.RECONCILE_PENDING
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        pending_operation = unit_of_work.operations.get_operation(operation_id)
        pending_step = unit_of_work.operations.get_step(step_id)
    assert pending_operation.status is OperationStatus.RUNNING
    assert pending_step.status is StepStatus.RUNNING
    _assert_external_effect_recovery_invariants(
        recording_stub=recording_stub,
        expected_submit_count=1,
        persisted_operation=pending_operation,
        persisted_step=pending_step,
        expected_identity=expected_identity,
        allow_ready=False,
        artifact_store=artifact_store,
    )

    second_outcome = recovery_port.recover(operation, step, recovery_control, recovery_session)
    assert second_outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_operation.ready_closure_ref is not None
    assert persisted_operation.repository_operation_id == expected_identity


def test_external_effect_recovery_port_post_request_no_artifact_recreation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "stub-recovery-no-artifact-recreation.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-recovery-no-artifact-recreation"
    step_id = "step-stub-recovery-no-artifact-recreation"
    worker_id = "worker-stub-recovery-no-artifact-recreation"
    lease_token = "lease-stub-recovery-no-artifact-recreation"

    request_bytes = _stub_request_bytes()
    request_id = request_artifact_id(request_bytes)
    expected_identity = _expected_stub_identity()
    polling_stub = PollingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes),
        default_poll_result=StubOutcome.CONFIRMED,
    )
    recording_stub = RecordingExternalEffectStub(polling_stub)

    _publish_stub_post_request_checkpoint(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.ACCEPTED.value,
    )
    request_ids_before = _artifact_ids(artifact_store)
    assert request_id in request_ids_before

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=recording_stub,
        now_factory=lambda: BASE_TIME,
    )
    session, control = _recovery_session(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED

    request_ids_after = _artifact_ids(artifact_store)
    assert request_id in request_ids_after
    assert request_ids_before <= request_ids_after
    new_ids = request_ids_after - request_ids_before
    assert request_id not in new_ids
    assert recording_stub.submit_count == 0

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    _assert_external_effect_recovery_invariants(
        recording_stub=recording_stub,
        expected_submit_count=0,
        persisted_operation=persisted_operation,
        persisted_step=persisted_step,
        expected_identity=expected_identity,
        allow_ready=True,
        artifact_store=artifact_store,
        preserve_occupancy=False,
    )
