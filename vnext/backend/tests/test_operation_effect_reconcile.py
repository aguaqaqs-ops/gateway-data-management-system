"""External-effect identity reconcile adapter tests (P4-R5-S2b owner)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gateway_backend.application.checkpoints import (
    envelope_for_step,
    load_checkpoint_envelope,
    make_checkpoint_step_builder,
    prepare_step_checkpoint,
)
from tests.support.external_effect_stub import (
    DeterministicExternalEffectStub,
    ExternalEffectStub,
    RecordingExternalEffectStub,
    StubOutcome,
    build_request_bytes,
    compute_operation_identity,
    request_artifact_id,
)
from gateway_backend.application.recovery import (
    DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    ExternalEffectReconcilePhase,
    ExternalEffectRequestIdentity,
    JOB_STATE_IDEMPOTENCY_KEY,
    JOB_STATE_OPERATION_IDENTITY,
    JOB_STATE_REQUEST_FINGERPRINT,
    JOB_STATE_REQUEST_SENT,
    RecoveryOutcome,
    RecoveryOutcomeDisposition,
    classify_external_effect_phase,
    compute_request_fingerprint,
    validate_external_effect_identity,
)
from tests.support.synthetic_jobs import (
    PollingExternalEffectStub,
    build_external_effect_stub_handler,
    build_external_effect_stub_recovery_port,
    external_effect_stub_job_key,
)
from gateway_backend.artifacts import InMemoryArtifactStore, put_with_built_ref
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
from gateway_backend.operations.worker import ExecutionControl, ExecutorAcknowledgment
from tests.support.runtime_settings import make_operation_worker_settings

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
IDEMPOTENCY_KEY_ALPHA = "idem-alpha"
REQUEST_BODY_ALPHA = "request-alpha"


def _request_bytes() -> bytes:
    return build_request_bytes(IDEMPOTENCY_KEY_ALPHA, REQUEST_BODY_ALPHA)


def _expected_identity() -> str:
    request_bytes = _request_bytes()
    return compute_operation_identity(IDEMPOTENCY_KEY_ALPHA, request_bytes)


def _stub_operation_document(operation_id: str, *, stub_outcome: str) -> dict[str, object]:
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
        "job_contract_version": "backend-vnext/synthetic/stub/v1",
        "job_kind": "synthetic.external-effect-stub",
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
        "step_name": "request",
        "updated_at": "2026-08-24T12:00:00Z",
        "worker_id": None,
    }


def _bootstrap_stub_claimed(
    db_path: Path,
    *,
    operation_id: str,
    step_id: str,
    worker_id: str = "worker-reconcile-1",
    lease_token: str = "lease-reconcile-1",
    stub_outcome: str = StubOutcome.ACCEPTED.value,
) -> tuple[LeaseSession, ExecutionControl]:
    bootstrap_control_database(make_operation_worker_settings(db_path.parent, control_db_path=db_path))
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


def _job_state_for_identity(
    *,
    request_artifact_id: str,
    operation_identity: str,
    request_fingerprint: str | None = None,
) -> dict[str, object]:
    fingerprint = request_fingerprint or compute_request_fingerprint(_request_bytes())
    return {
        JOB_STATE_IDEMPOTENCY_KEY: IDEMPOTENCY_KEY_ALPHA,
        JOB_STATE_REQUEST_FINGERPRINT: fingerprint,
        "request_artifact_id": request_artifact_id,
        JOB_STATE_OPERATION_IDENTITY: operation_identity,
        JOB_STATE_REQUEST_SENT: True,
    }


IDENTITY_VALIDATION_CASES: tuple[
    tuple[str, dict[str, object], str, type[ExternalEffectRequestIdentity] | RecoveryOutcomeDisposition],
    ...,
] = (
    (
        "matching_identity",
        _job_state_for_identity(
            request_artifact_id=request_artifact_id(_request_bytes()),
            operation_identity=_expected_identity(),
        ),
        _expected_identity(),
        ExternalEffectRequestIdentity,
    ),
    (
        "idempotency_mismatch",
        {
            ** _job_state_for_identity(
                request_artifact_id=request_artifact_id(_request_bytes()),
                operation_identity=_expected_identity(),
            ),
            JOB_STATE_IDEMPOTENCY_KEY: "other-key",
        },
        _expected_identity(),
        RecoveryOutcomeDisposition.MANUAL_RECOVERY,
    ),
    (
        "fingerprint_mismatch",
        _job_state_for_identity(
            request_artifact_id=request_artifact_id(_request_bytes()),
            operation_identity=_expected_identity(),
            request_fingerprint="deadbeef",
        ),
        _expected_identity(),
        RecoveryOutcomeDisposition.MANUAL_RECOVERY,
    ),
    (
        "operation_identity_mismatch",
        _job_state_for_identity(
            request_artifact_id=request_artifact_id(_request_bytes()),
            operation_identity="synthetic-stub-op:wrong",
        ),
        _expected_identity(),
        RecoveryOutcomeDisposition.MANUAL_RECOVERY,
    ),
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "job_state", "expected_identity", "expected_type"),
    IDENTITY_VALIDATION_CASES,
)
def test_validate_external_effect_identity_matrix(
    name: str,
    job_state: dict[str, object],
    expected_identity: str,
    expected_type: type[ExternalEffectRequestIdentity] | RecoveryOutcomeDisposition,
) -> None:
    del name
    result = validate_external_effect_identity(
        idempotency_key=IDEMPOTENCY_KEY_ALPHA,
        request_bytes=_request_bytes(),
        job_state=job_state,
        expected_operation_identity=expected_identity,
    )
    if expected_type is ExternalEffectRequestIdentity:
        assert isinstance(result, ExternalEffectRequestIdentity)
        assert result.repository_operation_id == expected_identity
        assert result.idempotency_key == IDEMPOTENCY_KEY_ALPHA
    else:
        assert isinstance(result, RecoveryOutcome)
        assert result.disposition is expected_type
        assert result.diagnostic_code == DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH


@pytest.mark.unit
def test_classify_external_effect_phase_matrix() -> None:
    request_bytes = _request_bytes()
    request_ref_id = request_artifact_id(request_bytes)
    job_state = _job_state_for_identity(
        request_artifact_id=request_ref_id,
        operation_identity=_expected_identity(),
    )
    assert (
        classify_external_effect_phase(checkpoint_ref=None, job_state=None)
        is ExternalEffectReconcilePhase.PRE_REQUEST
    )
    assert (
        classify_external_effect_phase(checkpoint_ref=object(), job_state=job_state)  # type: ignore[arg-type]
        is ExternalEffectReconcilePhase.POST_REQUEST
    )


@pytest.mark.integration
def test_recovery_port_non_polling_stub_fails_closed_without_confirmed_fallback(
    tmp_path: Path,
) -> None:
    class SubmitOnlyStub(ExternalEffectStub):
        def submit(self, _idempotency_key: str, _request_ref: object) -> str:
            return _expected_identity()

    db_path = tmp_path / "non-polling-reconcile.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-non-polling-reconcile"
    step_id = "step-non-polling-reconcile"
    session, control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    request_bytes = _request_bytes()
    request_ref = put_with_built_ref(
        artifact_store,
        request_bytes,
        artifact_id=request_artifact_id(request_bytes),
        media_type="application/jcs",
    )
    envelope = envelope_for_step(
        key=external_effect_stub_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=step.attempt_count,
        job_state=_job_state_for_identity(
            request_artifact_id=request_ref.artifact_id,
            operation_identity=_expected_identity(),
        ),
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    before = set(artifact_store._artifacts)
    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=SubmitOnlyStub(),
    )
    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert set(artifact_store._artifacts) == before
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.ready_closure_ref is None


@pytest.mark.integration
def test_accepted_handler_then_recovery_polls_without_resubmit(tmp_path: Path) -> None:
    db_path = tmp_path / "accepted-poll.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-accepted-poll"
    step_id = "step-accepted-poll"
    worker_id = "worker-accepted-poll"
    lease_token = "lease-accepted-poll"

    request_bytes = _request_bytes()
    inner_stub = DeterministicExternalEffectStub(request_bytes=request_bytes)
    polling_stub = PollingExternalEffectStub(inner_stub, default_poll_result=None)
    recording_stub = RecordingExternalEffectStub(polling_stub)
    expected_identity = _expected_identity()
    polling_stub.configure_poll(expected_identity, [None, StubOutcome.CONFIRMED])

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
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)
    assert step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(artifact_store, step.checkpoint_ref)
    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=polling_stub,
    )
    recovery_session = LeaseSession(
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

    first_outcome = recovery_port.recover(operation, step, control, recovery_session)
    assert first_outcome.disposition is RecoveryOutcomeDisposition.RECONCILE_PENDING
    assert recording_stub.submit_count == 1

    second_outcome = recovery_port.recover(operation, step, control, recovery_session)
    assert second_outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED
    assert recording_stub.submit_count == 1

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_step.status is StepStatus.SUCCEEDED
    assert persisted_operation.repository_operation_id == expected_identity
    assert persisted_operation.ready_closure_ref is not None


@pytest.mark.integration
def test_confirmed_reload_recovery_polls_without_resubmit(tmp_path: Path) -> None:
    db_path = tmp_path / "confirmed-reload.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-confirmed-reload"
    step_id = "step-confirmed-reload"
    worker_id = "worker-confirmed-reload"
    lease_token = "lease-confirmed-reload"

    request_bytes = _request_bytes()
    inner_stub = DeterministicExternalEffectStub(request_bytes=request_bytes)
    polling_stub = PollingExternalEffectStub(inner_stub, default_poll_result=StubOutcome.CONFIRMED)
    recording_stub = RecordingExternalEffectStub(polling_stub)

    session, control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        worker_id=worker_id,
        lease_token=lease_token,
        stub_outcome=StubOutcome.CONFIRMED.value,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    request_ref = put_with_built_ref(
        artifact_store,
        request_bytes,
        artifact_id=request_artifact_id(request_bytes),
        media_type="application/jcs",
    )
    operation_identity = _expected_identity()
    envelope = envelope_for_step(
        key=external_effect_stub_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=step.attempt_count,
        job_state=_job_state_for_identity(
            request_artifact_id=request_ref.artifact_id,
            operation_identity=operation_identity,
        ),
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=recording_stub,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED
    assert recording_stub.submit_count == 0

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.repository_operation_id == operation_identity
    assert persisted_operation.ready_closure_ref is not None


@pytest.mark.integration
def test_unknown_poll_returns_manual_recovery_without_ready(tmp_path: Path) -> None:
    db_path = tmp_path / "unknown-poll.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-unknown-poll"
    step_id = "step-unknown-poll"

    request_bytes = _request_bytes()
    polling_stub = PollingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes),
        default_poll_result=StubOutcome.UNKNOWN,
    )
    recording_stub = RecordingExternalEffectStub(polling_stub)

    session, control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        stub_outcome=StubOutcome.UNKNOWN.value,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    request_ref = put_with_built_ref(
        artifact_store,
        request_bytes,
        artifact_id=request_artifact_id(request_bytes),
        media_type="application/jcs",
    )
    operation_identity = _expected_identity()
    envelope = envelope_for_step(
        key=external_effect_stub_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=step.attempt_count,
        job_state=_job_state_for_identity(
            request_artifact_id=request_ref.artifact_id,
            operation_identity=operation_identity,
        ),
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=polling_stub,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert outcome.diagnostic_code == DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED
    assert recording_stub.submit_count == 0

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_operation.ready_closure_ref is None


@pytest.mark.integration
def test_fingerprint_mismatch_returns_manual_without_resubmit(tmp_path: Path) -> None:
    db_path = tmp_path / "fingerprint-mismatch.sqlite3"
    artifact_store = InMemoryArtifactStore()
    operation_id = "operation-fingerprint-mismatch"
    step_id = "step-fingerprint-mismatch"

    request_bytes = _request_bytes()
    polling_stub = PollingExternalEffectStub(
        DeterministicExternalEffectStub(request_bytes=request_bytes),
        default_poll_result=StubOutcome.CONFIRMED,
    )
    recording_stub = RecordingExternalEffectStub(polling_stub)

    session, control = _bootstrap_stub_claimed(
        db_path,
        operation_id=operation_id,
        step_id=step_id,
        stub_outcome=StubOutcome.CONFIRMED.value,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    request_ref = put_with_built_ref(
        artifact_store,
        request_bytes,
        artifact_id=request_artifact_id(request_bytes),
        media_type="application/jcs",
    )
    operation_identity = _expected_identity()
    envelope = envelope_for_step(
        key=external_effect_stub_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=step.attempt_count,
        job_state=_job_state_for_identity(
            request_artifact_id=request_ref.artifact_id,
            operation_identity=operation_identity,
            request_fingerprint="mismatched-fingerprint",
        ),
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))

    recovery_port = build_external_effect_stub_recovery_port(
        artifact_store,
        external_stub=recording_stub,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    outcome = recovery_port.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert outcome.diagnostic_code == DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH
    assert recording_stub.submit_count == 0

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
    assert persisted_operation.ready_closure_ref is None
