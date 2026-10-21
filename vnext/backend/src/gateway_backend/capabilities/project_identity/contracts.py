"""Public value contracts for canonical project identity assessment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableSet

PROJECT_IDENTITY_SCHEMA_VERSION = "project-identity-assessment/v1"
PROJECT_IDENTITY_RULE_VERSION = "version-manager-overlap/v1"


class ProjectIdentityStatus(StrEnum):
    SAME_PROJECT = "SAME_PROJECT"
    DIFFERENT_PROJECT = "DIFFERENT_PROJECT"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True, slots=True)
class ProjectIdentityInput:
    snapshot_digest: DigestRef
    table_set: SnapshotTableSet | None

    def __post_init__(self) -> None:
        if type(self.snapshot_digest) is not DigestRef:
            raise ValueError("snapshot_digest must be DigestRef")
        if self.table_set is not None:
            if type(self.table_set) is not SnapshotTableSet:
                raise ValueError("table_set must be SnapshotTableSet or None")
            if self.table_set.snapshot_digest != self.snapshot_digest:
                raise ValueError("table_set snapshot digest must match snapshot_digest")


@dataclass(frozen=True, slots=True)
class ProjectIdentityAssessment:
    schema_version: str
    rule_version: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    status: ProjectIdentityStatus
    assessment_digest: DigestRef
    comparable_columns: tuple[str, ...]
    before_row_count: int
    current_row_count: int
    before_distinct_entry_count: int
    current_distinct_entry_count: int
    matched_entry_count: int
    before_entry_set_digest: DigestRef | None
    current_entry_set_digest: DigestRef | None
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != PROJECT_IDENTITY_SCHEMA_VERSION:
            raise ValueError("schema_version is unsupported")
        if self.rule_version != PROJECT_IDENTITY_RULE_VERSION:
            raise ValueError("rule_version is unsupported")
        for field_name in ("before_snapshot_digest", "current_snapshot_digest", "assessment_digest"):
            if type(getattr(self, field_name)) is not DigestRef:
                raise ValueError(f"{field_name} must be DigestRef")
        if type(self.status) is not ProjectIdentityStatus:
            raise ValueError("status must be ProjectIdentityStatus")
        if type(self.comparable_columns) is not tuple or any(
            type(item) is not str or item == "" for item in self.comparable_columns
        ):
            raise ValueError("comparable_columns must contain non-empty strings")
        if self.comparable_columns != tuple(sorted(set(self.comparable_columns))):
            raise ValueError("comparable_columns must be sorted and unique")
        for field_name in (
            "before_row_count",
            "current_row_count",
            "before_distinct_entry_count",
            "current_distinct_entry_count",
            "matched_entry_count",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in ("before_entry_set_digest", "current_entry_set_digest"):
            value = getattr(self, field_name)
            if value is not None and type(value) is not DigestRef:
                raise ValueError(f"{field_name} must be DigestRef or None")
        if type(self.diagnostics) is not tuple or any(
            type(item) is not str or item == "" for item in self.diagnostics
        ):
            raise ValueError("diagnostics must contain non-empty strings")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))):
            raise ValueError("diagnostics must be sorted and unique")
        if self.status is ProjectIdentityStatus.UNVERIFIABLE:
            if not self.diagnostics:
                raise ValueError("UNVERIFIABLE assessment requires diagnostics")
        elif self.diagnostics:
            raise ValueError("verifiable assessment must not contain diagnostics")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rule_version": self.rule_version,
            "before_snapshot_digest": self.before_snapshot_digest.value,
            "current_snapshot_digest": self.current_snapshot_digest.value,
            "status": self.status.value,
            "comparable_columns": list(self.comparable_columns),
            "before_row_count": self.before_row_count,
            "current_row_count": self.current_row_count,
            "before_distinct_entry_count": self.before_distinct_entry_count,
            "current_distinct_entry_count": self.current_distinct_entry_count,
            "matched_entry_count": self.matched_entry_count,
            "before_entry_set_digest": (
                None if self.before_entry_set_digest is None else self.before_entry_set_digest.value
            ),
            "current_entry_set_digest": (
                None if self.current_entry_set_digest is None else self.current_entry_set_digest.value
            ),
            "diagnostics": list(self.diagnostics),
            "assessment_digest": self.assessment_digest.value,
        }


__all__ = [
    "PROJECT_IDENTITY_RULE_VERSION",
    "PROJECT_IDENTITY_SCHEMA_VERSION",
    "ProjectIdentityAssessment",
    "ProjectIdentityInput",
    "ProjectIdentityStatus",
]
