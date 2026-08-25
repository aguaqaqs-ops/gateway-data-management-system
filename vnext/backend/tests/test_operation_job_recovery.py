"""Cross-boundary synthetic job reload and fault-matrix tests (P4-R4-S3c owner).

Fault matrix ownership (plan §13):

| Boundary | Authoritative owner |
|---|---|
| payload reload | ``test_cross_boundary_payload_reload_resolves_version_and_semantic_input`` |
| checkpoint round-trip | ``test_operation_checkpoint_contracts`` (S2a); reload completion here |
| artifact missing/corrupt | ``test_reload_rejects_missing_or_corrupt_checkpoint_without_ready`` |
| closure set-once | ``test_operation_worker_integration`` (integration); S2a unit |
| duplicate delivery | ``test_duplicate_delivery_*``, ``test_terminal_publication_is_idempotent_on_duplicate`` |
| cancel before request | ``test_operation_job_synthetic`` (S3b) |
| cancel after request/unknown | ``test_operation_job_synthetic`` + ``test_stub_unknown_reload_does_not_resubmit`` |
| crash before/after CAS | pure/stub tests here; process SIGKILL in ``test_operation_worker_process`` |
| stale CAS | ``test_operation_worker_integration`` (file-backed LeaseSession) |

Process crash tests prove durable readback only; expired RUNNING lease is not R5 takeover.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from gateway_backend.application.synthetic_jobs import (
    EXTERNAL_EFFECT_STUB_JOB_KIND,
    EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION,
    EXTERNAL_EFFECT_STUB_STEP_NAME,
    ExternalEffectStubPayload,
    PURE_COMPUTE_JOB_KIND,
    PURE_COMPUTE_PAYLOAD_VERSION,
    PURE_COMPUTE_STEP_NAME,
    PureComputePayload,
    compute_pure_compute_output_bytes,
    external_effect_stub_composition_bundle,
    external_effect_stub_job_key,
    pure_compute_composition_bundle,
    pure_compute_job_key,
)
from gateway_backend.artifacts import InMemoryArtifactStore, put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.operations.contracts import OperationRecord, StepRecord
from gateway_backend.bootstrap.operation_worker import bootstrap_control_database
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
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
from gateway_backend.operations.state import validate_operation_transition
from gateway_backend.operations.worker import ClaimedExecutor, ExecutionControl, ExecutorAcknowledgment
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


def test_stub_reload_after_request_sent_completes_confirmed(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-reload.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-reload"
    step_id = "step-stub-reload"
    worker_id = "worker-stub-reload-1"
    lease_token = "lease-stub-reload-1"

    _publish_stub_checkpoint_only(
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
    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_step.status is StepStatus.SUCCEEDED
    assert persisted_operation.repository_operation_id == _expected_stub_identity()


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


def test_stub_unknown_reload_does_not_resubmit(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-unknown-reload.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-unknown"
    step_id = "step-stub-unknown"

    _publish_stub_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id="worker-stub-unknown-1",
        lease_token="lease-stub-unknown-1",
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
    control = ExecutionControl()
    session = LeaseSession(
        worker_id="worker-stub-unknown-1",
        lease_token="lease-stub-unknown-1",
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )

    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
    assert recording_stub.submit_count == 0

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert persisted_operation.repository_operation_id == _expected_stub_identity()
    assert persisted_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(artifact_store, persisted_step.checkpoint_ref)
    assert envelope.job_state["operation_identity"] == _expected_stub_identity()


def test_stub_crash_before_checkpoint_retries_request(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-crash-before.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-crash-before"
    step_id = "step-stub-crash-before"

    request_bytes = build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)
    recording_stub = RecordingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes)
    )
    session, control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id="worker-stub-crash-1",
        lease_token="lease-stub-crash-1",
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

    session_after_restart = LeaseSession(
        worker_id="worker-stub-crash-1",
        lease_token="lease-stub-crash-1",
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    second_ack = executor(operation, step, control, session_after_restart)
    assert second_ack is ExecutorAcknowledgment.SAFE_HANDOFF
    assert recording_stub.submit_count == 1

    envelope = load_checkpoint_envelope(artifact_store, first_checkpoint_ref)
    assert envelope.job_state["operation_identity"] == _expected_stub_identity()


def test_stub_crash_after_checkpoint_preserves_job_state(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-crash-after.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-stub-crash-after"
    step_id = "step-stub-crash-after"

    checkpoint_ref = _publish_stub_checkpoint_only(
        db_path,
        artifact_store,
        operation_id=operation_id,
        step_id=step_id,
        worker_id="worker-stub-crash-after-1",
        lease_token="lease-stub-crash-after-1",
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
    control = ExecutionControl()
    session = LeaseSession(
        worker_id="worker-stub-crash-after-1",
        lease_token="lease-stub-crash-after-1",
        operation_id=operation_id,
        step_id=step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    executor(operation, step, control, session)

    envelope_after = load_checkpoint_envelope(artifact_store, checkpoint_ref)
    assert envelope_after.job_state == envelope_before.job_state
    assert recording_stub.submit_count == 0


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


def test_pure_compute_crash_before_checkpoint_preserves_semantic_output(tmp_path: Path) -> None:
    """Simulate artifact write before checkpoint CAS; reload must not change semantic output."""
    db_path = tmp_path / "pure-crash-before.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-pure-crash-before"
    step_id = "step-pure-crash-before"
    worker_id = "worker-pure-crash-before"
    lease_token = "lease-pure-crash-before"

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


def test_pure_compute_crash_after_checkpoint_completes_terminal(tmp_path: Path) -> None:
    """Checkpoint durable readback completes terminal publication; not R5 takeover."""
    db_path = tmp_path / "pure-crash-after.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-pure-crash-after"
    step_id = "step-pure-crash-after"
    worker_id = "worker-pure-crash-after"
    lease_token = "lease-pure-crash-after"

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
