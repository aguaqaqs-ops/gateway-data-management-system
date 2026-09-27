"""SQLite connection profile and explicit transaction owner."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Self

from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.infrastructure.control_db.sqlite_protection import SQLiteArtifactProtectionStore
from gateway_backend.operations import OperationStore, StoreBusy

if TYPE_CHECKING:
    from gateway_backend.application.history.ports import HistoryComparePort
    from gateway_backend.infrastructure.control_db.sqlite_history_compare import (
        SQLiteHistoryCompareRepository,
    )
    from gateway_backend.domain.archive.ports import ArchiveRepository
    from gateway_backend.domain.baseline.ports import BaselineRepository
    from gateway_backend.domain.workspace.models import ResolvedScope
    from gateway_backend.domain.workspace.ports import WorkspaceRepository
    from gateway_backend.infrastructure.control_db.sqlite_review import SQLiteReviewRepository
    from gateway_backend.infrastructure.control_db.sqlite_submission import SQLiteSubmissionRepository

from gateway_backend.infrastructure.control_db.control_db_connect import (
    BUSY_TIMEOUT_MS,
    connect_control_db,
)


class ControlDbIntegrityError(RuntimeError):
    """Raised when SQLite integrity or foreign-key checks fail at startup."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def assert_control_db_integrity(connection: sqlite3.Connection) -> None:
    """Run bounded PRAGMA integrity checks without leaking row payloads."""

    try:
        integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.OperationalError as exc:
        _raise_if_busy(exc)
        raise ControlDbIntegrityError("control DB integrity check failed") from None
    if len(integrity_rows) != 1 or integrity_rows[0][0] != "ok":
        raise ControlDbIntegrityError("control DB integrity check failed")
    if foreign_key_rows:
        raise ControlDbIntegrityError("control DB foreign key check failed")


