"""SQLite row-file export cache with expiring artifact protection."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta

from gateway_shared_kernel import DigestRef

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    PARQUET_MEDIA_TYPE,
    SNAPSHOT_EXPORT_CACHE_TTL_SECONDS,
    SnapshotTableArtifactCacheKey,
)
from gateway_backend.infrastructure.control_db.sqlite_protection import (
    SQLiteArtifactProtectionStore,
)

_OWNER_KIND = "snapshot-table-export-cache"
_OWNER_PREFIX = "snapshot-export-"
_PRUNE_LIMIT = 64
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class SQLiteSnapshotTableExportCache:
    """Use the active control DB transaction for cache rows and protection intents."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        protection: SQLiteArtifactProtectionStore,
        now: datetime,
        read_only: bool = False,
        ttl: timedelta = timedelta(seconds=SNAPSHOT_EXPORT_CACHE_TTL_SECONDS),
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteSnapshotTableExportCache requires an active transaction")
        if now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
            raise ValueError("now must be an aware UTC datetime")
        if ttl.total_seconds() <= 0:
            raise ValueError("ttl must be positive")
        self._connection = connection
        self._protection = protection
        self._now = now
        self._read_only = read_only
        self._ttl = ttl

    def lookup_many(
        self,
        keys: tuple[SnapshotTableArtifactCacheKey, ...],
    ) -> dict[SnapshotTableArtifactCacheKey, ArtifactRef]:
        if type(keys) is not tuple or any(type(key) is not SnapshotTableArtifactCacheKey for key in keys):
            raise ValueError("keys must contain SnapshotTableArtifactCacheKey")
        self._prune_expired()
        results: dict[SnapshotTableArtifactCacheKey, ArtifactRef] = {}
        for key in keys:
            if key.repository_id is None:
                continue
            row = self._connection.execute(
                """
                SELECT artifact_id, media_type, size_bytes, raw_sha256, expires_at_us
                FROM snapshot_table_export_cache
                WHERE repository_id = ? AND row_layout_digest = ?
                    AND parquet_writer_contract_version = ?
                """,
                _key_values(key),
            ).fetchone()
            if row is None:
                continue
            artifact_id, media_type, size_bytes, raw_sha256, expires_at_us = row
            owner_id = _owner_id(key)
            if expires_at_us <= _to_epoch_us(self._now):
                self._delete_key(key, owner_id)
                continue
            try:
                ref = ArtifactRef(
                    artifact_id=artifact_id,
                    media_type=media_type,
                    size_bytes=size_bytes,
                    raw_sha256=DigestRef(raw_sha256),
                )
            except (TypeError, ValueError):
                self._delete_key(key, owner_id)
                continue
            if ref.media_type != PARQUET_MEDIA_TYPE:
                self._delete_key(key, owner_id)
                continue
            self._extend_protection(key, ref, owner_id)
            results[key] = ref
        return results

    def store_many(
        self,
        entries: tuple[tuple[SnapshotTableArtifactCacheKey, ArtifactRef], ...],
    ) -> None:
        self._require_writable()
        if type(entries) is not tuple or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not SnapshotTableArtifactCacheKey
            or type(item[1]) is not ArtifactRef
            for item in entries
        ):
            raise ValueError("entries must contain (cache key, artifact ref) pairs")
        self._prune_expired()
        for key, ref in entries:
            if key.repository_id is None:
                continue
            if ref.media_type != PARQUET_MEDIA_TYPE:
                raise ValueError("snapshot export cache only stores Parquet artifacts")
            owner_id = _owner_id(key)
            self._protection.clear_protection(owner_kind=_OWNER_KIND, owner_id=owner_id)
            expires_at_us = _to_epoch_us(self._now + self._ttl)
            self._connection.execute(
                """
                INSERT INTO snapshot_table_export_cache (
                    repository_id, row_layout_digest, parquet_writer_contract_version,
                    artifact_id, media_type, size_bytes, raw_sha256, expires_at_us
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, row_layout_digest, parquet_writer_contract_version)
                DO UPDATE SET artifact_id = excluded.artifact_id,
                    media_type = excluded.media_type,
                    size_bytes = excluded.size_bytes,
                    raw_sha256 = excluded.raw_sha256,
                    expires_at_us = excluded.expires_at_us
                """,
                (*_key_values(key), ref.artifact_id, ref.media_type, ref.size_bytes,
                 ref.raw_sha256.value, expires_at_us),
            )
            self._insert_protection(ref, owner_id, expires_at_us)

    def discard_many(self, keys: tuple[SnapshotTableArtifactCacheKey, ...]) -> None:
        self._require_writable()
        if type(keys) is not tuple or any(type(key) is not SnapshotTableArtifactCacheKey for key in keys):
            raise ValueError("keys must contain SnapshotTableArtifactCacheKey")
        for key in keys:
            if key.repository_id is not None:
                self._delete_key(key, _owner_id(key))

    def _prune_expired(self) -> None:
        if self._read_only:
            return
        rows = self._connection.execute(
            """
            SELECT repository_id, row_layout_digest, parquet_writer_contract_version
            FROM snapshot_table_export_cache
            WHERE expires_at_us <= ?
            ORDER BY expires_at_us
            LIMIT ?
            """,
            (_to_epoch_us(self._now), _PRUNE_LIMIT),
        ).fetchall()
        for repository_id, row_layout_digest, writer_version in rows:
            key = SnapshotTableArtifactCacheKey(
                row_layout_digest=DigestRef(row_layout_digest),
                repository_id=repository_id,
                parquet_writer_contract_version=writer_version,
            )
            self._delete_key(key, _owner_id(key))

    def _delete_key(self, key: SnapshotTableArtifactCacheKey, owner_id: str) -> None:
        if self._read_only:
            return
        self._connection.execute(
            """
            DELETE FROM snapshot_table_export_cache
            WHERE repository_id = ? AND row_layout_digest = ?
                AND parquet_writer_contract_version = ?
            """,
            _key_values(key),
        )
        self._protection.clear_protection(owner_kind=_OWNER_KIND, owner_id=owner_id)

    def _extend_protection(
        self,
        key: SnapshotTableArtifactCacheKey,
        ref: ArtifactRef,
        owner_id: str,
    ) -> None:
        expires_at_us = _to_epoch_us(self._now + self._ttl)
        if self._read_only:
            return
        self._connection.execute(
            """
            UPDATE snapshot_table_export_cache SET expires_at_us = ?
            WHERE repository_id = ? AND row_layout_digest = ?
                AND parquet_writer_contract_version = ?
            """,
            (expires_at_us, *_key_values(key)),
        )
        self._insert_protection(ref, owner_id, expires_at_us)

    def _insert_protection(
        self,
        ref: ArtifactRef,
        owner_id: str,
        expires_at_us: int,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO artifact_protection_intents (
                artifact_id, owner_kind, owner_id, intent, recorded_at_us, expires_at_us
            ) VALUES (?, ?, ?, 'ttl-cache', ?, ?)
            ON CONFLICT(artifact_id, owner_kind, owner_id) DO UPDATE SET
                intent = excluded.intent,
                recorded_at_us = excluded.recorded_at_us,
                expires_at_us = excluded.expires_at_us
            """,
            (ref.artifact_id, _OWNER_KIND, owner_id, _to_epoch_us(self._now), expires_at_us),
        )

    def _require_writable(self) -> None:
        if self._read_only:
            raise RuntimeError("snapshot export cache is read-only in this transaction")


def _key_values(key: SnapshotTableArtifactCacheKey) -> tuple[object, ...]:
    if key.repository_id is None:
        raise ValueError("snapshot export cache requires repository scope")
    return (
        key.repository_id,
        key.row_layout_digest.value,
        key.parquet_writer_contract_version,
    )


def _owner_id(key: SnapshotTableArtifactCacheKey) -> str:
    payload = "\0".join(
        str(item) for item in _key_values(key)
    ).encode("utf-8")
    return _OWNER_PREFIX + hashlib.sha256(payload).hexdigest()


def _to_epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be an aware UTC datetime")
    delta = value - _EPOCH
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
