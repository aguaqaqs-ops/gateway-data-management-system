"""SQLite read queries for History projection facts.

``HistorySubmissionRow`` stays in infrastructure; ``HistorySubmissionFact`` lives in
application. Do not merge them: ``test_architecture`` forbids control_db imports of
application types.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
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
