"""History read ports consumed by application queries."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gateway_backend.application.history.contracts import HistoryFacts, HistoryPageSnapshot
from gateway_backend.application.submission.ports import (
    WorkspaceControlTransaction,
    WorkspaceControlUnitOfWorkFactory,
)

HistoryControlUnitOfWorkFactory = WorkspaceControlUnitOfWorkFactory


@runtime_checkable
class HistoryReadPort(Protocol):
    def load_facts(
        self,
        *,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> HistoryFacts:
        """Load one readonly snapshot of History facts for an authorized scope."""


@runtime_checkable
class HistorySnapshotLoaderPort(Protocol):
    def load_page_in_transaction(
        self,
        unit_of_work: WorkspaceControlTransaction,
        *,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        limit: int,
        after_order_key: list[object] | None,
    ) -> HistoryPageSnapshot:
        """Load one paginated History page within an active readonly transaction."""
