"""Pure-compute synthetic job determinism and publication tests."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.checkpoints import (
    load_checkpoint_envelope,
    load_ready_closure,
)
from tests.support.external_effect_stub import (
    ExternalEffectStub,
    StubOutcome,
    build_request_bytes,
    compute_operation_identity,
)
from gateway_backend.application.job_definitions import build_job_worker_composition
from tests.support.synthetic_jobs import (
    EXTERNAL_EFFECT_STUB_JOB_KIND,
    EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION,
    EXTERNAL_EFFECT_STUB_STEP_NAME,
    PURE_COMPUTE_JOB_KIND,
    PURE_COMPUTE_PAYLOAD_VERSION,
    PURE_COMPUTE_STEP_NAME,
    build_external_effect_stub_handler,
    build_pure_compute_handler,
    compute_pure_compute_output_bytes,
    external_effect_stub_composition_bundle,
    external_effect_stub_job_key,
    pure_compute_composition_bundle,
    pure_compute_job_key,
)
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, put_with_built_ref
from gateway_backend.artifacts.serialize import artifact_ref_to_dict
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
from gateway_backend.operations.state import WritePrecondition
from gateway_backend.operations.worker import ClaimedExecutor, ExecutionControl, ExecutorAcknowledgment
from tests.support.runtime_settings import make_operation_worker_settings
from gateway_backend.bootstrap.operation_worker import bootstrap_control_database
from tests.support.artifact_staging import open_local_store, reopen_local_store, staging_root

pytestmark = pytest.mark.unit

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
LEASE_EXPIRES_AT = BASE_TIME + timedelta(seconds=30)
SEED_ALPHA = "alpha"
SEED_BETA = "beta"
IDEMPOTENCY_KEY_ALPHA = "idem-alpha"
IDEMPOTENCY_KEY_BETA = "idem-beta"
REQUEST_BODY_ALPHA = "request-alpha"
REQUEST_BODY_BETA = "request-beta"

STUB_OUTCOME_TERMINAL_EXPECTATIONS: tuple[
    tuple[StubOutcome, OperationStatus, StepStatus, bool, ExecutorAcknowledgment],
    ...,
] = (
    (StubOutcome.CONFIRMED, OperationStatus.SUCCEEDED, StepStatus.SUCCEEDED, True, ExecutorAcknowledgment.PUBLISHED),
    (StubOutcome.UNKNOWN, OperationStatus.RUNNING, StepStatus.RUNNING, False, ExecutorAcknowledgment.SAFE_HANDOFF),
)

PAYLOAD_BINDING_PARITY: tuple[tuple[str, str], ...] = (
    ("pure-compute", "inline"),
    ("pure-compute", "ref"),
    ("external-effect-stub", "inline"),
    ("external-effect-stub", "ref"),
)


def _operation_document(operation_id: str, *, seed: str = SEED_ALPHA) -> dict[str, object]:
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
        "job_payload": {"seed": seed},
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


def _claimed_pure_compute_session(
    db_path: Path,
    *,
    operation_id: str = "operation-pure-1",
    step_id: str = "step-pure-1",
    worker_id: str = "worker-pure-1",
    lease_token: str = "lease-pure-1",
    seed: str = SEED_ALPHA,
) -> tuple[LeaseSession, ExecutionControl, ControlDbUnitOfWork]:
    bootstrap_control_database(make_operation_worker_settings(db_path.parent, control_db_path=db_path))
    operation = operation_record_from_document(_operation_document(operation_id, seed=seed))
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
    return session, control, ControlDbUnitOfWork(db_path, read_only=True)


def _pure_compute_payload_ref(
    store: InMemoryArtifactStore,
    *,
    seed: str = SEED_ALPHA,
) -> ArtifactRef:
    payload_bytes = canonicalize_json_value({"seed": seed})
    return put_with_built_ref(
        store,
        payload_bytes,
        artifact_id="pure-compute-payload",
        media_type="application/json",
    )


def _stub_payload_ref(
    store: InMemoryArtifactStore,
    *,
    idempotency_key: str = IDEMPOTENCY_KEY_ALPHA,
    request_body: str = REQUEST_BODY_ALPHA,
    stub_outcome: str = StubOutcome.CONFIRMED.value,
) -> ArtifactRef:
    payload_bytes = canonicalize_json_value(
        {
            "idempotency_key": idempotency_key,
            "request_body": request_body,
            "stub_outcome": stub_outcome,
        }
    )
    return put_with_built_ref(
        store,
        payload_bytes,
        artifact_id="external-effect-stub-payload",
        media_type="application/json",
    )


def _claimed_pure_compute_session_with_binding(
    db_path: Path,
    artifact_store: InMemoryArtifactStore,
    *,
    binding: str,
    operation_id: str = "operation-pure-parity",
    step_id: str = "step-pure-parity",
    worker_id: str = "worker-pure-parity",
    lease_token: str = "lease-pure-parity",
    seed: str = SEED_ALPHA,
) -> tuple[LeaseSession, ExecutionControl, ControlDbUnitOfWork]:
    bootstrap_control_database(make_operation_worker_settings(db_path.parent, control_db_path=db_path))
    document = dict(_operation_document(operation_id, seed=seed))
    if binding == "ref":
        payload_ref = _pure_compute_payload_ref(artifact_store, seed=seed)
        document["job_payload"] = None
        document["job_payload_ref"] = artifact_ref_to_dict(payload_ref)
    operation = operation_record_from_document(document)
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
    return session, control, ControlDbUnitOfWork(db_path, read_only=True)


def _claimed_stub_session_with_binding(
    db_path: Path,
    artifact_store: InMemoryArtifactStore,
    *,
    binding: str,
    operation_id: str = "operation-stub-parity",
    step_id: str = "step-stub-parity",
    worker_id: str = "worker-stub-parity",
    lease_token: str = "lease-stub-parity",
    idempotency_key: str = IDEMPOTENCY_KEY_ALPHA,
    request_body: str = REQUEST_BODY_ALPHA,
    stub_outcome: str = StubOutcome.CONFIRMED.value,
) -> tuple[LeaseSession, ExecutionControl, ControlDbUnitOfWork]:
    bootstrap_control_database(make_operation_worker_settings(db_path.parent, control_db_path=db_path))
    document = dict(
        _stub_operation_document(
            operation_id,
            idempotency_key=idempotency_key,
            request_body=request_body,
            stub_outcome=stub_outcome,
        )
    )
    if binding == "ref":
        payload_ref = _stub_payload_ref(
            artifact_store,
            idempotency_key=idempotency_key,
            request_body=request_body,
            stub_outcome=stub_outcome,
        )
        document["job_payload"] = None
        document["job_payload_ref"] = artifact_ref_to_dict(payload_ref)
    operation = operation_record_from_document(document)
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
    return session, control, ControlDbUnitOfWork(db_path, read_only=True)


def _wrapped_pure_compute_executor(store: InMemoryArtifactStore) -> ClaimedExecutor:
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


def test_pure_compute_output_digest_is_deterministic() -> None:
    first = compute_pure_compute_output_bytes(SEED_ALPHA)
    second = compute_pure_compute_output_bytes(SEED_ALPHA)
    other = compute_pure_compute_output_bytes(SEED_BETA)
    assert first == second
    assert raw_blob_digest(first) == raw_blob_digest(second)
    assert raw_blob_digest(first) != raw_blob_digest(other)


def test_same_ref_output_put_is_idempotent() -> None:
    store = InMemoryArtifactStore()
    output_bytes = compute_pure_compute_output_bytes(SEED_ALPHA)
    digest = raw_blob_digest(output_bytes).value
    artifact_id = f"pure-compute-output:{digest}"
    first = put_with_built_ref(
        store,
        output_bytes,
        artifact_id=artifact_id,
        media_type="application/jcs",
    )
    second = put_with_built_ref(
        store,
        output_bytes,
        artifact_id=artifact_id,
        media_type="application/jcs",
    )
    assert first == second
    assert store.locate(first) == output_bytes


def test_fresh_run_publishes_checkpoint_and_ready_closure(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    artifact_store = InMemoryArtifactStore()
    session, control, read_uow = _claimed_pure_compute_session(db_path)
    executor = _wrapped_pure_compute_executor(artifact_store)

    with read_uow as unit_of_work:
        operation = unit_of_work.operations.get_operation("operation-pure-1")
        step = unit_of_work.operations.get_step("step-pure-1")

    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation("operation-pure-1")
        persisted_step = unit_of_work.operations.get_step("step-pure-1")
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_step.status is StepStatus.SUCCEEDED
    assert persisted_step.checkpoint_ref is not None
    assert persisted_operation.ready_closure_ref is not None

    closure = load_ready_closure(artifact_store, persisted_operation.ready_closure_ref)
    assert len(closure.outputs) == 1
    output_ref = closure.outputs[0].artifact_ref
    assert artifact_store.locate(output_ref) == compute_pure_compute_output_bytes(SEED_ALPHA)


def test_ready_closure_output_ordering_and_integrity(tmp_path: Path) -> None:
    db_path = tmp_path / "closure.sqlite3"
    artifact_store = InMemoryArtifactStore()
    session, control, read_uow = _claimed_pure_compute_session(
        db_path,
        operation_id="operation-closure",
        step_id="step-closure",
    )
    executor = _wrapped_pure_compute_executor(artifact_store)

    with read_uow as unit_of_work:
        operation = unit_of_work.operations.get_operation("operation-closure")
        step = unit_of_work.operations.get_step("step-closure")

    executor(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation("operation-closure")
    closure_ref = persisted_operation.ready_closure_ref
    assert closure_ref is not None
    closure = load_ready_closure(artifact_store, closure_ref)
    artifact_ids = [entry.artifact_ref.artifact_id for entry in closure.outputs]
    assert artifact_ids == sorted(artifact_ids)
    assert len(set(artifact_ids)) == len(artifact_ids)


def test_cancel_before_publication_publishes_cancelled(tmp_path: Path) -> None:
    db_path = tmp_path / "cancel.sqlite3"
    artifact_store = InMemoryArtifactStore()
    session, control, _ = _claimed_pure_compute_session(
        db_path,
        operation_id="operation-cancel",
        step_id="step-cancel",
    )
    handler = build_pure_compute_handler(artifact_store)

    with ControlDbUnitOfWork(db_path) as unit_of_work:
        store = unit_of_work.operations
        current_operation = store.get_operation("operation-cancel")
        current_step = store.get_step("step-cancel")
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
                worker_id="worker-pure-1",
                lease_token="lease-pure-1",
            ),
        ) == (TransitionDisposition.APPLY, TransitionDisposition.APPLY)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation("operation-cancel")
        step = unit_of_work.operations.get_step("step-cancel")

    handler(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation("operation-cancel")
        persisted_step = unit_of_work.operations.get_step("step-cancel")
    assert persisted_operation.status is OperationStatus.CANCELLED
    assert persisted_step.status is StepStatus.CANCELLED
    assert persisted_operation.ready_closure_ref is None
    assert persisted_step.checkpoint_ref is None
    assert artifact_store._artifacts == {}


@pytest.mark.integration
def test_artifact_round_trip_after_reopen(tmp_path: Path) -> None:
    root = staging_root(tmp_path)
    store = open_local_store(root)
    output_bytes = compute_pure_compute_output_bytes(SEED_ALPHA)
    digest = raw_blob_digest(output_bytes).value
    ref = put_with_built_ref(
        store,
        output_bytes,
        artifact_id=f"pure-compute-output:{digest}",
        media_type="application/jcs",
    )
    reopened = reopen_local_store(root)
    assert reopened.locate(ref) == output_bytes


def _stub_operation_document(
    operation_id: str,
    *,
    idempotency_key: str = IDEMPOTENCY_KEY_ALPHA,
    request_body: str = REQUEST_BODY_ALPHA,
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
            "idempotency_key": idempotency_key,
            "request_body": request_body,
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


def _claimed_stub_session(
    db_path: Path,
    *,
    operation_id: str = "operation-stub-1",
    step_id: str = "step-stub-1",
    worker_id: str = "worker-stub-1",
    lease_token: str = "lease-stub-1",
    idempotency_key: str = IDEMPOTENCY_KEY_ALPHA,
    request_body: str = REQUEST_BODY_ALPHA,
    stub_outcome: str = StubOutcome.CONFIRMED.value,
) -> tuple[LeaseSession, ExecutionControl, ControlDbUnitOfWork]:
    bootstrap_control_database(make_operation_worker_settings(db_path.parent, control_db_path=db_path))
    operation = operation_record_from_document(
        _stub_operation_document(
            operation_id,
            idempotency_key=idempotency_key,
            request_body=request_body,
            stub_outcome=stub_outcome,
        )
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
    return session, control, ControlDbUnitOfWork(db_path, read_only=True)


def _wrapped_stub_executor(store: InMemoryArtifactStore) -> ClaimedExecutor:
    definitions, handlers, decoders = external_effect_stub_composition_bundle(store)
    composition = build_job_worker_composition(
        definitions,
        handlers,
        artifact_store=store,
        decoders=decoders,
    )
    executor = composition.worker_registry.resolve(external_effect_stub_job_key())
    assert executor is not None
    return executor


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


def _expected_stub_identity(
    *,
    idempotency_key: str = IDEMPOTENCY_KEY_ALPHA,
    request_body: str = REQUEST_BODY_ALPHA,
) -> str:
    request_bytes = build_request_bytes(idempotency_key, request_body)
    return compute_operation_identity(idempotency_key, request_bytes)


def test_stub_operation_identity_is_deterministic() -> None:
    first = _expected_stub_identity()
    second = _expected_stub_identity()
    other = _expected_stub_identity(idempotency_key=IDEMPOTENCY_KEY_BETA, request_body=REQUEST_BODY_BETA)
    assert first == second
    assert first != other


def test_normal_submit_identity_mismatch_fails_closed_without_ready(tmp_path: Path) -> None:
    class WrongIdentityStub(ExternalEffectStub):
        def submit(self, _idempotency_key: str, _request_ref: ArtifactRef) -> str:
            return "synthetic-stub-op:wrong"

    db_path = tmp_path / "stub-identity-mismatch.sqlite3"
    artifact_store = InMemoryArtifactStore()
    session, control, read_uow = _claimed_stub_session(db_path)
    executor = build_external_effect_stub_handler(
        artifact_store,
        external_stub=WrongIdentityStub(),
    )
    with read_uow as unit_of_work:
        operation = unit_of_work.operations.get_operation("operation-stub-1")
        step = unit_of_work.operations.get_step("step-stub-1")

    assert executor(operation, step, control, session) is ExecutorAcknowledgment.PUBLISHED
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation("operation-stub-1")
        persisted_step = unit_of_work.operations.get_step("step-stub-1")
    assert persisted_operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    assert persisted_operation.ready_closure_ref is None
    assert persisted_operation.repository_operation_id is None
    assert persisted_step.checkpoint_ref is None
    assert not any("response" in artifact_id for artifact_id in artifact_store._artifacts)


def test_cancel_before_request_publishes_cancelled(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-cancel-before.sqlite3"
    artifact_store = InMemoryArtifactStore()
    session, control, _ = _claimed_stub_session(
        db_path,
        operation_id="operation-stub-cancel-before",
        step_id="step-stub-cancel-before",
    )
    handler = build_external_effect_stub_handler(artifact_store)
    _apply_cancel_intent(
        db_path,
        operation_id="operation-stub-cancel-before",
        step_id="step-stub-cancel-before",
        worker_id="worker-stub-1",
        lease_token="lease-stub-1",
    )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation("operation-stub-cancel-before")
        step = unit_of_work.operations.get_step("step-stub-cancel-before")

    handler(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation("operation-stub-cancel-before")
        persisted_step = unit_of_work.operations.get_step("step-stub-cancel-before")
    assert persisted_operation.status is OperationStatus.CANCELLED
    assert persisted_step.status is StepStatus.CANCELLED
    assert persisted_operation.ready_closure_ref is None
    assert persisted_step.checkpoint_ref is None
    assert persisted_operation.repository_operation_id is None
    assert artifact_store._artifacts == {}


def test_cancel_after_request_retains_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-cancel-after.sqlite3"
    artifact_store = InMemoryArtifactStore()
    session, control, read_uow = _claimed_stub_session(
        db_path,
        operation_id="operation-stub-cancel-after",
        step_id="step-stub-cancel-after",
        stub_outcome=StubOutcome.ACCEPTED.value,
    )
    executor = _wrapped_stub_executor(artifact_store)

    with read_uow as unit_of_work:
        operation = unit_of_work.operations.get_operation("operation-stub-cancel-after")
        step = unit_of_work.operations.get_step("step-stub-cancel-after")

    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.SAFE_HANDOFF

    _apply_cancel_intent(
        db_path,
        operation_id="operation-stub-cancel-after",
        step_id="step-stub-cancel-after",
        worker_id="worker-stub-1",
        lease_token="lease-stub-1",
    )

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation("operation-stub-cancel-after")
        step = unit_of_work.operations.get_step("step-stub-cancel-after")

    session_after_cancel = LeaseSession(
        worker_id="worker-stub-1",
        lease_token="lease-stub-1",
        operation_id=operation.operation_id,
        step_id=step.step_id,
        write_uow_factory=lambda: ControlDbUnitOfWork(db_path),
        control=control,
        observer=lambda _event: None,
    )
    second_ack = executor(operation, step, control, session_after_cancel)
    assert second_ack is ExecutorAcknowledgment.SAFE_HANDOFF

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation("operation-stub-cancel-after")
        persisted_step = unit_of_work.operations.get_step("step-stub-cancel-after")
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_step.checkpoint_ref is not None
    envelope = load_checkpoint_envelope(artifact_store, persisted_step.checkpoint_ref)
    assert envelope.job_state["operation_identity"] == _expected_stub_identity()
    assert persisted_operation.repository_operation_id is None


@pytest.mark.parametrize(
    ("stub_outcome", "operation_status", "step_status", "expects_ready_closure", "expected_ack"),
    STUB_OUTCOME_TERMINAL_EXPECTATIONS,
)
def test_stub_terminal_outcomes(
    tmp_path: Path,
    stub_outcome: StubOutcome,
    operation_status: OperationStatus,
    step_status: StepStatus,
    expects_ready_closure: bool,
    expected_ack: ExecutorAcknowledgment,
) -> None:
    db_path = tmp_path / f"stub-{stub_outcome.value}.sqlite3"
    artifact_store = InMemoryArtifactStore()
    session, control, read_uow = _claimed_stub_session(
        db_path,
        operation_id=f"operation-stub-{stub_outcome.value}",
        step_id=f"step-stub-{stub_outcome.value}",
        stub_outcome=stub_outcome.value,
    )
    executor = _wrapped_stub_executor(artifact_store)

    with read_uow as unit_of_work:
        operation = unit_of_work.operations.get_operation(f"operation-stub-{stub_outcome.value}")
        step = unit_of_work.operations.get_step(f"step-stub-{stub_outcome.value}")

    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is expected_ack

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(f"operation-stub-{stub_outcome.value}")
        persisted_step = unit_of_work.operations.get_step(f"step-stub-{stub_outcome.value}")
    assert persisted_operation.status is operation_status
    assert persisted_step.status is step_status
    if stub_outcome is StubOutcome.UNKNOWN:
        assert persisted_operation.repository_operation_id is None
    else:
        assert persisted_operation.repository_operation_id == _expected_stub_identity()
    assert persisted_step.checkpoint_ref is not None
    if expects_ready_closure:
        assert persisted_operation.ready_closure_ref is not None
        closure = load_ready_closure(artifact_store, persisted_operation.ready_closure_ref)
        assert len(closure.outputs) == 1
    else:
        assert persisted_operation.ready_closure_ref is None
        assert persisted_operation.status is not OperationStatus.FAILED
        assert persisted_operation.status is not OperationStatus.CANCELLED


def test_accepted_outcome_safe_handoff_after_request(tmp_path: Path) -> None:
    db_path = tmp_path / "stub-accepted.sqlite3"
    artifact_store = InMemoryArtifactStore()
    session, control, read_uow = _claimed_stub_session(
        db_path,
        operation_id="operation-stub-accepted",
        step_id="step-stub-accepted",
        stub_outcome=StubOutcome.ACCEPTED.value,
    )
    executor = _wrapped_stub_executor(artifact_store)

    with read_uow as unit_of_work:
        operation = unit_of_work.operations.get_operation("operation-stub-accepted")
        step = unit_of_work.operations.get_step("step-stub-accepted")

    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.SAFE_HANDOFF

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation("operation-stub-accepted")
        persisted_step = unit_of_work.operations.get_step("step-stub-accepted")
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_step.checkpoint_ref is not None
    assert persisted_operation.ready_closure_ref is None
    assert persisted_operation.repository_operation_id is None


@pytest.mark.parametrize(("consumer", "binding"), PAYLOAD_BINDING_PARITY)
def test_synthetic_payload_binding_parity(
    tmp_path: Path,
    consumer: str,
    binding: str,
) -> None:
    db_path = tmp_path / f"payload-parity-{consumer}-{binding}.sqlite3"
    artifact_store = InMemoryArtifactStore()
    expected_identity = _expected_stub_identity()
    expected_digest = raw_blob_digest(compute_pure_compute_output_bytes(SEED_ALPHA))

    if consumer == "pure-compute":
        session, control, read_uow = _claimed_pure_compute_session_with_binding(
            db_path,
            artifact_store,
            binding=binding,
        )
        executor = _wrapped_pure_compute_executor(artifact_store)
        operation_id = "operation-pure-parity"
        step_id = "step-pure-parity"
    else:
        session, control, read_uow = _claimed_stub_session_with_binding(
            db_path,
            artifact_store,
            binding=binding,
        )
        executor = _wrapped_stub_executor(artifact_store)
        operation_id = "operation-stub-parity"
        step_id = "step-stub-parity"

    with read_uow as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(step_id)

    acknowledgment = executor(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_step = unit_of_work.operations.get_step(step_id)

    if consumer == "pure-compute":
        assert persisted_operation.status is OperationStatus.SUCCEEDED
        assert persisted_step.status is StepStatus.SUCCEEDED
        assert persisted_operation.ready_closure_ref is not None
        closure = load_ready_closure(artifact_store, persisted_operation.ready_closure_ref)
        assert closure.outputs[0].artifact_ref.raw_sha256 == expected_digest
    else:
        assert persisted_operation.status is OperationStatus.SUCCEEDED
        assert persisted_step.status is StepStatus.SUCCEEDED
        assert persisted_operation.repository_operation_id == expected_identity
        assert persisted_step.checkpoint_ref is not None
        envelope = load_checkpoint_envelope(artifact_store, persisted_step.checkpoint_ref)
        assert envelope.job_state["operation_identity"] == expected_identity
