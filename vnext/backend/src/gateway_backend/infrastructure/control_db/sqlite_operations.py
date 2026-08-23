"""SQLite row mapping and transaction-scoped OperationStore adapter."""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from gateway_shared_kernel import CanonicalEncodingError
from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.operations import (
    ClaimCandidate,
    CorruptPersistedRecord,
    ConflictingDuplicate,
    DEFAULT_CLAIM_LIMIT,
    DEFAULT_PAGE_LIMIT,
    MAX_CLAIM_LIMIT,
    MAX_PAGE_LIMIT,
    JobStepKey,
    IntegrityScanPage,
    LeaseExpired,
    OperationRecord,
    OperationStatus,
    RecordNotFound,
    StaleWrite,
    StepRecord,
    StepStatus,
    StoreBusy,
    TransitionDisposition,
    WritePrecondition,
    operation_record_from_document,
    step_record_from_document,
    validate_operation_transition,
    validate_step_transition,
    validate_write_precondition,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1
_MAX_CURSOR_BYTES = 1024
_CURSOR_VERSION = 1
_INTEGRITY_CURSOR_VERSION = 1
_INTEGRITY_OPERATION_PHASE = "operations"
_INTEGRITY_STEP_PHASE = "steps"
_ACTIVE_OPERATION_STATUSES = ("QUEUED", "RUNNING", "MANUAL_RECOVERY_REQUIRED")
_ACTIVE_STEP_STATUSES = (
    "PENDING",
    "RUNNING",
    "RETRY_WAIT",
    "MANUAL_RECOVERY_REQUIRED",
)

_OPERATION_COLUMNS = (
    "operation_id, contract_version, optimistic_version, job_kind, job_contract_version, "
    "job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id, "
    "checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested, created_at_us, "
    "updated_at_us, completed_at_us"
)
_STEP_COLUMNS = (
    "step_id, operation_id, contract_version, optimistic_version, step_name, attempt_count, "
    "status, diagnostic, cancel_requested, retry_not_before_us, worker_id, lease_token, "
    "lease_expires_at_us, checkpoint_ref, prior_output_refs, created_at_us, updated_at_us, "
    "started_at_us, completed_at_us, eligible_at_us"
)
_OPERATION_INSERT_COLUMNS = (
    "operation_id, contract_version, optimistic_version, job_kind, job_contract_version, "
    "job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id, "
    "checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested, created_at_us, "
    "updated_at_us, completed_at_us"
)
_OPERATION_UPDATE_COLUMNS = (
    "contract_version, optimistic_version, job_kind, job_contract_version, job_payload, "
    "job_payload_ref, business_refs, artifact_refs, repository_operation_id, checkpoint_ref, "
    "ready_closure_ref, status, diagnostic, cancel_requested, created_at_us, updated_at_us, "
    "completed_at_us"
)
_STEP_INSERT_COLUMNS = (
    "step_id, operation_id, contract_version, optimistic_version, step_name, attempt_count, "
    "status, diagnostic, cancel_requested, retry_not_before_us, worker_id, lease_token, "
    "lease_expires_at_us, checkpoint_ref, prior_output_refs, created_at_us, updated_at_us, "
    "started_at_us, completed_at_us, eligible_at_us"
)
_STEP_UPDATE_COLUMNS = (
    "operation_id, contract_version, optimistic_version, step_name, attempt_count, status, "
    "diagnostic, cancel_requested, retry_not_before_us, worker_id, lease_token, "
    "lease_expires_at_us, checkpoint_ref, prior_output_refs, created_at_us, updated_at_us, "
    "started_at_us, completed_at_us, eligible_at_us"
)


class SQLiteOperationStore:
    """Concrete OperationStore participant bound to one already-open transaction."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        transaction_now: datetime,
        read_only: bool = False,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteOperationStore requires an active transaction")
        if type(read_only) is not bool:
            raise ValueError("read_only must be a bool")
        _validate_utc_datetime(transaction_now, "transaction_now")
        self._connection = connection
        self._transaction_now = transaction_now
        self._read_only = read_only

    def get_operation(self, operation_id: str) -> OperationRecord:
        self._require_transaction()
        _validate_identity(operation_id, "operation_id")
        row = self._select_operation_row(operation_id)
        if row is None:
            raise RecordNotFound(f"operation {operation_id!r} was not found")
        return operation_record_from_row(_as_mapping(row))

    def get_step(self, step_id: str) -> StepRecord:
        self._require_transaction()
        _validate_identity(step_id, "step_id")
        row = self._select_step_row(step_id)
        if row is None:
            raise RecordNotFound(f"step {step_id!r} was not found")
        return step_record_from_row(_as_mapping(row))

    def list_steps(
        self,
        operation_id: str,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> tuple[tuple[StepRecord, ...], str | None]:
        self._require_transaction()
        _validate_identity(operation_id, "operation_id")
        _validate_page_request(limit, cursor, maximum=MAX_PAGE_LIMIT)
        self.get_operation(operation_id)
        cursor_values = _decode_cursor(
            cursor,
            scope="steps",
            fields=("created_at_us", "step_id"),
        )
        query = f"SELECT {_STEP_COLUMNS} FROM step_records WHERE operation_id = ?"
        parameters: list[object] = [operation_id]
        if cursor_values is not None:
            query += " AND (created_at_us > ? OR (created_at_us = ? AND step_id > ?))"
            parameters.extend(
                [
                    cursor_values["created_at_us"],
                    cursor_values["created_at_us"],
                    cursor_values["step_id"],
                ]
            )
        query += " ORDER BY created_at_us, step_id LIMIT ?"
        rows = self._execute(query, (*parameters, limit + 1)).fetchall()
        visible_rows, has_more = _page_rows(rows, limit)
        records = tuple(step_record_from_row(_as_mapping(row)) for row in visible_rows)
        next_cursor = None
        if has_more and visible_rows:
            last = _as_mapping(visible_rows[-1])
            next_cursor = _encode_cursor(
                "steps",
                created_at_us=_required_row_int(last, "created_at_us"),
                step_id=_required_row_text(last, "step_id"),
            )
        return records, next_cursor

    def list_operations_by_status(
        self,
        status: OperationStatus,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> tuple[tuple[OperationRecord, ...], str | None]:
        self._require_transaction()
        if type(status) is not OperationStatus:
            raise ValueError("status must be OperationStatus")
        _validate_page_request(limit, cursor, maximum=MAX_PAGE_LIMIT)
        cursor_values = _decode_cursor(
            cursor,
            scope="operation_status",
            fields=("status", "updated_at_us", "operation_id"),
        )
        if cursor_values is not None and cursor_values["status"] != status.value:
            raise ValueError("cursor status does not match requested status")
        query = f"SELECT {_OPERATION_COLUMNS} FROM operation_records WHERE status = ?"
        parameters: list[object] = [status.value]
        if cursor_values is not None:
            query += " AND (updated_at_us > ? OR (updated_at_us = ? AND operation_id > ?))"
            parameters.extend(
                [
                    cursor_values["updated_at_us"],
                    cursor_values["updated_at_us"],
                    cursor_values["operation_id"],
                ]
            )
        query += " ORDER BY updated_at_us, operation_id LIMIT ?"
        rows = self._execute(query, (*parameters, limit + 1)).fetchall()
        visible_rows, has_more = _page_rows(rows, limit)
        records = tuple(operation_record_from_row(_as_mapping(row)) for row in visible_rows)
        next_cursor = None
        if has_more and visible_rows:
            last = _as_mapping(visible_rows[-1])
            next_cursor = _encode_cursor(
                "operation_status",
                status=status.value,
                updated_at_us=_required_row_int(last, "updated_at_us"),
                operation_id=_required_row_text(last, "operation_id"),
            )
        return records, next_cursor

    def list_claim_candidates(
        self,
        now: datetime,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_CLAIM_LIMIT,
    ) -> tuple[tuple[ClaimCandidate, ...], str | None]:
        self._require_transaction()
        _validate_utc_datetime(now, "now")
        _validate_page_request(limit, cursor, maximum=MAX_CLAIM_LIMIT)
        cursor_values = _decode_cursor(
            cursor,
            scope="claim",
            fields=("eligible_at_us", "created_at_us", "step_id"),
        )
        query = (
            f"SELECT s.{_STEP_COLUMNS.replace(', ', ', s.')} FROM step_records AS s "
            "JOIN operation_records AS o ON o.operation_id = s.operation_id "
            "WHERE s.status IN ('PENDING', 'RETRY_WAIT') AND s.eligible_at_us <= ? "
            "AND o.status IN ('QUEUED', 'RUNNING')"
        )
        parameters: list[object] = [_datetime_to_epoch_us(now)]
        if cursor_values is not None:
            query += (
                " AND (s.eligible_at_us > ? OR "
                "(s.eligible_at_us = ? AND (s.created_at_us > ? OR "
                "(s.created_at_us = ? AND s.step_id > ?))))"
            )
            parameters.extend(
                [
                    cursor_values["eligible_at_us"],
                    cursor_values["eligible_at_us"],
                    cursor_values["created_at_us"],
                    cursor_values["created_at_us"],
                    cursor_values["step_id"],
                ]
            )
        query += " ORDER BY s.eligible_at_us, s.created_at_us, s.step_id LIMIT ?"
        rows = self._execute(query, (*parameters, limit + 1)).fetchall()
        visible_rows, has_more = _page_rows(rows, limit)
        candidates: list[ClaimCandidate] = []
        for row in visible_rows:
            step = step_record_from_row(_as_mapping(row))
            operation = self.get_operation(step.operation_id)
            if step.status not in {StepStatus.PENDING, StepStatus.RETRY_WAIT}:
                raise CorruptPersistedRecord("claim query returned a non-claimable step")
            if step.retry_not_before is not None and step.status is StepStatus.PENDING:
                raise CorruptPersistedRecord("PENDING step has retry metadata")
            eligible_at = step.created_at if step.status is StepStatus.PENDING else step.retry_not_before
            if eligible_at is None:
                raise CorruptPersistedRecord("claimable step has no eligibility time")
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
        next_cursor = None
        if has_more and visible_rows:
            last = _as_mapping(visible_rows[-1])
            next_cursor = _encode_cursor(
                "claim",
                eligible_at_us=_required_row_int(last, "eligible_at_us"),
                created_at_us=_required_row_int(last, "created_at_us"),
                step_id=_required_row_text(last, "step_id"),
            )
        return tuple(candidates), next_cursor

    def scan_active_integrity(
        self,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> IntegrityScanPage:
        """Validate a bounded keyset page of active Operations or Steps.

        Operations are scanned before Steps.  The cursor records the phase and the
        last ``(updated_at_us, identity)`` pair in that phase, so callers can
        repeatedly invoke this method without exposing SQL or row layout.
        """

        self._require_transaction()
        _validate_page_request(limit, cursor, maximum=MAX_PAGE_LIMIT)
        phase, last_updated_at_us, last_identity = _decode_integrity_cursor(cursor)

        if phase == _INTEGRITY_OPERATION_PHASE:
            rows = self._select_active_operation_rows(
                last_updated_at_us=last_updated_at_us,
                last_identity=last_identity,
                limit=limit,
            )
            visible_rows, has_more = _page_rows(rows, limit)
            for row in visible_rows:
                operation_record_from_row(_as_mapping(row))
            if has_more and visible_rows:
                last = _as_mapping(visible_rows[-1])
                return IntegrityScanPage(
                    operations_scanned=len(visible_rows),
                    steps_scanned=0,
                    next_cursor=_encode_integrity_cursor(
                        _INTEGRITY_OPERATION_PHASE,
                        updated_at_us=_required_row_int(last, "updated_at_us"),
                        identity=_required_row_text(last, "operation_id"),
                    ),
                )

            remaining = limit - len(visible_rows)
            if remaining == 0:
                return IntegrityScanPage(
                    operations_scanned=len(visible_rows),
                    steps_scanned=0,
                    next_cursor=_encode_integrity_cursor(_INTEGRITY_STEP_PHASE),
                )
            step_rows = self._select_active_step_rows(
                last_updated_at_us=None,
                last_identity=None,
                limit=remaining,
            )
            visible_step_rows, step_has_more = _page_rows(step_rows, remaining)
            for row in visible_step_rows:
                step = step_record_from_row(_as_mapping(row))
                self._validate_active_step_owner(step)
            next_cursor = None
            if step_has_more and visible_step_rows:
                last = _as_mapping(visible_step_rows[-1])
                next_cursor = _encode_integrity_cursor(
                    _INTEGRITY_STEP_PHASE,
                    updated_at_us=_required_row_int(last, "updated_at_us"),
                    identity=_required_row_text(last, "step_id"),
                )
            return IntegrityScanPage(
                operations_scanned=len(visible_rows),
                steps_scanned=len(visible_step_rows),
                next_cursor=next_cursor,
            )

        rows = self._select_active_step_rows(
            last_updated_at_us=last_updated_at_us,
            last_identity=last_identity,
            limit=limit,
        )
        visible_rows, has_more = _page_rows(rows, limit)
        for row in visible_rows:
            step = step_record_from_row(_as_mapping(row))
            self._validate_active_step_owner(step)
        next_cursor = None
        if has_more and visible_rows:
            last = _as_mapping(visible_rows[-1])
            next_cursor = _encode_integrity_cursor(
                _INTEGRITY_STEP_PHASE,
                updated_at_us=_required_row_int(last, "updated_at_us"),
                identity=_required_row_text(last, "step_id"),
            )
        return IntegrityScanPage(
            operations_scanned=0,
            steps_scanned=len(visible_rows),
            next_cursor=next_cursor,
        )

    def insert_operation_with_initial_step(
        self,
        operation: OperationRecord,
        step: StepRecord,
    ) -> TransitionDisposition:
        self._require_writable()
        if type(operation) is not OperationRecord or type(step) is not StepRecord:
            raise ValueError("operation and step must be their R1 record types")
        if operation.status is not OperationStatus.QUEUED:
            raise ValueError("initial operation must be QUEUED")
        if step.status is not StepStatus.PENDING:
            raise ValueError("initial step must be PENDING")
        if step.operation_id != operation.operation_id:
            raise ValueError("initial step must belong to operation")

        existing_operation_row = self._select_operation_row(operation.operation_id)
        existing_step_row = self._select_step_row(step.step_id)
        existing_named_step_row = self._select_step_by_name(step.operation_id, step.step_name)
        if existing_operation_row is not None or existing_step_row is not None or existing_named_step_row is not None:
            existing_operation = (
                operation_record_from_row(_as_mapping(existing_operation_row))
                if existing_operation_row is not None
                else None
            )
            existing_step = (
                step_record_from_row(_as_mapping(existing_step_row))
                if existing_step_row is not None
                else None
            )
            named_step = (
                step_record_from_row(_as_mapping(existing_named_step_row))
                if existing_named_step_row is not None
                else None
            )
            if existing_operation == operation and existing_step == step and named_step == step:
                return TransitionDisposition.IDEMPOTENT
            raise ConflictingDuplicate("create identity already has a different record")

        try:
            self._insert_operation(operation_record_to_row(operation))
            self._insert_step(step_record_to_row(step))
        except sqlite3.IntegrityError as exc:
            raise ConflictingDuplicate("create conflicted with an existing identity") from exc
        return TransitionDisposition.APPLY

    def insert_successor_step(self, step: StepRecord) -> TransitionDisposition:
        self._require_writable()
        if type(step) is not StepRecord:
            raise ValueError("step must be an R1 StepRecord")
        if step.status is not StepStatus.PENDING:
            raise ValueError("successor step must be PENDING")
        self.get_operation(step.operation_id)
        existing_step_row = self._select_step_row(step.step_id)
        existing_named_step_row = self._select_step_by_name(step.operation_id, step.step_name)
        if existing_step_row is not None or existing_named_step_row is not None:
            existing_step = (
                step_record_from_row(_as_mapping(existing_step_row))
                if existing_step_row is not None
                else None
            )
            named_step = (
                step_record_from_row(_as_mapping(existing_named_step_row))
                if existing_named_step_row is not None
                else None
            )
            if existing_step == step and named_step == step:
                return TransitionDisposition.IDEMPOTENT
            raise ConflictingDuplicate("successor identity already has a different record")
        try:
            self._insert_step(step_record_to_row(step))
        except sqlite3.IntegrityError as exc:
            raise ConflictingDuplicate("successor identity conflicted") from exc
        return TransitionDisposition.APPLY

    def compare_and_set_operation(
        self,
        candidate: OperationRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
    ) -> TransitionDisposition:
        self._require_writable()
        if type(candidate) is not OperationRecord:
            raise ValueError("candidate must be an OperationRecord")
        current = self.get_operation(candidate.operation_id)
        if current.status.is_final_terminal() and current != candidate:
            raise ConflictingDuplicate("terminal operation has a different candidate")
        disposition = validate_operation_transition(
            current,
            candidate,
            recovery_authorized=recovery_authorized,
        )
        if disposition is TransitionDisposition.IDEMPOTENT:
            return disposition
        self._validate_precondition(current, precondition)
        row = operation_record_to_row(candidate)
        assignments = ", ".join(f"{column} = :{column}" for column in _OPERATION_UPDATE_COLUMNS.split(", "))
        parameters = dict(row)
        parameters["where_operation_id"] = candidate.operation_id
        parameters["expected_version"] = precondition.expected_optimistic_version
        result = self._execute(
            f"UPDATE operation_records SET {assignments} "
            "WHERE operation_id = :where_operation_id AND optimistic_version = :expected_version",
            parameters,
        )
        if result.rowcount != 1:
            self._raise_cas_failure_operation(candidate, precondition)
        return TransitionDisposition.APPLY

    def compare_and_set_step(
        self,
        candidate: StepRecord,
        precondition: WritePrecondition,
        *,
        recovery_authorized: bool = False,
        require_live_lease: bool = False,
    ) -> TransitionDisposition:
        self._require_writable()
        if type(candidate) is not StepRecord:
            raise ValueError("candidate must be a StepRecord")
        if type(require_live_lease) is not bool:
            raise ValueError("require_live_lease must be a bool")
        current = self.get_step(candidate.step_id)
        if current.status.is_final_terminal() and current != candidate:
            raise ConflictingDuplicate("terminal step has a different candidate")
        disposition = validate_step_transition(
            current,
            candidate,
            recovery_authorized=recovery_authorized,
        )
        if disposition is TransitionDisposition.IDEMPOTENT:
            return disposition
        self._validate_precondition(current, precondition)
        if require_live_lease:
            if current.lease_expires_at is None or current.lease_expires_at <= self._transaction_now:
                raise LeaseExpired("step lease is no longer live")
        row = step_record_to_row(candidate)
        assignments = ", ".join(f"{column} = :{column}" for column in _STEP_UPDATE_COLUMNS.split(", "))
        parameters = dict(row)
        parameters["where_step_id"] = candidate.step_id
        parameters["expected_version"] = precondition.expected_optimistic_version
        if precondition.worker_id is None:
            lease_where = "worker_id IS NULL AND lease_token IS NULL"
        else:
            lease_where = "worker_id = :expected_worker_id AND lease_token = :expected_lease_token"
            parameters["expected_worker_id"] = precondition.worker_id
            parameters["expected_lease_token"] = precondition.lease_token
        live_where = ""
        if require_live_lease:
            live_where = " AND lease_expires_at_us > :transaction_now_us"
            parameters["transaction_now_us"] = _datetime_to_epoch_us(self._transaction_now)
        result = self._execute(
            f"UPDATE step_records SET {assignments} "
            "WHERE step_id = :where_step_id AND optimistic_version = :expected_version "
            f"AND {lease_where}{live_where}",
            parameters,
        )
        if result.rowcount != 1:
            self._raise_cas_failure_step(candidate, precondition, require_live_lease)
        return TransitionDisposition.APPLY

    def _validate_precondition(
        self,
        current: OperationRecord | StepRecord,
        precondition: WritePrecondition,
    ) -> None:
        if type(precondition) is not WritePrecondition:
            raise ValueError("precondition must be WritePrecondition")
        try:
            if isinstance(current, OperationRecord):
                validate_write_precondition(
                    current_optimistic_version=current.optimistic_version,
                    current_worker_id=None,
                    current_lease_token=None,
                    precondition=precondition,
                )
            else:
                validate_write_precondition(
                    current_optimistic_version=current.optimistic_version,
                    current_worker_id=current.worker_id,
                    current_lease_token=current.lease_token,
                    precondition=precondition,
                )
        except ValueError as exc:
            raise StaleWrite("write precondition no longer matches") from exc

    def _raise_cas_failure_operation(
        self,
        candidate: OperationRecord,
        precondition: WritePrecondition,
    ) -> None:
        row = self._select_operation_row(candidate.operation_id)
        if row is None:
            raise RecordNotFound(f"operation {candidate.operation_id!r} was not found")
        current = operation_record_from_row(_as_mapping(row))
        try:
            validate_write_precondition(
                current_optimistic_version=current.optimistic_version,
                current_worker_id=None,
                current_lease_token=None,
                precondition=precondition,
            )
        except ValueError as exc:
            raise StaleWrite("operation CAS lost its precondition") from exc
        raise ConflictingDuplicate("operation CAS affected an unexpected row count")

    def _raise_cas_failure_step(
        self,
        candidate: StepRecord,
        precondition: WritePrecondition,
        require_live_lease: bool,
    ) -> None:
        row = self._select_step_row(candidate.step_id)
        if row is None:
            raise RecordNotFound(f"step {candidate.step_id!r} was not found")
        current = step_record_from_row(_as_mapping(row))
        if require_live_lease and (
            current.lease_expires_at is None or current.lease_expires_at <= self._transaction_now
        ):
            raise LeaseExpired("step lease is no longer live")
        try:
            validate_write_precondition(
                current_optimistic_version=current.optimistic_version,
                current_worker_id=current.worker_id,
                current_lease_token=current.lease_token,
                precondition=precondition,
            )
        except ValueError as exc:
            raise StaleWrite("step CAS lost its precondition") from exc
        raise ConflictingDuplicate("step CAS affected an unexpected row count")

    def _select_operation_row(self, operation_id: str) -> sqlite3.Row | None:
        return cast(sqlite3.Row | None, self._execute(
            f"SELECT {_OPERATION_COLUMNS} FROM operation_records WHERE operation_id = ?",
            (operation_id,),
        ).fetchone())

    def _select_step_row(self, step_id: str) -> sqlite3.Row | None:
        return cast(sqlite3.Row | None, self._execute(
            f"SELECT {_STEP_COLUMNS} FROM step_records WHERE step_id = ?",
            (step_id,),
        ).fetchone())

    def _select_step_by_name(self, operation_id: str, step_name: str) -> sqlite3.Row | None:
        return cast(sqlite3.Row | None, self._execute(
            f"SELECT {_STEP_COLUMNS} FROM step_records WHERE operation_id = ? AND step_name = ?",
            (operation_id, step_name),
        ).fetchone())

    def _select_active_operation_rows(
        self,
        *,
        last_updated_at_us: int | None,
        last_identity: str | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        placeholders = ", ".join("?" for _ in _ACTIVE_OPERATION_STATUSES)
        query = (
            f"SELECT {_OPERATION_COLUMNS} FROM operation_records "
            f"WHERE status IN ({placeholders})"
        )
        parameters: list[object] = list(_ACTIVE_OPERATION_STATUSES)
        if last_updated_at_us is not None and last_identity is not None:
            query += " AND (updated_at_us > ? OR (updated_at_us = ? AND operation_id > ?))"
            parameters.extend([last_updated_at_us, last_updated_at_us, last_identity])
        query += " ORDER BY updated_at_us, operation_id LIMIT ?"
        parameters.append(limit + 1)
        return self._execute(query, tuple(parameters)).fetchall()

    def _select_active_step_rows(
        self,
        *,
        last_updated_at_us: int | None,
        last_identity: str | None,
        limit: int,
    ) -> list[sqlite3.Row]:
        placeholders = ", ".join("?" for _ in _ACTIVE_STEP_STATUSES)
        query = f"SELECT {_STEP_COLUMNS} FROM step_records WHERE status IN ({placeholders})"
        parameters: list[object] = list(_ACTIVE_STEP_STATUSES)
        if last_updated_at_us is not None and last_identity is not None:
            query += " AND (updated_at_us > ? OR (updated_at_us = ? AND step_id > ?))"
            parameters.extend([last_updated_at_us, last_updated_at_us, last_identity])
        query += " ORDER BY updated_at_us, step_id LIMIT ?"
        parameters.append(limit + 1)
        return self._execute(query, tuple(parameters)).fetchall()

    def _validate_active_step_owner(self, step: StepRecord) -> None:
        row = self._select_operation_row(step.operation_id)
        if row is None:
            raise CorruptPersistedRecord("active step has no owning operation")
        operation = operation_record_from_row(_as_mapping(row))
        if operation.status.is_final_terminal():
            raise CorruptPersistedRecord("active step belongs to a terminal operation")

    def _insert_operation(self, row: Mapping[str, object]) -> None:
        columns = _OPERATION_INSERT_COLUMNS
        names = [column.strip() for column in columns.split(",")]
        placeholders = ", ".join(f":{name}" for name in names)
        self._execute(
            f"INSERT INTO operation_records ({columns}) VALUES ({placeholders})",
            dict(row),
        )

    def _insert_step(self, row: Mapping[str, object]) -> None:
        columns = _STEP_INSERT_COLUMNS
        names = [column.strip() for column in columns.split(",")]
        placeholders = ", ".join(f":{name}" for name in names)
        self._execute(
            f"INSERT INTO step_records ({columns}) VALUES ({placeholders})",
            dict(row),
        )

    def _execute(self, query: str, parameters: object = ()) -> sqlite3.Cursor:
        try:
            return self._connection.execute(query, cast(Any, parameters))
        except sqlite3.OperationalError as exc:
            _raise_if_busy(exc)
            raise

    def _require_transaction(self) -> None:
        if not self._connection.in_transaction:
            raise RuntimeError("SQLiteOperationStore transaction is no longer active")

    def _require_writable(self) -> None:
        self._require_transaction()
        if self._read_only:
            raise RuntimeError("operation store is bound to a read-only transaction")


def _as_mapping(row: object) -> Mapping[str, object]:
    if not isinstance(row, sqlite3.Row):
        raise CorruptPersistedRecord("SQLite query did not return a row")
    return cast(Mapping[str, object], row)


def _page_rows(rows: list[sqlite3.Row], limit: int) -> tuple[list[sqlite3.Row], bool]:
    if len(rows) > limit:
        return rows[:limit], True
    return rows, False


def _validate_page_request(limit: object, cursor: object, *, maximum: int) -> None:
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


def _encode_cursor(scope: str, **values: object) -> str:
    payload = {"scope": scope, "version": _CURSOR_VERSION, **values}
    raw = canonicalize_json_value(payload)
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    if len(encoded.encode("utf-8")) > _MAX_CURSOR_BYTES:
        raise ValueError("generated cursor exceeds its maximum size")
    return encoded


def _decode_cursor(
    cursor: str | None,
    *,
    scope: str,
    fields: tuple[str, ...],
) -> dict[str, object] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        if canonicalize_jcs(raw) != raw:
            raise ValueError("cursor JSON is not canonical")
        payload = json.loads(raw)
    except (UnicodeEncodeError, ValueError, json.JSONDecodeError, CanonicalEncodingError) as exc:
        raise ValueError("cursor is malformed") from exc
    if type(payload) is not dict:
        raise ValueError("cursor payload must be an object")
    expected_keys = {"scope", "version", *fields}
    if set(payload) != expected_keys:
        raise ValueError("cursor fields do not match the requested query")
    if payload.get("scope") != scope or payload.get("version") != _CURSOR_VERSION:
        raise ValueError("cursor scope or version is unsupported")
    for field in fields:
        value = payload[field]
        if field.endswith("_us") and (type(value) is not int):
            raise ValueError(f"cursor field {field} must be an integer")
        if field in {"step_id", "operation_id", "status"} and type(value) is not str:
            raise ValueError(f"cursor field {field} must be text")
    return cast(dict[str, object], payload)


def _validate_identity(value: object, label: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if len(value.encode("utf-8")) > 255:
        raise ValueError(f"{label} is too long")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} must not contain control characters")


def _validate_utc_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be an aware UTC datetime")


def _required_row_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if type(value) is not int:
        raise CorruptPersistedRecord(f"{key} is not an integer")
    return value


def _required_row_text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if type(value) is not str:
        raise CorruptPersistedRecord(f"{key} is not text")
    return value


def _raise_if_busy(exc: sqlite3.OperationalError) -> None:
    message = str(exc).lower()
    if "busy" in message or "locked" in message:
        raise StoreBusy("control DB is busy") from None


def operation_record_to_row(record: OperationRecord) -> dict[str, object]:
    document = record.to_document()
    return {
        "operation_id": record.operation_id,
        "contract_version": record.contract_version,
        "optimistic_version": record.optimistic_version,
        "job_kind": record.job_kind,
        "job_contract_version": record.job_contract_version,
        "job_payload": record.job_payload,
        "job_payload_ref": _optional_json_blob(document["job_payload_ref"]),
        "business_refs": _json_blob(document["business_refs"]),
        "artifact_refs": _json_blob(document["artifact_refs"]),
        "repository_operation_id": record.repository_operation_id,
        "checkpoint_ref": _optional_json_blob(document["checkpoint_ref"]),
        "ready_closure_ref": _optional_json_blob(document["ready_closure_ref"]),
        "status": record.status.value,
        "diagnostic": _optional_json_blob(document["diagnostic"]),
        "cancel_requested": int(record.cancel_requested),
        "created_at_us": _datetime_to_epoch_us(record.created_at),
        "updated_at_us": _datetime_to_epoch_us(record.updated_at),
        "completed_at_us": (
            _datetime_to_epoch_us(record.completed_at) if record.completed_at is not None else None
        ),
    }


def step_record_to_row(record: StepRecord) -> dict[str, object]:
    document = record.to_document()
    eligible_at_us: int | None
    if record.status is StepStatus.PENDING:
        eligible_at_us = _datetime_to_epoch_us(record.created_at)
    elif record.status is StepStatus.RETRY_WAIT:
        if record.retry_not_before is None:
            raise ValueError("RETRY_WAIT step requires retry_not_before")
        eligible_at_us = _datetime_to_epoch_us(record.retry_not_before)
    else:
        eligible_at_us = None
    return {
        "step_id": record.step_id,
        "operation_id": record.operation_id,
        "contract_version": record.contract_version,
        "optimistic_version": record.optimistic_version,
        "step_name": record.step_name,
        "attempt_count": record.attempt_count,
        "status": record.status.value,
        "diagnostic": _optional_json_blob(document["diagnostic"]),
        "cancel_requested": int(record.cancel_requested),
        "retry_not_before_us": (
            _datetime_to_epoch_us(record.retry_not_before)
            if record.retry_not_before is not None
            else None
        ),
        "worker_id": record.worker_id,
        "lease_token": record.lease_token,
        "lease_expires_at_us": (
            _datetime_to_epoch_us(record.lease_expires_at)
            if record.lease_expires_at is not None
            else None
        ),
        "checkpoint_ref": _optional_json_blob(document["checkpoint_ref"]),
        "prior_output_refs": _json_blob(document["prior_output_refs"]),
        "created_at_us": _datetime_to_epoch_us(record.created_at),
        "updated_at_us": _datetime_to_epoch_us(record.updated_at),
        "started_at_us": (
            _datetime_to_epoch_us(record.started_at) if record.started_at is not None else None
        ),
        "completed_at_us": (
            _datetime_to_epoch_us(record.completed_at) if record.completed_at is not None else None
        ),
        "eligible_at_us": eligible_at_us,
    }


def operation_record_from_row(row: Mapping[str, object]) -> OperationRecord:
    try:
        document = {
            "artifact_refs": _json_value(row, "artifact_refs", list),
            "business_refs": _json_value(row, "business_refs", list),
            "cancel_requested": _bool_value(row, "cancel_requested"),
            "checkpoint_ref": _optional_json_value(row, "checkpoint_ref"),
            "completed_at": _optional_timestamp(row, "completed_at_us"),
            "contract_version": _text_value(row, "contract_version"),
            "created_at": _timestamp(row, "created_at_us"),
            "diagnostic": _optional_json_value(row, "diagnostic"),
            "document_type": "operation",
            "job_contract_version": _text_value(row, "job_contract_version"),
            "job_kind": _text_value(row, "job_kind"),
            "job_payload": _optional_json_value(row, "job_payload"),
            "job_payload_ref": _optional_json_value(row, "job_payload_ref"),
            "operation_id": _text_value(row, "operation_id"),
            "optimistic_version": _non_negative_int(row, "optimistic_version"),
            "ready_closure_ref": _optional_json_value(row, "ready_closure_ref"),
            "repository_operation_id": _optional_text_value(row, "repository_operation_id"),
            "status": _text_value(row, "status"),
            "updated_at": _timestamp(row, "updated_at_us"),
        }
        return operation_record_from_document(document)
    except CorruptPersistedRecord:
        raise
    except (
        CanonicalEncodingError,
        IndexError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise CorruptPersistedRecord("operation row failed R1 readback") from exc


def step_record_from_row(row: Mapping[str, object]) -> StepRecord:
    try:
        status = _text_value(row, "status")
        created_at = _timestamp_value(row, "created_at_us")
        retry_not_before = _optional_timestamp_value(row, "retry_not_before_us")
        eligible_at_us = _optional_int(row, "eligible_at_us")
        expected_eligible_at_us = _expected_eligible_at_us(status, created_at, retry_not_before)
        if eligible_at_us != expected_eligible_at_us:
            raise ValueError("eligible_at_us does not match persisted step status")
        document = {
            "attempt_count": _non_negative_int(row, "attempt_count"),
            "cancel_requested": _bool_value(row, "cancel_requested"),
            "checkpoint_ref": _optional_json_value(row, "checkpoint_ref"),
            "completed_at": _optional_timestamp(row, "completed_at_us"),
            "contract_version": _text_value(row, "contract_version"),
            "created_at": _format_utc_timestamp(created_at),
            "diagnostic": _optional_json_value(row, "diagnostic"),
            "document_type": "step",
            "lease_expires_at": _optional_timestamp(row, "lease_expires_at_us"),
            "lease_token": _optional_text_value(row, "lease_token"),
            "operation_id": _text_value(row, "operation_id"),
            "optimistic_version": _non_negative_int(row, "optimistic_version"),
            "prior_output_refs": _json_value(row, "prior_output_refs", list),
            "retry_not_before": (
                _format_utc_timestamp(retry_not_before) if retry_not_before is not None else None
            ),
            "started_at": _optional_timestamp(row, "started_at_us"),
            "status": status,
            "step_id": _text_value(row, "step_id"),
            "step_name": _text_value(row, "step_name"),
            "updated_at": _timestamp(row, "updated_at_us"),
            "worker_id": _optional_text_value(row, "worker_id"),
        }
        return step_record_from_document(document)
    except CorruptPersistedRecord:
        raise
    except (
        CanonicalEncodingError,
        IndexError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise CorruptPersistedRecord("step row failed R1 readback") from exc


def _json_blob(value: object) -> bytes:
    return canonicalize_json_value(value)


def _optional_json_blob(value: object) -> bytes | None:
    return None if value is None else _json_blob(value)


def _json_value(
    row: Mapping[str, object],
    key: str,
    expected_type: type[Any] | tuple[type[Any], ...],
) -> object:
    raw = _blob_value(row, key)
    try:
        canonical = canonicalize_jcs(raw)
    except CanonicalEncodingError:
        raise
    if canonical != raw:
        raise ValueError(f"{key} is not canonical JSON")
    value = json.loads(canonical)
    if not isinstance(value, expected_type):
        raise ValueError(f"{key} has the wrong JSON root type")
    return value


def _optional_json_value(row: Mapping[str, object], key: str) -> object | None:
    raw = row[key]
    if raw is None:
        return None
    return _json_value(row, key, (dict, list))


def _blob_value(row: Mapping[str, object], key: str) -> bytes:
    value = row[key]
    if type(value) is not bytes:
        raise ValueError(f"{key} must be a BLOB")
    return value


def _text_value(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if type(value) is not str:
        raise ValueError(f"{key} must be TEXT")
    return value


def _optional_text_value(row: Mapping[str, object], key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    return _text_value(row, key)


def _non_negative_int(row: Mapping[str, object], key: str) -> int:
    value = _required_int(row, key)
    if value < 0:
        raise ValueError(f"{key} must be non-negative")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if type(value) is not int:
        raise ValueError(f"{key} must be INTEGER")
    return value


def _optional_int(row: Mapping[str, object], key: str) -> int | None:
    value = row[key]
    if value is None:
        return None
    return _required_int(row, key)


def _bool_value(row: Mapping[str, object], key: str) -> bool:
    value = _required_int(row, key)
    if value not in (0, 1):
        raise ValueError(f"{key} must be 0 or 1")
    return bool(value)


def _timestamp(row: Mapping[str, object], key: str) -> str:
    return _format_utc_timestamp(_timestamp_value(row, key))


def _timestamp_value(row: Mapping[str, object], key: str) -> datetime:
    return _epoch_us_to_datetime(_required_int(row, key))


def _optional_timestamp(row: Mapping[str, object], key: str) -> str | None:
    value = _optional_timestamp_value(row, key)
    return None if value is None else _format_utc_timestamp(value)


def _optional_timestamp_value(row: Mapping[str, object], key: str) -> datetime | None:
    value = _optional_int(row, key)
    return None if value is None else _epoch_us_to_datetime(value)


def _datetime_to_epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must use UTC")
    delta = value - _EPOCH
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    if micros < _SQLITE_INT_MIN or micros > _SQLITE_INT_MAX:
        raise ValueError("timestamp is outside SQLite INTEGER range")
    return micros


def _epoch_us_to_datetime(value: int) -> datetime:
    if type(value) is not int or value < _SQLITE_INT_MIN or value > _SQLITE_INT_MAX:
        raise ValueError("timestamp must be a SQLite INTEGER")
    seconds, micros = divmod(value, 1_000_000)
    return _EPOCH + timedelta(seconds=seconds, microseconds=micros)


def _format_utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must use UTC")
    fraction = f"{value.microsecond:06d}".rstrip("0")
    suffix = f".{fraction}" if fraction else ""
    return f"{value:%Y-%m-%dT%H:%M:%S}{suffix}Z"


def _expected_eligible_at_us(
    status: str,
    created_at: datetime,
    retry_not_before: datetime | None,
) -> int | None:
    if status == StepStatus.PENDING.value:
        return _datetime_to_epoch_us(created_at)
    if status == StepStatus.RETRY_WAIT.value:
        if retry_not_before is None:
            raise ValueError("RETRY_WAIT step requires retry_not_before")
        return _datetime_to_epoch_us(retry_not_before)
    return None


def _encode_integrity_cursor(
    phase: str,
    *,
    updated_at_us: int | None = None,
    identity: str | None = None,
) -> str:
    if phase not in {_INTEGRITY_OPERATION_PHASE, _INTEGRITY_STEP_PHASE}:
        raise ValueError("integrity cursor phase is unsupported")
    if (updated_at_us is None) != (identity is None):
        raise ValueError("integrity cursor key must be complete")
    payload = {
        "identity": identity,
        "phase": phase,
        "scope": "active_integrity",
        "updated_at_us": updated_at_us,
        "version": _INTEGRITY_CURSOR_VERSION,
    }
    raw = canonicalize_json_value(payload)
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    if len(encoded.encode("utf-8")) > _MAX_CURSOR_BYTES:
        raise ValueError("generated integrity cursor exceeds its maximum size")
    return encoded


def _decode_integrity_cursor(
    cursor: str | None,
) -> tuple[str, int | None, str | None]:
    if cursor is None:
        return _INTEGRITY_OPERATION_PHASE, None, None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        if canonicalize_jcs(raw) != raw:
            raise ValueError("cursor JSON is not canonical")
        payload = json.loads(raw)
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError, json.JSONDecodeError, CanonicalEncodingError) as exc:
        raise ValueError("integrity cursor is malformed") from exc
    if type(payload) is not dict:
        raise ValueError("integrity cursor payload must be an object")
    if set(payload) != {"identity", "phase", "scope", "updated_at_us", "version"}:
        raise ValueError("integrity cursor fields do not match")
    if payload["scope"] != "active_integrity" or payload["version"] != _INTEGRITY_CURSOR_VERSION:
        raise ValueError("integrity cursor scope or version is unsupported")
    phase = payload["phase"]
    if phase not in {_INTEGRITY_OPERATION_PHASE, _INTEGRITY_STEP_PHASE}:
        raise ValueError("integrity cursor phase is unsupported")
    updated_at_us = payload["updated_at_us"]
    identity = payload["identity"]
    if updated_at_us is None and identity is None:
        return phase, None, None
    if type(updated_at_us) is not int or type(identity) is not str or not identity:
        raise ValueError("integrity cursor key is invalid")
    return phase, updated_at_us, identity
