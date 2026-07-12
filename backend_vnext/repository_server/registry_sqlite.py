from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import time

from ..core.digests import canonical_json_bytes
from .registry import (
    DigestRef,
    RegistryEntry,
    RegistryEntryQuery,
    RegistryEntrySpec,
    build_registry_entry_key,
)


@dataclass(frozen=True, slots=True)
class SQLiteRegistrySettings:
    repository_id: str
    sqlite_path: Path
    journal_mode: str
    busy_timeout_ms: int
    user_version: int


class SQLiteRepositoryRegistry:
    def __init__(
        self,
        *,
        sqlite_path: Path,
        repository_id: str,
        busy_timeout_ms: int = 5000,
    ) -> None:
        self.repository_id = _require_repository_id(repository_id)
        self.sqlite_path = Path(sqlite_path)
        self.busy_timeout_ms = _require_positive_int(busy_timeout_ms, "busy_timeout_ms")
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get_entry(self, entry_key: DigestRef | str) -> RegistryEntry | None:
        normalized_entry_key = _require_entry_key(entry_key)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM registry_entry
                WHERE repository_id = ? AND entry_key = ?
                """,
                (self.repository_id, normalized_entry_key),
            ).fetchone()
        if row is None:
            return None
        return _entry_from_row(row)

    def list_entries(
        self,
        query: RegistryEntryQuery | None = None,
    ) -> tuple[RegistryEntry, ...]:
        query = query or RegistryEntryQuery()
        if not isinstance(query, RegistryEntryQuery):
            raise TypeError("query must be a RegistryEntryQuery or None")

        sql = "SELECT * FROM registry_entry WHERE repository_id = ?"
        params: list[object] = [self.repository_id]
        if query.entry_key is not None:
            sql += " AND entry_key = ?"
            params.append(query.entry_key.to_payload())
        if query.entry_kind is not None:
            sql += " AND entry_kind = ?"
            params.append(query.entry_kind)
        if query.namespace is not None:
            sql += " AND namespace = ?"
            params.append(query.namespace)
        if query.logical_ref is not None:
            sql += " AND logical_ref = ?"
            params.append(query.logical_ref)
        if query.owner is not None:
            sql += " AND owner = ?"
            params.append(query.owner)
        if query.tag is not None:
            sql += " AND tag = ?"
            params.append(query.tag)
        if query.operation_id is not None:
            sql += " AND operation_id = ?"
            params.append(query.operation_id)
        if query.status is not None:
            sql += " AND status = ?"
            params.append(query.status)
        if query.content_digest is not None:
            sql += " AND content_digest = ?"
            params.append(query.content_digest.to_payload())
        if query.manifest_digest is not None:
            sql += " AND manifest_digest = ?"
            params.append(query.manifest_digest.to_payload())
        if query.created_at_ms_min is not None:
            sql += " AND created_at_ms >= ?"
            params.append(query.created_at_ms_min)
        if query.created_at_ms_max is not None:
            sql += " AND created_at_ms <= ?"
            params.append(query.created_at_ms_max)
        if query.updated_at_ms_min is not None:
            sql += " AND updated_at_ms >= ?"
            params.append(query.updated_at_ms_min)
        if query.updated_at_ms_max is not None:
            sql += " AND updated_at_ms <= ?"
            params.append(query.updated_at_ms_max)
        sql += " ORDER BY created_at_ms, entry_id"
        if query.limit is not None:
            sql += " LIMIT ?"
            params.append(query.limit)
        elif query.offset:
            sql += " LIMIT -1"
        if query.offset:
            sql += " OFFSET ?"
            params.append(query.offset)
        with self._connect() as connection:
            rows = connection.execute(sql, tuple(params)).fetchall()
        return tuple(_entry_from_row(row) for row in rows)

    def upsert_entry(
        self,
        spec: RegistryEntrySpec,
        *,
        now_ms: int | None = None,
    ) -> RegistryEntry:
        if not isinstance(spec, RegistryEntrySpec):
            raise TypeError("spec must be a RegistryEntrySpec")
        if spec.entry_key is not None and spec.identity is not None:
            derived_entry_key = build_registry_entry_key(
                self.repository_id,
                spec.entry_kind,
                spec.identity,
            )
            if spec.entry_key != derived_entry_key:
                raise ValueError("entry_key does not match the derived identity key")
        entry_key = spec.resolved_entry_key(self.repository_id)
        timestamp_ms = _current_time_ms() if now_ms is None else _require_positive_int(now_ms, "now_ms")
        payload = {
            "repository_id": self.repository_id,
            "entry_key": entry_key.to_payload(),
            "entry_kind": spec.entry_kind,
            "namespace": spec.namespace,
            "logical_ref": spec.logical_ref,
            "owner": spec.owner,
            "tag": spec.tag,
            "operation_id": spec.operation_id,
            "status": spec.status,
            "content_digest": (
                spec.content_digest.to_payload() if spec.content_digest is not None else None
            ),
            "manifest_digest": (
                spec.manifest_digest.to_payload() if spec.manifest_digest is not None else None
            ),
            "created_at_ms": timestamp_ms,
            "updated_at_ms": timestamp_ms,
            "metadata_json": canonical_json_bytes(spec.metadata).decode("utf-8"),
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO registry_entry (
                    repository_id,
                    entry_key,
                    entry_kind,
                    namespace,
                    logical_ref,
                    owner,
                    tag,
                    operation_id,
                    status,
                    content_digest,
                    manifest_digest,
                    created_at_ms,
                    updated_at_ms,
                    metadata_json
                ) VALUES (
                    :repository_id,
                    :entry_key,
                    :entry_kind,
                    :namespace,
                    :logical_ref,
                    :owner,
                    :tag,
                    :operation_id,
                    :status,
                    :content_digest,
                    :manifest_digest,
                    :created_at_ms,
                    :updated_at_ms,
                    :metadata_json
                )
                ON CONFLICT(repository_id, entry_key) DO UPDATE SET
                    entry_kind = excluded.entry_kind,
                    namespace = excluded.namespace,
                    logical_ref = excluded.logical_ref,
                    owner = excluded.owner,
                    tag = excluded.tag,
                    operation_id = excluded.operation_id,
                    status = excluded.status,
                    content_digest = excluded.content_digest,
                    manifest_digest = excluded.manifest_digest,
                    updated_at_ms = excluded.updated_at_ms,
                    metadata_json = excluded.metadata_json
                """,
                payload,
            )
            row = connection.execute(
                """
                SELECT * FROM registry_entry
                WHERE repository_id = ? AND entry_key = ?
                """,
                (self.repository_id, entry_key.to_payload()),
            ).fetchone()
        if row is None:
            raise KeyError("registry entry was not inserted")
        return _entry_from_row(row)

    def delete_entry(self, entry_key: DigestRef | str) -> None:
        normalized_entry_key = _require_entry_key(entry_key)
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM registry_entry
                WHERE repository_id = ? AND entry_key = ?
                """,
                (self.repository_id, normalized_entry_key),
            )

    def sqlite_settings(self) -> SQLiteRegistrySettings:
        with self._connect() as connection:
            journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
            busy_timeout_ms = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        return SQLiteRegistrySettings(
            repository_id=self.repository_id,
            sqlite_path=self.sqlite_path,
            journal_mode=journal_mode,
            busy_timeout_ms=busy_timeout_ms,
            user_version=user_version,
        )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS registry_entry (
                    entry_id INTEGER PRIMARY KEY,
                    repository_id TEXT NOT NULL,
                    entry_key TEXT NOT NULL,
                    entry_kind TEXT NOT NULL,
                    namespace TEXT NOT NULL DEFAULT '',
                    logical_ref TEXT NOT NULL DEFAULT '',
                    owner TEXT NOT NULL DEFAULT '',
                    tag TEXT NOT NULL DEFAULT '',
                    operation_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    content_digest TEXT,
                    manifest_digest TEXT,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    CHECK (length(trim(repository_id)) > 0),
                    CHECK (length(trim(entry_key)) > 0),
                    CHECK (length(trim(entry_kind)) > 0),
                    CHECK (length(trim(status)) > 0)
                )
                """,
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS registry_entry_uq_key
                ON registry_entry(repository_id, entry_key)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS registry_entry_idx_kind_namespace_created
                ON registry_entry(repository_id, entry_kind, namespace, created_at_ms)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS registry_entry_idx_logical_ref
                ON registry_entry(repository_id, logical_ref)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS registry_entry_idx_owner
                ON registry_entry(repository_id, owner)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS registry_entry_idx_tag
                ON registry_entry(repository_id, tag)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS registry_entry_idx_operation
                ON registry_entry(repository_id, operation_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS registry_entry_idx_status
                ON registry_entry(repository_id, status)
                """
            )
            connection.execute("PRAGMA user_version = 1")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.sqlite_path,
            timeout=self.busy_timeout_ms / 1000,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection


def _entry_from_row(row: sqlite3.Row) -> RegistryEntry:
    return RegistryEntry(
        entry_id=int(row["entry_id"]),
        repository_id=str(row["repository_id"]),
        entry_key=str(row["entry_key"]),
        entry_kind=str(row["entry_kind"]),
        namespace=str(row["namespace"] or ""),
        logical_ref=str(row["logical_ref"] or ""),
        owner=str(row["owner"] or ""),
        tag=str(row["tag"] or ""),
        operation_id=str(row["operation_id"] or ""),
        status=str(row["status"]),
        content_digest=row["content_digest"],
        manifest_digest=row["manifest_digest"],
        created_at_ms=int(row["created_at_ms"]),
        updated_at_ms=int(row["updated_at_ms"]),
        metadata=_json_to_metadata(row["metadata_json"]),
    )


def _json_to_metadata(raw_json: str) -> dict[str, object]:
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise TypeError("registry metadata must decode to an object")
    return payload


def _require_repository_id(repository_id: object) -> str:
    if not isinstance(repository_id, str):
        raise TypeError("repository_id must be a string")
    normalized = repository_id.strip()
    if not normalized:
        raise ValueError("repository_id must be a non-empty string")
    return normalized


def _require_entry_key(entry_key: DigestRef | str) -> str:
    if isinstance(entry_key, DigestRef):
        return entry_key.to_payload()
    if not isinstance(entry_key, str):
        raise TypeError("entry_key must be a DigestRef or string")
    normalized = entry_key.strip()
    if not normalized:
        raise ValueError("entry_key must be a non-empty string")
    return normalized


def _require_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _current_time_ms() -> int:
    return time.time_ns() // 1_000_000
