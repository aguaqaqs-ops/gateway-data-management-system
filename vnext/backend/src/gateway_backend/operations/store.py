"""SQLite-neutral durable operation store ports and outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from gateway_backend.operations.contracts import (
    JobStepKey,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    _validate_opaque_id,
)
from gateway_backend.operations.state import (
    TransitionDisposition,
    WritePrecondition,
)

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 100
DEFAULT_CLAIM_LIMIT = 1
MAX_CLAIM_LIMIT = 1
_MAX_CURSOR_BYTES = 1024


class _OperationStoreError(Exception):
    """Internal common base; concrete store outcomes remain individually typed."""


class RecordNotFound(_OperationStoreError):
    """The requested operation or step does not exist."""


class StaleWrite(_OperationStoreError):
    """The candidate was based on an older optimistic version or lease identity."""


class LeaseExpired(_OperationStoreError):
    """A live-lease write was attempted after the current lease expired."""


class ConflictingDuplicate(_OperationStoreError):
    """An identity already exists with a different persisted record."""


class StoreBusy(_OperationStoreError):
    """The store could not acquire its bounded transaction lock."""


class CorruptPersistedRecord(_OperationStoreError):
    """A persisted row cannot be reconstructed as a valid R1 record."""


class UnsupportedSchemaVersion(_OperationStoreError):
    """The store contains a schema version newer than this program supports."""


@dataclass(frozen=True, slots=True)
class ClaimCandidate:
    """A bounded runnable-step identity; it carries no handler or business payload."""

    operation_id: str
    step_id: str
    job_step_key: JobStepKey
    status: StepStatus
    eligible_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        _validate_opaque_id(self.operation_id, "operation_id")
        _validate_opaque_id(self.step_id, "step_id")
        if type(self.job_step_key) is not JobStepKey:
            raise ValueError("job_step_key must be JobStepKey")
        if type(self.status) is not StepStatus:
            raise ValueError("status must be StepStatus")
        if self.status not in {StepStatus.PENDING, StepStatus.RETRY_WAIT}:
            raise ValueError("claim candidate status must be PENDING or RETRY_WAIT")
        _validate_utc_datetime(self.eligible_at, "eligible_at")
        _validate_utc_datetime(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class IntegrityScanPage:
    """Bounded result for validating active persisted operation state."""

    operations_scanned: int
    steps_scanned: int
    next_cursor: str | None

    def __post_init__(self) -> None:
        if type(self.operations_scanned) is not int or self.operations_scanned < 0:
            raise ValueError("operations_scanned must be a non-negative integer")
        if type(self.steps_scanned) is not int or self.steps_scanned < 0:
            raise ValueError("steps_scanned must be a non-negative integer")
        if self.next_cursor is not None and (
            type(self.next_cursor) is not str or not self.next_cursor
        ):
            raise ValueError("next_cursor must be a non-empty string or None")


@runtime_checkable
class OperationStore(Protocol):
    """Transaction-scoped operation participant; it never commits or rolls back."""

    @property
    def transaction_now(self) -> datetime:
        """Return the single UTC clock sample owned by the active transaction."""

    def get_operation(self, operation_id: str) -> OperationRecord:
        """Return an operation or raise RecordNotFound."""

    def get_step(self, step_id: str) -> StepRecord:
        """Return a step or raise RecordNotFound."""

    def list_steps(
        self,
        operation_id: str,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> tuple[tuple[StepRecord, ...], str | None]:
        """Return a bounded operation-scoped keyset page and its opaque next cursor."""

    def list_operations_by_status(
        self,
        status: OperationStatus,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> tuple[tuple[OperationRecord, ...], str | None]:
        """Return a bounded status-scoped keyset page and its opaque next cursor."""

    def list_claim_candidates(
        self,
        now: datetime,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_CLAIM_LIMIT,
    ) -> tuple[tuple[ClaimCandidate, ...], str | None]:
        """Return due PENDING/RETRY_WAIT candidates in stable keyset order."""

    def scan_active_integrity(
        self,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> IntegrityScanPage:
        """Validate one bounded page of active persisted records."""

    def insert_operation_with_initial_step(
        self,
        operation: OperationRecord,
        step: StepRecord,
    ) -> TransitionDisposition:
        """Insert the operation and its first step, or return exact idempotency."""

    def insert_successor_step(self, step: StepRecord) -> TransitionDisposition:
        """Insert a successor step, or return exact idempotency."""

    def compare_and_set_operation(
        self,
        candidate: OperationRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
    ) -> TransitionDisposition:
        """Apply a guarded operation candidate or return exact terminal idempotency."""

    def compare_and_set_step(
        self,
        candidate: StepRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
        require_live_lease: bool = False,
    ) -> TransitionDisposition:
        """Apply a guarded step candidate with optional live-lease enforcement."""


@runtime_checkable
class OperationUnitOfWork(Protocol):
    """Transaction owner exposing the operation participant and future repositories."""

    @property
    def operations(self) -> OperationStore:
        """Return the participant bound to this UoW transaction."""

    def __enter__(self) -> Self:
        """Begin or return the already-open transaction scope."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Commit on a clean exit, roll back on an exception, and never suppress it."""


def _validate_page_request(limit: object, cursor: object, *, maximum: int) -> None:
    """Validate bounded pagination arguments for concrete store implementations."""

    if type(limit) is not int or limit < 1 or limit > maximum:
        raise ValueError(f"limit must be an integer in the range 1..{maximum}")
    if cursor is None:
        return
    if type(cursor) is not str or not cursor:
        raise ValueError("cursor must be a non-empty string or None")
    if len(cursor.encode("utf-8")) > _MAX_CURSOR_BYTES:
        raise ValueError(f"cursor must be at most {_MAX_CURSOR_BYTES} UTF-8 bytes")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in cursor):
        raise ValueError("cursor must not contain control characters")


def _validate_utc_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{label} must be an aware UTC datetime")
    offset = value.utcoffset()
    if offset != timedelta(0):
        raise ValueError(f"{label} must be an aware UTC datetime")


__all__ = [
    "DEFAULT_CLAIM_LIMIT",
    "DEFAULT_PAGE_LIMIT",
    "MAX_CLAIM_LIMIT",
    "MAX_PAGE_LIMIT",
    "ClaimCandidate",
    "IntegrityScanPage",
    "CorruptPersistedRecord",
    "ConflictingDuplicate",
    "LeaseExpired",
    "OperationStore",
    "OperationUnitOfWork",
    "RecordNotFound",
    "StaleWrite",
    "StoreBusy",
    "UnsupportedSchemaVersion",
]
