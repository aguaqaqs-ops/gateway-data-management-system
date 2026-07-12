from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
import threading
from typing import Protocol

from .models import WorkspaceRecord
from .versions import WORKSPACE_STORE_SCHEMA_VERSION


class WorkspaceStore(Protocol):
    def create(self, record: WorkspaceRecord) -> WorkspaceRecord: ...

    def get(self, workspace_id: str) -> WorkspaceRecord | None: ...

    def save(self, record: WorkspaceRecord, *, expected_version: int | None = None) -> WorkspaceRecord: ...

    def delete(self, workspace_id: str) -> None: ...

    def list_by_batch(self, batch_id: str) -> tuple[WorkspaceRecord, ...]: ...


@dataclass
class InMemoryWorkspaceStore:
    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, WorkspaceRecord] = {}

    def create(self, record: WorkspaceRecord) -> WorkspaceRecord:
        with self._lock:
            if record.workspace_id in self._records:
                raise ValueError("workspace already exists")
            self._records[record.workspace_id] = record
            return record

    def get(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._lock:
            return self._records.get(workspace_id)

    def save(self, record: WorkspaceRecord, *, expected_version: int | None = None) -> WorkspaceRecord:
        with self._lock:
            current = self._records.get(record.workspace_id)
            if current is None:
                raise KeyError("workspace not found")
            if expected_version is not None and current.version != expected_version:
                raise ValueError("workspace version mismatch")
            self._records[record.workspace_id] = record
            return record

    def delete(self, workspace_id: str) -> None:
        with self._lock:
            self._records.pop(workspace_id, None)

    def list_by_batch(self, batch_id: str) -> tuple[WorkspaceRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in self._records.values()
                if record.batch_id == batch_id
            )


@dataclass
class SqliteWorkspaceStore:
    sqlite_path: Path
    busy_timeout_ms: int = 5000

    def __post_init__(self) -> None:
        self.sqlite_path = Path(self.sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def schema_version(self) -> str:
        return WORKSPACE_STORE_SCHEMA_VERSION

    def create(self, record: WorkspaceRecord) -> WorkspaceRecord:
        payload = json.dumps(record.to_payload(), ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO workspace_record (
                        workspace_id,
                        batch_id,
                        version,
                        record_json,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.workspace_id,
                        record.batch_id,
                        record.version,
                        payload,
                        record.created_at.astimezone().isoformat(),
                        record.updated_at.astimezone().isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("workspace already exists") from exc
        return record

    def get(self, workspace_id: str) -> WorkspaceRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM workspace_record WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, Mapping):
            raise TypeError("workspace record payload must be a mapping")
        return WorkspaceRecord.from_payload(payload)

    def save(self, record: WorkspaceRecord, *, expected_version: int | None = None) -> WorkspaceRecord:
        payload = json.dumps(record.to_payload(), ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            if expected_version is None:
                expected_version = record.version - 1
            updated = connection.execute(
                """
                UPDATE workspace_record
                SET batch_id = ?, version = ?, record_json = ?, updated_at = ?
                WHERE workspace_id = ? AND version = ?
                """,
                (
                    record.batch_id,
                    record.version,
                    payload,
                    record.updated_at.astimezone().isoformat(),
                    record.workspace_id,
                    expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("workspace version mismatch")
        return record

    def delete(self, workspace_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM workspace_record WHERE workspace_id = ?",
                (workspace_id,),
            )

    def list_by_batch(self, batch_id: str) -> tuple[WorkspaceRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json
                FROM workspace_record
                WHERE batch_id = ?
                ORDER BY created_at, workspace_id
                """,
                (batch_id,),
            ).fetchall()
        return tuple(WorkspaceRecord.from_payload(json.loads(row[0])) for row in rows)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workspace_record (
                    workspace_id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    version INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_workspace_record_batch_id ON workspace_record(batch_id)"
            )
            connection.execute("PRAGMA user_version = 1")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.sqlite_path,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection
