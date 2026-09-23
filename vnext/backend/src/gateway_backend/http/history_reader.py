"""Production History read adapter bridging SQLite facts to application contracts.

Maps ``HistorySubmissionRow`` to ``HistorySubmissionFact`` here so infrastructure
does not import application types.
"""

from __future__ import annotations

from pathlib import Path

from gateway_backend.application.history.contracts import HistoryFacts, HistorySubmissionFact
from gateway_backend.application.history.ports import HistoryReadPort
from gateway_backend.infrastructure.control_db.sqlite_history import SQLiteHistoryReader


class HttpHistoryReader(HistoryReadPort):
    """Load HistoryFacts through the control DB readonly snapshot."""

    def __init__(self, db_path: Path) -> None:
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
