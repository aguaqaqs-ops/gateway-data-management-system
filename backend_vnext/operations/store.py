from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
import threading
from typing import Protocol

from ..core.digests import canonical_json_bytes
from ..core.results import ResultRecord
from .models import OperationRecord
from .versions import OPERATION_STORE_SCHEMA_VERSION


class OperationStore(Protocol):
    def create(self, record: OperationRecord) -> OperationRecord: ...

    def get(self, operation_id: str) -> OperationRecord | None: ...

    def save(self, record: OperationRecord, *, expected_version: int | None = None) -> OperationRecord: ...

    def delete(self, operation_id: str) -> None: ...


@dataclass
class InMemoryOperationStore:
    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, OperationRecord] = {}

    def create(self, record: OperationRecord) -> OperationRecord:
        with self._lock:
            if record.operation_id in self._records:
                raise ValueError("operation already exists")
            self._records[record.operation_id] = record
            return record

    def get(self, operation_id: str) -> OperationRecord | None:
        with self._lock:
            return self._records.get(operation_id)

    def save(self, record: OperationRecord, *, expected_version: int | None = None) -> OperationRecord:
        with self._lock:
            current = self._records.get(record.operation_id)
            if current is None:
                raise KeyError("operation not found")
            if expected_version is not None and current.version != expected_version:
                raise ValueError("operation version mismatch")
            self._records[record.operation_id] = record
            return record

    def delete(self, operation_id: str) -> None:
        with self._lock:
            self._records.pop(operation_id, None)


@dataclass
class SqliteOperationStore:
    sqlite_path: Path
    busy_timeout_ms: int = 5000

    def __post_init__(self) -> None:
        self.sqlite_path = Path(self.sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def schema_version(self) -> str:
        return OPERATION_STORE_SCHEMA_VERSION

    def create(self, record: OperationRecord) -> OperationRecord:
        payload = json.dumps(record.to_payload(), ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO operation_record (
                        operation_id,
                        version,
                        record_json,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record.operation_id,
                        record.version,
                        payload,
                        record.created_at.astimezone().isoformat(),
                        record.updated_at.astimezone().isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("operation already exists") from exc
        return record

    def get(self, operation_id: str) -> OperationRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM operation_record WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, Mapping):
            raise TypeError("operation record payload must be a mapping")
        return OperationRecord.from_payload(payload)

    def save(self, record: OperationRecord, *, expected_version: int | None = None) -> OperationRecord:
        payload = json.dumps(record.to_payload(), ensure_ascii=False, sort_keys=True)
        with self._connect() as connection:
            if expected_version is None:
                expected_version = record.version - 1
            updated = connection.execute(
                """
                UPDATE operation_record
                SET version = ?, record_json = ?, updated_at = ?
                WHERE operation_id = ? AND version = ?
                """,
                (
                    record.version,
                    payload,
                    record.updated_at.astimezone().isoformat(),
                    record.operation_id,
                    expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("operation version mismatch")
        return record

    def delete(self, operation_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM operation_record WHERE operation_id = ?",
                (operation_id,),
            )

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operation_record (
                    operation_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
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
