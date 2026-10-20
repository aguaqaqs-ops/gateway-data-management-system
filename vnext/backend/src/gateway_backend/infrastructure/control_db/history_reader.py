"""Production History read adapter bridging SQLite facts to application contracts.

Maps ``HistorySubmissionRow`` to ``HistorySubmissionFact`` here so infrastructure
does not import application types.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gateway_backend.application.history.contracts import (
    HistoryFacts,
    HistoryNodeKind,
    HistoryNodeRefKind,
    HistoryPageEntry,
    HistoryPageSnapshot,
    HistorySubmissionFact,
)
from gateway_backend.application.history.ports import (
    HistoryControlTransaction,
    HistoryReadPort,
    HistorySnapshotLoaderPort,
)
from gateway_backend.domain.archive.models import ArchiveDispositionKind
from gateway_backend.domain.baseline.models import BaselineNodeKind
from gateway_backend.domain.submission.review import ReviewStatus
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.sqlite_history import (
    HistoryPageSnapshotInfra,
    SQLiteHistoryReader,
    load_history_page_from_connection,
)


class HttpHistoryReader(HistoryReadPort, HistorySnapshotLoaderPort):
    """Load HistoryFacts and paginated snapshots through the control DB."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._reader = SQLiteHistoryReader(db_path)

    def load_facts(
        self,
        *,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> HistoryFacts:
        snapshot = self._reader.load_snapshot(
            repository_id=repository_id,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
        )
        return HistoryFacts(
            repository_id=snapshot.repository_id,
            baseline_nodes=snapshot.baseline_nodes,
            submissions=tuple(
                HistorySubmissionFact(
                    submission=row.submission,
                    review_status=row.review_status,
                    disposition=row.disposition,
                )
                for row in snapshot.submissions
            ),
            head=snapshot.head,
        )

    def load_page_in_transaction(
        self,
        unit_of_work: HistoryControlTransaction,
        *,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        limit: int,
        after_order_key: list[object] | None,
    ) -> HistoryPageSnapshot:
        if not isinstance(unit_of_work, ControlDbUnitOfWork):
            raise TypeError("history snapshot loader requires ControlDbUnitOfWork")
        page = load_history_page_from_connection(
            unit_of_work.connection,
            repository_id=repository_id,
            gateway_device_external_key=gateway_device_external_key,
            business_project_id=business_project_id,
            limit=limit,
            after_order_key=after_order_key,
        )
        return _map_page_snapshot(page)


def _map_page_snapshot(page: HistoryPageSnapshotInfra) -> HistoryPageSnapshot:
    return HistoryPageSnapshot(
        head=page.head,
        entries=tuple(_map_page_entry(row) for row in page.rows),
        promoted_by_submission=dict(page.promoted_by_submission),
        has_next_page=page.has_next_page,
    )


def _map_page_entry(row: object) -> HistoryPageEntry:
    from gateway_backend.infrastructure.control_db.sqlite_history import HistoryPageRow

    if not isinstance(row, HistoryPageRow):
        raise TypeError("history page row has unexpected type")
    created_at = _epoch_us_to_datetime(row.created_at_us)
    if row.ref_kind == "baseline_node":
        if row.baseline_kind is None:
            raise ValueError("baseline page row is missing baseline_kind")
        return HistoryPageEntry(
            ref_kind=HistoryNodeRefKind.BASELINE_NODE,
            ref_id=row.ref_id,
            node_kind=HistoryNodeKind.BASELINE_NODE,
            commit_id=row.commit_id,
            created_at=created_at,
            baseline_kind=BaselineNodeKind(row.baseline_kind),
            parent_node_id=row.parent_node_id,
        )
    if row.review_status is None or row.based_on_baseline_node_id is None:
        raise ValueError("submission page row is missing required fields")
    disposition = None
    if row.archive_disposition is not None:
        disposition = ArchiveDispositionKind(row.archive_disposition)
    return HistoryPageEntry(
        ref_kind=HistoryNodeRefKind.SUBMISSION,
        ref_id=row.ref_id,
        node_kind=HistoryNodeKind.SUBMISSION,
        commit_id=row.commit_id,
        created_at=created_at,
        based_on_baseline_node_id=row.based_on_baseline_node_id,
        review_status=ReviewStatus(row.review_status),
        archive_disposition=disposition,
        identity_exception=row.identity_exception,
    )


def _epoch_us_to_datetime(value: int) -> datetime:
    seconds, micros = divmod(value, 1_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(microsecond=micros)
