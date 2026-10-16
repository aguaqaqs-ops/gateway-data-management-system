"""Expired-lease classification, retry scheduling, CAS takeover and R5 fault-matrix tests.

P4-R5-S3c fault matrix (this file owns lease expiry, stale writer, retry exhaustion,
operator action at the Operations boundary):

| Fault boundary | Authoritative owner |
|---|---|
| lease expiry | ``test_expired_running_schedules_retry_wait_via_guarded_cas``, ``test_due_retry_wait_reclaim_*``, ``test_concurrent_recovery_cas_*``, ``test_live_running_lease_*``; process owner in ``test_operation_recovery_process`` |
| stale writer | ``test_old_lease_token_is_fenced_after_takeover``; ``test_operator_command_stale_expected_version_*`` |
| retry exhaustion | ``test_session_budget_exhaustion_marks_manual_recovery`` (``CROSS_BOUNDARY_RETRY_CAPABILITIES``) |
| operator action | S2c ``test_operator_*`` (authorized CAS port); ``test_manual_recovery_retains_occupancy_*`` |

Consumer E2E lease/takeover proofs remain in S3a ``test_pure_compute_lease_takeover_*``.
S3c does not duplicate S3a/S3b RecoveryPort consumer invariants.
"""

from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import cast

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationStatus,
    StepStatus,
    TransitionDisposition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.contracts import JobStepKey, OperationRecord, StepRecord
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.recovery import (
    RECOVERY_BACKOFF_CAP_SECONDS,
    OperatorRecoveryCommand,
    OperatorRecoveryRequest,
    OPERATOR_RECOVERY_WORKER_ID,
    RecoveryCapabilityValue,
    StartupRecovery,
    AuthorizedOperatorRecovery,
    build_authorized_operator_recovery,
    build_startup_recovery,
)
from gateway_backend.operations.store import LeaseExpired, StaleWrite
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    RecoveryHook,
    StartupDisposition,
)
from gateway_backend.operations.worker_startup import WorkerStartup

pytestmark = pytest.mark.integration

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
JOB_KEY = JobStepKey(job_kind="import.package", step_name="validate")
OPERATOR_REASON = "operator authorized recovery action"

CROSS_BOUNDARY_RETRY_CAPABILITIES: tuple[RecoveryCapabilityValue, ...] = (
    RecoveryCapabilityValue.PURE_RECOMPUTE,
    RecoveryCapabilityValue.EXTERNAL_EFFECT,
)


def _deterministic_jitter(lower: float, _upper: float) -> float:
    return lower


class _MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _noop_executor(
    _operation: OperationRecord,
    _step: StepRecord,
    _control: ExecutionControl,
    _session: object,
) -> ExecutorAcknowledgment:
    return ExecutorAcknowledgment.PUBLISHED


def _terminal_executor(
    operation: OperationRecord,
    step: StepRecord,
    _control: ExecutionControl,
    session: LeaseSession,
) -> ExecutorAcknowledgment:
    session.publish_operation(
        lambda _operation, current_step, now: (
            dataclasses.replace(
                current_step,
                status=StepStatus.SUCCEEDED,
                updated_at=now,
                completed_at=now,
                worker_id=None,
                lease_token=None,
                lease_expires_at=None,
                optimistic_version=current_step.optimistic_version + 1,
            ),
            dataclasses.replace(
                operation,
                status=OperationStatus.SUCCEEDED,
                updated_at=now,
                completed_at=now,
                optimistic_version=operation.optimistic_version + 1,
            ),
        )
    )
    return ExecutorAcknowledgment.PUBLISHED


class _Registry:
    def __init__(self, executor: ClaimedExecutor | None = None) -> None:
        self._executor = executor

    def resolve(self, key: JobStepKey) -> ClaimedExecutor | None:
        if key == JOB_KEY:
            return cast(
                ClaimedExecutor,
                self._executor if self._executor is not None else _noop_executor,
            )
        return None


def _ready_recovery(_operation: OperationRecord, _step: StepRecord) -> StartupDisposition:
    return StartupDisposition.READY


