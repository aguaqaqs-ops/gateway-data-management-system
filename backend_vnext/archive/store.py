from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Protocol

from .models import (
    ArchiveAnomalyResolutionRecord,
    ArchiveBatchRecord,
    ArchiveCandidateRecord,
    ArchiveExecutionRecord,
    WorkspaceArchiveConfirmationRecord,
)


class ArchiveStore(Protocol):
    def create_batch(self, record: ArchiveBatchRecord) -> ArchiveBatchRecord: ...

    def get_batch(self, batch_id: str) -> ArchiveBatchRecord | None: ...

    def save_batch(self, record: ArchiveBatchRecord, *, expected_version: int | None = None) -> ArchiveBatchRecord: ...

    def create_confirmation(self, record: WorkspaceArchiveConfirmationRecord) -> WorkspaceArchiveConfirmationRecord: ...

    def get_confirmation(self, confirmation_id: str) -> WorkspaceArchiveConfirmationRecord | None: ...

    def save_confirmation(self, record: WorkspaceArchiveConfirmationRecord, *, expected_version: int | None = None) -> WorkspaceArchiveConfirmationRecord: ...

    def list_confirmations_by_batch(self, batch_id: str) -> tuple[WorkspaceArchiveConfirmationRecord, ...]: ...

    def create_candidate(self, record: ArchiveCandidateRecord) -> ArchiveCandidateRecord: ...

    def get_candidate(self, candidate_id: str) -> ArchiveCandidateRecord | None: ...

    def save_candidate(self, record: ArchiveCandidateRecord, *, expected_version: int | None = None) -> ArchiveCandidateRecord: ...

    def list_candidates_by_batch(self, batch_id: str) -> tuple[ArchiveCandidateRecord, ...]: ...

    def create_anomaly_resolution(self, record: ArchiveAnomalyResolutionRecord) -> ArchiveAnomalyResolutionRecord: ...

    def get_anomaly_resolution(self, resolution_id: str) -> ArchiveAnomalyResolutionRecord | None: ...

    def save_anomaly_resolution(self, record: ArchiveAnomalyResolutionRecord, *, expected_version: int | None = None) -> ArchiveAnomalyResolutionRecord: ...

    def list_anomaly_resolutions_by_batch(self, batch_id: str) -> tuple[ArchiveAnomalyResolutionRecord, ...]: ...

    def create_execution(self, record: ArchiveExecutionRecord) -> ArchiveExecutionRecord: ...

    def get_execution(self, execution_id: str) -> ArchiveExecutionRecord | None: ...

    def get_execution_by_idempotency_key(self, idempotency_key: str) -> ArchiveExecutionRecord | None: ...

    def save_execution(self, record: ArchiveExecutionRecord, *, expected_version: int | None = None) -> ArchiveExecutionRecord: ...

    def list_executions_by_batch(self, batch_id: str) -> tuple[ArchiveExecutionRecord, ...]: ...

    def next_confirmation_identity(self) -> str: ...

    def next_candidate_identity(self) -> str: ...

    def next_anomaly_resolution_identity(self) -> str: ...

    def next_execution_identity(self) -> str: ...


