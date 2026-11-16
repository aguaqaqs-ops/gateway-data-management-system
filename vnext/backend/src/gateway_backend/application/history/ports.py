"""Control transaction and read ports owned by History use cases."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol, runtime_checkable

from gateway_backend.application.control_transactions import ControlTransaction
from gateway_backend.application.canonical_metadata.ports import CommitCanonicalMetadataPort
from gateway_backend.application.history.contracts import (
    HistoryCompareAcceptanceRecord,
    HistoryFacts,
    HistoryPageSnapshot,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.artifacts.canonical_table_store import CanonicalTableIndexPort
from gateway_backend.domain.workspace.models import ResolvedScope
from gateway_backend.operations import OperationStore


class HistoryControlTransaction(ControlTransaction, Protocol):
    def count_queued_operations(self) -> int: ...

    @property
    def canonical_tables(self) -> CanonicalTableIndexPort: ...

    @property
    def commit_canonical_metadata(self) -> CommitCanonicalMetadataPort: ...

    @property
    def operations(self) -> OperationStore: ...

    @property
    def history_compare(self) -> HistoryComparePort: ...

    def resolve_provisioned_scope(
        self,
        *,
        gateway_device_external_key: str,
        business_project_id: str,
    ) -> ResolvedScope: ...

    def set_artifact_protection(
        self,
        refs: tuple[ArtifactRef, ...],
        *,
        owner_kind: str,
        owner_id: str,
        intent: str,
        expires_at: datetime | None = None,
    ) -> bool: ...

    def clear_artifact_protection(self, *, owner_kind: str, owner_id: str) -> int: ...

    def list_artifact_protection_for_owner(
        self,
        *,
        owner_kind: str,
        owner_id: str,
    ) -> frozenset[str]: ...


class HistoryControlUnitOfWorkFactory(Protocol):
    def __call__(
        self,
        *,
        read_only: bool = False,
    ) -> AbstractContextManager[HistoryControlTransaction]: ...


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

    def find_candidates(
        self, *, gateway_device_external_key: str, business_project_id: str,
        request_fingerprint: str, now: datetime,
    ) -> tuple[HistoryCompareAcceptanceRecord, ...]: ...

    def save_alias(self, *, record: HistoryCompareAcceptanceRecord, idempotency_key: str) -> None: ...

    def list_acceptances(
        self, *, gateway_device_external_key: str, business_project_id: str, repository_id: str,
        now: datetime, after: tuple[datetime, str] | None, limit: int,
    ) -> tuple[HistoryCompareAcceptanceRecord, ...]: ...

    def active_operation_ids(self, *, gateway_device_external_key: str, business_project_id: str) -> tuple[str, ...]: ...

    def count_aliases(self, operation_id: str) -> int: ...

    def result_protection_matches(self, operation_id: str, artifact_ids: frozenset[str], expires_at: datetime) -> bool: ...

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

@runtime_checkable
class HistorySnapshotLoaderPort(Protocol):
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
        """Load one paginated History page within an active readonly transaction."""