def initialize_and_verify_control_db(
    db_path: Path,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> None:
    """Initialize schema, then fail closed on integrity errors."""

    initialize_control_db(db_path, now=now)
    connection = connect_control_db(db_path)
    try:
        assert_control_db_integrity(connection)
    finally:
        connection.close()


def initialize_control_db(
    db_path: Path,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> None:
    """Bootstrap the component schema using a short-lived configured connection."""

    from gateway_backend.infrastructure.control_db.migrations import (
        bootstrap_control_schema,
        bootstrap_workspace_schema,
    )

    connection = connect_control_db(db_path)
    try:
        bootstrap_control_schema(connection, now=now)
        bootstrap_workspace_schema(connection, now=now)
    finally:
        connection.close()


class ControlDbUnitOfWork:
    """Own one connection and one explicit transaction scope."""

    def __init__(
        self,
        db_path: Path,
        *,
        read_only: bool = False,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if type(read_only) is not bool:
            raise ValueError("read_only must be a bool")
        _validate_db_path(db_path)
        self._db_path = db_path
        self._read_only = read_only
        self._now = now
        self._connection: sqlite3.Connection | None = None
        self._transaction_now: datetime | None = None
        self._operations: OperationStore | None = None
        self._workspace: WorkspaceRepository | None = None
        self._protection: SQLiteArtifactProtectionStore | None = None
        self._submission: SQLiteSubmissionRepository | None = None
        self._review: SQLiteReviewRepository | None = None
        self._baseline: BaselineRepository | None = None
        self._archive: ArchiveRepository | None = None
        self._history_compare: SQLiteHistoryCompareRepository | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the infrastructure connection to concrete same-transaction participants."""

        if self._connection is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._connection

    @property
    def operations(self) -> OperationStore:
        """Return the operation participant bound to this transaction."""

        if self._operations is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._operations

    @property
    def workspace(self) -> WorkspaceRepository:
        """Return the workspace participant bound to this transaction."""

        if self._workspace is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._workspace

    @property
    def submission(self) -> SQLiteSubmissionRepository:
        """Return the submission participant bound to this transaction."""

        if self._submission is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._submission

    @property
    def protection(self) -> SQLiteArtifactProtectionStore:
        """Return the artifact-protection participant bound to this transaction."""

        if self._protection is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._protection

    @property
    def review(self) -> SQLiteReviewRepository:
        """Return the review participant bound to this transaction."""

        if self._review is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._review

    @property
    def baseline(self) -> BaselineRepository:
        """Return the baseline participant bound to this transaction."""

        if self._baseline is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._baseline

    @property
    def archive(self) -> ArchiveRepository:
        """Return the archive participant bound to this transaction."""

        if self._archive is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._archive

    @property
    def history_compare(self) -> HistoryComparePort:
        """Return the history compare participant bound to this transaction."""

        if self._history_compare is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._history_compare

    def set_artifact_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
    ) -> bool:
        """Record protection intents in the current transaction."""

        return self.protection.set_protection(
            refs,
            owner_kind=owner_kind,
            owner_id=owner_id,
            intent=intent,
            recorded_at=self.transaction_now,
        )

    def clear_artifact_protection(self, *, owner_kind: str, owner_id: str) -> int:
        """Delete protection intents owned by one (kind, id) pair."""

        return self.protection.clear_protection(owner_kind=owner_kind, owner_id=owner_id)

    def list_artifact_protection_for_owner(
        self,
        *,
        owner_kind: str,
        owner_id: str,
    ) -> frozenset[str]:
        """Return artifact ids protected by one owner within the current transaction."""

        rows = self.connection.execute(
            """
            SELECT artifact_id FROM artifact_protection_intents
            WHERE owner_kind = ? AND owner_id = ?
            """,
            (owner_kind, owner_id),
        ).fetchall()
        return frozenset(row[0] for row in rows)

    @property
    def transaction_now(self) -> datetime:
        """Return the single UTC clock sample captured for this transaction."""

        if self._transaction_now is None:
            raise RuntimeError("control DB unit of work is not active")
        return self._transaction_now

    def resolve_provisioned_scope(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> ResolvedScope:
        """Return transaction-fresh provisioned scope for one device/project key."""

        from gateway_backend.infrastructure.control_db.sqlite_provisioned_scope import (
            resolve_provisioned_scope_from_connection,
        )

        return resolve_provisioned_scope_from_connection(
            self.connection,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
        )

    def is_submission_closed(self, submission_id: str) -> bool:
        """Return whether one submission appears in any ArchiveResult disposition."""

        return self.archive.is_submission_closed(submission_id)

    def __enter__(self) -> Self:
        if self._connection is not None:
            raise RuntimeError("control DB unit of work cannot be entered twice")
        connection = connect_control_db(self._db_path)
        try:
            connection.execute("BEGIN" if self._read_only else "BEGIN IMMEDIATE")
            transaction_now = self._now()
            _validate_utc_datetime(transaction_now, "transaction clock")
            from gateway_backend.infrastructure.control_db.sqlite_archive import (
                SQLiteArchiveRepository,
            )
            from gateway_backend.infrastructure.control_db.sqlite_history_compare import (
                SQLiteHistoryCompareRepository,
            )
            from gateway_backend.infrastructure.control_db.sqlite_baseline import (
                SQLiteBaselineRepository,
            )
            from gateway_backend.infrastructure.control_db.sqlite_operations import (
                SQLiteOperationStore,
            )
            from gateway_backend.infrastructure.control_db.sqlite_review import (
                SQLiteReviewRepository,
            )
            from gateway_backend.infrastructure.control_db.sqlite_submission import (
                SQLiteSubmissionRepository,
            )
            from gateway_backend.infrastructure.control_db.sqlite_workspace import (
                SQLiteWorkspaceRepository,
            )

            self._transaction_now = transaction_now
            self._operations = SQLiteOperationStore(
                connection,
                transaction_now=transaction_now,
                read_only=self._read_only,
            )
            self._workspace = SQLiteWorkspaceRepository(
                connection,
                transaction_now=transaction_now,
                read_only=self._read_only,
            )
            self._protection = SQLiteArtifactProtectionStore(
                connection,
                read_only=self._read_only,
            )
            self._submission = SQLiteSubmissionRepository(
                connection,
                transaction_now=transaction_now,
                read_only=self._read_only,
            )
            self._review = SQLiteReviewRepository(
                connection,
                transaction_now=transaction_now,
                read_only=self._read_only,
            )
            self._baseline = SQLiteBaselineRepository(
                connection,
                read_only=self._read_only,
            )
            self._archive = SQLiteArchiveRepository(
                connection,
                transaction_now=transaction_now,
                read_only=self._read_only,
            )
            self._history_compare = SQLiteHistoryCompareRepository(
                connection,
                read_only=self._read_only,
            )
        except sqlite3.OperationalError as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()
            _raise_if_busy(exc)
            raise
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()
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
        rollback_only = bool(getattr(self._operations, "_rollback_only", False))
        self._connection = None
        self._operations = None
        self._workspace = None
        self._protection = None
        self._submission = None
        self._review = None
        self._baseline = None
        self._archive = None
        self._history_compare = None
        self._transaction_now = None
        if connection is None:
            return
        try:
            connection.execute("ROLLBACK" if exc_type is not None or rollback_only else "COMMIT")
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


def _validate_utc_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an aware UTC datetime")
