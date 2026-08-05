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

SYNCHRONOUS_MUTATION_SUCCESS_STATUS = 201


class MutationKind(StrEnum):
    CREATE_REPOSITORY = "create_repository"
    UPLOAD_ARTIFACT = "upload_artifact"


class EffectStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"


class MutationStoreError(RuntimeError):
    """Base error for mutation store failures."""


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
class ClaimResult:
    idempotency_id: int
    is_new: bool
    fingerprint: bytes
    effect: EffectRecord | None
    terminal_not_published: bool


class MutationStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.Lock()

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

    def mark_succeeded(self, effect_id: int, *, response_body: dict[str, Any]) -> EffectRecord:
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


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