@dataclass
class InMemoryArchiveStore:
    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._batches: dict[str, ArchiveBatchRecord] = {}
        self._confirmations: dict[str, WorkspaceArchiveConfirmationRecord] = {}
        self._candidates: dict[str, ArchiveCandidateRecord] = {}
        self._anomaly_resolutions: dict[str, ArchiveAnomalyResolutionRecord] = {}
        self._executions: dict[str, ArchiveExecutionRecord] = {}
        self._confirmation_next = 1
        self._candidate_next = 1
        self._anomaly_resolution_next = 1
        self._execution_next = 1

    def create_batch(self, record: ArchiveBatchRecord) -> ArchiveBatchRecord:
        with self._lock:
            if record.batch_id in self._batches:
                raise ValueError("archive batch already exists")
            self._batches[record.batch_id] = record
            return record

    def get_batch(self, batch_id: str) -> ArchiveBatchRecord | None:
        with self._lock:
            return self._batches.get(batch_id)

    def save_batch(self, record: ArchiveBatchRecord, *, expected_version: int | None = None) -> ArchiveBatchRecord:
        with self._lock:
            current = self._batches.get(record.batch_id)
            if current is None:
                raise KeyError("archive batch not found")
            if expected_version is not None and current.version != expected_version:
                raise ValueError("archive batch version mismatch")
            self._batches[record.batch_id] = record
            return record

    def create_confirmation(self, record: WorkspaceArchiveConfirmationRecord) -> WorkspaceArchiveConfirmationRecord:
        with self._lock:
            if record.confirmation_id in self._confirmations:
                raise ValueError("archive confirmation already exists")
            self._confirmations[record.confirmation_id] = record
            return record

    def get_confirmation(self, confirmation_id: str) -> WorkspaceArchiveConfirmationRecord | None:
        with self._lock:
            return self._confirmations.get(confirmation_id)

    def save_confirmation(
        self,
        record: WorkspaceArchiveConfirmationRecord,
        *,
        expected_version: int | None = None,
    ) -> WorkspaceArchiveConfirmationRecord:
        with self._lock:
            current = self._confirmations.get(record.confirmation_id)
            if current is None:
                raise KeyError("archive confirmation not found")
            if expected_version is not None and current.version != expected_version:
                raise ValueError("archive confirmation version mismatch")
            self._confirmations[record.confirmation_id] = record
            return record

    def list_confirmations_by_batch(self, batch_id: str) -> tuple[WorkspaceArchiveConfirmationRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in sorted(
                    self._confirmations.values(),
                    key=lambda item: (item.created_at, item.confirmation_id),
                )
                if record.batch_id == batch_id
            )

    def create_candidate(self, record: ArchiveCandidateRecord) -> ArchiveCandidateRecord:
        with self._lock:
            if record.candidate_id in self._candidates:
                raise ValueError("archive candidate already exists")
            self._candidates[record.candidate_id] = record
            return record

    def get_candidate(self, candidate_id: str) -> ArchiveCandidateRecord | None:
        with self._lock:
            return self._candidates.get(candidate_id)

    def save_candidate(
        self,
        record: ArchiveCandidateRecord,
        *,
        expected_version: int | None = None,
    ) -> ArchiveCandidateRecord:
        with self._lock:
            current = self._candidates.get(record.candidate_id)
            if current is None:
                raise KeyError("archive candidate not found")
            if expected_version is not None and current.version != expected_version:
                raise ValueError("archive candidate version mismatch")
            self._candidates[record.candidate_id] = record
            return record

    def list_candidates_by_batch(self, batch_id: str) -> tuple[ArchiveCandidateRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in sorted(
                    self._candidates.values(),
                    key=lambda item: (item.created_at, item.candidate_id),
                )
                if record.batch_id == batch_id
            )

    def create_anomaly_resolution(self, record: ArchiveAnomalyResolutionRecord) -> ArchiveAnomalyResolutionRecord:
        with self._lock:
            if record.resolution_id in self._anomaly_resolutions:
                raise ValueError("archive anomaly resolution already exists")
            self._anomaly_resolutions[record.resolution_id] = record
            return record

    def get_anomaly_resolution(self, resolution_id: str) -> ArchiveAnomalyResolutionRecord | None:
        with self._lock:
            return self._anomaly_resolutions.get(resolution_id)

    def save_anomaly_resolution(
        self,
        record: ArchiveAnomalyResolutionRecord,
        *,
        expected_version: int | None = None,
    ) -> ArchiveAnomalyResolutionRecord:
        with self._lock:
            current = self._anomaly_resolutions.get(record.resolution_id)
            if current is None:
                raise KeyError("archive anomaly resolution not found")
            if expected_version is not None and current.version != expected_version:
                raise ValueError("archive anomaly resolution version mismatch")
            self._anomaly_resolutions[record.resolution_id] = record
            return record

    def list_anomaly_resolutions_by_batch(self, batch_id: str) -> tuple[ArchiveAnomalyResolutionRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in sorted(
                    self._anomaly_resolutions.values(),
                    key=lambda item: (item.created_at, item.resolution_id),
                )
                if record.batch_id == batch_id
            )

    def create_execution(self, record: ArchiveExecutionRecord) -> ArchiveExecutionRecord:
        with self._lock:
            if record.execution_id in self._executions:
                raise ValueError("archive execution already exists")
            self._executions[record.execution_id] = record
            return record

    def get_execution(self, execution_id: str) -> ArchiveExecutionRecord | None:
        with self._lock:
            return self._executions.get(execution_id)

    def get_execution_by_idempotency_key(self, idempotency_key: str) -> ArchiveExecutionRecord | None:
        with self._lock:
            for execution in self._executions.values():
                if execution.command_idempotency_key == idempotency_key:
                    return execution
            return None

    def save_execution(
        self,
        record: ArchiveExecutionRecord,
        *,
        expected_version: int | None = None,
    ) -> ArchiveExecutionRecord:
        with self._lock:
            current = self._executions.get(record.execution_id)
            if current is None:
                raise KeyError("archive execution not found")
            if expected_version is not None and current.version != expected_version:
                raise ValueError("archive execution version mismatch")
            self._executions[record.execution_id] = record
            return record

    def list_executions_by_batch(self, batch_id: str) -> tuple[ArchiveExecutionRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in sorted(
                    self._executions.values(),
                    key=lambda item: (item.created_at, item.execution_id),
                )
                if record.batch_id == batch_id
            )

    def next_confirmation_identity(self) -> str:
        with self._lock:
            value = self._confirmation_next
            self._confirmation_next += 1
        return f"archive-confirmation-{value:03d}"

    def next_candidate_identity(self) -> str:
        with self._lock:
            value = self._candidate_next
            self._candidate_next += 1
        return f"archive-candidate-{value:03d}"

    def next_anomaly_resolution_identity(self) -> str:
        with self._lock:
            value = self._anomaly_resolution_next
            self._anomaly_resolution_next += 1
        return f"archive-anomaly-resolution-{value:03d}"

    def next_execution_identity(self) -> str:
        with self._lock:
            value = self._execution_next
            self._execution_next += 1
        return f"archive-execution-{value:03d}"
