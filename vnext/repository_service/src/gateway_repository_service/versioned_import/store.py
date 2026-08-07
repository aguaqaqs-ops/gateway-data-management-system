"""Durable store for Versioned import operations."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID, uuid4

from gateway_repository_contracts import (
    OperationStatus,
    SimpleError,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedImportResult,
    VersionedOperation,
)
from gateway_repository_service.mutation_store import IdempotencyKeyHash, MutationStore
from gateway_repository_service.versioned_import.models import (
    ArtifactOperationReference,
    ClaimOrEnqueueResult,
    ImportFingerprintConflict,
    ImportOperationExecutionContext,
    ImportOperationStoreError,
    ImportOperationTransitionRejected,
    ImportReplayCountRejected,
    ImportRequestBinding,
    ManualCorrectionDecision,
    ORDINARY_TERMINAL_ERROR_CODES,
    RecoveryAuditAction,
    StoredImportOperation,
    derive_operation_marker,
    derive_private_ref_name,
    is_manual_recovery_error,
    is_protected_operation_status,
    utc_now_iso,
    validate_result_matches_operation_row,
)


class ImportOperationStore:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        transaction_lock: threading.Lock | None = None,
    ) -> None:
        self._connection = connection
        self._lock = transaction_lock or threading.Lock()
        self._mutation_store = MutationStore(connection, transaction_lock=self._lock)

    @property
    def mutation_store(self) -> MutationStore:
        return self._mutation_store

    def claim_or_enqueue(
        self,
        binding: ImportRequestBinding,
        *,
        key_hash: IdempotencyKeyHash,
        fingerprint: bytes,
        operation_id: UUID | None = None,
    ) -> ClaimOrEnqueueResult:
        with self._transaction():
            row = self._fetch_by_key(binding.repository_id, key_hash)
            if row is not None:
                if bytes(row["request_fingerprint"]) != fingerprint:
                    raise ImportFingerprintConflict(repository_id=binding.repository_id)
                operation = self._operation_from_row(row)
                return ClaimOrEnqueueResult(
                    operation_id=operation.operation_id,
                    is_new=False,
                    operation=operation,
                )

            new_operation_id = operation_id or uuid4()
            now = utc_now_iso()
            enqueue_sequence = self._allocate_enqueue_sequence(binding.repository_id)
            private_ref_name = derive_private_ref_name(new_operation_id)
            operation_marker = derive_operation_marker(new_operation_id)
            self._connection.execute(
                """
                INSERT INTO repository_import_operations (
                    operation_id,
                    repository_scope,
                    key_hash,
                    request_fingerprint,
                    artifact_id,
                    artifact_media_type,
                    artifact_size_bytes,
                    artifact_raw_sha256,
                    target_ref,
                    expected_commit_id,
                    requested_verification_policy,
                    unknown_type_policy,
                    status,
                    private_ref_name,
                    operation_marker,
                    canonicalization_manifest_digest,
                    automatic_replay_count,
                    enqueue_sequence,
                    result_json,
                    error_json,
                    created_at,
                    started_at,
                    updated_at,
                    completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, NULL, NULL, ?, NULL, ?, NULL)
                """,
                (
                    str(new_operation_id),
                    binding.repository_id.hex,
                    key_hash.digest,
                    fingerprint,
                    str(binding.artifact_ref.artifact_id),
                    binding.artifact_ref.media_type,
                    binding.artifact_ref.size_bytes,
                    binding.artifact_ref.raw_sha256,
                    binding.target_ref,
                    binding.expected_commit_id,
                    binding.verification_policy.value,
                    binding.unknown_type_policy.value,
                    OperationStatus.QUEUED.value,
                    private_ref_name,
                    operation_marker,
                    enqueue_sequence,
                    now,
                    now,
                ),
            )
            inserted = self._fetch_by_operation_id(new_operation_id)
            if inserted is None:
                raise ImportOperationStoreError("failed to insert import operation")
            operation = self._operation_from_row(inserted)
            return ClaimOrEnqueueResult(
                operation_id=operation.operation_id,
                is_new=True,
                operation=operation,
            )

    def get_operation(
        self,
        repository_id: UUID,
        operation_id: UUID,
    ) -> StoredImportOperation | None:
        with self._transaction():
            row = self._fetch_by_operation_id(operation_id)
            if row is None:
                return None
            if str(row["repository_scope"]) != repository_id.hex:
                return None
            return self._operation_from_row(row)

    def load_execution_context(self, operation_id: UUID) -> ImportOperationExecutionContext | None:
        with self._transaction():
            row = self._fetch_by_operation_id(operation_id)
            if row is None:
                return None
            return self._execution_context_from_row(row)

    def list_earliest_queued_per_repository(
        self,
    ) -> list[tuple[UUID, UUID, int]]:
        with self._lock:
            cursor = self._connection.execute(
                """
                SELECT repository_scope, operation_id, enqueue_sequence
                FROM repository_import_operations AS candidate
                WHERE status = ?
                  AND enqueue_sequence = (
                    SELECT MIN(inner.enqueue_sequence)
                    FROM repository_import_operations AS inner
                    WHERE inner.repository_scope = candidate.repository_scope
                      AND inner.status = ?
                  )
                ORDER BY repository_scope ASC
                """,
                (OperationStatus.QUEUED.value, OperationStatus.QUEUED.value),
            )
            results: list[tuple[UUID, UUID, int]] = []
            for row in cursor.fetchall():
                results.append(
                    (
                        UUID(str(row["repository_scope"])),
                        UUID(str(row["operation_id"])),
                        int(row["enqueue_sequence"]),
                    )
                )
            return results

    def claim_next_queued(self, repository_id: UUID) -> StoredImportOperation | None:
        with self._transaction():
            row = self._connection.execute(
                """
                SELECT operation_id
                FROM repository_import_operations
                WHERE repository_scope = ?
                  AND status = ?
                ORDER BY enqueue_sequence ASC
                LIMIT 1
                """,
                (repository_id.hex, OperationStatus.QUEUED.value),
            ).fetchone()
            if row is None:
                return None
            operation_id = UUID(str(row["operation_id"]))
            return self._claim_if_queued_locked(operation_id)

    def claim_if_queued(self, operation_id: UUID) -> StoredImportOperation | None:
        with self._transaction():
            return self._claim_if_queued_locked(operation_id)

    def mark_succeeded(self, operation_id: UUID, *, result: VersionedImportResult) -> StoredImportOperation:
        validated = self._validate_terminal_result(operation_id, result=result, error=None)
        with self._transaction():
            row = self._fetch_by_operation_id(operation_id)
            if row is None:
                raise ImportOperationStoreError(f"operation {operation_id} does not exist")
            if str(row["status"]) == OperationStatus.SUCCEEDED.value:
                return self._operation_from_row(row)
            if str(row["status"]) != OperationStatus.RUNNING.value:
                raise ImportOperationTransitionRejected(
                    f"operation {operation_id} is not running"
                )
            validate_result_matches_operation_row(row, result)
            now = utc_now_iso()
            assert validated.result is not None
            result_json = json.dumps(
                validated.result.model_dump(mode="json"),
                separators=(",", ":"),
                sort_keys=True,
            )
            self._connection.execute(
                """
                UPDATE repository_import_operations
                SET status = ?,
                    result_json = ?,
                    error_json = NULL,
                    canonicalization_manifest_digest = ?,
                    updated_at = ?,
                    completed_at = ?
                WHERE operation_id = ?
                  AND status = ?
                """,
                (
                    OperationStatus.SUCCEEDED.value,
                    result_json,
                    result.canonicalization_manifest_digest,
                    now,
                    now,
                    str(operation_id),
                    OperationStatus.RUNNING.value,
                ),
            )
            self._mutation_store.record_artifact_consumed(
                UUID(str(row["artifact_id"])),
                operation_id=operation_id,
                consumed_at=now,
                repository_id=UUID(str(row["repository_scope"])),
            )
            updated = self._fetch_by_operation_id(operation_id)
            if updated is None:
                raise ImportOperationStoreError(f"operation {operation_id} disappeared")
            return self._operation_from_row(updated)

    def mark_failed(self, operation_id: UUID, *, error: SimpleError) -> StoredImportOperation:
        if error.request_id is not None:
            raise ImportOperationStoreError("persisted operation error request_id must be empty")
        validated = self._validate_terminal_result(operation_id, result=None, error=error)
        with self._transaction():
            row = self._fetch_by_operation_id(operation_id)
            if row is None:
                raise ImportOperationStoreError(f"operation {operation_id} does not exist")
            if str(row["status"]) == OperationStatus.FAILED.value:
                return self._operation_from_row(row)
            if str(row["status"]) != OperationStatus.RUNNING.value:
                raise ImportOperationTransitionRejected(
                    f"operation {operation_id} is not running"
                )
            now = utc_now_iso()
            assert validated.error is not None
            error_json = json.dumps(
                validated.error.model_dump(mode="json"),
                separators=(",", ":"),
                sort_keys=True,
            )
            self._connection.execute(
                """
                UPDATE repository_import_operations
                SET status = ?,
                    result_json = NULL,
                    error_json = ?,
                    updated_at = ?,
                    completed_at = ?
                WHERE operation_id = ?
                  AND status = ?
                """,
                (
                    OperationStatus.FAILED.value,
                    error_json,
                    now,
                    now,
                    str(operation_id),
                    OperationStatus.RUNNING.value,
                ),
            )
            updated = self._fetch_by_operation_id(operation_id)
            if updated is None:
                raise ImportOperationStoreError(f"operation {operation_id} disappeared")
            return self._operation_from_row(updated)

    def increment_automatic_replay_count(self, operation_id: UUID) -> StoredImportOperation:
        with self._transaction():
            row = self._fetch_by_operation_id(operation_id)
            if row is None:
                raise ImportOperationStoreError(f"operation {operation_id} does not exist")
            if int(row["automatic_replay_count"]) != 0:
                raise ImportReplayCountRejected(
                    f"operation {operation_id} automatic replay count is already 1"
                )
            now = utc_now_iso()
            self._connection.execute(
                """
                UPDATE repository_import_operations
                SET automatic_replay_count = 1,
                    updated_at = ?
                WHERE operation_id = ?
                  AND automatic_replay_count = 0
                """,
                (now, str(operation_id)),
            )
            updated = self._fetch_by_operation_id(operation_id)
            if updated is None or int(updated["automatic_replay_count"]) != 1:
                raise ImportReplayCountRejected(
                    f"operation {operation_id} automatic replay count could not be incremented"
                )
            return self._operation_from_row(updated)

    def apply_manual_correction(
        self,
        operation_id: UUID,
        *,
        decision: ManualCorrectionDecision,
        evidence_summary: dict[str, Any],
        final_result: VersionedImportResult | None = None,
        final_error: SimpleError | None = None,
    ) -> StoredImportOperation:
        with self._transaction():
            row = self._fetch_by_operation_id(operation_id)
            if row is None:
                raise ImportOperationStoreError(f"operation {operation_id} does not exist")
            current = self._operation_from_row(row)
            if current.status != OperationStatus.FAILED or not is_manual_recovery_error(current.error):
                raise ImportOperationTransitionRejected(
                    f"operation {operation_id} is not awaiting manual recovery"
                )
            prior_code = current.error.code if current.error is not None else None
            now = utc_now_iso()
            if decision == ManualCorrectionDecision.SUCCEEDED:
                if final_result is None:
                    raise ImportOperationStoreError("manual SUCCEEDED correction requires final_result")
                validated = self._validate_terminal_result(
                    operation_id,
                    result=final_result,
                    error=None,
                )
                assert validated.result is not None
                validate_result_matches_operation_row(row, final_result)
                result_json = json.dumps(
                    validated.result.model_dump(mode="json"),
                    separators=(",", ":"),
                    sort_keys=True,
                )
                self._connection.execute(
                    """
                    UPDATE repository_import_operations
                    SET status = ?,
                        result_json = ?,
                        error_json = NULL,
                        canonicalization_manifest_digest = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE operation_id = ?
                      AND status = ?
                      AND error_json IS NOT NULL
                    """,
                    (
                        OperationStatus.SUCCEEDED.value,
                        result_json,
                        final_result.canonicalization_manifest_digest,
                        now,
                        now,
                        str(operation_id),
                        OperationStatus.FAILED.value,
                    ),
                )
                self._mutation_store.record_artifact_consumed(
                    current.artifact_id,
                    operation_id=operation_id,
                    consumed_at=now,
                    repository_id=current.repository_id,
                )
                audit_action = RecoveryAuditAction.INSPECT_APPLY_SUCCESS
                final_status = OperationStatus.SUCCEEDED.value
                final_code = None
            else:
                if final_error is None:
                    raise ImportOperationStoreError(
                        "manual NOT_PUBLISHED correction requires final_error"
                    )
                if final_error.request_id is not None:
                    raise ImportOperationStoreError(
                        "persisted operation error request_id must be empty"
                    )
                if final_error.code not in ORDINARY_TERMINAL_ERROR_CODES:
                    raise ImportOperationTransitionRejected(
                        "manual NOT_PUBLISHED correction requires an ordinary stable error code"
                    )
                validated = self._validate_terminal_result(
                    operation_id,
                    result=None,
                    error=final_error,
                )
                assert validated.error is not None
                error_json = json.dumps(
                    validated.error.model_dump(mode="json"),
                    separators=(",", ":"),
                    sort_keys=True,
                )
                self._connection.execute(
                    """
                    UPDATE repository_import_operations
                    SET status = ?,
                        result_json = NULL,
                        error_json = ?,
                        updated_at = ?,
                        completed_at = ?
                    WHERE operation_id = ?
                      AND status = ?
                      AND error_json IS NOT NULL
                    """,
                    (
                        OperationStatus.FAILED.value,
                        error_json,
                        now,
                        now,
                        str(operation_id),
                        OperationStatus.FAILED.value,
                    ),
                )
                audit_action = RecoveryAuditAction.INSPECT_APPLY_NOT_PUBLISHED
                final_status = OperationStatus.FAILED.value
                final_code = final_error.code

            self._connection.execute(
                """
                INSERT INTO repository_import_recovery_audit (
                    operation_id,
                    action,
                    prior_status,
                    prior_code,
                    final_status,
                    final_code,
                    evidence_summary_json,
                    applied_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(operation_id),
                    audit_action.value,
                    OperationStatus.FAILED.value,
                    prior_code,
                    final_status,
                    final_code,
                    json.dumps(evidence_summary, separators=(",", ":"), sort_keys=True),
                    now,
                ),
            )
            updated = self._fetch_by_operation_id(operation_id)
            if updated is None:
                raise ImportOperationStoreError(f"operation {operation_id} disappeared")
            return self._operation_from_row(updated)

    def has_unresolved_manual_barrier(self, repository_id: UUID) -> bool:
        with self._transaction():
            cursor = self._connection.execute(
                """
                SELECT error_json
                FROM repository_import_operations
                WHERE repository_scope = ?
                  AND status = ?
                """,
                (repository_id.hex, OperationStatus.FAILED.value),
            )
            for row in cursor.fetchall():
                error = self._parse_error_json(row["error_json"])
                if is_manual_recovery_error(error):
                    return True
            return False

    def list_artifact_references(self, artifact_id: UUID) -> list[ArtifactOperationReference]:
        with self._transaction():
            cursor = self._connection.execute(
                """
                SELECT operation_id, status, error_json
                FROM repository_import_operations
                WHERE artifact_id = ?
                ORDER BY enqueue_sequence ASC
                """,
                (str(artifact_id),),
            )
            references: list[ArtifactOperationReference] = []
            for row in cursor.fetchall():
                status = OperationStatus(str(row["status"]))
                error = self._parse_error_json(row["error_json"])
                references.append(
                    ArtifactOperationReference(
                        operation_id=UUID(str(row["operation_id"])),
                        status=status,
                        is_protected=is_protected_operation_status(status, error),
                    )
                )
            return references

    def can_delete_artifact_bytes(self, artifact_id: UUID) -> bool:
        references = self.list_artifact_references(artifact_id)
        if any(reference.is_protected for reference in references):
            return False
        return any(reference.status == OperationStatus.SUCCEEDED for reference in references)

    def mark_artifact_bytes_deleted(self, artifact_id: UUID) -> None:
        with self._transaction():
            self._mutation_store.record_artifact_bytes_deleted(artifact_id, deleted_at=utc_now_iso())

    def _allocate_enqueue_sequence(self, repository_id: UUID) -> int:
        row = self._connection.execute(
            """
            SELECT COALESCE(MAX(enqueue_sequence), 0) + 1 AS next_sequence
            FROM repository_import_operations
            WHERE repository_scope = ?
            """,
            (repository_id.hex,),
        ).fetchone()
        if row is None:
            raise ImportOperationStoreError("failed to allocate enqueue sequence")
        return int(row["next_sequence"])

    def _claim_if_queued_locked(self, operation_id: UUID) -> StoredImportOperation | None:
        row = self._fetch_by_operation_id(operation_id)
        if row is None or str(row["status"]) != OperationStatus.QUEUED.value:
            return None
        now = utc_now_iso()
        self._connection.execute(
            """
            UPDATE repository_import_operations
            SET status = ?,
                started_at = ?,
                updated_at = ?
            WHERE operation_id = ?
              AND status = ?
            """,
            (
                OperationStatus.RUNNING.value,
                now,
                now,
                str(operation_id),
                OperationStatus.QUEUED.value,
            ),
        )
        updated = self._fetch_by_operation_id(operation_id)
        if updated is None or str(updated["status"]) != OperationStatus.RUNNING.value:
            return None
        return self._operation_from_row(updated)

    def _validate_terminal_result(
        self,
        operation_id: UUID,
        *,
        result: VersionedImportResult | None,
        error: SimpleError | None,
    ) -> VersionedOperation:
        if result is not None:
            return VersionedOperation.model_validate({
                "operation_id": operation_id,
                "status": OperationStatus.SUCCEEDED.value,
                "result": result.model_dump(),
                "error": None,
            })
        if error is not None:
            return VersionedOperation.model_validate({
                "operation_id": operation_id,
                "status": OperationStatus.FAILED.value,
                "result": None,
                "error": error.model_dump(),
            })
        raise ImportOperationStoreError("terminal validation requires result or error")

    def _fetch_by_key(
        self,
        repository_id: UUID,
        key_hash: IdempotencyKeyHash,
    ) -> sqlite3.Row | None:
        cursor = self._connection.execute(
            """
            SELECT *
            FROM repository_import_operations
            WHERE repository_scope = ?
              AND key_hash = ?
            """,
            (repository_id.hex, key_hash.digest),
        )
        row = cursor.fetchone()
        return cast(sqlite3.Row | None, row)

    def _fetch_by_operation_id(self, operation_id: UUID) -> sqlite3.Row | None:
        cursor = self._connection.execute(
            """
            SELECT *
            FROM repository_import_operations
            WHERE operation_id = ?
            """,
            (str(operation_id),),
        )
        row = cursor.fetchone()
        return cast(sqlite3.Row | None, row)

    def _operation_from_row(self, row: sqlite3.Row) -> StoredImportOperation:
        result = self._parse_result_json(row["result_json"])
        error = self._parse_error_json(row["error_json"])
        status = OperationStatus(str(row["status"]))
        operation_id = UUID(str(row["operation_id"]))
        validated = VersionedOperation.model_validate({
            "operation_id": operation_id,
            "status": status.value,
            "result": result.model_dump() if result is not None else None,
            "error": error.model_dump() if error is not None else None,
        })
        return StoredImportOperation(
            operation_id=operation_id,
            repository_id=UUID(str(row["repository_scope"])),
            status=validated.status,
            artifact_id=UUID(str(row["artifact_id"])),
            private_ref_name=str(row["private_ref_name"]),
            operation_marker=str(row["operation_marker"]),
            automatic_replay_count=int(row["automatic_replay_count"]),
            result=validated.result,
            error=validated.error,
            created_at=str(row["created_at"]),
            started_at=str(row["started_at"]) if row["started_at"] is not None else None,
            updated_at=str(row["updated_at"]),
            completed_at=str(row["completed_at"]) if row["completed_at"] is not None else None,
            canonicalization_manifest_digest=(
                str(row["canonicalization_manifest_digest"])
                if row["canonicalization_manifest_digest"] is not None
                else None
            ),
        )

    @staticmethod
    def _execution_context_from_row(row: sqlite3.Row) -> ImportOperationExecutionContext:
        return ImportOperationExecutionContext(
            operation_id=UUID(str(row["operation_id"])),
            repository_id=UUID(str(row["repository_scope"])),
            artifact_id=UUID(str(row["artifact_id"])),
            artifact_media_type=str(row["artifact_media_type"]),
            artifact_size_bytes=int(row["artifact_size_bytes"]),
            artifact_raw_sha256=str(row["artifact_raw_sha256"]),
            target_ref=str(row["target_ref"]),
            expected_commit_id=str(row["expected_commit_id"]),
            verification_policy=VerificationPolicy(str(row["requested_verification_policy"])),
            unknown_type_policy=UnknownTypePolicy(str(row["unknown_type_policy"])),
            private_ref_name=str(row["private_ref_name"]),
            operation_marker=str(row["operation_marker"]),
        )

    @staticmethod
    def _parse_result_json(payload: object) -> VersionedImportResult | None:
        if payload is None:
            return None
        return VersionedImportResult.model_validate(json.loads(str(payload)))

    @staticmethod
    def _parse_error_json(payload: object) -> SimpleError | None:
        if payload is None:
            return None
        return SimpleError.model_validate(json.loads(str(payload)))

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
