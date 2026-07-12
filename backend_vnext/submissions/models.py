from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum

from ..core.digests import DigestRef


class SubmissionStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class SubmissionArchiveStatus(StrEnum):
    NOT_ARCHIVED = "NOT_ARCHIVED"
    ARCHIVED_AS_MAINLINE = "ARCHIVED_AS_MAINLINE"
    ARCHIVED_AS_HISTORY = "ARCHIVED_AS_HISTORY"
    CLOSED_NOT_ARCHIVED = "CLOSED_NOT_ARCHIVED"


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


def _optional_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))


@dataclass(frozen=True, slots=True)
class SubmissionRecord:
    submission_id: str
    workspace_id: str
    batch_id: str | None = None
    status: SubmissionStatus | str = SubmissionStatus.PENDING_REVIEW
    archive_status: SubmissionArchiveStatus | str = SubmissionArchiveStatus.NOT_ARCHIVED
    submitter_actor_id: str | None = None
    source_package_id: str | None = None
    preview_binding_id: str | None = None
    preview_revision_id: str | None = None
    preview_source_digest: DigestRef | str | None = None
    submit_source_package_digest: DigestRef | str | None = None
    repository_id: str | None = None
    repository_target_ref: str | None = None
    repository_commit_hash: str | None = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_by_actor_id: str | None = None
    reviewed_at: datetime | None = None
    withdrawn_by_actor_id: str | None = None
    withdrawn_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def __post_init__(self) -> None:
        for field_name in ("submission_id", "workspace_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.batch_id is not None and (not isinstance(self.batch_id, str) or not self.batch_id):
            raise ValueError("batch_id must be a non-empty string or None")
        object.__setattr__(self, "status", SubmissionStatus(self.status))
        object.__setattr__(self, "archive_status", SubmissionArchiveStatus(self.archive_status))
        for field_name in (
            "submitter_actor_id",
            "source_package_id",
            "preview_binding_id",
            "preview_revision_id",
            "repository_id",
            "repository_target_ref",
            "repository_commit_hash",
            "reviewed_by_actor_id",
            "withdrawn_by_actor_id",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        object.__setattr__(self, "preview_source_digest", _optional_digest(self.preview_source_digest))
        object.__setattr__(self, "submit_source_package_digest", _optional_digest(self.submit_source_package_digest))
        for field_name in ("submitted_at", "created_at", "updated_at", "reviewed_at", "withdrawn_at"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime or None")
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")

    def start_review(
        self,
        *,
        reviewer_actor_id: str,
        reviewed_at: datetime | None = None,
    ) -> "SubmissionRecord":
        self._ensure_status(SubmissionStatus.PENDING_REVIEW, "start_submission_review")
        timestamp = reviewed_at or datetime.now(timezone.utc)
        return replace(
            self,
            status=SubmissionStatus.IN_REVIEW,
            reviewed_by_actor_id=reviewer_actor_id,
            reviewed_at=timestamp,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def approve(
        self,
        *,
        reviewer_actor_id: str,
        reviewed_at: datetime | None = None,
    ) -> "SubmissionRecord":
        self._ensure_status(SubmissionStatus.IN_REVIEW, "approve_submission")
        timestamp = reviewed_at or datetime.now(timezone.utc)
        return replace(
            self,
            status=SubmissionStatus.APPROVED,
            reviewed_by_actor_id=reviewer_actor_id,
            reviewed_at=timestamp,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def reject(
        self,
        *,
        reviewer_actor_id: str,
        reviewed_at: datetime | None = None,
    ) -> "SubmissionRecord":
        self._ensure_status(SubmissionStatus.IN_REVIEW, "reject_submission")
        timestamp = reviewed_at or datetime.now(timezone.utc)
        return replace(
            self,
            status=SubmissionStatus.REJECTED,
            reviewed_by_actor_id=reviewer_actor_id,
            reviewed_at=timestamp,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def withdraw(
        self,
        *,
        actor_id: str,
        withdrawn_at: datetime | None = None,
    ) -> "SubmissionRecord":
        self._ensure_status(SubmissionStatus.PENDING_REVIEW, "withdraw_submission")
        timestamp = withdrawn_at or datetime.now(timezone.utc)
        return replace(
            self,
            status=SubmissionStatus.WITHDRAWN,
            withdrawn_by_actor_id=actor_id,
            withdrawn_at=timestamp,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def mark_archived_as_mainline(self) -> "SubmissionRecord":
        return replace(
            self,
            archive_status=SubmissionArchiveStatus.ARCHIVED_AS_MAINLINE,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def mark_archived_as_history(self) -> "SubmissionRecord":
        return replace(
            self,
            archive_status=SubmissionArchiveStatus.ARCHIVED_AS_HISTORY,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def mark_closed_not_archived(self) -> "SubmissionRecord":
        return replace(
            self,
            archive_status=SubmissionArchiveStatus.CLOSED_NOT_ARCHIVED,
            updated_at=datetime.now(timezone.utc),
            version=self.version + 1,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "submission_id": self.submission_id,
            "workspace_id": self.workspace_id,
            "batch_id": self.batch_id,
            "status": self.status.value,
            "archive_status": self.archive_status.value,
            "submitter_actor_id": self.submitter_actor_id,
            "source_package_id": self.source_package_id,
            "preview_binding_id": self.preview_binding_id,
            "preview_revision_id": self.preview_revision_id,
            "preview_source_digest": (
                None
                if self.preview_source_digest is None
                else self.preview_source_digest.to_payload()
            ),
            "submit_source_package_digest": (
                None
                if self.submit_source_package_digest is None
                else self.submit_source_package_digest.to_payload()
            ),
            "repository_id": self.repository_id,
            "repository_target_ref": self.repository_target_ref,
            "repository_commit_hash": self.repository_commit_hash,
            "submitted_at": self.submitted_at.astimezone(timezone.utc).isoformat(),
            "reviewed_by_actor_id": self.reviewed_by_actor_id,
            "reviewed_at": (
                None
                if self.reviewed_at is None
                else self.reviewed_at.astimezone(timezone.utc).isoformat()
            ),
            "withdrawn_by_actor_id": self.withdrawn_by_actor_id,
            "withdrawn_at": (
                None
                if self.withdrawn_at is None
                else self.withdrawn_at.astimezone(timezone.utc).isoformat()
            ),
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SubmissionRecord":
        submitted_at = _optional_datetime(payload.get("submitted_at"), field_name="submitted_at")
        created_at = _optional_datetime(payload.get("created_at"), field_name="created_at")
        updated_at = _optional_datetime(payload.get("updated_at"), field_name="updated_at")
        reviewed_at = _optional_datetime(payload.get("reviewed_at"), field_name="reviewed_at")
        withdrawn_at = _optional_datetime(payload.get("withdrawn_at"), field_name="withdrawn_at")
        if submitted_at is None:
            submitted_at = datetime.now(timezone.utc)
        if created_at is None:
            created_at = submitted_at
        if updated_at is None:
            updated_at = submitted_at
        version_value = payload.get("version")
        if not isinstance(version_value, int) or isinstance(version_value, bool) or version_value < 1:
            raise TypeError("version must be a positive integer")
        return cls(
            submission_id=_required_str(payload, "submission_id"),
            workspace_id=_required_str(payload, "workspace_id"),
            batch_id=_optional_str(payload.get("batch_id"), field_name="batch_id"),
            status=_required_str(payload, "status"),
            archive_status=_required_str(payload, "archive_status"),
            submitter_actor_id=_optional_str(payload.get("submitter_actor_id"), field_name="submitter_actor_id"),
            source_package_id=_optional_str(payload.get("source_package_id"), field_name="source_package_id"),
            preview_binding_id=_optional_str(payload.get("preview_binding_id"), field_name="preview_binding_id"),
            preview_revision_id=_optional_str(payload.get("preview_revision_id"), field_name="preview_revision_id"),
            preview_source_digest=_optional_digest(payload.get("preview_source_digest")),
            submit_source_package_digest=_optional_digest(payload.get("submit_source_package_digest")),
            repository_id=_optional_str(payload.get("repository_id"), field_name="repository_id"),
            repository_target_ref=_optional_str(payload.get("repository_target_ref"), field_name="repository_target_ref"),
            repository_commit_hash=_optional_str(payload.get("repository_commit_hash"), field_name="repository_commit_hash"),
            submitted_at=submitted_at,
            reviewed_by_actor_id=_optional_str(payload.get("reviewed_by_actor_id"), field_name="reviewed_by_actor_id"),
            reviewed_at=reviewed_at,
            withdrawn_by_actor_id=_optional_str(payload.get("withdrawn_by_actor_id"), field_name="withdrawn_by_actor_id"),
            withdrawn_at=withdrawn_at,
            created_at=created_at,
            updated_at=updated_at,
            version=version_value,
        )

    def _ensure_status(self, expected: SubmissionStatus, action: str) -> None:
        if self.status != expected:
            raise ValueError(
                f"{action} requires {expected.value}, got {self.status.value}"
            )
