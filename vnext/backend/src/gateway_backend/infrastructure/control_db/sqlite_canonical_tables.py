"""Derived canonical content index using existing transaction/protection owners."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.canonical_table_store import (
    CANONICAL_IPC_MEDIA_TYPE,
    CanonicalTableKey,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.infrastructure.control_db.sqlite_protection import (
    SQLiteArtifactProtectionStore,
    _datetime_to_epoch_us,
)

BASELINE_HEAD_OWNER = "canonical-baseline-head"
CANONICAL_CACHE_OWNER = "canonical-table-cache"


class SQLiteCanonicalTableCache:
    def __init__(
        self, connection: sqlite3.Connection, *, protection: SQLiteArtifactProtectionStore,
        now: datetime, read_only: bool = False,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("canonical table cache requires an active transaction")
        self._connection = connection
        self._protection = protection
        self._now = now
        self._read_only = read_only

    def lookup(self, key: CanonicalTableKey) -> ArtifactRef | None:
        row = self._connection.execute(
            """SELECT media_type, size_bytes, raw_sha256, expires_at_us
               FROM canonical_table_cache WHERE artifact_id = ? AND repository_id = ?""",
            (key.artifact_id, key.repository_id),
        ).fetchone()
        if row is None or (row[3] is not None and row[3] <= _datetime_to_epoch_us(self._now)):
            return None
        ref = ArtifactRef(key.artifact_id, row[0], row[1], DigestRef(row[2]))
        if not self._read_only and row[3] is not None:
            self._protection.touch_canonical_ttl((ref.artifact_id,), recorded_at=self._now)
        # Lookup's transaction protects the ref before any reader checks files.
        return ref

    def register(self, key: CanonicalTableKey, ref: ArtifactRef) -> None:
        self._require_writable()
        self._prune_expired()
        if ref.artifact_id != key.artifact_id or ref.media_type != CANONICAL_IPC_MEDIA_TYPE:
            raise ValueError("canonical cache ref does not match content identity")
        existing = self._connection.execute(
            "SELECT media_type, size_bytes, raw_sha256 FROM canonical_table_cache WHERE artifact_id = ?",
            (ref.artifact_id,),
        ).fetchone()
        if existing is not None and tuple(existing) != (ref.media_type, ref.size_bytes, ref.raw_sha256.value):
            raise ValueError("canonical content identity has different raw bytes")
        self._connection.execute(
            """INSERT INTO canonical_table_cache (
                   artifact_id, repository_id, media_type, size_bytes, raw_sha256, expires_at_us
               ) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(artifact_id) DO NOTHING""",
            (ref.artifact_id, key.repository_id, ref.media_type, ref.size_bytes,
             ref.raw_sha256.value, _datetime_to_epoch_us(self._now)),
        )
        self._protection.touch_canonical_ttl((ref.artifact_id,), recorded_at=self._now)

    def bind_commit(self, *, repository_id: str, commit_id: str, refs: tuple[ArtifactRef, ...]) -> None:
        """Index only an already verified exact commit; no file or repository IO."""
        self._require_writable()
        if not commit_id:
            raise ValueError("exact commit_id is required")
        for ref in refs:
            row = self._connection.execute(
                "SELECT repository_id FROM canonical_table_cache WHERE artifact_id = ?",
                (ref.artifact_id,),
            ).fetchone()
            if row is None or row[0] != repository_id:
                raise ValueError("canonical commit ref is not registered in this scope")
            self._connection.execute(
                """INSERT INTO canonical_commit_tables (repository_id, commit_id, artifact_id)
                   VALUES (?, ?, ?) ON CONFLICT DO NOTHING""",
                (repository_id, commit_id, ref.artifact_id),
            )
        current = self._connection.execute(
            """SELECT n.commit_id FROM baseline_head_records h
               JOIN baseline_node_records n ON n.node_id = h.node_id
               WHERE h.repository_id = ?""", (repository_id,),
        ).fetchone()
        if current is not None and current[0] == commit_id:
            self._protection.set_protection(
                refs, owner_kind=BASELINE_HEAD_OWNER, owner_id=repository_id,
                intent="baseline-head", recorded_at=self._now,
            )

    def move_head(self, *, repository_id: str, commit_id: str) -> None:
        """Called by the actual initial/Archive CAS transaction, never Submit."""
        self._require_writable()
        rows = self._connection.execute(
            """SELECT c.artifact_id, c.media_type, c.size_bytes, c.raw_sha256
               FROM canonical_commit_tables b JOIN canonical_table_cache c USING (artifact_id)
               WHERE b.repository_id = ? AND b.commit_id = ?""",
            (repository_id, commit_id),
        ).fetchall()
        self._protection.clear_protection(owner_kind=BASELINE_HEAD_OWNER, owner_id=repository_id)
        refs = tuple(ArtifactRef(row[0], row[1], row[2], DigestRef(row[3])) for row in rows)
        self._protection.set_protection(
            refs, owner_kind=BASELINE_HEAD_OWNER, owner_id=repository_id,
            intent="baseline-head", recorded_at=self._now,
        )

    def _require_writable(self) -> None:
        if self._read_only:
            raise RuntimeError("canonical table cache is read-only")

    def _prune_expired(self) -> None:
        expired = self._connection.execute(
            """SELECT artifact_id FROM canonical_table_cache WHERE expires_at_us <= ?
               ORDER BY expires_at_us LIMIT 64""", (_datetime_to_epoch_us(self._now),),
        ).fetchall()
        for row in expired:
            if self._protection.is_protected(row[0]):
                continue
            self._connection.execute(
                "DELETE FROM artifact_protection_intents WHERE artifact_id = ? AND owner_kind = ?",
                (row[0], CANONICAL_CACHE_OWNER),
            )
            self._connection.execute("DELETE FROM canonical_table_cache WHERE artifact_id = ?", (row[0],))
