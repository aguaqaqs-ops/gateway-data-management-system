from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum


class BaselineBatchStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    INVALIDATED = "INVALIDATED"


class BaselineBatchArchiveGateStatus(StrEnum):
    COLLECTING_CONFIRMATIONS = "COLLECTING_CONFIRMATIONS"
    READY_FOR_ARCHIVE = "READY_FOR_ARCHIVE"
    ARCHIVING = "ARCHIVING"
    ARCHIVE_FROZEN = "ARCHIVE_FROZEN"
    ARCHIVED = "ARCHIVED"


class WorkspaceArchiveConfirmationStatus(StrEnum):
    CONFIRMED_WITH_CANDIDATE = "CONFIRMED_WITH_CANDIDATE"
    CONFIRMED_DISCARDED = "CONFIRMED_DISCARDED"


class ArchiveCandidateSourceKind(StrEnum):
    APPROVED_SUBMISSION = "APPROVED_SUBMISSION"
    REJECTED_SUBMISSION = "REJECTED_SUBMISSION"
    WITHDRAWN_SUBMISSION = "WITHDRAWN_SUBMISSION"
    WORKSPACE_PREVIEW = "WORKSPACE_PREVIEW"
    WORKSPACE_INITIAL_ONLY = "WORKSPACE_INITIAL_ONLY"


class ArchiveCandidateRole(StrEnum):
    MAINLINE_MODIFIED = "MAINLINE_MODIFIED"
    BASELINE_INITIAL_HISTORY = "BASELINE_INITIAL_HISTORY"


class ArchiveCandidateStatus(StrEnum):
    NOT_ARCHIVED = "NOT_ARCHIVED"
    ARCHIVED_AS_MAINLINE = "ARCHIVED_AS_MAINLINE"
    ARCHIVED_AS_HISTORY = "ARCHIVED_AS_HISTORY"
    CLOSED_NOT_ARCHIVED = "CLOSED_NOT_ARCHIVED"


class AnomalyResolutionType(StrEnum):
    RESOLVED_BY_PEER = "RESOLVED_BY_PEER"
    MANUAL_ACCEPT_EXTERNAL_CHANGE = "MANUAL_ACCEPT_EXTERNAL_CHANGE"
    MANUAL_ACCEPT_INCOMPLETE_SUMMARY = "MANUAL_ACCEPT_INCOMPLETE_SUMMARY"
    MANUAL_ACCEPT_ABNORMAL_MODIFIED = "MANUAL_ACCEPT_ABNORMAL_MODIFIED"
    SUPERSEDED_BY_LATER_SUBMISSION = "SUPERSEDED_BY_LATER_SUBMISSION"


class ArchiveExecutionStatus(StrEnum):
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    SUCCEEDED_TRANSFER_FAILED = "SUCCEEDED_TRANSFER_FAILED"
    FAILED_FROZEN = "FAILED_FROZEN"


class ArchiveExecutionTransferStatus(StrEnum):
    PENDING = "PENDING"
    TRANSFERRED = "TRANSFERRED"
    LOCAL_PURGED = "LOCAL_PURGED"
    TRANSFER_FAILED = "TRANSFER_FAILED"


def _optional_datetime(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be an ISO 8601 string or None")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _required_str(payload: Mapping[str, object], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _optional_str(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string or None")
    return value


