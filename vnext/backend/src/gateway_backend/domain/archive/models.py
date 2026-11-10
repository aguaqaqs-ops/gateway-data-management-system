"""Archive domain records for persisted plans, results and audit events."""

from __future__ import annotations

import json
from gateway_backend.artifacts.types import validate_artifact_id

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SubmissionDispositionKind(StrEnum):
    ARCHIVED_BASELINE = "ARCHIVED_BASELINE"
    CLOSED_NOT_ARCHIVED = "CLOSED_NOT_ARCHIVED"


class ArchiveSubjectKind(StrEnum):
    CONFIRM_SELECTION = "CONFIRM_SELECTION"
    APPROVED_SIBLING_EXCLUDED = "APPROVED_SIBLING_EXCLUDED"
    PROJECT_IDENTITY_EXCEPTION = "PROJECT_IDENTITY_EXCEPTION"
    CONFIGURATION_SOURCE = "CONFIGURATION_SOURCE"
    CONFIGURATION_TIME_QUALITY = "CONFIGURATION_TIME_QUALITY"
    CONFIGURATION_TIME_ORDER = "CONFIGURATION_TIME_ORDER"


class ArchiveConfirmationAction(StrEnum):
    CONFIRM = "CONFIRM"
    REVOKE = "REVOKE"


class ArchiveAnomalyResolutionAction(StrEnum):
    ACKNOWLEDGE_EXCLUSION = "ACKNOWLEDGE_EXCLUSION"
    ACKNOWLEDGE_IDENTITY_EXCEPTION = "ACKNOWLEDGE_IDENTITY_EXCEPTION"
    ACKNOWLEDGE_SOURCE_EXCEPTION = "ACKNOWLEDGE_SOURCE_EXCEPTION"
    ACKNOWLEDGE_TIME_QUALITY = "ACKNOWLEDGE_TIME_QUALITY"
    ACKNOWLEDGE_TIME_ORDER = "ACKNOWLEDGE_TIME_ORDER"
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
        if type(self.sequence) is not int or not 0 <= self.sequence <= 9007199254740991:
            raise ValueError("sequence must be a non-negative integer")


class SubmissionDispositionSourceKind(StrEnum):
    ARCHIVE = "ARCHIVE"
    MANUAL_CLOSE = "MANUAL_CLOSE"


@dataclass(frozen=True, slots=True)
class ManualSubmissionClosure:
    closed_by: str
    closed_at: datetime
    reason: str
    idempotency_key: str
    request_fingerprint: str
    expected_review_version: int
    expected_baseline_node_id: str
    expected_baseline_head_version: int
    workspace_id: str
    workspace_generation: int
    upload_revision_id: str
    preview_result_id: str
    workspace_version: int
    configuration_facts_digest: str

    def __post_init__(self) -> None:
        for name in ("closed_by", "reason", "idempotency_key", "request_fingerprint",
            "expected_baseline_node_id", "workspace_id", "upload_revision_id", "preview_result_id", "configuration_facts_digest"):
            value = getattr(self, name)
            if type(value) is not str or not value or len(value.encode("utf-8")) > (4096 if name == "reason" else 255):
                raise ValueError("invalid manual closure text binding")
        for value in (self.expected_review_version, self.expected_baseline_head_version,
            self.workspace_generation, self.workspace_version):
            if type(value) is not int or not 0 <= value <= 9007199254740991:
                raise ValueError("invalid manual closure safe integer")
        if self.closed_at.tzinfo is None or self.closed_at.utcoffset() is None:
            raise ValueError("manual closure time must be aware")


