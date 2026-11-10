"""SQLite-backed artifact protection intent records."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from gateway_backend.artifacts.types import ArtifactRef, validate_artifact_id
from gateway_backend.artifacts.canonical_table_store import CANONICAL_TABLE_TTL_SECONDS

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1


class SQLiteArtifactProtectionStore:
    """Record and query artifact protection intents within one control DB transaction."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        read_only: bool = False,
        now: datetime | None = None,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteArtifactProtectionStore requires an active transaction")
        self._connection = connection
        self._read_only = read_only
        if now is not None:
            _datetime_to_epoch_us(now)
        self._now = now

    def set_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
        recorded_at: datetime,
    ) -> bool:
        if self._read_only:
            raise RuntimeError("artifact protection store is read-only in this transaction")
        applied = False
        recorded_at_us = _datetime_to_epoch_us(recorded_at)
        for ref in refs:
            existing = self._connection.execute(
                """
                SELECT intent FROM artifact_protection_intents
                WHERE artifact_id = ? AND owner_kind = ? AND owner_id = ?
                """,
                (ref.artifact_id, owner_kind, owner_id),
            ).fetchone()
            if existing is not None and existing[0] == intent:
                continue
            self._connection.execute(
                """
                INSERT INTO artifact_protection_intents (
                    artifact_id, owner_kind, owner_id, intent, recorded_at_us
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id, owner_kind, owner_id) DO UPDATE SET
                    intent = excluded.intent,
                    recorded_at_us = excluded.recorded_at_us
                """,
                (ref.artifact_id, owner_kind, owner_id, intent, recorded_at_us),
            )
            self._connection.execute(
                "UPDATE canonical_table_cache SET expires_at_us = NULL WHERE artifact_id = ?",
                (ref.artifact_id,),
            )
            applied = True
        return applied

    def clear_protection(self, *, owner_kind: str, owner_id: str) -> int:
        if self._read_only:
            raise RuntimeError("artifact protection store is read-only in this transaction")
        canonical_ids = tuple(row[0] for row in self._connection.execute(
            """SELECT p.artifact_id FROM artifact_protection_intents p
               JOIN canonical_table_cache c ON c.artifact_id = p.artifact_id
               WHERE p.owner_kind = ? AND p.owner_id = ?""",
            (owner_kind, owner_id),
        ))
        cursor = self._connection.execute(
            """
            DELETE FROM artifact_protection_intents
            WHERE owner_kind = ? AND owner_id = ?
            """,
            (owner_kind, owner_id),
        )
        self.touch_canonical_ttl(
            canonical_ids, recorded_at=datetime.now(UTC) if self._now is None else self._now,
        )
        return int(cursor.rowcount)

    def touch_canonical_ttl(self, artifact_ids: tuple[str, ...], *, recorded_at: datetime) -> None:
        """Keep registered canonical content until TTL after its last strong owner."""
        if self._read_only:
            raise RuntimeError("artifact protection store is read-only in this transaction")
        for artifact_id in artifact_ids:
            validate_artifact_id(artifact_id)
        now_us = _datetime_to_epoch_us(recorded_at)
        expires_at_us = now_us + CANONICAL_TABLE_TTL_SECONDS * 1_000_000
        for artifact_id in artifact_ids:
            strong = self._connection.execute(
                """SELECT 1 FROM artifact_protection_intents WHERE artifact_id = ?
                   AND owner_kind != 'canonical-table-cache' AND expires_at_us IS NULL LIMIT 1""",
                (artifact_id,),
            ).fetchone()
            if strong is not None:
                self._connection.execute(
                    "UPDATE canonical_table_cache SET expires_at_us = NULL WHERE artifact_id = ?",
                    (artifact_id,),
                )
                continue
            self._connection.execute(
                "UPDATE canonical_table_cache SET expires_at_us = ? WHERE artifact_id = ?",
                (expires_at_us, artifact_id),
            )
            self._connection.execute(
                """INSERT INTO artifact_protection_intents (
                       artifact_id, owner_kind, owner_id, intent, recorded_at_us, expires_at_us
                   ) VALUES (?, 'canonical-table-cache', ?, 'ttl-cache', ?, ?)
                   ON CONFLICT(artifact_id, owner_kind, owner_id) DO UPDATE SET
                       recorded_at_us = excluded.recorded_at_us, expires_at_us = excluded.expires_at_us""",
                (artifact_id, artifact_id, now_us, expires_at_us),
            )

    def clear_protection_intent(self, *, owner_kind: str, owner_id: str, intent: str) -> int:
        """Release one derived intent without removing this owner's workflow pins."""
        if self._read_only:
            raise RuntimeError("artifact protection store is read-only in this transaction")
        canonical_ids = tuple(row[0] for row in self._connection.execute(
            """SELECT p.artifact_id FROM artifact_protection_intents p
               JOIN canonical_table_cache c ON c.artifact_id=p.artifact_id
               WHERE p.owner_kind=? AND p.owner_id=? AND p.intent=?""",
            (owner_kind, owner_id, intent),
        ))
        cursor = self._connection.execute(
            "DELETE FROM artifact_protection_intents WHERE owner_kind=? AND owner_id=? AND intent=?",
            (owner_kind, owner_id, intent),
        )
        self.touch_canonical_ttl(
            canonical_ids, recorded_at=datetime.now(UTC) if self._now is None else self._now,
        )
        return int(cursor.rowcount)

    def is_protected(self, artifact_id: str) -> bool:
        validate_artifact_id(artifact_id)
        now_us = _datetime_to_epoch_us(
            datetime.now(UTC) if self._now is None else self._now
        )
        row = self._connection.execute(
            """
            SELECT 1 FROM artifact_protection_intents
            WHERE artifact_id = ? AND (expires_at_us IS NULL OR expires_at_us > ?)
            LIMIT 1
            """,
            (artifact_id, now_us),
        ).fetchone()
        return row is not None


def _datetime_to_epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("recorded_at must be an aware UTC datetime")
    delta = value - _EPOCH
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    if micros < _SQLITE_INT_MIN or micros > _SQLITE_INT_MAX:
        raise ValueError("timestamp is outside SQLite INTEGER range")
    return micros
