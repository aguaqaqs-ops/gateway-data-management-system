"""SQLite read queries for History projection facts.

``HistorySubmissionRow`` stays in infrastructure; ``HistorySubmissionFact`` lives in
application. Do not merge them: ``test_architecture`` forbids control_db imports of
application types.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gateway_backend.domain.archive.models import ArchiveDispositionKind
from gateway_backend.domain.baseline.models import BaselineNode
from gateway_backend.domain.submission.models import Submission
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.domain.workspace.models import BaselineHead
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_baseline import (
    get_current_head_from_connection,
    node_from_row,
)
from gateway_backend.infrastructure.control_db.sqlite_submission import (
    SUBMISSION_COLUMNS,
    row_mapping,
    submission_from_row,
)

_BASELINE_NODE_COLUMNS = (
    "node_id, repository_id, gateway_device_external_key, business_project_id, "
    "commit_id, kind, parent_node_id, source_submission_id, created_at_us"
)
_SUBMISSION_COLUMN_NAMES = tuple(column.strip() for column in SUBMISSION_COLUMNS.split(","))
_BASELINE_KIND_RANK = 0
_SUBMISSION_KIND_RANK = 1


@dataclass(frozen=True, slots=True)
class HistorySubmissionRow:
    submission: Submission
    review_status: ReviewStatus
    disposition: ArchiveDispositionKind | None


@dataclass(frozen=True, slots=True)
class HistorySnapshot:
    repository_id: str
    baseline_nodes: tuple[BaselineNode, ...]
    submissions: tuple[HistorySubmissionRow, ...]
    head: BaselineHead


@dataclass(frozen=True, slots=True)
class HistoryPageRow:
    ref_kind: str
    ref_id: str
    kind_rank: int
    created_at_us: int
    commit_id: str
    baseline_kind: str | None
    parent_node_id: str | None
    based_on_baseline_node_id: str | None
    review_status: str | None
    archive_disposition: str | None


@dataclass(frozen=True, slots=True)
class HistoryPageSnapshotInfra:
    repository_id: str
    head: BaselineHead
    rows: tuple[HistoryPageRow, ...]
    promoted_by_submission: dict[str, str]
    has_next_page: bool


class SQLiteHistoryReader:
    """Read-only History snapshot adapter backed by the local control DB."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def load_snapshot(
        self,
        *,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> HistorySnapshot:
        with ControlDbUnitOfWork(self._db_path, read_only=True) as unit_of_work:
            return load_history_snapshot_from_connection(
                unit_of_work.connection,
                repository_id=repository_id,
                gateway_device_external_key=gateway_device_external_key,
                business_project_id=business_project_id,
            )


def load_history_snapshot_from_connection(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
) -> HistorySnapshot:
    baseline_nodes = _load_baseline_nodes(
        connection,
        repository_id=repository_id,
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
    )
    submissions = _load_submission_rows(connection, repository_id=repository_id)
    head = get_current_head_from_connection(connection, repository_id)
    return HistorySnapshot(
        repository_id=repository_id,
        baseline_nodes=baseline_nodes,
        submissions=submissions,
        head=head,
    )


def load_history_page_from_connection(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    limit: int,
    after_order_key: list[object] | None,
) -> HistoryPageSnapshotInfra:
    head = get_current_head_from_connection(connection, repository_id)
    promoted_by_submission = _load_promoted_by_submission(
        connection,
        repository_id=repository_id,
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
    )
    rows = _load_history_page_rows(
        connection,
        repository_id=repository_id,
        gateway_device_external_key=gateway_device_external_key,
        business_project_id=business_project_id,
        limit=limit + 1,
        after_order_key=after_order_key,
    )
    has_next_page = len(rows) > limit
    page_rows = rows[:limit]
    return HistoryPageSnapshotInfra(
        repository_id=repository_id,
        head=head,
        rows=page_rows,
        promoted_by_submission=promoted_by_submission,
        has_next_page=has_next_page,
    )


