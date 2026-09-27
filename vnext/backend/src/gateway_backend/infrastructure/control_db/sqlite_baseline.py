"""SQLite adapter for Baseline Head authority."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from gateway_backend.domain.baseline.errors import BaselineHeadVersionConflict
from gateway_backend.domain.baseline.models import (
    BaselineHeadRecord,
    BaselineNode,
    BaselineNodeKind,
)
from gateway_backend.domain.baseline.ports import BaselineRepository
from gateway_backend.domain.workspace.errors import ScopeResolutionError
from gateway_backend.domain.workspace.models import BaselineHead

_BASELINE_NODE_KINDS = ("'INITIAL'", "'ARCHIVED_SUBMISSION'")


class SQLiteBaselineRepository(BaselineRepository):
    """Same-transaction Baseline persistence participant."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        read_only: bool = False,
    ) -> None:
        self._connection = connection
        self._read_only = read_only

    def get_head_record(self, repository_id: str) -> BaselineHeadRecord | None:
        row = self._connection.execute(
            """
            SELECT repository_id, node_id, optimistic_version
            FROM baseline_head_records
            WHERE repository_id = ?
            """,
            (repository_id,),
        ).fetchone()
        if row is None:
            return None
        return BaselineHeadRecord(
            repository_id=row["repository_id"],
            node_id=row["node_id"],
            optimistic_version=row["optimistic_version"],
        )

    def get_node(self, node_id: str) -> BaselineNode | None:
        row = self._connection.execute(
            """
            SELECT node_id, repository_id, gateway_device_external_key, business_project_id,
                   commit_id, kind, parent_node_id, source_submission_id, created_at_us
            FROM baseline_node_records
            WHERE node_id = ?
            """,
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        return node_from_row(row)

    def get_initial_node(self, repository_id: str) -> BaselineNode | None:
        row = self._connection.execute(
            """
            SELECT node_id, repository_id, gateway_device_external_key, business_project_id,
                   commit_id, kind, parent_node_id, source_submission_id, created_at_us
            FROM baseline_node_records
            WHERE repository_id = ? AND kind = 'INITIAL'
            """,
            (repository_id,),
        ).fetchone()
        if row is None:
            return None
        return node_from_row(row)

    def save_initial_node_and_head(
        self,
        node: BaselineNode,
        head: BaselineHeadRecord,
    ) -> None:
        if self._read_only:
            raise RuntimeError("baseline repository is read-only")
        if node.kind is not BaselineNodeKind.INITIAL:
            raise ValueError("save_initial_node_and_head requires an INITIAL node")
        if head.optimistic_version != 0:
            raise ValueError("initial head must start at optimistic_version 0")
        if node.repository_id != head.repository_id or node.node_id != head.node_id:
            raise ValueError("initial node and head must reference the same repository and node")
        created_at_us = _datetime_to_epoch_us(node.created_at)
        self._connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)
            """,
            (
                node.node_id,
                node.repository_id,
                node.gateway_device_external_key,
                node.business_project_id,
                node.commit_id,
                node.kind.value,
                created_at_us,
            ),
        )
        self._connection.execute(
            """
            INSERT INTO baseline_head_records (repository_id, node_id, optimistic_version)
            VALUES (?, ?, ?)
            """,
            (head.repository_id, head.node_id, head.optimistic_version),
        )

    def save_archived_node_and_cas_head(
        self,
        node: BaselineNode,
        *,
        expected_head: BaselineHeadRecord,
        new_head_node_id: str,
        new_head_version: int,
    ) -> BaselineHeadRecord:
        if self._read_only:
            raise RuntimeError("baseline repository is read-only")
        if node.kind is not BaselineNodeKind.ARCHIVED_SUBMISSION:
            raise ValueError("save_archived_node_and_cas_head requires ARCHIVED_SUBMISSION")
        if node.repository_id != expected_head.repository_id:
            raise ValueError("archived node repository must match expected head repository")
        if new_head_node_id != node.node_id:
            raise ValueError("new head node id must match archived node id")
        if new_head_version != expected_head.optimistic_version + 1:
            raise ValueError("new head version must advance expected head by one")
        created_at_us = _datetime_to_epoch_us(node.created_at)
        self._connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.node_id,
                node.repository_id,
                node.gateway_device_external_key,
                node.business_project_id,
                node.commit_id,
                node.kind.value,
                node.parent_node_id,
                node.source_submission_id,
                created_at_us,
            ),
        )
        cursor = self._connection.execute(
            """
            UPDATE baseline_head_records
            SET node_id = ?, optimistic_version = ?
            WHERE repository_id = ? AND optimistic_version = ?
            """,
            (
                new_head_node_id,
                new_head_version,
                expected_head.repository_id,
                expected_head.optimistic_version,
            ),
        )
        if cursor.rowcount != 1:
            raise BaselineHeadVersionConflict("baseline head version conflict during archive")
        return BaselineHeadRecord(
            repository_id=expected_head.repository_id,
            node_id=new_head_node_id,
            optimistic_version=new_head_version,
        )


class SQLiteBaselineHeadRead:
    """Read BaselineHead adapter DTO from baseline authority tables."""

    def __init__(self, db_path: object) -> None:
        from pathlib import Path

        if not isinstance(db_path, Path):
            raise ValueError("db_path must be a pathlib.Path")
        self._db_path = db_path

    def get_current_head(self, repository_id: str) -> BaselineHead:
        from gateway_backend.infrastructure.control_db.control_db_connect import connect_control_db
        from gateway_backend.infrastructure.control_db.sqlite_operations import _raise_if_busy
        from gateway_backend.operations.store import StoreBusy

        connection = connect_control_db(self._db_path)
        try:
            try:
                connection.execute("BEGIN")
            except sqlite3.OperationalError as exc:
                _raise_if_busy(exc)
                raise
            try:
                return get_current_head_from_connection(connection, repository_id)
            except sqlite3.OperationalError as exc:
                _raise_if_busy(exc)
                raise
        except StoreBusy:
            raise
        finally:
            connection.close()


def get_current_head_from_connection(
    connection: sqlite3.Connection,
    repository_id: str,
) -> BaselineHead:
    row = connection.execute(
        """
        SELECT head.node_id, node.commit_id, head.optimistic_version
        FROM baseline_head_records AS head
        INNER JOIN baseline_node_records AS node ON node.node_id = head.node_id
        WHERE head.repository_id = ?
        """,
        (repository_id,),
    ).fetchone()
    if row is None:
        raise KeyError(repository_id)
    return BaselineHead(
        business_baseline_node_id=row["node_id"],
        business_baseline_commit_id=row["commit_id"],
        baseline_head_version=row["optimistic_version"],
    )


def assert_initial_scope_matches(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
) -> None:
    """Reject scope resolution when INITIAL node scope does not match the caller."""

    row = connection.execute(
        """
        SELECT gateway_device_external_key, business_project_id
        FROM baseline_node_records
        WHERE repository_id = ? AND kind = 'INITIAL'
        """,
        (repository_id,),
    ).fetchone()
    if row is None:
        raise ScopeResolutionError("baseline initial node is missing")
    if (
        row["gateway_device_external_key"] != gateway_device_external_key
        or row["business_project_id"] != business_project_id
    ):
        raise ScopeResolutionError("baseline initial scope does not match provisioned mapping")


def node_from_row(row: sqlite3.Row) -> BaselineNode:
    created_at_us = row["created_at_us"]
    if type(created_at_us) is not int:
        raise RuntimeError("baseline node row has invalid created_at_us")
    return BaselineNode(
        node_id=row["node_id"],
        repository_id=row["repository_id"],
        gateway_device_external_key=row["gateway_device_external_key"],
        business_project_id=row["business_project_id"],
        commit_id=row["commit_id"],
        kind=BaselineNodeKind(row["kind"]),
        parent_node_id=row["parent_node_id"],
        source_submission_id=row["source_submission_id"],
        created_at=_epoch_us_to_datetime(created_at_us),
    )


def _datetime_to_epoch_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("datetime must be aware UTC")
    delta = value - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def _epoch_us_to_datetime(value: int) -> datetime:
    seconds, micros = divmod(value, 1_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=micros)


__all__ = [
    "SQLiteBaselineHeadRead",
    "SQLiteBaselineRepository",
    "assert_initial_scope_matches",
    "get_current_head_from_connection",
    "node_from_row",
]
