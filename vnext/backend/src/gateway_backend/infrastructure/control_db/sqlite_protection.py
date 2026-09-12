"""SQLite-backed artifact protection intent records."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from gateway_backend.artifacts.types import ArtifactRef

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
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteArtifactProtectionStore requires an active transaction")
        self._connection = connection
        self._read_only = read_only

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
            applied = True
        return applied

    def is_protected(self, artifact_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM artifact_protection_intents WHERE artifact_id = ? LIMIT 1",
            (artifact_id,),
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