def _operation_document(operation_id: str) -> dict[str, object]:
    return {
        "artifact_refs": [],
        "business_refs": [],
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2024-01-02T03:04:05Z",
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": "backend-vnext/import-package/v1",
        "job_kind": "import.package",
        "job_payload": {"request": {"value": 1}},
        "job_payload_ref": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "ready_closure_ref": None,
        "repository_operation_id": None,
        "status": OperationStatus.QUEUED.value,
        "updated_at": "2024-01-02T03:04:05Z",
    }


def _step_document(operation_id: str, step_id: str) -> dict[str, object]:
    return {
        "attempt_count": 0,
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2024-01-02T03:04:05Z",
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
        "step_name": "validate",
        "updated_at": "2024-01-02T03:04:05Z",
        "worker_id": None,
    }


@dataclasses.dataclass
class TakeoverHarness:
    db_path: Path
    clock: _MutableClock
    capability: RecoveryCapabilityValue
    attempt_count: int = 1

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

    def operator_recovery(self) -> AuthorizedOperatorRecovery:
        return build_authorized_operator_recovery(
            write_uow_factory=self.write_uow,
            capability_lookup=lambda _job_kind, _step_name: self.capability,
        )

    def seed_manual_recovery(
        self,
        *,
        operation_id: str = "operation-manual-1",
        step_id: str = "step-manual-1",
    ) -> tuple[OperationRecord, StepRecord]:
        operation, step = self.seed_running_with_attempt_count(
            3,
            operation_id=operation_id,
            step_id=step_id,
        )
        self.advance_past_lease(step)
        startup = self.worker_startup()
        assert startup.startup() is StartupDisposition.FATAL_BLOCK
        with self.read_uow() as unit_of_work:
            store = unit_of_work.operations
            persisted_step = store.get_step(step_id)
            persisted_operation = store.get_operation(operation_id)
        assert persisted_step.status is StepStatus.MANUAL_RECOVERY_REQUIRED
        assert persisted_operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
        return persisted_operation, persisted_step

    def operator_request(
        self,
        command: OperatorRecoveryCommand,
        operation: OperationRecord,
        step: StepRecord,
        *,
        reason: str = OPERATOR_REASON,
    ) -> OperatorRecoveryRequest:
        return OperatorRecoveryRequest(
            command=command,
            operation_id=operation.operation_id,
            step_id=step.step_id,
            expected_operation_optimistic_version=operation.optimistic_version,
            expected_step_optimistic_version=step.optimistic_version,
            reason=reason,
        )

    def worker_startup(self, *, worker_id: str = "worker-takeover") -> WorkerStartup:
        return WorkerStartup(
            read_uow_factory=self.read_uow,
            write_uow_factory=self.write_uow,
            registry=_Registry(cast(ClaimedExecutor, _terminal_executor)),
            recovery_hook=cast(RecoveryHook, _ready_recovery),
            startup_recovery=self.startup_recovery(),
            observer=lambda _event: None,
            worker_id_factory=lambda: worker_id,
            lease_token_factory=lambda: f"lease-{worker_id}",
        )

    def seed_claimed_running(
        self,
        *,
        operation_id: str = "operation-takeover-1",
        step_id: str = "step-takeover-1",
        worker_id: str = "worker-old",
        lease_token: str = "lease-old",
        attempt_count: int | None = None,
    ) -> tuple[OperationRecord, StepRecord]:
        operation = operation_record_from_document(_operation_document(operation_id))
        step = step_record_from_document(_step_document(operation_id, step_id))
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
        operation_id: str = "operation-takeover-1",
        step_id: str = "step-takeover-1",
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


def _make_harness(
    tmp_path: Path,
    *,
    capability: RecoveryCapabilityValue = RecoveryCapabilityValue.PURE_RECOMPUTE,
    clock: datetime | None = None,
) -> TakeoverHarness:
    db_path = tmp_path / "takeover.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    clock_value = clock if clock is not None else BASE_TIME
    mutable_clock = _MutableClock(clock_value)
    initialize_control_db(db_path)
    return TakeoverHarness(db_path=db_path, clock=mutable_clock, capability=capability)


STARTUP_CAPABILITIES = (
    RecoveryCapabilityValue.PURE_RECOMPUTE,
    RecoveryCapabilityValue.EXTERNAL_EFFECT,
    RecoveryCapabilityValue.NON_RETRYABLE,
)

