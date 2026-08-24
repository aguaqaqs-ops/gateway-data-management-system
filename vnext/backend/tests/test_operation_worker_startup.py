"""Startup topology and atomic claim tests without SQLite or worker threads."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Callable, Self, TypeVar, cast

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.operations.contracts import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    JobStepKey,
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.state import TransitionDisposition, WritePrecondition
from gateway_backend.operations.store import (
    ClaimCandidate,
    ConflictingDuplicate,
    IntegrityScanPage,
    LeaseExpired,
    RecordNotFound,
    StaleWrite,
    StoreBusy,
)
from gateway_backend.operations.worker import (
    ClaimedWork,
    ExecutorAcknowledgment,
    RecoveryHook,
    StartupDisposition,
    WorkerEvent,
)
from gateway_backend.operations.worker_startup import WorkerStartup

pytestmark = pytest.mark.unit

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def _operation(
    operation_id: str,
    *,
    status: OperationStatus = OperationStatus.QUEUED,
    job_kind: str = "import.package",
) -> OperationRecord:
    diagnostic = (
        OperationDiagnostic(code="MANUAL", message="operator action required")
        if status is OperationStatus.MANUAL_RECOVERY_REQUIRED
        else None
    )
    return OperationRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        operation_id=operation_id,
        job_kind=job_kind,
        job_contract_version="backend-vnext/import-package/v1",
        job_payload=canonicalize_json_value({}),
        job_payload_ref=None,
        business_refs=(),
        artifact_refs=(),
        repository_operation_id=None,
        checkpoint_ref=None,
        ready_closure_ref=None,
        status=status,
        diagnostic=diagnostic,
        cancel_requested=False,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        completed_at=None,
        optimistic_version=0,
    )


def _step(
    operation_id: str,
    step_id: str,
    *,
    status: StepStatus = StepStatus.PENDING,
    step_name: str = "validate",
) -> StepRecord:
    is_running = status is StepStatus.RUNNING
    is_retry = status is StepStatus.RETRY_WAIT
    is_manual = status is StepStatus.MANUAL_RECOVERY_REQUIRED
    diagnostic = (
        OperationDiagnostic(
            code="MANUAL" if is_manual else "RETRY",
            message="operator action required" if is_manual else "retry later",
        )
        if is_retry or is_manual
        else None
    )
    return StepRecord(
        contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
        step_id=step_id,
        operation_id=operation_id,
        step_name=step_name,
        status=status,
        attempt_count=0 if status is StepStatus.PENDING else 1,
        diagnostic=diagnostic,
        cancel_requested=False,
        retry_not_before=BASE_TIME if is_retry else None,
        worker_id="old-worker" if is_running else None,
        lease_token="old-lease" if is_running else None,
        lease_expires_at=BASE_TIME + timedelta(seconds=30) if is_running else None,
        checkpoint_ref=None,
        prior_output_refs=(),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
        started_at=BASE_TIME if is_running or is_retry or is_manual else None,
        completed_at=None,
        optimistic_version=0,
    )


class FakeStore:
    """A bounded transaction participant implementing the R2 store port."""

    def __init__(
        self,
        operations: tuple[OperationRecord, ...] = (),
        steps: tuple[StepRecord, ...] = (),
        *,
        step_listing_overrides: dict[str, tuple[StepRecord, ...]] | None = None,
    ) -> None:
        self.operation_records = {item.operation_id: item for item in operations}
        self.step_records = {item.step_id: item for item in steps}
        self.step_listing_overrides = step_listing_overrides or {}
        self.transaction_now = BASE_TIME + timedelta(seconds=1)
        self.in_transaction = False
        self.transaction_kind: str | None = None
        self.events: list[str] = []
        self.scan_calls = 0
        self.integrity_passes = 0
        self.claim_candidate_calls = 0
        self.write_count = 0
        self.rollback_count = 0
        self.busy_scan_once = False
        self.claim_candidate_sequences: list[tuple[ClaimCandidate, ...]] = []

    def begin(self, kind: str) -> None:
        assert not self.in_transaction
        self.in_transaction = True
        self.transaction_kind = kind
        self.events.append(f"begin:{kind}")

    def finish(self, *, rollback: bool) -> None:
        self.in_transaction = False
        self.transaction_kind = None
        if rollback:
            self.rollback_count += 1
            self.events.append("rollback")
        else:
            self.events.append("commit")

    def get_operation(self, operation_id: str) -> OperationRecord:
        try:
            return self.operation_records[operation_id]
        except KeyError as exc:
            raise RecordNotFound(operation_id) from exc

    def get_step(self, step_id: str) -> StepRecord:
        try:
            return self.step_records[step_id]
        except KeyError as exc:
            raise RecordNotFound(step_id) from exc

    def list_steps(
        self,
        operation_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[tuple[StepRecord, ...], str | None]:
        self.events.append(f"steps:{operation_id}:{cursor}")
        records = self.step_listing_overrides.get(
            operation_id,
            tuple(
                sorted(
                    (
                        step
                        for step in self.step_records.values()
                        if step.operation_id == operation_id
                    ),
                    key=lambda item: item.step_id,
                )
            ),
        )
        return _page(records, cursor, limit, prefix="step")

    def list_operations_by_status(
        self,
        status: OperationStatus,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[tuple[OperationRecord, ...], str | None]:
        self.events.append(f"operations:{status.value}:{cursor}")
        records = tuple(
            sorted(
                (
                    operation
                    for operation in self.operation_records.values()
                    if operation.status is status
                ),
                key=lambda item: item.operation_id,
            )
        )
        return _page(records, cursor, limit, prefix="operation")

    def list_claim_candidates(
        self,
        now: datetime,
        *,
        cursor: str | None = None,
        limit: int = 1,
    ) -> tuple[tuple[ClaimCandidate, ...], str | None]:
        del cursor, limit
        self.claim_candidate_calls += 1
        self.events.append("claim_candidates")
        if self.claim_candidate_sequences:
            return self.claim_candidate_sequences.pop(0), None

        candidates: list[ClaimCandidate] = []
        for step in self.step_records.values():
            if step.status not in {StepStatus.PENDING, StepStatus.RETRY_WAIT}:
                continue
            operation = self.operation_records[step.operation_id]
            if operation.status not in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
                continue
            eligible_at = step.created_at if step.status is StepStatus.PENDING else step.retry_not_before
            assert eligible_at is not None
            if eligible_at > now:
                continue
            candidates.append(
                ClaimCandidate(
                    operation_id=operation.operation_id,
                    step_id=step.step_id,
                    job_step_key=JobStepKey(
                        job_kind=operation.job_kind,
                        step_name=step.step_name,
                    ),
                    status=step.status,
                    eligible_at=eligible_at,
                    created_at=step.created_at,
                )
            )
        candidates.sort(key=lambda item: (item.eligible_at, item.created_at, item.step_id))
        return tuple(candidates[:1]), None

    def scan_active_integrity(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> IntegrityScanPage:
        self.scan_calls += 1
        self.events.append(f"scan:{cursor}")
        if cursor is None:
            self.integrity_passes += 1
        if self.busy_scan_once:
            self.busy_scan_once = False
            raise StoreBusy("synthetic busy")

        operations = tuple(
            sorted(
                (
                    operation
                    for operation in self.operation_records.values()
                    if not operation.status.is_final_terminal()
                ),
                key=lambda item: item.operation_id,
            )
        )
        steps = tuple(
            sorted(
                (
                    step
                    for step in self.step_records.values()
                    if not step.status.is_final_terminal()
                ),
                key=lambda item: item.step_id,
            )
        )
        phase, index = _decode_scan_cursor(cursor)
        if phase == "operations":
            operation_values = operations
            operation_batch = operation_values[index : index + limit]
            if index + len(operation_batch) < len(operation_values):
                next_cursor = f"operations:{index + len(operation_batch)}"
            elif steps:
                next_cursor = "steps:0"
            else:
                next_cursor = None
            return IntegrityScanPage(len(operation_batch), 0, next_cursor)

        step_values = steps
        step_batch = step_values[index : index + limit]
        next_cursor = (
            f"steps:{index + len(step_batch)}"
            if index + len(step_batch) < len(step_values)
            else None
        )
        return IntegrityScanPage(0, len(step_batch), next_cursor)

    def insert_operation_with_initial_step(
        self,
        operation: OperationRecord,
        step: StepRecord,
    ) -> TransitionDisposition:
        self.operation_records[operation.operation_id] = operation
        self.step_records[step.step_id] = step
        return TransitionDisposition.APPLY

    def insert_successor_step(self, step: StepRecord) -> TransitionDisposition:
        if step.step_id in self.step_records:
            raise ConflictingDuplicate(step.step_id)
        self.step_records[step.step_id] = step
        return TransitionDisposition.APPLY

    def compare_and_set_operation(
        self,
        candidate: OperationRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
    ) -> TransitionDisposition:
        del recovery_authorized
        current = self.get_operation(candidate.operation_id)
        if precondition.expected_optimistic_version != current.optimistic_version:
            raise StaleWrite("operation version mismatch")
        if precondition.worker_id is not None or precondition.lease_token is not None:
            raise StaleWrite("operation lease precondition is not null")
        self.operation_records[candidate.operation_id] = candidate
        self.write_count += 1
        return TransitionDisposition.APPLY

    def compare_and_set_step(
        self,
        candidate: StepRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
        require_live_lease: bool = False,
    ) -> TransitionDisposition:
        del recovery_authorized
        current = self.get_step(candidate.step_id)
        if precondition.expected_optimistic_version != current.optimistic_version:
            raise StaleWrite("step version mismatch")
        if (
            precondition.worker_id != current.worker_id
            or precondition.lease_token != current.lease_token
        ):
            raise StaleWrite("step lease precondition mismatch")
        if require_live_lease and (
            current.lease_expires_at is None or current.lease_expires_at <= self.transaction_now
        ):
            raise LeaseExpired("step lease expired")
        self.step_records[candidate.step_id] = candidate
        self.write_count += 1
        return TransitionDisposition.APPLY


class FakeUow:
    def __init__(self, store: FakeStore, *, kind: str) -> None:
        self.store = store
        self.kind = kind
        self._snapshot: tuple[dict[str, OperationRecord], dict[str, StepRecord]] | None = None

    @property
    def operations(self) -> FakeStore:
        return self.store

    def __enter__(self) -> Self:
        self._snapshot = (self.store.operation_records.copy(), self.store.step_records.copy())
        self.store.begin(self.kind)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_value, traceback
        if exc_type is not None:
            assert self._snapshot is not None
            self.store.operation_records, self.store.step_records = self._snapshot
        self.store.finish(rollback=exc_type is not None)
        self._snapshot = None


class UowFactory:
    def __init__(self, store: FakeStore, *, kind: str) -> None:
        self.store = store
        self.kind = kind
        self.calls = 0

    def __call__(self) -> FakeUow:
        self.calls += 1
        return FakeUow(self.store, kind=self.kind)


class Registry:
    def __init__(self, keys: set[JobStepKey]) -> None:
        self.keys = keys
        self.calls: list[JobStepKey] = []
        self.executor = lambda *_args: ExecutorAcknowledgment.PUBLISHED

    def resolve(self, key: JobStepKey) -> Callable[..., ExecutorAcknowledgment] | None:
        self.calls.append(key)
        return self.executor if key in self.keys else None


def _startup(
    store: FakeStore,
    registry: Registry,
    recovery_hook: Callable[[OperationRecord, StepRecord], StartupDisposition]
    | None = None,
    *,
    page_limit: int = 50,
    worker_id_factory: Callable[[], str] | None = None,
    lease_token_factory: Callable[[], str] | None = None,
) -> tuple[WorkerStartup, UowFactory, UowFactory, list[WorkerEvent]]:
    read_factory = UowFactory(store, kind="read")
    write_factory = UowFactory(store, kind="write")
    events: list[WorkerEvent] = []

    def ready_recovery(
        _operation: OperationRecord,
        _step: StepRecord,
    ) -> StartupDisposition:
        return StartupDisposition.READY

    def observe(event: WorkerEvent) -> None:
        events.append(event)

    effective_recovery = recovery_hook if recovery_hook is not None else ready_recovery
    startup = WorkerStartup(
        read_uow_factory=read_factory,
        write_uow_factory=write_factory,
        registry=registry,
        recovery_hook=cast(RecoveryHook, effective_recovery),
        observer=observe,
        worker_id_factory=worker_id_factory or (lambda: "worker-test"),
        lease_token_factory=lease_token_factory or (lambda: "lease-test"),
        page_limit=page_limit,
    )
    return startup, read_factory, write_factory, events


def _decode_scan_cursor(cursor: str | None) -> tuple[str, int]:
    if cursor is None:
        return "operations", 0
    phase, index = cursor.split(":")
    return phase, int(index)


PageValue = TypeVar("PageValue")


def _page(
    values: tuple[PageValue, ...],
    cursor: str | None,
    limit: int,
    *,
    prefix: str,
) -> tuple[tuple[PageValue, ...], str | None]:
    index = 0 if cursor is None else int(cursor.split(":")[1])
    batch = values[index : index + limit]
    next_cursor = (
        f"{prefix}:{index + len(batch)}" if index + len(batch) < len(values) else None
    )
    return batch, next_cursor


def test_startup_scans_all_pages_in_order_and_keeps_recovery_outside_read_uow() -> None:
    operation_one = _operation("op-1")
    operation_two = _operation("op-2", status=OperationStatus.RUNNING)
    steps = (
        _step("op-1", "step-1"),
        _step("op-2", "step-2", status=StepStatus.RUNNING),
    )
    store = FakeStore((operation_one, operation_two), steps)
    registry = Registry(
        {
            JobStepKey("import.package", "validate"),
        }
    )
    recovery_calls: list[str] = []

    def recovery(operation: OperationRecord, step: StepRecord) -> StartupDisposition:
        assert not store.in_transaction
        recovery_calls.append(f"{operation.operation_id}:{step.step_id}")
        return StartupDisposition.READY

    startup, read_factory, _write_factory, events = _startup(
        store,
        registry,
        recovery,
        page_limit=1,
    )

    assert startup.startup() is StartupDisposition.READY
    assert read_factory.calls == 4
    assert recovery_calls == ["op-1:step-1", "op-2:step-2"]
    assert [event.code.value for event in events] == ["worker_ready"]
    assert store.scan_calls >= 4
    assert store.events[0] == "begin:read"
    assert any(event.startswith("scan:") for event in store.events)


TOPOLOGY_FAULTS = (
    ("zero active steps", (), None),
    (
        "multiple active steps",
        (_step("op-1", "step-1"), _step("op-1", "step-2", step_name="publish")),
        None,
    ),
    (
        "owner mismatch",
        (),
        {"op-1": (_step("other-op", "step-1"),)},
    ),
)


@pytest.mark.parametrize("name,steps,overrides", TOPOLOGY_FAULTS)
def test_topology_faults_fail_closed_before_recovery(
    name: str,
    steps: tuple[StepRecord, ...],
    overrides: dict[str, tuple[StepRecord, ...]] | None,
) -> None:
    del name
    operation = _operation("op-1")
    store = FakeStore(
        (operation,),
        steps,
        step_listing_overrides=overrides,
    )
    registry = Registry({JobStepKey("import.package", "validate")})
    recovery_calls: list[str] = []
    def recovery(operation: OperationRecord, _step: StepRecord) -> StartupDisposition:
        recovery_calls.append(operation.operation_id)
        return StartupDisposition.READY

    startup, _read_factory, _write_factory, events = _startup(store, registry, recovery)

    assert startup.startup() is StartupDisposition.FATAL_BLOCK
    assert recovery_calls == []
    assert [event.code.value for event in events] == ["startup_failed"]
    assert store.write_count == 0


def test_manual_recovery_is_warned_and_never_claimed_while_other_work_runs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    manual_operation = _operation(
        "op-manual",
        status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
    )
    queued_operation = _operation("op-queued")
    store = FakeStore(
        (manual_operation, queued_operation),
        (
            _step(
                "op-manual",
                "step-manual",
                status=StepStatus.MANUAL_RECOVERY_REQUIRED,
            ),
            _step("op-queued", "step-queued"),
        ),
    )
    registry = Registry({JobStepKey("import.package", "validate")})
    startup, _read_factory, _write_factory, _events = _startup(store, registry)

    assert startup.startup() is StartupDisposition.READY
    assert "manual recovery required" in caplog.text
    work = startup.claim_one()
    assert work is not None
    assert work.step.step_id == "step-queued"
    assert store.step_records["step-manual"].status is StepStatus.MANUAL_RECOVERY_REQUIRED


def test_empty_database_is_ready_with_empty_registry_and_has_no_claim() -> None:
    store = FakeStore()
    startup, _read_factory, write_factory, events = _startup(store, Registry(set()))

    assert startup.startup() is StartupDisposition.READY
    assert startup.claim_one() is None
    assert write_factory.calls == 1
    assert [event.code.value for event in events] == ["worker_ready"]


@pytest.mark.parametrize(
    ("recovery_result", "expected", "expected_integrity_passes"),
    (
        (StartupDisposition.READY, StartupDisposition.READY, 2),
        (StartupDisposition.RETRYABLE_BLOCK, StartupDisposition.RETRYABLE_BLOCK, 1),
        (StartupDisposition.FATAL_BLOCK, StartupDisposition.FATAL_BLOCK, 1),
    ),
)
def test_recovery_disposition_controls_second_gate(
    recovery_result: StartupDisposition,
    expected: StartupDisposition,
    expected_integrity_passes: int,
) -> None:
    operation = _operation("op-1")
    store = FakeStore((operation,), (_step("op-1", "step-1"),))
    registry = Registry({JobStepKey("import.package", "validate")})
    startup, _read_factory, _write_factory, _events = _startup(
        store,
        registry,
        lambda _operation, _step: recovery_result,
    )

    assert startup.startup() is expected
    assert store.integrity_passes == expected_integrity_passes


def test_second_gate_catches_unknown_key_created_by_recovery() -> None:
    operation = _operation("op-1")
    store = FakeStore((operation,), (_step("op-1", "step-1"),))
    registry = Registry({JobStepKey("import.package", "validate")})
    mutated = False

    def recovery(_operation: OperationRecord, _current_step: StepRecord) -> StartupDisposition:
        nonlocal mutated
        if not mutated:
            mutated = True
            new_operation = _operation_record_for_test("op-unknown", "unknown.job")
            store.operation_records[new_operation.operation_id] = new_operation
            store.step_records["step-unknown"] = _step(
                "op-unknown",
                "step-unknown",
            )
        return StartupDisposition.READY

    startup, _read_factory, _write_factory, events = _startup(store, registry, recovery)

    assert startup.startup() is StartupDisposition.FATAL_BLOCK
    assert [event.code.value for event in events] == ["startup_failed"]


def test_atomic_claim_uses_one_write_uow_and_commits_exact_identity() -> None:
    operation = _operation("op-1")
    store = FakeStore((operation,), (_step("op-1", "step-1"),))
    registry = Registry({JobStepKey("import.package", "validate")})
    token_values = iter(("lease-1", "lease-2"))
    startup, _read_factory, write_factory, events = _startup(
        store,
        registry,
        worker_id_factory=lambda: "worker-stable",
        lease_token_factory=lambda: next(token_values),
    )

    assert startup.startup() is StartupDisposition.READY
    work = startup.claim_one()

    assert isinstance(work, ClaimedWork)
    assert work.operation.status is OperationStatus.RUNNING
    assert work.step.status is StepStatus.RUNNING
    assert work.step.worker_id == "worker-stable"
    assert work.step.lease_token == "lease-1"
    assert write_factory.calls == 1
    assert store.claim_candidate_calls == 2
    assert [event.code.value for event in events] == ["worker_ready", "claim_succeeded"]


def test_missing_registry_rolls_back_without_generating_a_lease_token() -> None:
    operation = _operation("op-1")
    step = _step("op-1", "step-1")
    store = FakeStore((operation,), (step,))
    registry = Registry(set())
    generated_tokens: list[str] = []

    def token_factory() -> str:
        generated_tokens.append("unexpected")
        return "lease-1"

    startup, _read_factory, _write_factory, _events = _startup(
        store,
        registry,
        lease_token_factory=token_factory,
    )

    # Empty startup is valid; a later unknown runnable record must still be
    # rejected by the atomic claim preflight.
    store.operation_records.clear()
    store.step_records.clear()
    assert startup.startup() is StartupDisposition.READY
    store.operation_records[operation.operation_id] = operation
    store.step_records[step.step_id] = step
    before = (store.operation_records.copy(), store.step_records.copy())

    with pytest.raises(ValueError, match="registry"):
        startup.claim_one()

    assert generated_tokens == []
    assert store.operation_records == before[0]
    assert store.step_records == before[1]
    assert store.rollback_count == 1


def test_identity_mismatch_rolls_back_the_claim_prefix() -> None:
    operation_one = _operation("op-1")
    operation_two = _operation("op-2")
    step_one = _step("op-1", "step-1")
    step_two = _step("op-2", "step-2")
    store = FakeStore((operation_one, operation_two), (step_one, step_two))
    candidate_one = ClaimCandidate(
        operation_id="op-1",
        step_id="step-1",
        job_step_key=JobStepKey("import.package", "validate"),
        status=StepStatus.PENDING,
        eligible_at=BASE_TIME,
        created_at=BASE_TIME,
    )
    candidate_two = dataclasses.replace(candidate_one, operation_id="op-2", step_id="step-2")
    store.claim_candidate_sequences = [(candidate_one,), (candidate_two,)]
    registry = Registry({JobStepKey("import.package", "validate")})
    startup, _read_factory, _write_factory, _events = _startup(store, registry)

    assert startup.startup() is StartupDisposition.READY
    with pytest.raises(ValueError, match="identity"):
        startup.claim_one()

    assert store.operation_records["op-1"].status is OperationStatus.QUEUED
    assert store.operation_records["op-2"].status is OperationStatus.QUEUED
    assert store.step_records["step-1"].status is StepStatus.PENDING
    assert store.step_records["step-2"].status is StepStatus.PENDING
    assert store.rollback_count == 1


def test_default_identity_factories_are_typed_uuid4_and_worker_id_is_stable() -> None:
    operations = (_operation("op-1"), _operation("op-2"))
    steps = (_step("op-1", "step-1"), _step("op-2", "step-2"))
    store = FakeStore(operations, steps)
    registry = Registry({JobStepKey("import.package", "validate")})
    startup, _read_factory, _write_factory, _events = WorkerStartupHarness.make(store, registry)

    assert startup.startup() is StartupDisposition.READY
    first = startup.claim_one()
    second = startup.claim_one()

    assert first is not None and second is not None
    assert first.step.worker_id == second.step.worker_id
    assert first.step.worker_id is not None
    assert first.step.lease_token is not None
    assert second.step.lease_token is not None
    assert first.step.worker_id.startswith("worker-")
    assert first.step.lease_token.startswith("lease-")
    assert uuid.UUID(first.step.worker_id.removeprefix("worker-")).version == 4
    assert uuid.UUID(first.step.lease_token.removeprefix("lease-")).version == 4
    assert first.step.lease_token != second.step.lease_token


def test_store_busy_is_retryable_without_sleep() -> None:
    store = FakeStore()
    store.busy_scan_once = True
    startup, _read_factory, _write_factory, events = _startup(store, Registry(set()))

    assert startup.startup() is StartupDisposition.RETRYABLE_BLOCK
    assert [event.code.value for event in events] == ["startup_failed"]
    assert startup.startup() is StartupDisposition.READY


def _operation_record_for_test(operation_id: str, job_kind: str) -> OperationRecord:
    return _operation(operation_id, job_kind=job_kind)


class WorkerStartupHarness:
    """Uses production identity factories while keeping UoW creation fake."""

    @staticmethod
    def make(
        store: FakeStore,
        registry: Registry,
    ) -> tuple[WorkerStartup, UowFactory, UowFactory, list[WorkerEvent]]:
        read_factory = UowFactory(store, kind="read")
        write_factory = UowFactory(store, kind="write")
        events: list[WorkerEvent] = []

        def ready_recovery(
            _operation: OperationRecord,
            _step: StepRecord,
        ) -> StartupDisposition:
            return StartupDisposition.READY

        def observe(event: WorkerEvent) -> None:
            events.append(event)

        startup = WorkerStartup(
            read_uow_factory=read_factory,
            write_uow_factory=write_factory,
            registry=registry,
            recovery_hook=cast(RecoveryHook, ready_recovery),
            observer=observe,
        )
        return startup, read_factory, write_factory, events
