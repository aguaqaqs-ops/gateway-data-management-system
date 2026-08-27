"""SQLite-neutral startup gates and the single-step atomic claim boundary."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from gateway_backend.operations.contracts import (
    JobStepKey,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    _validate_opaque_id,
)
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.recovery import StartupRecovery
from gateway_backend.operations.store import (
    CorruptPersistedRecord,
    ClaimCandidate,
    DEFAULT_PAGE_LIMIT,
    IntegrityScanPage,
    MAX_PAGE_LIMIT,
    OperationStore,
    RecordNotFound,
    StaleWrite,
    StoreBusy,
    UnsupportedSchemaVersion,
)
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ClaimedWork,
    RecoveryHook,
    ReadUnitOfWorkFactory,
    StartupDisposition,
    WorkerEvent,
    WorkerEventCode,
    WorkerObserver,
    WorkerRegistry,
    WriteUnitOfWorkFactory,
)

_LOGGER = logging.getLogger(__name__)

_ACTIVE_OPERATION_STATUSES = (
    OperationStatus.QUEUED,
    OperationStatus.RUNNING,
    OperationStatus.MANUAL_RECOVERY_REQUIRED,
)
_ACTIVE_STEP_STATUSES = frozenset(
    {
        StepStatus.PENDING,
        StepStatus.RUNNING,
        StepStatus.RETRY_WAIT,
        StepStatus.MANUAL_RECOVERY_REQUIRED,
    }
)
_REGISTRY_STEP_STATUSES = frozenset(
    {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.RETRY_WAIT}
)


def _new_worker_id() -> str:
    return f"worker-{uuid.uuid4()}"


def _new_lease_token() -> str:
    return f"lease-{uuid.uuid4()}"


@dataclass(frozen=True, slots=True)
class _ActivePair:
    operation: OperationRecord
    step: StepRecord


class WorkerStartup:
    """Run the bounded startup gates and claim at most one runnable step.

    The class only consumes the SQLite-neutral UoW and worker ports.  Startup
    validation keeps read transactions separate from the recovery callback; a
    callback therefore cannot accidentally perform handler or recovery I/O while
    a startup read transaction is open.
    """

    __slots__ = (
        "_read_uow_factory",
        "_write_uow_factory",
        "_registry",
        "_recovery_hook",
        "_startup_recovery",
        "_observer",
        "_lease_token_factory",
        "_page_limit",
        "_worker_id",
        "_ready",
    )

    def __init__(
        self,
        *,
        read_uow_factory: ReadUnitOfWorkFactory,
        write_uow_factory: WriteUnitOfWorkFactory,
        registry: WorkerRegistry,
        recovery_hook: RecoveryHook,
        observer: WorkerObserver,
        startup_recovery: StartupRecovery | None = None,
        worker_id_factory: Callable[[], str] = _new_worker_id,
        lease_token_factory: Callable[[], str] = _new_lease_token,
        page_limit: int = DEFAULT_PAGE_LIMIT,
    ) -> None:
        if not callable(read_uow_factory):
            raise ValueError("read_uow_factory must be callable")
        if not callable(write_uow_factory):
            raise ValueError("write_uow_factory must be callable")
        if not callable(getattr(registry, "resolve", None)):
            raise ValueError("registry must provide a callable resolve method")
        if not callable(recovery_hook):
            raise ValueError("recovery_hook must be callable")
        if startup_recovery is not None and type(startup_recovery) is not StartupRecovery:
            raise ValueError("startup_recovery must be StartupRecovery or None")
        if not callable(observer):
            raise ValueError("observer must be callable")
        if not callable(worker_id_factory):
            raise ValueError("worker_id_factory must be callable")
        if not callable(lease_token_factory):
            raise ValueError("lease_token_factory must be callable")
        if type(page_limit) is not int or not 1 <= page_limit <= MAX_PAGE_LIMIT:
            raise ValueError(f"page_limit must be an integer in the range 1..{MAX_PAGE_LIMIT}")

        worker_id = worker_id_factory()
        _validate_opaque_id(worker_id, "worker_id")

        self._read_uow_factory = read_uow_factory
        self._write_uow_factory = write_uow_factory
        self._registry = registry
        self._recovery_hook = recovery_hook
        self._startup_recovery = startup_recovery
        self._observer = observer
        self._lease_token_factory = lease_token_factory
        self._page_limit = page_limit
        self._worker_id = worker_id
        self._ready = False

    def startup(self) -> StartupDisposition:
        """Run the ordered double startup gate without sleeping or mutating state."""

        self._ready = False
        try:
            self._scan_integrity()
            active_pairs = self._validate_topology_and_registry()
            recovery_disposition = self._run_recovery(active_pairs)
            if recovery_disposition is not StartupDisposition.READY:
                self._emit_startup_block("recovery_blocked")
                return recovery_disposition

            self._scan_integrity()
            self._validate_topology_and_registry()
        except StoreBusy:
            self._emit_startup_block("store_busy")
            return StartupDisposition.RETRYABLE_BLOCK
        except StaleWrite:
            self._emit_startup_block("stale_write")
            return StartupDisposition.RETRYABLE_BLOCK
        except (CorruptPersistedRecord, UnsupportedSchemaVersion, RecordNotFound, ValueError) as exc:
            self._emit_startup_block(_failure_category(exc))
            return StartupDisposition.FATAL_BLOCK

        self._ready = True
        self._observer(
            WorkerEvent(
                code=WorkerEventCode.WORKER_READY,
                worker_id=self._worker_id,
            )
        )
        return StartupDisposition.READY

    def claim_one(self) -> ClaimedWork | None:
        """Atomically preflight, claim, verify, and commit one runnable step."""

        if not self._ready:
            raise ValueError("worker startup gate has not reached READY")

        with self._write_uow_factory() as unit_of_work:
            store = unit_of_work.operations
            transaction_now = store.transaction_now
            candidates, _ = store.list_claim_candidates(
                transaction_now,
                limit=1,
            )
            if not candidates:
                return None

            candidate = candidates[0]
            executor = self._resolve_executor(candidate.job_step_key)
            lease_token = self._lease_token_factory()
            _validate_opaque_id(lease_token, "lease_token")
            claimed = OperationLifecycleActions(
                store,
                transaction_now=transaction_now,
            ).claim_one(self._worker_id, lease_token)
            if claimed is None:
                raise ValueError("claim candidate disappeared inside the write transaction")

            operation, step = claimed
            self._assert_claim_identity(
                candidate,
                operation,
                step,
                lease_token,
            )
            work = ClaimedWork(
                operation=operation,
                step=step,
                executor=executor,
            )

        self._observer(
            WorkerEvent(
                code=WorkerEventCode.CLAIM_SUCCEEDED,
                operation_id=work.operation.operation_id,
                step_id=work.step.step_id,
                worker_id=self._worker_id,
                attempt=work.step.attempt_count,
            )
        )
        return work

    def _scan_integrity(self) -> None:
        with self._read_uow_factory() as unit_of_work:
            store = unit_of_work.operations
            cursor: str | None = None
            while True:
                page = store.scan_active_integrity(
                    cursor=cursor,
                    limit=self._page_limit,
                )
                if type(page) is not IntegrityScanPage:
                    raise ValueError("integrity scan must return IntegrityScanPage")
                next_cursor = page.next_cursor
                if next_cursor is None:
                    return
                if next_cursor == cursor:
                    raise ValueError("integrity scan cursor did not advance")
                cursor = next_cursor

    def _validate_topology_and_registry(self) -> tuple[_ActivePair, ...]:
        pairs: list[_ActivePair] = []
        with self._read_uow_factory() as unit_of_work:
            store = unit_of_work.operations
            for operation_status in _ACTIVE_OPERATION_STATUSES:
                cursor: str | None = None
                while True:
                    operations, next_cursor = store.list_operations_by_status(
                        operation_status,
                        cursor=cursor,
                        limit=self._page_limit,
                    )
                    for operation in operations:
                        active_steps = self._active_steps(store, operation)
                        if len(active_steps) != 1:
                            raise ValueError(
                                "non-terminal operation must have exactly one active step"
                            )
                        step = active_steps[0]
                        if step.operation_id != operation.operation_id:
                            raise ValueError("active step owner does not match operation")

                        pair = _ActivePair(operation=operation, step=step)
                        pairs.append(pair)
                        if self._is_manual(pair):
                            _LOGGER.warning(
                                "manual recovery required for operation_id=%s step_id=%s",
                                operation.operation_id,
                                step.step_id,
                            )
                        else:
                            if step.status not in _REGISTRY_STEP_STATUSES:
                                raise ValueError("active step status is not registry-runnable")
                            self._resolve_executor(
                                JobStepKey(
                                    job_kind=operation.job_kind,
                                    step_name=step.step_name,
                                )
                            )

                    if next_cursor is None:
                        break
                    if next_cursor == cursor:
                        raise ValueError("operation status cursor did not advance")
                    cursor = next_cursor
        return tuple(pairs)

    def _active_steps(
        self,
        store: OperationStore,
        operation: OperationRecord,
    ) -> tuple[StepRecord, ...]:
        operation_store = store
        cursor: str | None = None
        active: list[StepRecord] = []
        while True:
            steps, next_cursor = operation_store.list_steps(
                operation.operation_id,
                cursor=cursor,
                limit=self._page_limit,
            )
            for step in steps:
                if type(step) is not StepRecord:
                    raise ValueError("step listing must return StepRecord values")
                if step.status in _ACTIVE_STEP_STATUSES:
                    active.append(step)
            if next_cursor is None:
                return tuple(active)
            if next_cursor == cursor:
                raise ValueError("operation step cursor did not advance")
            cursor = next_cursor

    def _run_recovery(self, pairs: tuple[_ActivePair, ...]) -> StartupDisposition:
        disposition = StartupDisposition.READY
        for pair in pairs:
            if self._is_manual(pair):
                continue
            if self._startup_recovery is not None:
                candidate = self._startup_recovery.recover_pair(pair.operation, pair.step)
            else:
                candidate = self._recovery_hook(pair.operation, pair.step)
            if type(candidate) is not StartupDisposition:
                raise ValueError("recovery must return StartupDisposition")
            if candidate is StartupDisposition.FATAL_BLOCK:
                disposition = StartupDisposition.FATAL_BLOCK
            elif (
                candidate is StartupDisposition.RETRYABLE_BLOCK
                and disposition is StartupDisposition.READY
            ):
                disposition = StartupDisposition.RETRYABLE_BLOCK
        return disposition

    def _resolve_executor(self, key: JobStepKey) -> ClaimedExecutor:
        executor = self._registry.resolve(key)
        if executor is None:
            raise ValueError("registry has no executor for the runnable JobStepKey")
        if not callable(executor):
            raise ValueError("registry returned a non-callable executor")
        return executor

    def _assert_claim_identity(
        self,
        candidate: ClaimCandidate,
        operation: OperationRecord,
        step: StepRecord,
        lease_token: str,
    ) -> None:
        if operation.operation_id != candidate.operation_id:
            raise ValueError("claimed operation identity does not match the candidate")
        if step.step_id != candidate.step_id:
            raise ValueError("claimed step identity does not match the candidate")
        if step.operation_id != operation.operation_id:
            raise ValueError("claimed step owner does not match the operation")
        if JobStepKey(operation.job_kind, step.step_name) != candidate.job_step_key:
            raise ValueError("claimed JobStepKey does not match the candidate")
        if operation.status is not OperationStatus.RUNNING:
            raise ValueError("claimed operation must be RUNNING")
        if step.status is not StepStatus.RUNNING:
            raise ValueError("claimed step must be RUNNING")
        if step.worker_id != self._worker_id or step.lease_token != lease_token:
            raise ValueError("claimed lease identity does not match the worker")

    @staticmethod
    def _is_manual(pair: _ActivePair) -> bool:
        return (
            pair.operation.status is OperationStatus.MANUAL_RECOVERY_REQUIRED
            or pair.step.status is StepStatus.MANUAL_RECOVERY_REQUIRED
        )

    def _emit_startup_block(
        self,
        error_category: str,
    ) -> None:
        self._observer(
            WorkerEvent(
                code=WorkerEventCode.STARTUP_FAILED,
                worker_id=self._worker_id,
                error_category=error_category,
            )
        )


def _failure_category(error: BaseException) -> str:
    if isinstance(error, CorruptPersistedRecord):
        return "corrupt_persisted_record"
    if isinstance(error, UnsupportedSchemaVersion):
        return "unsupported_schema"
    if isinstance(error, RecordNotFound):
        return "record_not_found"
    return "startup_invariant"


__all__ = ["WorkerStartup"]
