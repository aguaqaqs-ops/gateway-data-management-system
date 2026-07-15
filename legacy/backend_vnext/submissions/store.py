from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import threading
from typing import Protocol

from .models import SubmissionRecord
from .versions import (
    SUBMISSION_IDENTITY_STORE_SCHEMA_VERSION,
    SUBMISSION_STORE_SCHEMA_VERSION,
)


class SubmissionIdentityStore(Protocol):
    def next_identity(self) -> str: ...


@dataclass
class InMemorySubmissionIdentityStore:
    start_value: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.start_value, int) or isinstance(self.start_value, bool) or self.start_value < 1:
            raise ValueError("start_value must be a positive integer")
        self._lock = threading.Lock()
        self._next_value = self.start_value

    def next_identity(self) -> str:
        with self._lock:
            value = self._next_value
            self._next_value += 1
        return f"submission-{value:03d}"


@dataclass
class SqliteSubmissionIdentityStore:
    sqlite_path: Path
    busy_timeout_ms: int = 5000

    def __post_init__(self) -> None:
        self.sqlite_path = Path(self.sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def schema_version(self) -> str:
        return SUBMISSION_IDENTITY_STORE_SCHEMA_VERSION

    def next_identity(self) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT next_value FROM identity_sequences WHERE name = ?",
                ("submissions",),
            ).fetchone()
            if row is None:
                value = 1
                connection.execute(
                    """
                    INSERT INTO identity_sequences(name, next_value)
                    VALUES (?, ?)
                    """,
                    ("submissions", 2),
                )
            else:
                value = int(row["next_value"])
                connection.execute(
                    """
                    UPDATE identity_sequences
                    SET next_value = ?
                    WHERE name = ?
                    """,
                    (value + 1, "submissions"),
                )
        return f"submission-{value:03d}"

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS identity_sequences (
                    name TEXT PRIMARY KEY,
                    next_value INTEGER NOT NULL
                )
                """
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


class SubmissionStore(Protocol):
    def create(self, record: SubmissionRecord) -> SubmissionRecord: ...

    def get(self, submission_id: str) -> SubmissionRecord | None: ...

    def save(self, record: SubmissionRecord, *, expected_version: int | None = None) -> SubmissionRecord: ...

    def delete(self, submission_id: str) -> None: ...

    def list_by_batch(self, batch_id: str) -> tuple[SubmissionRecord, ...]: ...

    def list_by_workspace(self, workspace_id: str) -> tuple[SubmissionRecord, ...]: ...


@dataclass
class InMemorySubmissionStore:
    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, SubmissionRecord] = {}

    def create(self, record: SubmissionRecord) -> SubmissionRecord:
        with self._lock:
            if record.submission_id in self._records:
                raise ValueError("submission already exists")
            self._records[record.submission_id] = record
            return record

    def get(self, submission_id: str) -> SubmissionRecord | None:
        with self._lock:
            return self._records.get(submission_id)

    def save(self, record: SubmissionRecord, *, expected_version: int | None = None) -> SubmissionRecord:
        with self._lock:
            current = self._records.get(record.submission_id)
            if current is None:
                raise KeyError("submission not found")
            if expected_version is not None and current.version != expected_version:
                raise ValueError("submission version mismatch")
            self._records[record.submission_id] = record
            return record

    def delete(self, submission_id: str) -> None:
        with self._lock:
            self._records.pop(submission_id, None)

    def list_by_batch(self, batch_id: str) -> tuple[SubmissionRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in self._records.values()
                if record.batch_id == batch_id
            )

    def list_by_workspace(self, workspace_id: str) -> tuple[SubmissionRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in self._records.values()
                if record.workspace_id == workspace_id
            )


@dataclass
class SqliteSubmissionStore:
    sqlite_path: Path
    busy_timeout_ms: int = 5000

    def __post_init__(self) -> None:
        self.sqlite_path = Path(self.sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def schema_version(self) -> str:
        return SUBMISSION_STORE_SCHEMA_VERSION

    def create(self, record: SubmissionRecord) -> SubmissionRecord:
        payload = json.dumps(record.to_payload(), ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO submission_record (
                        submission_id,
                        workspace_id,
                        batch_id,
                        version,
                        record_json,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.submission_id,
                        record.workspace_id,
                        record.batch_id,
                        record.version,
                        payload,
                        record.created_at.astimezone().isoformat(),
                        record.updated_at.astimezone().isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("submission already exists") from exc
        return record

    def get(self, submission_id: str) -> SubmissionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM submission_record WHERE submission_id = ?",
                (submission_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, dict):
            raise TypeError("submission record payload must be a mapping")
        return SubmissionRecord.from_payload(payload)

    def save(self, record: SubmissionRecord, *, expected_version: int | None = None) -> SubmissionRecord:
        payload = json.dumps(record.to_payload(), ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            if expected_version is None:
                expected_version = record.version - 1
            updated = connection.execute(
                """
                UPDATE submission_record
                SET workspace_id = ?, batch_id = ?, version = ?, record_json = ?, updated_at = ?
                WHERE submission_id = ? AND version = ?
                """,
                (
                    record.workspace_id,
                    record.batch_id,
                    record.version,
                    payload,
                    record.updated_at.astimezone().isoformat(),
                    record.submission_id,
                    expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("submission version mismatch")
        return record

    def delete(self, submission_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM submission_record WHERE submission_id = ?",
                (submission_id,),
            )

    def list_by_batch(self, batch_id: str) -> tuple[SubmissionRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json
                FROM submission_record
                WHERE batch_id = ?
                ORDER BY created_at, submission_id
                """,
                (batch_id,),
            ).fetchall()
        return tuple(SubmissionRecord.from_payload(json.loads(row[0])) for row in rows)

    def list_by_workspace(self, workspace_id: str) -> tuple[SubmissionRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT record_json
                FROM submission_record
                WHERE workspace_id = ?
                ORDER BY created_at, submission_id
                """,
                (workspace_id,),
            ).fetchall()
        return tuple(SubmissionRecord.from_payload(json.loads(row[0])) for row in rows)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS submission_record (
                    submission_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    batch_id TEXT,
                    version INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_submission_record_batch_id ON submission_record(batch_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_submission_record_workspace_id ON submission_record(workspace_id)"
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