STARTUP_LEASE_DISPOSITION_CASES = (
    (
        "live",
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        StartupDisposition.RETRYABLE_BLOCK,
        StepStatus.RUNNING,
        OperationStatus.RUNNING,
        None,
    ),
    (
        "live",
        RecoveryCapabilityValue.EXTERNAL_EFFECT,
        StartupDisposition.RETRYABLE_BLOCK,
        StepStatus.RUNNING,
        OperationStatus.RUNNING,
        None,
    ),
    (
        "live",
        RecoveryCapabilityValue.NON_RETRYABLE,
        StartupDisposition.RETRYABLE_BLOCK,
        StepStatus.RUNNING,
        OperationStatus.RUNNING,
        None,
    ),
    (
        "expired",
        RecoveryCapabilityValue.PURE_RECOMPUTE,
        StartupDisposition.RETRYABLE_BLOCK,
        StepStatus.RETRY_WAIT,
        OperationStatus.RUNNING,
        "R5.RETRY_SCHEDULED",
    ),
    (
        "expired",
        RecoveryCapabilityValue.EXTERNAL_EFFECT,
        StartupDisposition.RETRYABLE_BLOCK,
        StepStatus.RETRY_WAIT,
        OperationStatus.RUNNING,
        "R5.RECONCILE_STARTED",
    ),
    (
        "expired",
        RecoveryCapabilityValue.NON_RETRYABLE,
        StartupDisposition.FATAL_BLOCK,
        StepStatus.MANUAL_RECOVERY_REQUIRED,
        OperationStatus.MANUAL_RECOVERY_REQUIRED,
        "R5.MANUAL_RECOVERY_REQUIRED",
    ),
)


@pytest.mark.parametrize(
    ("lease_state", "capability", "expected_startup", "expected_step", "expected_operation", "expected_code"),
    STARTUP_LEASE_DISPOSITION_CASES,
)
def test_running_lease_startup_disposition_matrix(
    tmp_path: Path,
    lease_state: str,
    capability: RecoveryCapabilityValue,
    expected_startup: StartupDisposition,
    expected_step: StepStatus,
    expected_operation: OperationStatus,
    expected_code: str | None,
) -> None:
    harness = _make_harness(tmp_path, capability=capability)
    operation, step = harness.seed_claimed_running()
    if lease_state == "expired":
        harness.advance_past_lease(step)

    assert harness.worker_startup().startup() is expected_startup

    with harness.read_uow() as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation.operation_id)
        persisted_step = unit_of_work.operations.get_step(step.step_id)
    assert persisted_operation.status is expected_operation
    assert persisted_step.status is expected_step
    if lease_state == "live":
        assert persisted_step.worker_id == step.worker_id
        assert persisted_step.lease_token == step.lease_token
        assert persisted_step.started_at == step.started_at
        assert persisted_step.diagnostic is None
    else:
        assert persisted_step.worker_id is None
        assert persisted_step.lease_token is None
        assert persisted_step.diagnostic is not None
        assert persisted_step.diagnostic.code == expected_code
        if expected_step is StepStatus.RETRY_WAIT:
            assert persisted_step.retry_not_before is not None
            assert persisted_step.retry_not_before <= harness.clock() + timedelta(
                seconds=RECOVERY_BACKOFF_CAP_SECONDS
            )
        else:
            assert persisted_step.retry_not_before is None


@pytest.mark.parametrize("capability", STARTUP_CAPABILITIES)
def test_transaction_recheck_blocks_a_lease_that_became_live(
    tmp_path: Path,
    capability: RecoveryCapabilityValue,
) -> None:
    harness = _make_harness(tmp_path, capability=capability)
    operation, step = harness.seed_claimed_running()
    lease_expires_at = step.lease_expires_at
    assert lease_expires_at is not None
    outer_now = lease_expires_at + timedelta(seconds=1)
    recovery = build_startup_recovery(
        write_uow_factory=harness.write_uow,
        capability_lookup=lambda _job_kind, _step_name: capability,
        jitter=_deterministic_jitter,
        now_factory=lambda: outer_now,
    )

    # The outer read sees expiry, then the transaction clock observes a live lease.
    assert recovery.recover_pair(operation, step) is StartupDisposition.RETRYABLE_BLOCK

    with harness.read_uow() as unit_of_work:
        persisted = unit_of_work.operations.get_step(step.step_id)
    assert persisted.status is StepStatus.RUNNING
    assert persisted.worker_id == step.worker_id
    assert persisted.lease_token == step.lease_token


def test_due_retry_wait_reclaim_preserves_started_at_and_increments_attempt(
    tmp_path: Path,
) -> None:
    harness = _make_harness(tmp_path)
    operation, step = harness.seed_claimed_running()
    original_started_at = step.started_at
    harness.advance_past_lease(step)
    startup = harness.worker_startup(worker_id="worker-reclaim")
    assert startup.startup() is StartupDisposition.RETRYABLE_BLOCK

    with harness.read_uow() as unit_of_work:
        retry_not_before = unit_of_work.operations.get_step(step.step_id).retry_not_before
    assert retry_not_before is not None
    harness.clock.value = retry_not_before

    assert startup.startup() is StartupDisposition.READY
    work = startup.claim_one()
    assert work is not None
    assert work.step.status is StepStatus.RUNNING
    assert work.step.attempt_count == step.attempt_count + 1
    assert work.step.started_at == original_started_at
    assert work.step.worker_id == "worker-reclaim"
    assert work.step.lease_token == "lease-worker-reclaim"
    del operation


@pytest.mark.parametrize("capability", CROSS_BOUNDARY_RETRY_CAPABILITIES)
def test_session_budget_exhaustion_marks_manual_recovery(
    tmp_path: Path,
    capability: RecoveryCapabilityValue,
) -> None:
    harness = _make_harness(tmp_path, capability=capability)
    operation, step = harness.seed_running_with_attempt_count(3)
    harness.advance_past_lease(step)
    startup = harness.worker_startup()
    assert startup.startup() is StartupDisposition.FATAL_BLOCK

    with harness.read_uow() as unit_of_work:
        persisted_step = unit_of_work.operations.get_step(step.step_id)
        persisted_operation = unit_of_work.operations.get_operation(operation.operation_id)
    assert persisted_step.status is StepStatus.MANUAL_RECOVERY_REQUIRED
    assert persisted_operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
    del operation