@dataclass(frozen=True, slots=True)
class SubmissionDisposition:
    submission_id: str
    disposition: SubmissionDispositionKind
    source_kind: SubmissionDispositionSourceKind
    result_id: str | None
    repository_id: str
    gateway_device_external_key: str
    business_project_id: str
    manual_closure: ManualSubmissionClosure | None = None

    def __post_init__(self) -> None:
        for value in (self.submission_id, self.repository_id, self.gateway_device_external_key, self.business_project_id):
            if type(value) is not str or not value:
                raise ValueError("submission disposition requires exact target/scope")
        if type(self.disposition) is not SubmissionDispositionKind or type(self.source_kind) is not SubmissionDispositionSourceKind:
            raise ValueError("invalid submission disposition kind/source")
        if self.source_kind is SubmissionDispositionSourceKind.ARCHIVE:
            if type(self.result_id) is not str or not self.result_id or self.manual_closure is not None:
                raise ValueError("archive disposition requires only a real result source")
        elif self.disposition is not SubmissionDispositionKind.CLOSED_NOT_ARCHIVED or self.result_id is not None or type(self.manual_closure) is not ManualSubmissionClosure:
            raise ValueError("manual close requires only a closed-not-archived source")


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
        validate_archive_artifact_bindings(json.loads(self.frozen_input_json))
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
    dispositions: tuple[SubmissionDisposition, ...]

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
        if type(self.sequence) is not int or not 1 <= self.sequence <= 9007199254740991:
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
    target_submission_id: str
    target_candidate_digest: str
    reason: str
    actor_id: str
    occurred_at: datetime
    idempotency_key: str
    request_fingerprint: str
    request_payload_json: str
    subject_payload_json: str

    def __post_init__(self) -> None:
        validate_archive_artifact_bindings(json.loads(self.subject_payload_json))
        if self.subject_kind not in {
            ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED,
            ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION,
            ArchiveSubjectKind.CONFIGURATION_SOURCE,
            ArchiveSubjectKind.CONFIGURATION_TIME_QUALITY,
            ArchiveSubjectKind.CONFIGURATION_TIME_ORDER,
        }:
            raise ValueError(
                "anomaly resolution event subject_kind must identify an archive anomaly"
            )
        if type(self.sequence) is not int or not 1 <= self.sequence <= 9007199254740991:
            raise ValueError("sequence must be a positive integer")
        if type(self.reason) is not str or not self.reason:
            raise ValueError("reason must be a non-empty string")
        for field_name in ("target_submission_id", "target_candidate_digest"):
            if type(getattr(self, field_name)) is not str or not getattr(self, field_name):
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.subject_kind is ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED and (
            self.action is ArchiveAnomalyResolutionAction.ACKNOWLEDGE_IDENTITY_EXCEPTION
        ):
            raise ValueError("approved sibling exclusions require ACKNOWLEDGE_EXCLUSION")
        if self.subject_kind is ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION and (
            self.action is ArchiveAnomalyResolutionAction.ACKNOWLEDGE_EXCLUSION
        ):
            raise ValueError("project identity exceptions require ACKNOWLEDGE_IDENTITY_EXCEPTION")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be an aware datetime")


def affirmative_resolution_action(kind: ArchiveSubjectKind) -> ArchiveAnomalyResolutionAction:
    return {
        ArchiveSubjectKind.APPROVED_SIBLING_EXCLUDED: ArchiveAnomalyResolutionAction.ACKNOWLEDGE_EXCLUSION,
        ArchiveSubjectKind.PROJECT_IDENTITY_EXCEPTION: ArchiveAnomalyResolutionAction.ACKNOWLEDGE_IDENTITY_EXCEPTION,
        ArchiveSubjectKind.CONFIGURATION_SOURCE: ArchiveAnomalyResolutionAction.ACKNOWLEDGE_SOURCE_EXCEPTION,
        ArchiveSubjectKind.CONFIGURATION_TIME_QUALITY: ArchiveAnomalyResolutionAction.ACKNOWLEDGE_TIME_QUALITY,
        ArchiveSubjectKind.CONFIGURATION_TIME_ORDER: ArchiveAnomalyResolutionAction.ACKNOWLEDGE_TIME_ORDER,
    }[kind]


def validate_archive_artifact_bindings(value: object) -> None:
    """Validate backend source bindings wherever the frozen archive embeds a subject."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "canonicalization_manifest_ref":
                validate_artifact_id(item)
            elif key == "source_artifact_id":
                if item is not None:
                    validate_artifact_id(item)
            elif key == "source_artifact_refs":
                if type(item) not in (list, tuple):
                    raise ValueError("archive source_artifact_refs must be a sequence")
                for artifact_id in item:
                    validate_artifact_id(artifact_id)
            else:
                validate_archive_artifact_bindings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            validate_archive_artifact_bindings(item)
