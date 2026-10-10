"""SQLite connection profile shared by control DB adapters."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from gateway_backend.operations import StoreBusy

BUSY_TIMEOUT_MS = 5_000


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
        _enable_wal(connection)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    except sqlite3.OperationalError as exc:
        _raise_if_busy(exc)
        raise
    if busy_timeout != BUSY_TIMEOUT_MS:
        raise RuntimeError("SQLite busy timeout profile was not applied")


def _enable_wal(connection: sqlite3.Connection) -> None:
    deadline = time.monotonic() + BUSY_TIMEOUT_MS / 1_000
    while True:
        try:
            journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if journal_mode != "wal":
                raise RuntimeError("SQLite WAL mode was not enabled")
            return
        except sqlite3.OperationalError as exc:
            if not _is_busy_error(exc):
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _raise_if_busy(exc)
                raise
            time.sleep(min(0.005, remaining))


def _raise_if_busy(exc: sqlite3.OperationalError) -> None:
    if _is_busy_error(exc):
        raise StoreBusy("control DB is busy") from None


def _is_busy_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "busy" in message or "locked" in message
