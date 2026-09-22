"""Archive domain records for persisted plans, results and audit events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ArchiveDispositionKind(StrEnum):
    ARCHIVED_BASELINE = "ARCHIVED_BASELINE"
    CLOSED_NOT_ARCHIVED = "CLOSED_NOT_ARCHIVED"


class ArchiveSubjectKind(StrEnum):
    CONFIRM_SELECTION = "CONFIRM_SELECTION"
    APPROVED_SIBLING_EXCLUDED = "APPROVED_SIBLING_EXCLUDED"


class ArchiveConfirmationAction(StrEnum):
    CONFIRM = "CONFIRM"
    REVOKE = "REVOKE"


class ArchiveAnomalyResolutionAction(StrEnum):
    ACKNOWLEDGE_EXCLUSION = "ACKNOWLEDGE_EXCLUSION"
    REVOKE = "REVOKE"


class ArchiveCommandKind(StrEnum):
    START = "START"
    CONFIRMATION = "CONFIRMATION"
    RESOLUTION = "RESOLUTION"


@dataclass(frozen=True, slots=True)
class ArchiveAuditReference:
    subject_digest: str
    sequence: int

    def __post_init__(self) -> None:
        if type(self.subject_digest) is not str or not self.subject_digest:
            raise ValueError("subject_digest must be a non-empty string")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ArchiveDisposition:
    submission_id: str
    disposition: ArchiveDispositionKind

    def __post_init__(self) -> None:
        if type(self.submission_id) is not str or not self.submission_id:
            raise ValueError("submission_id must be a non-empty string")
        if type(self.disposition) is not ArchiveDispositionKind:
            raise ValueError("disposition must be ArchiveDispositionKind")


@dataclass(frozen=True, slots=True)
class ArchivePlan:
    plan_id: str
    repository_id: str
    gateway_device_external_key: str
    business_project_id: str
    idempotency_key: str
    request_fingerprint: str
    accepted_by: str
    accepted_at: datetime
    old_baseline_node_id: str
    old_baseline_commit_id: str
    old_baseline_head_version: int
    candidate_set_digest: str
    selected_submission_id: str
    selected_candidate_digest: str
    selected_repository_commit_id: str
    confirmation_refs: tuple[ArchiveAuditReference, ...]
    anomaly_resolution_refs: tuple[ArchiveAuditReference, ...]
    frozen_input_json: str

    def __post_init__(self) -> None:
        if type(self.plan_id) is not str or not self.plan_id:
            raise ValueError("plan_id must be a non-empty string")
        if type(self.repository_id) is not str or not self.repository_id:
            raise ValueError("repository_id must be a non-empty string")
        if type(self.gateway_device_external_key) is not str or not self.gateway_device_external_key:
            raise ValueError("gateway_device_external_key must be a non-empty string")
        if type(self.business_project_id) is not str or not self.business_project_id:
            raise ValueError("business_project_id must be a non-empty string")
        if type(self.idempotency_key) is not str or not self.idempotency_key:
            raise ValueError("idempotency_key must be a non-empty string")
        if type(self.request_fingerprint) is not str or not self.request_fingerprint:
            raise ValueError("request_fingerprint must be a non-empty string")
        if type(self.accepted_by) is not str or not self.accepted_by:
            raise ValueError("accepted_by must be a non-empty string")
        if self.accepted_at.tzinfo is None or self.accepted_at.utcoffset() is None:
            raise ValueError("accepted_at must be an aware datetime")
        if type(self.old_baseline_head_version) is not int or self.old_baseline_head_version < 0:
            raise ValueError("old_baseline_head_version must be a non-negative integer")
        if type(self.confirmation_refs) is not tuple:
            raise ValueError("confirmation_refs must be a tuple")
        if type(self.anomaly_resolution_refs) is not tuple:
            raise ValueError("anomaly_resolution_refs must be a tuple")


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    result_id: str
    plan_id: str
    baseline_node_id: str
    archived_at: datetime
    dispositions: tuple[ArchiveDisposition, ...]

    def __post_init__(self) -> None:
        if type(self.result_id) is not str or not self.result_id:
            raise ValueError("result_id must be a non-empty string")
        if type(self.plan_id) is not str or not self.plan_id:
            raise ValueError("plan_id must be a non-empty string")
        if type(self.baseline_node_id) is not str or not self.baseline_node_id:
            raise ValueError("baseline_node_id must be a non-empty string")
        if self.archived_at.tzinfo is None or self.archived_at.utcoffset() is None:
            raise ValueError("archived_at must be an aware datetime")
        if type(self.dispositions) is not tuple:
            raise ValueError("dispositions must be a tuple")


@dataclass(frozen=True, slots=True)
class ArchiveConfirmationEvent:
    event_id: str
    repository_id: str
    gateway_device_external_key: str
    business_project_id: str
    subject_kind: ArchiveSubjectKind
    subject_digest: str
    sequence: int
    action: ArchiveConfirmationAction
    reason: str | None
    actor_id: str
    occurred_at: datetime
    idempotency_key: str
    request_fingerprint: str
    request_payload_json: str

    def __post_init__(self) -> None:
        if self.subject_kind is not ArchiveSubjectKind.CONFIRM_SELECTION:
            raise ValueError("confirmation event subject_kind must be CONFIRM_SELECTION")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if self.action is ArchiveConfirmationAction.REVOKE:
            if type(self.reason) is not str or not self.reason:
                raise ValueError("reason must be a non-empty string")
        elif self.reason is not None and (
            type(self.reason) is not str or not self.reason
        ):
            raise ValueError("reason must be null or a non-empty string")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be an aware datetime")


@dataclass(frozen=True, slots=True)
class ArchiveAnomalyResolutionEvent:
    event_id: str
    repository_id: str
    gateway_device_external_key: str
    business_project_id: str
    subject_kind: ArchiveSubjectKind
    subject_digest: str
    sequence: int
    action: ArchiveAnomalyResolutionAction
    issue_code: str
    sibling_submission_id: str
    sibling_candidate_digest: str
    reason: str
    actor_id: str
    occurred_at: datetime
    idempotency_key: str
    request_fingerprint: str
    request_payload_json: str

    def __post_init__(self) -> None:
        if self.subject_kind is not ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED:
            raise ValueError(
                "anomaly resolution event subject_kind must be APPROVED_SIBLING_EXCLUDED"
            )
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if type(self.reason) is not str or not self.reason:
            raise ValueError("reason must be a non-empty string")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be an aware datetime")
