from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum

from ..contracts.submit import PreviewInputBinding


class WorkspaceStatus(StrEnum):
    EMPTY = "EMPTY"
    INITIAL_READY = "INITIAL_READY"
    PREVIEW_READY = "PREVIEW_READY"
    SUBMITTED = "SUBMITTED"
    CLOSED = "CLOSED"


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


@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    workspace_id: str
    batch_id: str | None = None
    status: WorkspaceStatus | str = WorkspaceStatus.EMPTY
    latest_preview_input_binding: PreviewInputBinding | None = None
    active_submit_operation_id: str | None = None
    submitted_submission_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_id, str) or not self.workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if self.batch_id is not None and (not isinstance(self.batch_id, str) or not self.batch_id):
            raise ValueError("batch_id must be a non-empty string or None")
        object.__setattr__(self, "status", WorkspaceStatus(self.status))
        if self.latest_preview_input_binding is not None and not isinstance(
            self.latest_preview_input_binding,
            PreviewInputBinding,
        ):
            raise TypeError("latest_preview_input_binding must be a PreviewInputBinding or None")
        if self.active_submit_operation_id is not None and (
            not isinstance(self.active_submit_operation_id, str) or not self.active_submit_operation_id
        ):
            raise ValueError("active_submit_operation_id must be a non-empty string or None")
        if self.submitted_submission_id is not None and (
            not isinstance(self.submitted_submission_id, str) or not self.submitted_submission_id
        ):
            raise ValueError("submitted_submission_id must be a non-empty string or None")
        for field_name in ("created_at", "updated_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime")
            if value.tzinfo is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if self.status in {WorkspaceStatus.PREVIEW_READY, WorkspaceStatus.SUBMITTED} and self.latest_preview_input_binding is None:
            raise ValueError(f"{self.status.value} workspace must include latest_preview_input_binding")
        if self.active_submit_operation_id is not None and self.status != WorkspaceStatus.PREVIEW_READY:
            raise ValueError("active_submit_operation_id is only valid while workspace is PREVIEW_READY")

    def record_preview_input_binding(
        self,
        preview_input_binding: PreviewInputBinding,
        *,
        updated_at: datetime | None = None,
    ) -> "WorkspaceRecord":
        if not isinstance(preview_input_binding, PreviewInputBinding):
            raise TypeError("preview_input_binding must be a PreviewInputBinding")
        timestamp = updated_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        return replace(
            self,
            status=WorkspaceStatus.PREVIEW_READY,
            latest_preview_input_binding=preview_input_binding,
            active_submit_operation_id=None,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def with_batch_id(
        self,
        batch_id: str | None,
        *,
        updated_at: datetime | None = None,
    ) -> "WorkspaceRecord":
        if batch_id is not None and (not isinstance(batch_id, str) or not batch_id):
            raise ValueError("batch_id must be a non-empty string or None")
        timestamp = updated_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        if self.batch_id == batch_id:
            return self
        return replace(
            self,
            batch_id=batch_id,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def ensure_submit_acceptance_ready(
        self,
        preview_input_binding: PreviewInputBinding,
    ) -> None:
        if self.status != WorkspaceStatus.PREVIEW_READY:
            raise ValueError(
                f"workspace {self.workspace_id} is not PREVIEW_READY"
            )
        if self.latest_preview_input_binding is None:
            raise ValueError("workspace does not have a preview binding")
        if self.latest_preview_input_binding != preview_input_binding:
            raise ValueError("preview binding does not match the latest workspace preview")
        if self.active_submit_operation_id is not None:
            raise ValueError("workspace already has an active submit operation")

    def start_submit_acceptance(
        self,
        operation_id: str,
        *,
        updated_at: datetime | None = None,
    ) -> "WorkspaceRecord":
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("operation_id must be a non-empty string")
        if self.status != WorkspaceStatus.PREVIEW_READY:
            raise ValueError("workspace must be PREVIEW_READY to start submit acceptance")
        if self.active_submit_operation_id is not None:
            raise ValueError("workspace already has an active submit operation")
        timestamp = updated_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        return replace(
            self,
            active_submit_operation_id=operation_id,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def clear_active_submit_operation(
        self,
        operation_id: str,
        *,
        updated_at: datetime | None = None,
    ) -> "WorkspaceRecord":
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("operation_id must be a non-empty string")
        if self.active_submit_operation_id != operation_id:
            return self
        timestamp = updated_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        return replace(
            self,
            active_submit_operation_id=None,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def complete_submit(
        self,
        operation_id: str,
        submission_id: str,
        *,
        updated_at: datetime | None = None,
    ) -> "WorkspaceRecord":
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("operation_id must be a non-empty string")
        if not isinstance(submission_id, str) or not submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if self.status != WorkspaceStatus.PREVIEW_READY:
            raise ValueError("workspace must be PREVIEW_READY to complete submit")
        if self.active_submit_operation_id != operation_id:
            raise ValueError("workspace submit operation does not match")
        timestamp = updated_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        return replace(
            self,
            status=WorkspaceStatus.SUBMITTED,
            active_submit_operation_id=None,
            submitted_submission_id=submission_id,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def close(
        self,
        *,
        updated_at: datetime | None = None,
    ) -> "WorkspaceRecord":
        timestamp = updated_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        return replace(
            self,
            status=WorkspaceStatus.CLOSED,
            active_submit_operation_id=None,
            submitted_submission_id=None,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def reopen_after_terminal_submission(
        self,
        submission_id: str,
        *,
        updated_at: datetime | None = None,
    ) -> "WorkspaceRecord":
        if not isinstance(submission_id, str) or not submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if self.submitted_submission_id != submission_id:
            return self
        timestamp = updated_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must be timezone-aware")
        return replace(
            self,
            status=WorkspaceStatus.EMPTY,
            latest_preview_input_binding=None,
            active_submit_operation_id=None,
            submitted_submission_id=None,
            updated_at=timestamp,
            version=self.version + 1,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace_id,
            "batch_id": self.batch_id,
            "status": self.status.value,
            "latest_preview_input_binding": (
                None
                if self.latest_preview_input_binding is None
                else self.latest_preview_input_binding.to_payload()
            ),
            "active_submit_operation_id": self.active_submit_operation_id,
            "submitted_submission_id": self.submitted_submission_id,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "version": self.version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "WorkspaceRecord":
        preview_payload = payload.get("latest_preview_input_binding")
        if preview_payload is not None and not isinstance(preview_payload, Mapping):
            raise TypeError("latest_preview_input_binding payload must be a mapping or null")
        created_at_value = _optional_datetime(payload.get("created_at"), field_name="created_at")
        updated_at_value = _optional_datetime(payload.get("updated_at"), field_name="updated_at")
        if created_at_value is None:
            created_at_value = datetime.now(timezone.utc)
        if updated_at_value is None:
            updated_at_value = created_at_value
        version_value = payload.get("version")
        if not isinstance(version_value, int) or isinstance(version_value, bool) or version_value < 1:
            raise TypeError("version must be a positive integer")
        return cls(
            workspace_id=_required_str(payload, "workspace_id"),
            batch_id=_optional_str(payload.get("batch_id"), field_name="batch_id"),
            status=_required_str(payload, "status"),
            latest_preview_input_binding=(
                None
                if preview_payload is None
                else PreviewInputBinding.from_payload(preview_payload)
            ),
            active_submit_operation_id=_optional_str(
                payload.get("active_submit_operation_id"),
                field_name="active_submit_operation_id",
            ),
            submitted_submission_id=_optional_str(
                payload.get("submitted_submission_id"),
                field_name="submitted_submission_id",
            ),
            created_at=created_at_value,
            updated_at=updated_at_value,
            version=version_value,
        )
