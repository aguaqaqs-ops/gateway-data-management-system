"""SQLite connection profile and explicit transaction owner."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from gateway_backend.operations import StoreBusy

BUSY_TIMEOUT_MS = 5_000


def _utc_now() -> datetime:
    return datetime.now(UTC)


def connect_control_db(db_path: Path) -> sqlite3.Connection:
    """Open one configured SQLite connection for a caller-owned database path."""

    _validate_db_path(db_path)
    try:
        connection = sqlite3.connect(
            db_path,
            timeout=BUSY_TIMEOUT_MS / 1_000,
            isolation_level=None,
            check_same_thread=True,
        )
    except sqlite3.OperationalError as exc:
        _raise_if_busy(exc)
        raise
    connection.row_factory = sqlite3.Row
    try:
        _configure_connection(connection)
    except BaseException:
        connection.close()
        raise
    return connection


def initialize_control_db(
    db_path: Path,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> None:
    """Bootstrap the component schema using a short-lived configured connection."""

    from gateway_backend.infrastructure.control_db.migrations import bootstrap_control_schema

    connection = connect_control_db(db_path)
    try:
        bootstrap_control_schema(connection, now=now)
    finally:
        connection.close()


class ControlDbUnitOfWork:
    """Own one connection and one explicit transaction scope."""

    def __init__(self, db_path: Path, *, read_only: bool = False) -> None:
        if type(read_only) is not bool:
            raise ValueError("read_only must be a bool")
        _validate_db_path(db_path)
        self._db_path = db_path
        self._read_only = read_only
        self._connection: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the infrastructure connection to concrete same-transaction participants."""

        if self._connection is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._connection

    def __enter__(self) -> Self:
        if self._connection is not None:
            raise RuntimeError("control DB unit of work cannot be entered twice")
        connection = connect_control_db(self._db_path)
        try:
            connection.execute("BEGIN" if self._read_only else "BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            connection.close()
            _raise_if_busy(exc)
            raise
        self._connection = connection
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            connection.execute("ROLLBACK" if exc_type is not None else "COMMIT")
        except sqlite3.OperationalError as exc:
            _raise_if_busy(exc)
            raise
        finally:
            connection.close()


def _validate_db_path(db_path: object) -> None:
    if not isinstance(db_path, Path):
        raise ValueError("db_path must be a pathlib.Path")
    if not db_path.is_absolute():
        raise ValueError("db_path must be absolute")
    if not db_path.parent.is_dir():
        raise ValueError("db_path parent directory must already exist")


def _configure_connection(connection: sqlite3.Connection) -> None:
    try:
        connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if journal_mode != "wal":
            raise RuntimeError("SQLite WAL mode was not enabled")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    except sqlite3.OperationalError as exc:
        _raise_if_busy(exc)
        raise
    if busy_timeout != BUSY_TIMEOUT_MS:
        raise RuntimeError("SQLite busy timeout profile was not applied")


def _raise_if_busy(exc: sqlite3.OperationalError) -> None:
    message = str(exc).lower()
    if "busy" in message or "locked" in message:
        raise StoreBusy("control DB is busy") from None
