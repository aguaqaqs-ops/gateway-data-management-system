"""Archive domain persistence ports."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from gateway_backend.domain.archive.models import (
    ArchiveAnomalyResolutionEvent,
    ArchiveConfirmationEvent,
    ArchiveDisposition,
    ArchivePlan,
    ArchiveResult,
)


@runtime_checkable
class ArchiveAuditWritePort(Protocol):
    def get_latest_confirmation_sequence(
        self,
        repository_id: str,
        subject_digest: str,
    ) -> int:
        """Return latest confirmation sequence for one subject, or 0 when absent."""

    def get_latest_resolution_sequence(
        self,
        repository_id: str,
        subject_digest: str,
    ) -> int:
        """Return latest resolution sequence for one subject, or 0 when absent."""

    def append_confirmation(self, event: ArchiveConfirmationEvent) -> None:
        """Append one immutable confirmation event."""

    def append_anomaly_resolution(self, event: ArchiveAnomalyResolutionEvent) -> None:
        """Append one immutable anomaly resolution event."""

    def find_confirmation_idempotency(
        self,
        repository_id: str,
        idempotency_key: str,
    ) -> ArchiveConfirmationEvent | None:
        """Return durable confirmation event for one key when present."""

    def find_resolution_idempotency(
        self,
        repository_id: str,
        idempotency_key: str,
    ) -> ArchiveAnomalyResolutionEvent | None:
        """Return durable resolution event for one key when present."""

    def get_confirmation_event(
        self,
        repository_id: str,
        subject_digest: str,
        sequence: int,
    ) -> ArchiveConfirmationEvent | None:
        """Load one confirmation event by subject and sequence."""

    def get_resolution_event(
        self,
        repository_id: str,
        subject_digest: str,
        sequence: int,
    ) -> ArchiveAnomalyResolutionEvent | None:
        """Load one resolution event by subject and sequence."""

    def list_confirmation_events(
        self,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        subject_digest: str,
        after_sequence: int,
        limit: int,
    ) -> tuple[ArchiveConfirmationEvent, ...]:
        """Return confirmation events after one sequence within one scope."""

    def list_resolution_events(
        self,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        subject_digest: str,
        after_sequence: int,
        limit: int,
    ) -> tuple[ArchiveAnomalyResolutionEvent, ...]:
        """Return resolution events after one sequence within one scope."""


@runtime_checkable
class ArchiveRepository(ArchiveAuditWritePort, Protocol):
    def find_start_plan_by_key(
        self,
        repository_id: str,
        gateway_device_external_key: str,
        business_project_id: str,
        idempotency_key: str,
    ) -> ArchivePlan | None:
        """Return durable Start plan for one exact scope key when present."""

    def get_result_by_plan_id(self, plan_id: str) -> ArchiveResult | None:
        """Load one ArchiveResult by plan id."""

    def get_plan_by_id(self, plan_id: str) -> ArchivePlan | None:
        """Load one ArchivePlan by plan id."""

    def get_result_by_id(self, result_id: str) -> ArchiveResult | None:
        """Load one ArchiveResult by result id."""

    def list_dispositions_for_submission(self, submission_id: str) -> tuple[ArchiveDisposition, ...]:
        """Return all dispositions recorded for one submission."""

    def is_submission_closed(self, submission_id: str) -> bool:
        """Return whether one submission appears in any ArchiveResult disposition."""

    def insert_plan_result_and_dispositions(
        self,
        plan: ArchivePlan,
        result: ArchiveResult,
        dispositions: tuple[ArchiveDisposition, ...],
    ) -> None:
        """Insert immutable plan, result and disposition rows in the current transaction."""
