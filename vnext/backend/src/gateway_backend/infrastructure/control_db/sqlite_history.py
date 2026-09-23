"""SQLite read queries for History projection facts."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gateway_backend.domain.archive.models import ArchiveDispositionKind
from gateway_backend.domain.baseline.models import BaselineNode, BaselineNodeKind
from gateway_backend.domain.submission.models import Submission, SubmitTargetRef, SubmitUnknownTypePolicy, SubmitVerificationPolicy
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.domain.workspace.models import BaselineHead
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_baseline import get_current_head_from_connection

_BASELINE_NODE_COLUMNS = (
    "node_id, repository_id, gateway_device_external_key, business_project_id, "
    "commit_id, kind, parent_node_id, source_submission_id, created_at_us"
)
_SUBMISSION_COLUMNS = (
    "submission_id, submit_attempt_id, workspace_id, workspace_generation, "
    "upload_revision_id, preview_result_id, repository_id, based_on_baseline_node_id, "
    "business_baseline_commit_id, repository_commit_id, canonical_business_digest, "
    "source_artifact_refs, canonicalization_manifest_ref, canonicalization_manifest_digest, "
    "repository_import_artifact_raw_sha256, repository_artifact_id, "
    "requested_verification_policy, completed_verification_policy, "
    "requested_unknown_type_policy, target_ref, created_by, created_at_us"
)


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
    return tuple(_baseline_node_from_row(row) for row in rows)


def _load_submission_rows(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
) -> tuple[HistorySubmissionRow, ...]:
    submission_columns = ", ".join(f"s.{column.strip()}" for column in _SUBMISSION_COLUMNS.split(","))
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


def _baseline_node_from_row(row: Mapping[str, object]) -> BaselineNode:
    parent_node_id = row["parent_node_id"]
    source_submission_id = row["source_submission_id"]
    return BaselineNode(
        node_id=_required_text(row, "node_id"),
        repository_id=_required_text(row, "repository_id"),
        gateway_device_external_key=_required_text(row, "gateway_device_external_key"),
        business_project_id=_required_text(row, "business_project_id"),
        commit_id=_required_text(row, "commit_id"),
        kind=BaselineNodeKind(_required_text(row, "kind")),
        parent_node_id=None if parent_node_id is None else str(parent_node_id),
        source_submission_id=None if source_submission_id is None else str(source_submission_id),
        created_at=_epoch_us_to_datetime(_required_int(row, "created_at_us")),
    )


def _submission_row_from_row(row: Mapping[str, object]) -> HistorySubmissionRow:
    disposition_value = row["archive_disposition"]
    disposition = None if disposition_value is None else ArchiveDispositionKind(str(disposition_value))
    return HistorySubmissionRow(
        submission=_submission_from_row(row),
        review_status=ReviewStatus(_required_text(row, "review_status")),
        disposition=disposition,
    )


def _submission_from_row(row: Mapping[str, object]) -> Submission:
    source_refs_blob = row["source_artifact_refs"]
    if type(source_refs_blob) is not bytes:
        raise ValueError("source_artifact_refs must be bytes")
    source_refs = tuple(item.decode("utf-8") for item in source_refs_blob.split(b"\0") if item)
    return Submission(
        submission_id=_required_text(row, "submission_id"),
        submit_attempt_id=_required_text(row, "submit_attempt_id"),
        workspace_id=_required_text(row, "workspace_id"),
        workspace_generation=_required_int(row, "workspace_generation"),
        upload_revision_id=_required_text(row, "upload_revision_id"),
        preview_result_id=_required_text(row, "preview_result_id"),
        repository_id=_required_text(row, "repository_id"),
        based_on_baseline_node_id=_required_text(row, "based_on_baseline_node_id"),
        business_baseline_commit_id=_required_text(row, "business_baseline_commit_id"),
        repository_commit_id=_required_text(row, "repository_commit_id"),
        canonical_business_digest=_required_text(row, "canonical_business_digest"),
        source_artifact_refs=source_refs,
        canonicalization_manifest_ref=_required_text(row, "canonicalization_manifest_ref"),
        canonicalization_manifest_digest=_required_text(row, "canonicalization_manifest_digest"),
        repository_import_artifact_raw_sha256=_required_text(
            row,
            "repository_import_artifact_raw_sha256",
        ),
        repository_artifact_id=_required_text(row, "repository_artifact_id"),
        requested_verification_policy=SubmitVerificationPolicy(
            _required_text(row, "requested_verification_policy")
        ),
        completed_verification_policy=SubmitVerificationPolicy(
            _required_text(row, "completed_verification_policy")
        ),
        requested_unknown_type_policy=SubmitUnknownTypePolicy(
            _required_text(row, "requested_unknown_type_policy")
        ),
        target_ref=SubmitTargetRef(_required_text(row, "target_ref")),
        created_by=_required_text(row, "created_by"),
        created_at=_epoch_us_to_datetime(_required_int(row, "created_at_us")),
    )


def _required_text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _epoch_us_to_datetime(value: int) -> datetime:
    seconds, micros = divmod(value, 1_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=micros)
