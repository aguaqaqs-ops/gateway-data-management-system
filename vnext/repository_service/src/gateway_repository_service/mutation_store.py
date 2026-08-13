"""Transactional create/upload effect ledger and idempotency metadata."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from gateway_repository_service.diagnostics import log_event

SYNCHRONOUS_MUTATION_SUCCESS_STATUS = 201


class MutationKind(StrEnum):
    CREATE_REPOSITORY = "create_repository"
    UPLOAD_ARTIFACT = "upload_artifact"


class EffectStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"


class MutationStoreError(RuntimeError):
    """Base error for mutation store failures."""


class MutationStoreInvariantError(MutationStoreError):
    """Raised when a readable durable row violates mutation-store invariants."""


class FingerprintConflict(MutationStoreError):
    """Raised when the same idempotency scope is reused with a different fingerprint."""

    def __init__(self, *, scope: "IdempotencyScope") -> None:
        self.scope = scope
        super().__init__(f"idempotency fingerprint conflict for {scope!r}")


class IdempotencyTerminalNotPublished(MutationStoreError):
    """Raised when a prior attempt ended without publication and cannot be retried."""

    def __init__(self, *, scope: "IdempotencyScope") -> None:
        self.scope = scope
        super().__init__(f"idempotency scope is terminal-not-published for {scope!r}")


class DuplicateEffectClaim(MutationStoreError):
    """Raised when a concurrent claim already owns the effect for a scope."""

    def __init__(self, *, scope: "IdempotencyScope") -> None:
        self.scope = scope
        super().__init__(f"idempotency scope already has an effect owner for {scope!r}")


class TerminalTransitionRejected(MutationStoreError):
    """Raised when a terminal-not-published transition is not allowed."""

    def __init__(self, *, scope: "IdempotencyScope", reason: str) -> None:
        self.scope = scope
        super().__init__(f"terminal transition rejected for {scope!r}: {reason}")


@dataclass(frozen=True, slots=True)
class IdempotencyKeyHash:
    digest: bytes

    def __post_init__(self) -> None:
        if len(self.digest) != 32:
            raise ValueError("idempotency key hash must be 32 bytes")

    @classmethod
    def from_raw_key(cls, raw_key: str) -> "IdempotencyKeyHash":
        return cls(hashlib.sha256(raw_key.encode("utf-8")).digest())

    def __repr__(self) -> str:
        return f"IdempotencyKeyHash({self.digest.hex()[:16]}…)"


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    mutation_kind: MutationKind
    repository_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.mutation_kind == MutationKind.CREATE_REPOSITORY and self.repository_id is not None:
            raise ValueError("create_repository scope must not include repository_id")
        if self.mutation_kind == MutationKind.UPLOAD_ARTIFACT and self.repository_id is None:
            raise ValueError("upload_artifact scope requires repository_id")

    @classmethod
    def for_create(cls) -> "IdempotencyScope":
        return cls(mutation_kind=MutationKind.CREATE_REPOSITORY)

    @classmethod
    def for_upload(cls, repository_id: UUID) -> "IdempotencyScope":
        return cls(mutation_kind=MutationKind.UPLOAD_ARTIFACT, repository_id=repository_id)

    def repository_scope(self) -> str:
        return "" if self.repository_id is None else self.repository_id.hex

    def __repr__(self) -> str:
        if self.repository_id is None:
            return f"IdempotencyScope(kind={self.mutation_kind.value}, repository=None)"
        return f"IdempotencyScope(kind={self.mutation_kind.value}, repository={self.repository_id})"


@dataclass(frozen=True, slots=True)
class EffectRecord:
    effect_id: int
    idempotency_id: int
    resource_id: UUID
    status: EffectStatus
    response_status: int | None
    response_body: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class ArtifactLifecycleRecord:
    artifact_id: UUID
    repository_id: UUID
    media_type: str
    size_bytes: int
    raw_sha256: str
    consumed_by_operation_id: UUID | None = None
    consumed_at: str | None = None
    bytes_deleted_at: str | None = None
    created_at: str | None = None
    bytes_delete_intent_at: str | None = None
    bytes_delete_dev: int | None = None
    bytes_delete_ino: int | None = None
    bytes_delete_phase: str | None = None
    bytes_delete_generation: str | None = None
    bytes_deleted_receipt_dev: int | None = None
    bytes_deleted_receipt_ino: int | None = None
    bytes_deleted_receipt_generation: str | None = None


@dataclass(frozen=True, slots=True)
class CleanupCandidatePage:
    records: list[ArtifactLifecycleRecord]
    scanned: int
    cursor_cleanup_seq: int | None


@dataclass(frozen=True, slots=True)
class ReceiptGcPage:
    records: list[ArtifactLifecycleRecord]
    scanned: int
    cursor_artifact_id: str | None


@dataclass(frozen=True, slots=True)
class ResidualPage:
    records: list["ArtifactResidualRecord"]
    scanned: int
    cursor_residual_id: int | None


@dataclass(frozen=True, slots=True)
class ArtifactResidualRecord:
    residual_id: int
    artifact_id: UUID
    repository_id: UUID
    kind: str
    name: str
    parent_name: str
    dev: int
    ino: int
    generation: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class ClaimResult:
    idempotency_id: int
    is_new: bool
    fingerprint: bytes
    effect: EffectRecord | None
    terminal_not_published: bool


@dataclass(frozen=True, slots=True)
class StoredEffectView:
    effect_id: int
    idempotency_id: int
    scope: IdempotencyScope
    key_hash: IdempotencyKeyHash
    fingerprint: bytes
    terminal_not_published: bool
    resource_id: UUID
    status: EffectStatus
    response_body: dict[str, Any] | None


class MutationStore:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        transaction_lock: threading.Lock | None = None,
    ) -> None:
        self._connection = connection
        self._lock = transaction_lock if transaction_lock is not None else threading.Lock()

    @staticmethod
    def hash_idempotency_key(raw_key: str) -> IdempotencyKeyHash:
        return IdempotencyKeyHash.from_raw_key(raw_key)

    def claim_or_lookup(
        self,
        scope: IdempotencyScope,
        *,
        key_hash: IdempotencyKeyHash,
        fingerprint: bytes,
    ) -> ClaimResult:
        with self._transaction():
            row = self._fetch_idempotency_row(scope, key_hash)
            if row is None:
                idempotency_id = self._insert_idempotency(scope, key_hash, fingerprint)
                return ClaimResult(
                    idempotency_id=idempotency_id,
                    is_new=True,
                    fingerprint=fingerprint,
                    effect=None,
                    terminal_not_published=False,
                )
            if row["request_fingerprint"] != fingerprint:
                raise FingerprintConflict(scope=scope)
            if bool(row["terminal_not_published"]):
                raise IdempotencyTerminalNotPublished(scope=scope)
            effect = self._fetch_effect_for_idempotency(int(row["id"]))
            return ClaimResult(
                idempotency_id=int(row["id"]),
                is_new=False,
                fingerprint=fingerprint,
                effect=effect,
                terminal_not_published=False,
            )

    def allocate_pending(
        self,
        scope: IdempotencyScope,
        *,
        key_hash: IdempotencyKeyHash,
        fingerprint: bytes,
        resource_id: UUID,
    ) -> EffectRecord:
        with self._transaction():
            row = self._fetch_idempotency_row(scope, key_hash)
            if row is None:
                idempotency_id = self._insert_idempotency(scope, key_hash, fingerprint)
            else:
                if row["request_fingerprint"] != fingerprint:
                    raise FingerprintConflict(scope=scope)
                if bool(row["terminal_not_published"]):
                    raise IdempotencyTerminalNotPublished(scope=scope)
                idempotency_id = int(row["id"])

            existing = self._fetch_effect_for_idempotency(idempotency_id)
            if existing is not None:
                if existing.status == EffectStatus.SUCCEEDED:
                    return existing
                raise DuplicateEffectClaim(scope=scope)

            now = _utc_now_iso()
            cursor = self._connection.execute(
                """
                INSERT INTO synchronous_mutation_effects (
                    idempotency_id,
                    resource_id,
                    status,
                    response_status,
                    response_body,
                    updated_at
                ) VALUES (?, ?, ?, NULL, NULL, ?)
                """,
                (idempotency_id, str(resource_id), EffectStatus.PENDING.value, now),
            )
            effect_id = cursor.lastrowid
            if effect_id is None:
                raise MutationStoreError("failed to allocate pending effect")
            return EffectRecord(
                effect_id=int(effect_id),
                idempotency_id=idempotency_id,
                resource_id=resource_id,
                status=EffectStatus.PENDING,
                response_status=None,
                response_body=None,
            )

    def mark_succeeded(
        self,
        effect_id: int,
        *,
        response_body: dict[str, Any],
        artifact_lifecycle: ArtifactLifecycleRecord | None = None,
    ) -> EffectRecord:
        with self._transaction():
            row = self._fetch_effect_by_id(effect_id)
            if row is None:
                raise MutationStoreError(f"effect {effect_id} does not exist")
            if row["status"] == EffectStatus.SUCCEEDED.value:
                return self._effect_from_row(row)
            if row["status"] != EffectStatus.PENDING.value:
                raise MutationStoreError(f"effect {effect_id} is not pending")
            idempotency_row = self._fetch_idempotency_row_by_id(int(row["idempotency_id"]))
            if idempotency_row is None:
                raise MutationStoreError(f"idempotency row for effect {effect_id} does not exist")
            if bool(idempotency_row["terminal_not_published"]):
                raise TerminalTransitionRejected(
                    scope=self._scope_from_idempotency_row(idempotency_row),
                    reason="terminal-not-published effects cannot succeed",
                )
            now = _utc_now_iso()
            self._connection.execute(
                """
                UPDATE synchronous_mutation_effects
                SET status = ?, response_status = ?, response_body = ?, updated_at = ?
                WHERE effect_id = ?
                """,
                (
                    EffectStatus.SUCCEEDED.value,
                    SYNCHRONOUS_MUTATION_SUCCESS_STATUS,
                    json.dumps(response_body, separators=(",", ":"), sort_keys=True),
                    now,
                    effect_id,
                ),
            )
            if artifact_lifecycle is not None:
                self._upsert_artifact_lifecycle(artifact_lifecycle, now=now)
            updated = self._fetch_effect_by_id(effect_id)
            assert updated is not None
            return self._effect_from_row(updated)

    def get_stored_response(
        self,
        scope: IdempotencyScope,
        *,
        key_hash: IdempotencyKeyHash,
        fingerprint: bytes,
    ) -> tuple[int, dict[str, Any]] | None:
        with self._transaction():
            row = self._fetch_idempotency_row(scope, key_hash)
            if row is None:
                return None
            if row["request_fingerprint"] != fingerprint:
                raise FingerprintConflict(scope=scope)
            if bool(row["terminal_not_published"]):
                raise IdempotencyTerminalNotPublished(scope=scope)
            effect = self._fetch_effect_for_idempotency(int(row["id"]))
            if effect is None or effect.status != EffectStatus.SUCCEEDED:
                return None
            assert effect.response_status is not None
            assert effect.response_body is not None
            return effect.response_status, effect.response_body

    def has_succeeded_create(self, repository_id: UUID) -> bool:
        with self._transaction():
            cursor = self._connection.execute(
                """
                SELECT e.status
                FROM synchronous_mutation_effects AS e
                JOIN mutation_idempotency AS i ON i.id = e.idempotency_id
                WHERE i.mutation_kind = ?
                  AND i.repository_scope = ''
                  AND e.resource_id = ?
                """,
                (MutationKind.CREATE_REPOSITORY.value, str(repository_id)),
            )
            for row in cursor.fetchall():
                if str(row["status"]) == EffectStatus.SUCCEEDED.value:
                    return True
            return False

    def has_succeeded_upload(self, repository_id: UUID, artifact_id: UUID) -> bool:
        with self._transaction():
            cursor = self._connection.execute(
                """
                SELECT e.status
                FROM synchronous_mutation_effects AS e
                JOIN mutation_idempotency AS i ON i.id = e.idempotency_id
                WHERE i.mutation_kind = ?
                  AND i.repository_scope = ?
                  AND e.resource_id = ?
                """,
                (
                    MutationKind.UPLOAD_ARTIFACT.value,
                    repository_id.hex,
                    str(artifact_id),
                ),
            )
            for row in cursor.fetchall():
                if str(row["status"]) == EffectStatus.SUCCEEDED.value:
                    return True
            return False

    def iter_effects_by_status(self, status: EffectStatus) -> list[StoredEffectView]:
        with self._transaction():
            cursor = self._connection.execute(
                """
                SELECT
                    e.effect_id,
                    e.idempotency_id,
                    e.resource_id,
                    e.status,
                    e.response_body,
                    i.mutation_kind,
                    i.repository_scope,
                    i.key_hash,
                    i.request_fingerprint,
                    i.terminal_not_published
                FROM synchronous_mutation_effects AS e
                JOIN mutation_idempotency AS i ON i.id = e.idempotency_id
                WHERE e.status = ?
                ORDER BY e.effect_id
                """,
                (status.value,),
            )
            views: list[StoredEffectView] = []
            for row in cursor.fetchall():
                response_body = None
                if row["response_body"] is not None:
                    response_body = json.loads(str(row["response_body"]))
                views.append(
                    StoredEffectView(
                        effect_id=int(row["effect_id"]),
                        idempotency_id=int(row["idempotency_id"]),
                        scope=self._scope_from_idempotency_row(row),
                        key_hash=IdempotencyKeyHash(bytes(row["key_hash"])),
                        fingerprint=bytes(row["request_fingerprint"]),
                        terminal_not_published=bool(row["terminal_not_published"]),
                        resource_id=UUID(str(row["resource_id"])),
                        status=EffectStatus(str(row["status"])),
                        response_body=response_body,
                    )
                )
            return views

    def get_artifact_lifecycle(self, artifact_id: UUID) -> ArtifactLifecycleRecord | None:
        with self._transaction():
            cursor = self._connection.execute(
                """
                SELECT
                    artifact_id,
                    repository_scope,
                    media_type,
                    size_bytes,
                    raw_sha256,
                    consumed_by_operation_id,
                    consumed_at,
                    bytes_deleted_at,
                    created_at,
                    bytes_delete_intent_at,
                    bytes_delete_dev,
                    bytes_delete_ino,
                    bytes_delete_phase,
                    bytes_delete_generation,
                    bytes_deleted_receipt_dev,
                    bytes_deleted_receipt_ino,
                    bytes_deleted_receipt_generation
                FROM artifact_lifecycle
                WHERE artifact_id = ?
                """,
                (str(artifact_id),),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            try:
                return self._artifact_lifecycle_from_row(row)
            except (TypeError, ValueError) as exc:
                raise MutationStoreInvariantError("artifact lifecycle row is invalid") from exc

    def list_artifacts_pending_byte_cleanup(
        self,
        *,
        limit: int = 64,
        after_cleanup_seq: int | None = None,
    ) -> CleanupCandidatePage:
        """Return one keyset page of lifecycle rows that may own undeleted ready bytes.

        Cursor is the last raw SQL ``cleanup_seq`` (INTEGER), including poison rows.
        """

        if limit <= 0:
            return CleanupCandidatePage(
                records=[],
                scanned=0,
                cursor_cleanup_seq=None,
            )
        sql = """
                SELECT
                    artifact_id,
                    repository_scope,
                    media_type,
                    size_bytes,
                    raw_sha256,
                    consumed_by_operation_id,
                    consumed_at,
                    bytes_deleted_at,
                    created_at,
                    bytes_delete_intent_at,
                    bytes_delete_dev,
                    bytes_delete_ino,
                    bytes_delete_phase,
                    bytes_delete_generation,
                    bytes_deleted_receipt_dev,
                    bytes_deleted_receipt_ino,
                    bytes_deleted_receipt_generation,
                    cleanup_seq
                FROM artifact_lifecycle
                WHERE bytes_deleted_at IS NULL
                """
        params: list[object] = []
        if after_cleanup_seq is not None:
            sql += """
                AND cleanup_seq > ?
                """
            params.append(int(after_cleanup_seq))
        sql += """
                ORDER BY cleanup_seq ASC
                LIMIT ?
                """
        params.append(int(limit))
        with self._transaction():
            cursor = self._connection.execute(sql, params)
            records: list[ArtifactLifecycleRecord] = []
            scanned = 0
            last_seq: int | None = None
            for row in cursor.fetchall():
                scanned += 1
                seq_raw = row["cleanup_seq"] if "cleanup_seq" in row.keys() else row[-1]
                parsed_seq = _parse_cleanup_seq(seq_raw)
                if parsed_seq is not None:
                    last_seq = parsed_seq
                try:
                    records.append(self._artifact_lifecycle_from_row(row))
                except (TypeError, ValueError):
                    log_event(
                        "artifact_cleanup",
                        stage="list_candidates",
                        result="skipped",
                        cleanup_outcome="invalid_lifecycle_row",
                    )
                    continue
            return CleanupCandidatePage(
                records=records,
                scanned=scanned,
                cursor_cleanup_seq=last_seq,
            )

    def list_artifacts_with_bytes_deleted_receipt(
        self,
        *,
        limit: int = 64,
        after_artifact_id: str | None = None,
    ) -> ReceiptGcPage:
        """Return lifecycle rows that still carry a bytes-deleted residual receipt."""

        with self._transaction():
            sql = """
                SELECT
                    artifact_id,
                    repository_scope,
                    media_type,
                    size_bytes,
                    raw_sha256,
                    consumed_by_operation_id,
                    consumed_at,
                    bytes_deleted_at,
                    created_at,
                    bytes_delete_intent_at,
                    bytes_delete_dev,
                    bytes_delete_ino,
                    bytes_delete_phase,
                    bytes_delete_generation,
                    bytes_deleted_receipt_dev,
                    bytes_deleted_receipt_ino,
                    bytes_deleted_receipt_generation
                FROM artifact_lifecycle
                WHERE bytes_deleted_receipt_dev IS NOT NULL
                  AND bytes_deleted_receipt_ino IS NOT NULL
                  AND bytes_deleted_receipt_generation IS NOT NULL
                """
            params: list[object] = []
            if after_artifact_id is not None:
                sql += " AND artifact_id > ?"
                params.append(after_artifact_id)
            sql += " ORDER BY artifact_id ASC LIMIT ?"
            params.append(int(limit))
            cursor = self._connection.execute(sql, params)
            records: list[ArtifactLifecycleRecord] = []
            scanned = 0
            last_id: str | None = None
            for row in cursor.fetchall():
                scanned += 1
                last_id = str(row["artifact_id"])
                try:
                    records.append(self._artifact_lifecycle_from_row(row))
                except (TypeError, ValueError, MutationStoreInvariantError):
                    log_event(
                        "artifact_cleanup",
                        stage="list_receipt_gc",
                        result="skipped",
                        cleanup_outcome="invalid_lifecycle_row",
                    )
                    continue
            return ReceiptGcPage(
                records=records,
                scanned=scanned,
                cursor_artifact_id=last_id,
            )

    @staticmethod
    def _artifact_lifecycle_from_row(row: sqlite3.Row) -> ArtifactLifecycleRecord:
        from gateway_repository_service.artifact_retention import parse_durable_timestamp

        keys = row.keys()
        consumed_by_operation_id = row["consumed_by_operation_id"]
        intent_at_raw = row["bytes_delete_intent_at"] if "bytes_delete_intent_at" in keys else None
        intent_dev_raw = row["bytes_delete_dev"] if "bytes_delete_dev" in keys else None
        intent_ino_raw = row["bytes_delete_ino"] if "bytes_delete_ino" in keys else None
        phase_raw = row["bytes_delete_phase"] if "bytes_delete_phase" in keys else None
        generation_raw = (
            row["bytes_delete_generation"] if "bytes_delete_generation" in keys else None
        )
        intent_present = (
            intent_at_raw is not None,
            intent_dev_raw is not None,
            intent_ino_raw is not None,
            phase_raw is not None,
            generation_raw is not None,
        )
        if any(intent_present) and not all(intent_present):
            raise ValueError("partial delete intent fields")
        phase_text: str | None
        intent_at: str | None
        intent_dev: int | None
        intent_ino: int | None
        intent_generation: str | None
        if all(intent_present):
            phase_text = str(phase_raw)
            if phase_text not in {"quarantined", "detached"}:
                raise ValueError("invalid bytes_delete_phase")
            intent_at = str(intent_at_raw)
            if parse_durable_timestamp(intent_at) is None:
                raise ValueError("invalid bytes_delete_intent_at")
            assert intent_dev_raw is not None and intent_ino_raw is not None
            assert generation_raw is not None
            intent_dev = int(intent_dev_raw)
            intent_ino = int(intent_ino_raw)
            intent_generation = str(generation_raw)
            if not intent_generation:
                raise ValueError("invalid bytes_delete_generation")
        else:
            phase_text = None
            intent_at = None
            intent_dev = None
            intent_ino = None
            intent_generation = None

        bytes_deleted_at = (
            str(row["bytes_deleted_at"]) if row["bytes_deleted_at"] is not None else None
        )
        receipt_dev_raw = (
            row["bytes_deleted_receipt_dev"] if "bytes_deleted_receipt_dev" in keys else None
        )
        receipt_ino_raw = (
            row["bytes_deleted_receipt_ino"] if "bytes_deleted_receipt_ino" in keys else None
        )
        receipt_generation_raw = (
            row["bytes_deleted_receipt_generation"]
            if "bytes_deleted_receipt_generation" in keys
            else None
        )
        receipt_present = (
            receipt_dev_raw is not None,
            receipt_ino_raw is not None,
            receipt_generation_raw is not None,
        )
        if any(receipt_present) and not all(receipt_present):
            raise ValueError("partial delete receipt fields")
        receipt_dev: int | None
        receipt_ino: int | None
        receipt_generation: str | None
        if all(receipt_present):
            if bytes_deleted_at is None:
                raise ValueError("delete receipt requires bytes_deleted_at")
            assert receipt_dev_raw is not None and receipt_ino_raw is not None
            assert receipt_generation_raw is not None
            receipt_dev = int(receipt_dev_raw)
            receipt_ino = int(receipt_ino_raw)
            receipt_generation = str(receipt_generation_raw)
            if not receipt_generation:
                raise ValueError("invalid bytes_deleted_receipt_generation")
        else:
            receipt_dev = None
            receipt_ino = None
            receipt_generation = None

        if bytes_deleted_at is not None and any(intent_present):
            raise MutationStoreInvariantError(
                "bytes_deleted_at cannot coexist with delete intent fields"
            )

        return ArtifactLifecycleRecord(
            artifact_id=UUID(str(row["artifact_id"])),
            repository_id=UUID(str(row["repository_scope"])),
            media_type=str(row["media_type"]),
            size_bytes=int(row["size_bytes"]),
            raw_sha256=str(row["raw_sha256"]),
            consumed_by_operation_id=(
                UUID(str(consumed_by_operation_id))
                if consumed_by_operation_id is not None
                else None
            ),
            consumed_at=(str(row["consumed_at"]) if row["consumed_at"] is not None else None),
            bytes_deleted_at=bytes_deleted_at,
            created_at=str(row["created_at"]) if row["created_at"] is not None else None,
            bytes_delete_intent_at=intent_at,
            bytes_delete_dev=intent_dev,
            bytes_delete_ino=intent_ino,
            bytes_delete_phase=phase_text,
            bytes_delete_generation=intent_generation,
            bytes_deleted_receipt_dev=receipt_dev,
            bytes_deleted_receipt_ino=receipt_ino,
            bytes_deleted_receipt_generation=receipt_generation,
        )

    def record_artifact_consumed(
        self,
        artifact_id: UUID,
        *,
        operation_id: UUID,
        consumed_at: str,
        repository_id: UUID,
    ) -> None:
        cursor = self._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET consumed_by_operation_id = COALESCE(consumed_by_operation_id, ?),
                consumed_at = COALESCE(consumed_at, ?),
                updated_at = ?
            WHERE artifact_id = ?
              AND repository_scope = ?
            """,
            (
                str(operation_id),
                consumed_at,
                consumed_at,
                str(artifact_id),
                repository_id.hex,
            ),
        )
        if cursor.rowcount != 1:
            raise MutationStoreError("artifact lifecycle row is missing or scope mismatch")

    def record_artifact_bytes_deleted(
        self,
        artifact_id: UUID,
        *,
        deleted_at: str,
        repository_id: UUID,
        expected_dev: int | None = None,
        expected_ino: int | None = None,
        expected_generation: str | None = None,
    ) -> None:
        del expected_dev, expected_ino, expected_generation
        cursor = self._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_at = ?,
                updated_at = ?,
                bytes_delete_intent_at = NULL,
                bytes_delete_dev = NULL,
                bytes_delete_ino = NULL,
                bytes_delete_phase = NULL,
                bytes_delete_generation = NULL
            WHERE artifact_id = ?
              AND repository_scope = ?
              AND bytes_deleted_at IS NULL
            """,
            (
                deleted_at,
                deleted_at,
                str(artifact_id),
                repository_id.hex,
            ),
        )
        if cursor.rowcount != 1:
            raise MutationStoreError("artifact bytes_deleted_at CAS failed")
        row = self._connection.execute(
            """
            SELECT bytes_deleted_at, repository_scope,
                   bytes_delete_intent_at, bytes_delete_dev, bytes_delete_ino,
                   bytes_delete_phase, bytes_delete_generation
            FROM artifact_lifecycle
            WHERE artifact_id = ?
            """,
            (str(artifact_id),),
        ).fetchone()
        if (
            row is None
            or str(row["repository_scope"]) != repository_id.hex
            or row["bytes_deleted_at"] is None
            or row["bytes_delete_intent_at"] is not None
            or row["bytes_delete_dev"] is not None
            or row["bytes_delete_ino"] is not None
            or row["bytes_delete_phase"] is not None
            or row["bytes_delete_generation"] is not None
        ):
            raise MutationStoreError("artifact bytes_deleted_at readback failed")

    def clear_artifact_residual(
        self,
        *,
        residual_id: int,
        expected_dev: int,
        expected_ino: int,
    ) -> None:
        """Delete residual proof. Caller must already hold the transaction lock."""

        self._connection.execute(
            """
            DELETE FROM artifact_residual
            WHERE residual_id = ?
              AND dev = ?
              AND ino = ?
            """,
            (int(residual_id), int(expected_dev), int(expected_ino)),
        )

    def list_artifact_residuals(
        self,
        *,
        artifact_id: UUID | None = None,
        limit: int = 256,
        after_residual_id: int | None = None,
    ) -> ResidualPage:
        """List residual rows. Caller must already hold the transaction lock."""

        sql = """
            SELECT residual_id, artifact_id, repository_scope, kind, name, parent_name,
                   dev, ino, generation, created_at
            FROM artifact_residual
            """
        params: list[object] = []
        clauses: list[str] = []
        if artifact_id is not None:
            clauses.append("artifact_id = ?")
            params.append(str(artifact_id))
        if after_residual_id is not None:
            clauses.append("residual_id > ?")
            params.append(int(after_residual_id))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY residual_id ASC LIMIT ?"
        params.append(int(limit))
        rows = self._connection.execute(sql, params).fetchall()
        records: list[ArtifactResidualRecord] = []
        scanned = 0
        last_id: int | None = None
        for row in rows:
            scanned += 1
            try:
                last_id = int(row["residual_id"])
            except (TypeError, ValueError, KeyError):
                pass
            try:
                records.append(
                    ArtifactResidualRecord(
                        residual_id=int(row["residual_id"]),
                        artifact_id=UUID(str(row["artifact_id"])),
                        repository_id=UUID(hex=str(row["repository_scope"])),
                        kind=str(row["kind"]),
                        name=str(row["name"]),
                        parent_name=str(row["parent_name"]),
                        dev=int(row["dev"]),
                        ino=int(row["ino"]),
                        generation=(
                            None if row["generation"] is None else str(row["generation"])
                        ),
                        created_at=str(row["created_at"]),
                    )
                )
            except (TypeError, ValueError):
                log_event(
                    "artifact_cleanup",
                    stage="list_residuals",
                    result="skipped",
                    cleanup_outcome="invalid_residual_row",
                )
                continue
        return ResidualPage(
            records=records,
            scanned=scanned,
            cursor_residual_id=last_id,
        )

    def clear_artifact_bytes_delete_intent(
        self,
        artifact_id: UUID,
        *,
        repository_id: UUID,
        expected_dev: int,
        expected_ino: int,
        expected_generation: str,
    ) -> None:
        cursor = self._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_delete_intent_at = NULL,
                bytes_delete_dev = NULL,
                bytes_delete_ino = NULL,
                bytes_delete_phase = NULL,
                bytes_delete_generation = NULL
            WHERE artifact_id = ?
              AND repository_scope = ?
              AND bytes_delete_dev = ?
              AND bytes_delete_ino = ?
              AND bytes_delete_generation = ?
            """,
            (
                str(artifact_id),
                repository_id.hex,
                int(expected_dev),
                int(expected_ino),
                expected_generation,
            ),
        )
        # rowcount 0: intent already replaced or cleared — intentional no-op.
        _ = cursor.rowcount

    def clear_artifact_bytes_deleted_receipt(
        self,
        artifact_id: UUID,
        *,
        repository_id: UUID,
        expected_dev: int,
        expected_ino: int,
        expected_generation: str,
    ) -> None:
        cursor = self._connection.execute(
            """
            UPDATE artifact_lifecycle
            SET bytes_deleted_receipt_dev = NULL,
                bytes_deleted_receipt_ino = NULL,
                bytes_deleted_receipt_generation = NULL
            WHERE artifact_id = ?
              AND repository_scope = ?
              AND bytes_deleted_receipt_dev = ?
              AND bytes_deleted_receipt_ino = ?
              AND bytes_deleted_receipt_generation = ?
            """,
            (
                str(artifact_id),
                repository_id.hex,
                int(expected_dev),
                int(expected_ino),
                expected_generation,
            ),
        )
        # rowcount 0: receipt already cleared or mismatched — intentional no-op.
        _ = cursor.rowcount

    def mark_terminal_not_published(
        self,
        scope: IdempotencyScope,
        *,
        key_hash: IdempotencyKeyHash,
        fingerprint: bytes,
        effect_id: int,
    ) -> None:
        with self._transaction():
            row = self._fetch_idempotency_row(scope, key_hash)
            if row is None:
                raise MutationStoreError(f"idempotency scope {scope!r} does not exist")
            if row["request_fingerprint"] != fingerprint:
                raise FingerprintConflict(scope=scope)

            effect_row = self._fetch_effect_by_id(effect_id)
            if effect_row is None:
                raise MutationStoreError(f"effect {effect_id} does not exist")
            if int(effect_row["idempotency_id"]) != int(row["id"]):
                raise MutationStoreError(f"effect {effect_id} does not belong to idempotency scope")
            if effect_row["status"] == EffectStatus.SUCCEEDED.value:
                raise TerminalTransitionRejected(
                    scope=scope,
                    reason="succeeded effects cannot be marked terminal-not-published",
                )
            if effect_row["status"] != EffectStatus.PENDING.value:
                raise TerminalTransitionRejected(
                    scope=scope,
                    reason="only pending effects can be marked terminal-not-published",
                )

            self._connection.execute(
                """
                UPDATE mutation_idempotency
                SET terminal_not_published = 1
                WHERE id = ?
                """,
                (int(row["id"]),),
            )

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

    def _fetch_idempotency_row_by_id(self, idempotency_id: int) -> sqlite3.Row | None:
        cursor = self._connection.execute(
            """
            SELECT id, mutation_kind, repository_scope, request_fingerprint, terminal_not_published
            FROM mutation_idempotency
            WHERE id = ?
            """,
            (idempotency_id,),
        )
        row = cursor.fetchone()
        return cast(sqlite3.Row | None, row)

    @staticmethod
    def _scope_from_idempotency_row(row: sqlite3.Row) -> IdempotencyScope:
        mutation_kind = MutationKind(str(row["mutation_kind"]))
        repository_scope = str(row["repository_scope"])
        if mutation_kind == MutationKind.CREATE_REPOSITORY:
            return IdempotencyScope.for_create()
        return IdempotencyScope.for_upload(UUID(repository_scope))

    def _fetch_idempotency_row(
        self,
        scope: IdempotencyScope,
        key_hash: IdempotencyKeyHash,
    ) -> sqlite3.Row | None:
        cursor = self._connection.execute(
            """
            SELECT id, request_fingerprint, terminal_not_published
            FROM mutation_idempotency
            WHERE mutation_kind = ? AND repository_scope = ? AND key_hash = ?
            """,
            (scope.mutation_kind.value, scope.repository_scope(), key_hash.digest),
        )
        row = cursor.fetchone()
        return cast(sqlite3.Row | None, row)

    def _insert_idempotency(
        self,
        scope: IdempotencyScope,
        key_hash: IdempotencyKeyHash,
        fingerprint: bytes,
    ) -> int:
        now = _utc_now_iso()
        cursor = self._connection.execute(
            """
            INSERT INTO mutation_idempotency (
                mutation_kind,
                repository_scope,
                key_hash,
                request_fingerprint,
                terminal_not_published,
                created_at
            ) VALUES (?, ?, ?, ?, 0, ?)
            """,
            (
                scope.mutation_kind.value,
                scope.repository_scope(),
                key_hash.digest,
                fingerprint,
                now,
            ),
        )
        inserted_id = cursor.lastrowid
        if inserted_id is None:
            raise MutationStoreError("failed to insert idempotency metadata")
        return int(inserted_id)

    def _fetch_effect_for_idempotency(self, idempotency_id: int) -> EffectRecord | None:
        cursor = self._connection.execute(
            """
            SELECT effect_id, idempotency_id, resource_id, status, response_status, response_body
            FROM synchronous_mutation_effects
            WHERE idempotency_id = ?
            """,
            (idempotency_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._effect_from_row(row)

    def _fetch_effect_by_id(self, effect_id: int) -> sqlite3.Row | None:
        cursor = self._connection.execute(
            """
            SELECT effect_id, idempotency_id, resource_id, status, response_status, response_body
            FROM synchronous_mutation_effects
            WHERE effect_id = ?
            """,
            (effect_id,),
        )
        row = cursor.fetchone()
        return cast(sqlite3.Row | None, row)

    def _effect_from_row(self, row: sqlite3.Row) -> EffectRecord:
        response_body = None
        if row["response_body"] is not None:
            response_body = json.loads(str(row["response_body"]))
        return EffectRecord(
            effect_id=int(row["effect_id"]),
            idempotency_id=int(row["idempotency_id"]),
            resource_id=UUID(str(row["resource_id"])),
            status=EffectStatus(str(row["status"])),
            response_status=(
                int(row["response_status"]) if row["response_status"] is not None else None
            ),
            response_body=response_body,
        )

    def _upsert_artifact_lifecycle(self, record: ArtifactLifecycleRecord, *, now: str) -> None:
        self._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id,
                repository_scope,
                media_type,
                size_bytes,
                raw_sha256,
                created_at,
                updated_at,
                cleanup_seq
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                (SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle)
            )
            ON CONFLICT(artifact_id) DO UPDATE SET
                repository_scope = excluded.repository_scope,
                media_type = excluded.media_type,
                size_bytes = excluded.size_bytes,
                raw_sha256 = excluded.raw_sha256,
                updated_at = excluded.updated_at
            """,
            (
                str(record.artifact_id),
                record.repository_id.hex,
                record.media_type,
                record.size_bytes,
                record.raw_sha256,
                now,
                now,
            ),
        )


def _parse_cleanup_seq(seq_raw: object) -> int | None:
    if isinstance(seq_raw, bool):
        return None
    if isinstance(seq_raw, int) and seq_raw > 0:
        return seq_raw
    if isinstance(seq_raw, (str, bytes, bytearray)):
        try:
            parsed = int(seq_raw)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return parsed
    return None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
