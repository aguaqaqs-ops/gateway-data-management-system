"""History read ports consumed by application queries."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from gateway_backend.application.history.contracts import (
    HistoryCompareAcceptanceRecord,
    HistoryCompareIntegrityRecord,
    HistoryFacts,
    HistoryPageSnapshot,
)
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
class HistoryComparePort(Protocol):
    def find_acceptance_by_idempotency(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
        idempotency_key: str,
    ) -> HistoryCompareAcceptanceRecord | None:
        """Return durable acceptance for one scope/idempotency key."""

    def get_acceptance_by_operation_id(self, operation_id: str) -> HistoryCompareAcceptanceRecord | None:
        """Return durable acceptance for one operation id."""

    def save_acceptance(self, record: HistoryCompareAcceptanceRecord) -> None:
        """Persist one acceptance record."""

    def resolve_node_ref(
        self,
        *,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        ref_kind: str,
        ref_id: str,
    ) -> str | None:
        """Resolve one node ref to a commit id or None."""

    def has_pending_integrity_for_commit(self, *, repository_id: str, commit_id: str) -> bool:
        """Return whether a pending integrity incident blocks one commit."""

    def save_integrity_record(self, record: HistoryCompareIntegrityRecord) -> None:
        """Persist one integrity incident."""

    def get_integrity_by_operation_id(self, operation_id: str) -> HistoryCompareIntegrityRecord | None:
        """Return integrity incident for one operation."""

    def acknowledge_integrity(
        self,
        *,
        operation_id: str,
        resolution_reference: str,
        updated_at: datetime,
    ) -> HistoryCompareIntegrityRecord:
        """Acknowledge one integrity incident."""


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