def _load_promoted_by_submission(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT source_submission_id, node_id
        FROM baseline_node_records
        WHERE repository_id = ?
          AND gateway_device_external_key = ?
          AND business_project_id = ?
          AND source_submission_id IS NOT NULL
        """,
        (repository_id, gateway_device_external_key, business_project_id),
    ).fetchall()
    promoted: dict[str, str] = {}
    for row in rows:
        source_submission_id = row["source_submission_id"]
        node_id = row["node_id"]
        if type(source_submission_id) is not str or type(node_id) is not str:
            raise ValueError("promoted baseline row has invalid identifiers")
        promoted[source_submission_id] = node_id
    return promoted


def _load_history_page_rows(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    limit: int,
    after_order_key: list[object] | None,
) -> tuple[HistoryPageRow, ...]:
    cursor_clause = ""
    params: list[object] = [
        repository_id,
        gateway_device_external_key,
        business_project_id,
        repository_id,
    ]
    if after_order_key is not None:
        created_at_us, kind_rank, ref_id = after_order_key
        cursor_clause = "WHERE (created_at_us, kind_rank, ref_id) > (?, ?, ?)"
        params.extend([created_at_us, kind_rank, ref_id])
    params.append(limit)
    rows = connection.execute(
        f"""
        SELECT *
        FROM (
            SELECT
                'baseline_node' AS ref_kind,
                node_id AS ref_id,
                {_BASELINE_KIND_RANK} AS kind_rank,
                created_at_us,
                commit_id,
                kind AS baseline_kind,
                parent_node_id,
                NULL AS based_on_baseline_node_id,
                NULL AS review_status,
                NULL AS archive_disposition
            FROM baseline_node_records
            WHERE repository_id = ?
              AND gateway_device_external_key = ?
              AND business_project_id = ?
            UNION ALL
            SELECT
                'submission',
                s.submission_id,
                {_SUBMISSION_KIND_RANK},
                s.created_at_us,
                s.repository_commit_id,
                NULL,
                NULL,
                s.based_on_baseline_node_id,
                p.status,
                d.disposition
            FROM submission_records AS s
            INNER JOIN review_projection_records AS p
                ON p.submission_id = s.submission_id
            LEFT JOIN archive_disposition_records AS d
                ON d.submission_id = s.submission_id
            WHERE s.repository_id = ?
        ) AS history_nodes
        {cursor_clause}
        ORDER BY created_at_us ASC, kind_rank ASC, ref_id ASC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return tuple(_history_page_row_from_row(row) for row in rows)


def _history_page_row_from_row(row: sqlite3.Row) -> HistoryPageRow:
    created_at_us = row["created_at_us"]
    if type(created_at_us) is not int:
        raise ValueError("created_at_us must be an integer")
    ref_kind = row["ref_kind"]
    ref_id = row["ref_id"]
    kind_rank = row["kind_rank"]
    commit_id = row["commit_id"]
    if type(ref_kind) is not str or type(ref_id) is not str or type(commit_id) is not str:
        raise ValueError("history page row has invalid text fields")
    if type(kind_rank) is not int:
        raise ValueError("kind_rank must be an integer")
    baseline_kind = row["baseline_kind"]
    parent_node_id = row["parent_node_id"]
    based_on_baseline_node_id = row["based_on_baseline_node_id"]
    review_status = row["review_status"]
    archive_disposition = row["archive_disposition"]
    return HistoryPageRow(
        ref_kind=ref_kind,
        ref_id=ref_id,
        kind_rank=kind_rank,
        created_at_us=created_at_us,
        commit_id=commit_id,
        baseline_kind=None if baseline_kind is None else str(baseline_kind),
        parent_node_id=None if parent_node_id is None else str(parent_node_id),
        based_on_baseline_node_id=(
            None if based_on_baseline_node_id is None else str(based_on_baseline_node_id)
        ),
        review_status=None if review_status is None else str(review_status),
        archive_disposition=None if archive_disposition is None else str(archive_disposition),
    )


def _load_baseline_nodes(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
) -> tuple[BaselineNode, ...]:
    rows = connection.execute(
        f"""
        SELECT {_BASELINE_NODE_COLUMNS}
        FROM baseline_node_records
        WHERE repository_id = ?
          AND gateway_device_external_key = ?
          AND business_project_id = ?
        ORDER BY created_at_us ASC, node_id ASC
        """,
        (repository_id, gateway_device_external_key, business_project_id),
    ).fetchall()
    return tuple(node_from_row(row) for row in rows)


def _load_submission_rows(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
) -> tuple[HistorySubmissionRow, ...]:
    submission_columns = ", ".join(f"s.{column}" for column in _SUBMISSION_COLUMN_NAMES)
    rows = connection.execute(
        f"""
        SELECT
            {submission_columns},
            p.status AS review_status,
            d.disposition AS archive_disposition
        FROM submission_records AS s
        INNER JOIN review_projection_records AS p
            ON p.submission_id = s.submission_id
        LEFT JOIN archive_disposition_records AS d
            ON d.submission_id = s.submission_id
        WHERE s.repository_id = ?
        ORDER BY s.created_at_us ASC, s.submission_id ASC
        """,
        (repository_id,),
    ).fetchall()
    return tuple(_submission_row_from_row(row) for row in rows)


def _submission_row_from_row(row: sqlite3.Row) -> HistorySubmissionRow:
    mapping = row_mapping(row)
    submission_mapping = {name: mapping[name] for name in _SUBMISSION_COLUMN_NAMES}
    disposition_value = mapping["archive_disposition"]
    disposition = None if disposition_value is None else ArchiveDispositionKind(str(disposition_value))
    review_status_value = mapping["review_status"]
    if type(review_status_value) is not str or not review_status_value:
        raise ValueError("review_status must be a non-empty string")
    return HistorySubmissionRow(
        submission=submission_from_row(submission_mapping),
        review_status=ReviewStatus(review_status_value),
        disposition=disposition,
    )


def _epoch_us_to_datetime(value: int) -> datetime:
    seconds, micros = divmod(value, 1_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=micros)