def _optional_bool(value: object, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value


def _optional_str_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence of strings or null")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise TypeError(f"{field_name} must contain non-empty strings")
        normalized.append(item)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class ArchiveBatchRecord:
    batch_id: str
    repository_id: str
    base_main_hash: str
    status: BaselineBatchStatus | str = BaselineBatchStatus.OPEN
    archive_gate_status: BaselineBatchArchiveGateStatus | str = (
        BaselineBatchArchiveGateStatus.COLLECTING_CONFIRMATIONS
    )
    opened_by_actor_id: str | None = None
    open_reason: str | None = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    archive_gate_frozen_reason: str | None = None
    workspace_confirmation_set_hash: str | None = None
    candidate_set_hash: str | None = None
    selected_modified_candidate_id: str | None = None
    selected_initial_candidate_ids: tuple[str, ...] = field(default_factory=tuple)
    version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("batch_id", "repository_id", "base_main_hash"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "status", BaselineBatchStatus(self.status))
        object.__setattr__(
            self,
            "archive_gate_status",
            BaselineBatchArchiveGateStatus(self.archive_gate_status),
        )
        for field_name in ("opened_by_actor_id", "open_reason", "archive_gate_frozen_reason"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        for field_name in (
            "workspace_confirmation_set_hash",
            "candidate_set_hash",
            "selected_modified_candidate_id",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        if self.selected_initial_candidate_ids and any(
            not isinstance(item, str) or not item for item in self.selected_initial_candidate_ids
        ):
            raise ValueError("selected_initial_candidate_ids must contain non-empty strings")
        for field_name in ("opened_at", "closed_at", "invalidated_at"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime or None")
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")

    def mark_archive_gate_ready(self) -> "ArchiveBatchRecord":
        if self.status != BaselineBatchStatus.OPEN:
            return self
        if self.archive_gate_status in {
            BaselineBatchArchiveGateStatus.ARCHIVING,
            BaselineBatchArchiveGateStatus.ARCHIVE_FROZEN,
            BaselineBatchArchiveGateStatus.ARCHIVED,
        }:
            return self
        return replace(
            self,
            archive_gate_status=BaselineBatchArchiveGateStatus.READY_FOR_ARCHIVE,
            version=self.version + 1,
        )

    def mark_archive_gate_collecting(self) -> "ArchiveBatchRecord":
        if self.status != BaselineBatchStatus.OPEN:
            return self
        if self.archive_gate_status in {
            BaselineBatchArchiveGateStatus.ARCHIVING,
            BaselineBatchArchiveGateStatus.ARCHIVE_FROZEN,
            BaselineBatchArchiveGateStatus.ARCHIVED,
        }:
            return self
        return replace(
            self,
            archive_gate_status=BaselineBatchArchiveGateStatus.COLLECTING_CONFIRMATIONS,
            version=self.version + 1,
        )

    def ensure_ready_for_archive(self, action: str) -> None:
        if self.status != BaselineBatchStatus.OPEN:
            raise ValueError(f"{action} requires OPEN batch, got {self.status.value}")
        if self.archive_gate_status != BaselineBatchArchiveGateStatus.READY_FOR_ARCHIVE:
            raise ValueError(
                f"{action} requires READY_FOR_ARCHIVE gate, got {self.archive_gate_status.value}"
            )

    def start_archive(self) -> "ArchiveBatchRecord":
        self.ensure_ready_for_archive("execute_archive_mainline")
        return replace(
            self,
            archive_gate_status=BaselineBatchArchiveGateStatus.ARCHIVING,
            version=self.version + 1,
        )

    def complete_archive(self, *, closed_at: datetime) -> "ArchiveBatchRecord":
        if closed_at.tzinfo is None:
            raise ValueError("closed_at must be timezone-aware")
        return replace(
            self,
            status=BaselineBatchStatus.CLOSED,
            archive_gate_status=BaselineBatchArchiveGateStatus.ARCHIVED,
            closed_at=closed_at,
            version=self.version + 1,
        )

    def freeze_archive_gate(self, *, reason: str | None = None) -> "ArchiveBatchRecord":
        if reason is not None and (not isinstance(reason, str) or not reason):
            raise ValueError("reason must be a non-empty string or None")
        return replace(
            self,
            archive_gate_status=BaselineBatchArchiveGateStatus.ARCHIVE_FROZEN,
            archive_gate_frozen_reason=reason,
            version=self.version + 1,
        )

    def with_confirmation_hash(self, workspace_confirmation_set_hash: str) -> "ArchiveBatchRecord":
        if not isinstance(workspace_confirmation_set_hash, str) or not workspace_confirmation_set_hash:
            raise ValueError("workspace_confirmation_set_hash must be a non-empty string")
        return replace(
            self,
            workspace_confirmation_set_hash=workspace_confirmation_set_hash,
            version=self.version + 1,
        )

    def with_candidate_set_hash(self, candidate_set_hash: str) -> "ArchiveBatchRecord":
        if not isinstance(candidate_set_hash, str) or not candidate_set_hash:
            raise ValueError("candidate_set_hash must be a non-empty string")
        return replace(
            self,
            candidate_set_hash=candidate_set_hash,
            version=self.version + 1,
        )

    def with_selection(
        self,
        *,
        selected_modified_candidate_id: str,
        selected_initial_candidate_ids: tuple[str, ...],
    ) -> "ArchiveBatchRecord":
        if not isinstance(selected_modified_candidate_id, str) or not selected_modified_candidate_id:
            raise ValueError("selected_modified_candidate_id must be a non-empty string")
        if any(not isinstance(candidate_id, str) or not candidate_id for candidate_id in selected_initial_candidate_ids):
            raise ValueError("selected_initial_candidate_ids must contain non-empty strings")
        return replace(
            self,
            selected_modified_candidate_id=selected_modified_candidate_id,
            selected_initial_candidate_ids=tuple(selected_initial_candidate_ids),
            version=self.version + 1,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "batch_id": self.batch_id,
            "repository_id": self.repository_id,
            "base_main_hash": self.base_main_hash,
            "status": self.status.value,
            "archive_gate_status": self.archive_gate_status.value,
            "opened_by_actor_id": self.opened_by_actor_id,
            "open_reason": self.open_reason,
            "opened_at": self.opened_at.astimezone(timezone.utc).isoformat(),
            "closed_at": None if self.closed_at is None else self.closed_at.astimezone(timezone.utc).isoformat(),
            "invalidated_at": None if self.invalidated_at is None else self.invalidated_at.astimezone(timezone.utc).isoformat(),
            "invalidation_reason": self.invalidation_reason,
            "archive_gate_frozen_reason": self.archive_gate_frozen_reason,
            "workspace_confirmation_set_hash": self.workspace_confirmation_set_hash,
            "candidate_set_hash": self.candidate_set_hash,
            "selected_modified_candidate_id": self.selected_modified_candidate_id,
            "selected_initial_candidate_ids": list(self.selected_initial_candidate_ids),
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ArchiveBatchRecord":
        version_value = payload.get("version")
        if not isinstance(version_value, int) or isinstance(version_value, bool) or version_value < 1:
            raise TypeError("version must be a positive integer")
        opened_at = _optional_datetime(payload.get("opened_at"), field_name="opened_at")
        if opened_at is None:
            opened_at = datetime.now(timezone.utc)
        return cls(
            batch_id=_required_str(payload, "batch_id"),
            repository_id=_required_str(payload, "repository_id"),
            base_main_hash=_required_str(payload, "base_main_hash"),
            status=_required_str(payload, "status"),
            archive_gate_status=_required_str(payload, "archive_gate_status"),
            opened_by_actor_id=_optional_str(payload.get("opened_by_actor_id"), field_name="opened_by_actor_id"),
            open_reason=_optional_str(payload.get("open_reason"), field_name="open_reason"),
            opened_at=opened_at,
            closed_at=_optional_datetime(payload.get("closed_at"), field_name="closed_at"),
            invalidated_at=_optional_datetime(payload.get("invalidated_at"), field_name="invalidated_at"),
            invalidation_reason=_optional_str(payload.get("invalidation_reason"), field_name="invalidation_reason"),
            archive_gate_frozen_reason=_optional_str(payload.get("archive_gate_frozen_reason"), field_name="archive_gate_frozen_reason"),
            workspace_confirmation_set_hash=_optional_str(
                payload.get("workspace_confirmation_set_hash"),
                field_name="workspace_confirmation_set_hash",
            ),
            candidate_set_hash=_optional_str(
                payload.get("candidate_set_hash"),
                field_name="candidate_set_hash",
            ),
            selected_modified_candidate_id=_optional_str(
                payload.get("selected_modified_candidate_id"),
                field_name="selected_modified_candidate_id",
            ),
            selected_initial_candidate_ids=_optional_str_tuple(
                payload.get("selected_initial_candidate_ids"),
                field_name="selected_initial_candidate_ids",
            ),
            version=version_value,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceArchiveConfirmationRecord:
    confirmation_id: str
    batch_id: str
    workspace_id: str
    status: WorkspaceArchiveConfirmationStatus | str = (
        WorkspaceArchiveConfirmationStatus.CONFIRMED_DISCARDED
    )
    archive_candidate_id: str | None = None
    confirmed_by_actor_id: str | None = None
    reason: str | None = None
    confirmed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("confirmation_id", "batch_id", "workspace_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "status", WorkspaceArchiveConfirmationStatus(self.status))
        if self.archive_candidate_id is not None and (
            not isinstance(self.archive_candidate_id, str) or not self.archive_candidate_id
        ):
            raise ValueError("archive_candidate_id must be a non-empty string or None")
        for field_name in ("confirmed_by_actor_id", "reason"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        for field_name in ("confirmed_at", "created_at", "updated_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime")
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")

    def confirm_with_candidate(
        self,
        *,
        actor_id: str,
        archive_candidate_id: str,
        reason: str | None = None,
        confirmed_at: datetime | None = None,
    ) -> "WorkspaceArchiveConfirmationRecord":
        if not isinstance(actor_id, str) or not actor_id:
            raise ValueError("actor_id must be a non-empty string")
        if not isinstance(archive_candidate_id, str) or not archive_candidate_id:
            raise ValueError("archive_candidate_id must be a non-empty string")
        timestamp = confirmed_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return replace(
            self,
            status=WorkspaceArchiveConfirmationStatus.CONFIRMED_WITH_CANDIDATE,
            archive_candidate_id=archive_candidate_id,
            confirmed_by_actor_id=actor_id,
            reason=reason,
            confirmed_at=timestamp,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def confirm_discarded(
        self,
        *,
        actor_id: str,
        reason: str | None = None,
        confirmed_at: datetime | None = None,
    ) -> "WorkspaceArchiveConfirmationRecord":
        if not isinstance(actor_id, str) or not actor_id:
            raise ValueError("actor_id must be a non-empty string")
        timestamp = confirmed_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("confirmed_at must be timezone-aware")
        return replace(
            self,
            status=WorkspaceArchiveConfirmationStatus.CONFIRMED_DISCARDED,
            archive_candidate_id=None,
            confirmed_by_actor_id=actor_id,
            reason=reason,
            confirmed_at=timestamp,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "confirmation_id": self.confirmation_id,
            "batch_id": self.batch_id,
            "workspace_id": self.workspace_id,
            "status": self.status.value,
            "archive_candidate_id": self.archive_candidate_id,
            "confirmed_by_actor_id": self.confirmed_by_actor_id,
            "reason": self.reason,
            "confirmed_at": self.confirmed_at.astimezone(timezone.utc).isoformat(),
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "WorkspaceArchiveConfirmationRecord":
        version_value = payload.get("version")
        if not isinstance(version_value, int) or isinstance(version_value, bool) or version_value < 1:
            raise TypeError("version must be a positive integer")
        return cls(
            confirmation_id=_required_str(payload, "confirmation_id"),
            batch_id=_required_str(payload, "batch_id"),
            workspace_id=_required_str(payload, "workspace_id"),
            status=_required_str(payload, "status"),
            archive_candidate_id=_optional_str(payload.get("archive_candidate_id"), field_name="archive_candidate_id"),
            confirmed_by_actor_id=_optional_str(payload.get("confirmed_by_actor_id"), field_name="confirmed_by_actor_id"),
            reason=_optional_str(payload.get("reason"), field_name="reason"),
            confirmed_at=_optional_datetime(payload.get("confirmed_at"), field_name="confirmed_at") or datetime.now(timezone.utc),
            created_at=_optional_datetime(payload.get("created_at"), field_name="created_at") or datetime.now(timezone.utc),
            updated_at=_optional_datetime(payload.get("updated_at"), field_name="updated_at") or datetime.now(timezone.utc),
            version=version_value,
        )


@dataclass(frozen=True, slots=True)
class ArchiveCandidateRecord:
    candidate_id: str
    batch_id: str
    workspace_id: str
    source_kind: ArchiveCandidateSourceKind | str
    role: ArchiveCandidateRole | str
    status: ArchiveCandidateStatus | str = ArchiveCandidateStatus.NOT_ARCHIVED
    source_submission_id: str | None = None
    override_reason: str | None = None
    selected_for_archive: bool = False
    anomaly_resolution_required: bool = False
    configuration_generated_at: datetime | None = None
    abnormal_kind: str | None = None
    time_abnormal_reason: str | None = None
    created_by_actor_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("candidate_id", "batch_id", "workspace_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "source_kind", ArchiveCandidateSourceKind(self.source_kind))
        object.__setattr__(self, "role", ArchiveCandidateRole(self.role))
        object.__setattr__(self, "status", ArchiveCandidateStatus(self.status))
        for field_name in ("source_submission_id", "override_reason", "abnormal_kind", "time_abnormal_reason", "created_by_actor_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        if not isinstance(self.selected_for_archive, bool):
            raise TypeError("selected_for_archive must be a boolean")
        if not isinstance(self.anomaly_resolution_required, bool):
            raise TypeError("anomaly_resolution_required must be a boolean")
        if self.configuration_generated_at is not None:
            if not isinstance(self.configuration_generated_at, datetime):
                raise TypeError("configuration_generated_at must be a datetime or None")
            if self.configuration_generated_at.tzinfo is None:
                raise ValueError("configuration_generated_at must be timezone-aware")
        for field_name in ("created_at", "updated_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime")
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")

    def ensure_selectable_as_mainline(self) -> None:
        if self.status != ArchiveCandidateStatus.NOT_ARCHIVED:
            raise ValueError("mainline candidate must not already be archived")
        if self.role != ArchiveCandidateRole.MAINLINE_MODIFIED:
            raise ValueError("mainline candidate must have MAINLINE_MODIFIED role")
        if self.source_kind != ArchiveCandidateSourceKind.APPROVED_SUBMISSION and not self.override_reason:
            raise ValueError("mainline candidate requires override reason")

    def mark_archived_as_mainline(self) -> "ArchiveCandidateRecord":
        return replace(
            self,
            status=ArchiveCandidateStatus.ARCHIVED_AS_MAINLINE,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def mark_archived_as_history(self) -> "ArchiveCandidateRecord":
        return replace(
            self,
            status=ArchiveCandidateStatus.ARCHIVED_AS_HISTORY,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def mark_closed_not_archived(self) -> "ArchiveCandidateRecord":
        return replace(
            self,
            status=ArchiveCandidateStatus.CLOSED_NOT_ARCHIVED,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def select_for_archive(
        self,
        *,
        role: ArchiveCandidateRole,
        selected_for_archive: bool,
        override_reason: str | None = None,
        configuration_generated_at: datetime | None = None,
    ) -> "ArchiveCandidateRecord":
        if override_reason is not None and (not isinstance(override_reason, str) or not override_reason):
            raise ValueError("override_reason must be a non-empty string or None")
        if configuration_generated_at is not None:
            if configuration_generated_at.tzinfo is None:
                raise ValueError("configuration_generated_at must be timezone-aware")
        return replace(
            self,
            role=role,
            selected_for_archive=selected_for_archive,
            override_reason=override_reason if override_reason is not None else self.override_reason,
            configuration_generated_at=configuration_generated_at or self.configuration_generated_at,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def with_confirmation_metadata(
        self,
        *,
        anomaly_resolution_required: bool | None = None,
        abnormal_kind: str | None = None,
        time_abnormal_reason: str | None = None,
        source_submission_id: str | None = None,
    ) -> "ArchiveCandidateRecord":
        if anomaly_resolution_required is not None and not isinstance(anomaly_resolution_required, bool):
            raise TypeError("anomaly_resolution_required must be a boolean or None")
        for field_name, value in (
            ("abnormal_kind", abnormal_kind),
            ("time_abnormal_reason", time_abnormal_reason),
            ("source_submission_id", source_submission_id),
        ):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        return replace(
            self,
            anomaly_resolution_required=(
                self.anomaly_resolution_required
                if anomaly_resolution_required is None
                else anomaly_resolution_required
            ),
            abnormal_kind=abnormal_kind if abnormal_kind is not None else self.abnormal_kind,
            time_abnormal_reason=(
                time_abnormal_reason if time_abnormal_reason is not None else self.time_abnormal_reason
            ),
            source_submission_id=(
                source_submission_id if source_submission_id is not None else self.source_submission_id
            ),
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "batch_id": self.batch_id,
            "workspace_id": self.workspace_id,
            "source_kind": self.source_kind.value,
            "role": self.role.value,
            "status": self.status.value,
            "source_submission_id": self.source_submission_id,
            "override_reason": self.override_reason,
            "selected_for_archive": self.selected_for_archive,
            "anomaly_resolution_required": self.anomaly_resolution_required,
            "configuration_generated_at": (
                None
                if self.configuration_generated_at is None
                else self.configuration_generated_at.astimezone(timezone.utc).isoformat()
            ),
            "abnormal_kind": self.abnormal_kind,
            "time_abnormal_reason": self.time_abnormal_reason,
            "created_by_actor_id": self.created_by_actor_id,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ArchiveCandidateRecord":
        version_value = payload.get("version")
        if not isinstance(version_value, int) or isinstance(version_value, bool) or version_value < 1:
            raise TypeError("version must be a positive integer")
        configuration_generated_at = _optional_datetime(
            payload.get("configuration_generated_at"),
            field_name="configuration_generated_at",
        )
        created_at = _optional_datetime(payload.get("created_at"), field_name="created_at")
        updated_at = _optional_datetime(payload.get("updated_at"), field_name="updated_at")
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        if updated_at is None:
            updated_at = created_at
        return cls(
            candidate_id=_required_str(payload, "candidate_id"),
            batch_id=_required_str(payload, "batch_id"),
            workspace_id=_required_str(payload, "workspace_id"),
            source_kind=_required_str(payload, "source_kind"),
            role=_required_str(payload, "role"),
            status=_required_str(payload, "status"),
            source_submission_id=_optional_str(payload.get("source_submission_id"), field_name="source_submission_id"),
            override_reason=_optional_str(payload.get("override_reason"), field_name="override_reason"),
            selected_for_archive=_optional_bool(payload.get("selected_for_archive"), field_name="selected_for_archive"),
            anomaly_resolution_required=_optional_bool(
                payload.get("anomaly_resolution_required"),
                field_name="anomaly_resolution_required",
            ),
            configuration_generated_at=configuration_generated_at,
            abnormal_kind=_optional_str(payload.get("abnormal_kind"), field_name="abnormal_kind"),
            time_abnormal_reason=_optional_str(payload.get("time_abnormal_reason"), field_name="time_abnormal_reason"),
            created_by_actor_id=_optional_str(payload.get("created_by_actor_id"), field_name="created_by_actor_id"),
            created_at=created_at,
            updated_at=updated_at,
            version=version_value,
        )


@dataclass(frozen=True, slots=True)
class ArchiveAnomalyResolutionRecord:
    resolution_id: str
    batch_id: str
    candidate_id: str
    resolution_type: AnomalyResolutionType | str
    reason: str
    resolved_by_actor_id: str
    resolved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("resolution_id", "batch_id", "candidate_id", "reason", "resolved_by_actor_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "resolution_type", AnomalyResolutionType(self.resolution_type))
        for field_name in ("resolved_at", "created_at", "updated_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime")
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")

    def to_payload(self) -> dict[str, object]:
        return {
            "resolution_id": self.resolution_id,
            "batch_id": self.batch_id,
            "candidate_id": self.candidate_id,
            "resolution_type": self.resolution_type.value,
            "reason": self.reason,
            "resolved_by_actor_id": self.resolved_by_actor_id,
            "resolved_at": self.resolved_at.astimezone(timezone.utc).isoformat(),
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ArchiveAnomalyResolutionRecord":
        version_value = payload.get("version")
        if not isinstance(version_value, int) or isinstance(version_value, bool) or version_value < 1:
            raise TypeError("version must be a positive integer")
        return cls(
            resolution_id=_required_str(payload, "resolution_id"),
            batch_id=_required_str(payload, "batch_id"),
            candidate_id=_required_str(payload, "candidate_id"),
            resolution_type=_required_str(payload, "resolution_type"),
            reason=_required_str(payload, "reason"),
            resolved_by_actor_id=_required_str(payload, "resolved_by_actor_id"),
            resolved_at=_optional_datetime(payload.get("resolved_at"), field_name="resolved_at") or datetime.now(timezone.utc),
            created_at=_optional_datetime(payload.get("created_at"), field_name="created_at") or datetime.now(timezone.utc),
            updated_at=_optional_datetime(payload.get("updated_at"), field_name="updated_at") or datetime.now(timezone.utc),
            version=version_value,
        )


@dataclass(frozen=True, slots=True)
class ArchiveExecutionRecord:
    execution_id: str
    batch_id: str
    command_idempotency_key: str
    command_payload_hash: str
    requested_by_actor_id: str
    selected_modified_candidate_id: str
    selected_initial_candidate_ids: tuple[str, ...]
    status: ArchiveExecutionStatus | str = ArchiveExecutionStatus.PENDING
    transfer_status: ArchiveExecutionTransferStatus | str = ArchiveExecutionTransferStatus.PENDING
    old_main_hash: str | None = None
    new_main_hash: str | None = None
    open_ref_repository_ref: str | None = None
    open_ref_snapshot_id: str | None = None
    open_ref_snapshot_digest: str | None = None
    failure_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def __post_init__(self) -> None:
        for field_name in (
            "execution_id",
            "batch_id",
            "command_idempotency_key",
            "command_payload_hash",
            "requested_by_actor_id",
            "selected_modified_candidate_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if any(not isinstance(item, str) or not item for item in self.selected_initial_candidate_ids):
            raise ValueError("selected_initial_candidate_ids must contain non-empty strings")
        object.__setattr__(self, "status", ArchiveExecutionStatus(self.status))
        object.__setattr__(self, "transfer_status", ArchiveExecutionTransferStatus(self.transfer_status))
        for field_name in (
            "old_main_hash",
            "new_main_hash",
            "open_ref_repository_ref",
            "open_ref_snapshot_id",
            "open_ref_snapshot_digest",
            "failure_reason",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        for field_name in ("created_at", "updated_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime")
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")

    def mark_executing(self) -> "ArchiveExecutionRecord":
        return replace(
            self,
            status=ArchiveExecutionStatus.EXECUTING,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def mark_succeeded(
        self,
        *,
        new_main_hash: str,
        transfer_status: ArchiveExecutionTransferStatus | str,
        failure_reason: str | None = None,
    ) -> "ArchiveExecutionRecord":
        if not isinstance(new_main_hash, str) or not new_main_hash:
            raise ValueError("new_main_hash must be a non-empty string")
        transfer_status_value = ArchiveExecutionTransferStatus(transfer_status)
        status = (
            ArchiveExecutionStatus.SUCCEEDED_TRANSFER_FAILED
            if transfer_status_value is ArchiveExecutionTransferStatus.TRANSFER_FAILED
            else ArchiveExecutionStatus.SUCCEEDED
        )
        if failure_reason is not None and (not isinstance(failure_reason, str) or not failure_reason):
            raise ValueError("failure_reason must be a non-empty string or None")
        return replace(
            self,
            status=status,
            transfer_status=transfer_status_value,
            new_main_hash=new_main_hash,
            failure_reason=failure_reason,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def mark_open_ref_completed(
        self,
        *,
        open_ref_repository_ref: str,
        open_ref_snapshot_id: str,
        open_ref_snapshot_digest: str,
    ) -> "ArchiveExecutionRecord":
        for field_name, value in (
            ("open_ref_repository_ref", open_ref_repository_ref),
            ("open_ref_snapshot_id", open_ref_snapshot_id),
            ("open_ref_snapshot_digest", open_ref_snapshot_digest),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        return replace(
            self,
            open_ref_repository_ref=open_ref_repository_ref,
            open_ref_snapshot_id=open_ref_snapshot_id,
            open_ref_snapshot_digest=open_ref_snapshot_digest,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def mark_failed_frozen(self, *, reason: str) -> "ArchiveExecutionRecord":
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string")
        return replace(
            self,
            status=ArchiveExecutionStatus.FAILED_FROZEN,
            failure_reason=reason,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "execution_id": self.execution_id,
            "batch_id": self.batch_id,
            "command_idempotency_key": self.command_idempotency_key,
            "command_payload_hash": self.command_payload_hash,
            "requested_by_actor_id": self.requested_by_actor_id,
            "selected_modified_candidate_id": self.selected_modified_candidate_id,
            "selected_initial_candidate_ids": list(self.selected_initial_candidate_ids),
            "status": self.status.value,
            "transfer_status": self.transfer_status.value,
            "old_main_hash": self.old_main_hash,
            "new_main_hash": self.new_main_hash,
            "open_ref_repository_ref": self.open_ref_repository_ref,
            "open_ref_snapshot_id": self.open_ref_snapshot_id,
            "open_ref_snapshot_digest": self.open_ref_snapshot_digest,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "ArchiveExecutionRecord":
        version_value = payload.get("version")
        if not isinstance(version_value, int) or isinstance(version_value, bool) or version_value < 1:
            raise TypeError("version must be a positive integer")
        created_at = _optional_datetime(payload.get("created_at"), field_name="created_at")
        updated_at = _optional_datetime(payload.get("updated_at"), field_name="updated_at")
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        if updated_at is None:
            updated_at = created_at
        return cls(
            execution_id=_required_str(payload, "execution_id"),
            batch_id=_required_str(payload, "batch_id"),
            command_idempotency_key=_required_str(payload, "command_idempotency_key"),
            command_payload_hash=_required_str(payload, "command_payload_hash"),
            requested_by_actor_id=_required_str(payload, "requested_by_actor_id"),
            selected_modified_candidate_id=_required_str(payload, "selected_modified_candidate_id"),
            selected_initial_candidate_ids=_optional_str_tuple(
                payload.get("selected_initial_candidate_ids"),
                field_name="selected_initial_candidate_ids",
            ),
            status=_required_str(payload, "status"),
            transfer_status=_required_str(payload, "transfer_status"),
            old_main_hash=_optional_str(payload.get("old_main_hash"), field_name="old_main_hash"),
            new_main_hash=_optional_str(payload.get("new_main_hash"), field_name="new_main_hash"),
            open_ref_repository_ref=_optional_str(payload.get("open_ref_repository_ref"), field_name="open_ref_repository_ref"),
            open_ref_snapshot_id=_optional_str(payload.get("open_ref_snapshot_id"), field_name="open_ref_snapshot_id"),
            open_ref_snapshot_digest=_optional_str(payload.get("open_ref_snapshot_digest"), field_name="open_ref_snapshot_digest"),
            failure_reason=_optional_str(payload.get("failure_reason"), field_name="failure_reason"),
            created_at=created_at,
            updated_at=updated_at,
            version=version_value,
        )
