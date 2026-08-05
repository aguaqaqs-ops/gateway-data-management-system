"""Transactional control-store lifecycle for service-state SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Self


class ControlDbError(RuntimeError):
    """Raised when the control database cannot be opened or migrated."""


class ControlDbNewerVersionError(ControlDbError):
    """Raised when on-disk user_version exceeds the supported version."""


@dataclass
class ControlStore:
    path: Path
    connection: sqlite3.Connection
    user_version: int

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        expected_version: int,
        busy_timeout_ms: int,
    ) -> Self:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=busy_timeout_ms / 1000.0)
        try:
            connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            connection.execute("PRAGMA foreign_keys = ON")
            cls._ensure_wal_mode(connection)
            user_version = cls._migrate(connection, expected_version=expected_version)
            cls._verify_synchronous_full(connection)
            cls._verify_foreign_keys(connection)
            return cls(path=path, connection=connection, user_version=user_version)
        except Exception:
            connection.close()
            raise

    @staticmethod
    def _ensure_wal_mode(connection: sqlite3.Connection) -> None:
        journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        if journal_mode is None or str(journal_mode[0]).upper() != "WAL":
            raise ControlDbError("control database WAL mode is unavailable")

    @staticmethod
    def _verify_synchronous_full(connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA synchronous = FULL")
        synchronous = connection.execute("PRAGMA synchronous").fetchone()
        if synchronous is None or int(synchronous[0]) != 2:
            raise ControlDbError("control database synchronous mode is invalid")

    @staticmethod
    def _verify_foreign_keys(connection: sqlite3.Connection) -> None:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
        if foreign_keys is None or int(foreign_keys[0]) != 1:
            raise ControlDbError("control database foreign keys are disabled")

    @staticmethod
    def _migrate(connection: sqlite3.Connection, *, expected_version: int) -> int:
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current > expected_version:
            raise ControlDbNewerVersionError(
                f"control database user_version {current} is newer than supported {expected_version}"
            )
        if current == expected_version:
            return current

        connection.execute("BEGIN IMMEDIATE")
        try:
            replay_current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if replay_current > expected_version:
                raise ControlDbNewerVersionError(
                    "control database user_version changed during migration"
                )
            while replay_current < expected_version:
                next_version = replay_current + 1
                ControlStore._apply_migration_step(connection, next_version)
                connection.execute(f"PRAGMA user_version = {next_version}")
                replay_current = next_version
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return expected_version

    @staticmethod
    def _apply_migration_step(connection: sqlite3.Connection, target_version: int) -> None:
        del connection
        if target_version == 1:
            return
        raise ControlDbError(f"unsupported control database migration target {target_version}")

    def close(self) -> None:
        self.connection.close()

    def is_open(self) -> bool:
        try:
            self.connection.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            return False
        return True