@pytest.mark.serial
def test_concurrent_recovery_cas_leaves_single_retry_wait(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    _operation, step = harness.seed_claimed_running()
    harness.advance_past_lease(step)
    barrier = Barrier(2)
    results: list[StartupDisposition] = []

    def run_startup(worker_id: str) -> None:
        barrier.wait()
        startup = harness.worker_startup(worker_id=worker_id)
        results.append(startup.startup())

    with ThreadPoolExecutor(max_workers=2) as executor:
        executor.submit(run_startup, "worker-a")
        executor.submit(run_startup, "worker-b")
        executor.shutdown(wait=True)

    assert StartupDisposition.RETRYABLE_BLOCK in results
    assert any(
        disposition in {StartupDisposition.READY, StartupDisposition.RETRYABLE_BLOCK}
        for disposition in results
    )
    with harness.read_uow() as unit_of_work:
        persisted = unit_of_work.operations.get_step(step.step_id)
    assert persisted.status is StepStatus.RETRY_WAIT


def test_old_lease_token_is_fenced_after_takeover(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    operation, step = harness.seed_claimed_running(
        worker_id="worker-stale",
        lease_token="lease-stale",
    )
    original_started_at = step.started_at
    harness.advance_past_lease(step)
    reclaim_startup = harness.worker_startup(worker_id="worker-new")
    assert reclaim_startup.startup() is StartupDisposition.RETRYABLE_BLOCK

    with harness.read_uow() as unit_of_work:
        retry_not_before = unit_of_work.operations.get_step(step.step_id).retry_not_before
    assert retry_not_before is not None
    harness.clock.value = retry_not_before
    assert reclaim_startup.startup() is StartupDisposition.READY
    work = reclaim_startup.claim_one()
    assert work is not None
    assert work.step.started_at == original_started_at

    def stale_write_uow() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(harness.db_path, now=harness.clock)

    stale_session = LeaseSession(
        worker_id="worker-stale",
        lease_token="lease-stale",
        operation_id=operation.operation_id,
        step_id=step.step_id,
        write_uow_factory=stale_write_uow,
        control=ExecutionControl(),
        observer=lambda _event: None,
    )
    with pytest.raises((StaleWrite, LeaseExpired)):
        stale_session.refresh_control()
        stale_session.heartbeat()
    del operation


def test_operator_resume_reconcile_applies_authorized_cas(tmp_path: Path) -> None:
    harness = _make_harness(
        tmp_path,
        capability=RecoveryCapabilityValue.EXTERNAL_EFFECT,
    )
    operation, step = harness.seed_manual_recovery()
    original_started_at = step.started_at
    port = harness.operator_recovery()
    assert (
        port.execute(
            harness.operator_request(OperatorRecoveryCommand.RESUME_RECONCILE, operation, step)
        )
        is TransitionDisposition.APPLY
    )
    with harness.read_uow() as unit_of_work:
        store = unit_of_work.operations
        persisted_step = store.get_step(step.step_id)
        persisted_operation = store.get_operation(operation.operation_id)
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.started_at == original_started_at
    assert persisted_step.attempt_count == step.attempt_count
    assert persisted_step.worker_id == OPERATOR_RECOVERY_WORKER_ID
    assert persisted_step.lease_token == f"operator-{step.step_id}"
    assert persisted_step.lease_expires_at is not None
    assert persisted_step.diagnostic is None
    assert persisted_operation.diagnostic is None


def test_operator_retry_from_checkpoint_applies_authorized_cas(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    operation, step = harness.seed_manual_recovery()
    original_started_at = step.started_at
    port = harness.operator_recovery()
    assert (
        port.execute(
            harness.operator_request(
                OperatorRecoveryCommand.RETRY_FROM_CHECKPOINT,
                operation,
                step,
            )
        )
        is TransitionDisposition.APPLY
    )
    with harness.read_uow() as unit_of_work:
        persisted_step = unit_of_work.operations.get_step(step.step_id)
        persisted_operation = unit_of_work.operations.get_operation(operation.operation_id)
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.started_at == original_started_at
    assert persisted_step.worker_id == OPERATOR_RECOVERY_WORKER_ID


def test_operator_abort_confirmed_failure_applies_paired_failed_cas(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    operation, step = harness.seed_manual_recovery()
    port = harness.operator_recovery()
    assert (
        port.execute(
            harness.operator_request(
                OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
                operation,
                step,
            )
        )
        is TransitionDisposition.APPLY
    )
    with harness.read_uow() as unit_of_work:
        store = unit_of_work.operations
        persisted_step = store.get_step(step.step_id)
        persisted_operation = store.get_operation(operation.operation_id)
    assert persisted_step.status is StepStatus.FAILED
    assert persisted_operation.status is OperationStatus.FAILED
    assert persisted_step.diagnostic is not None
    assert persisted_step.diagnostic.message == OPERATOR_REASON
    assert persisted_operation.diagnostic is not None
    assert persisted_operation.diagnostic.message == OPERATOR_REASON


def test_operator_command_stale_expected_version_raises_stale_write(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    operation, step = harness.seed_manual_recovery()
    port = harness.operator_recovery()
    stale_request = OperatorRecoveryRequest(
        command=OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
        operation_id=operation.operation_id,
        step_id=step.step_id,
        expected_operation_optimistic_version=operation.optimistic_version - 1,
        expected_step_optimistic_version=step.optimistic_version,
        reason=OPERATOR_REASON,
    )
    with pytest.raises(StaleWrite):
        port.execute(stale_request)


@pytest.mark.parametrize(
    ("command", "capability"),
    (
        (OperatorRecoveryCommand.RESUME_RECONCILE, RecoveryCapabilityValue.PURE_RECOMPUTE),
        (OperatorRecoveryCommand.RETRY_FROM_CHECKPOINT, RecoveryCapabilityValue.EXTERNAL_EFFECT),
    ),
)
def test_operator_command_unauthorized_capability_rejected(
    tmp_path: Path,
    command: OperatorRecoveryCommand,
    capability: RecoveryCapabilityValue,
) -> None:
    harness = _make_harness(tmp_path, capability=capability)
    operation, step = harness.seed_manual_recovery()
    port = harness.operator_recovery()
    with pytest.raises(ValueError, match="requires"):
        port.execute(harness.operator_request(command, operation, step))


def test_operator_abort_idempotent_replay(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    operation, step = harness.seed_manual_recovery()
    port = harness.operator_recovery()
    request = harness.operator_request(
        OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
        operation,
        step,
    )
    assert port.execute(request) is TransitionDisposition.APPLY
    with harness.read_uow() as unit_of_work:
        store = unit_of_work.operations
        failed_step = store.get_step(step.step_id)
        failed_operation = store.get_operation(operation.operation_id)
    replay_request = harness.operator_request(
        OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
        failed_operation,
        failed_step,
    )
    assert port.execute(replay_request) is TransitionDisposition.IDEMPOTENT


def test_manual_recovery_retains_occupancy_and_excludes_claim(tmp_path: Path) -> None:
    harness = _make_harness(
        tmp_path,
        capability=RecoveryCapabilityValue.EXTERNAL_EFFECT,
    )
    operation, step = harness.seed_manual_recovery()
    with harness.read_uow() as unit_of_work:
        store = unit_of_work.operations
        assert store.list_claim_candidates(harness.clock())[0] == ()
        actions = OperationLifecycleActions(store, transaction_now=store.transaction_now)
        assert actions.claim_one("worker-claim", "lease-claim") is None

    port = harness.operator_recovery()
    port.execute(
        harness.operator_request(OperatorRecoveryCommand.RESUME_RECONCILE, operation, step)
    )
    with harness.read_uow() as unit_of_work:
        store = unit_of_work.operations
        assert store.list_claim_candidates(harness.clock())[0] == ()
        persisted_operation = store.get_operation(operation.operation_id)
        persisted_step = store.get_step(step.step_id)
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert not persisted_operation.status.is_final_terminal()


@pytest.mark.unit
def test_build_recovery_candidates_rejects_running_to_running_intent() -> None:
    from gateway_backend.operations.recovery import (
        RecoveryPolicyDecision,
        RecoveryPolicyDecisionDisposition,
        RecoveryTransitionIntent,
        build_recovery_candidates,
    )

    operation = OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id="op-0001",
        job_kind="import.package",
        job_contract_version="backend-vnext/import-package/v1",
        job_payload=canonicalize_json_value({}),
        job_payload_ref=None,
        business_refs=(),
        artifact_refs=(),
        repository_operation_id=None,
        checkpoint_ref=None,
        ready_closure_ref=None,
        status=OperationStatus.RUNNING,
        diagnostic=None,
        cancel_requested=False,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        completed_at=None,
        optimistic_version=1,
    )
    step = StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id="step-0001",
        operation_id=operation.operation_id,
        step_name="validate",
        status=StepStatus.RUNNING,
        attempt_count=1,
        diagnostic=None,
        cancel_requested=False,
        retry_not_before=None,
        worker_id="worker-1",
        lease_token="lease-1",
        lease_expires_at=BASE_TIME + timedelta(seconds=30),
        checkpoint_ref=None,
        prior_output_refs=(),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        started_at=BASE_TIME,
        completed_at=None,
        optimistic_version=1,
    )
    decision = RecoveryPolicyDecision(
        disposition=RecoveryPolicyDecisionDisposition.MOVE_TO_RETRY_WAIT,
        diagnostic_code="r5.retry_scheduled",
        retry_not_before=BASE_TIME + timedelta(seconds=1),
        reason="retry",
    )
    bad_intent = RecoveryTransitionIntent(
        step_source=StepStatus.RUNNING,
        step_target=StepStatus.RUNNING,
        operation_source=OperationStatus.RUNNING,
        operation_target=None,
        set_retry_not_before=None,
        retain_occupancy=False,
        increment_attempt_on_claim=False,
    )
    with pytest.raises(ValueError, match="RETRY_WAIT or MANUAL"):
        build_recovery_candidates(
            operation,
            step,
            bad_intent,
            decision=decision,
            transaction_now=BASE_TIME,
        )
