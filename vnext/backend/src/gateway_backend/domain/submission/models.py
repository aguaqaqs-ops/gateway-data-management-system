"""SubmitAttempt and Submission domain records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class SubmitAttemptState(StrEnum):
    PREPARED = "PREPARED"
    EFFECT_PENDING = "EFFECT_PENDING"
    FINALIZED = "FINALIZED"
    ABORTED = "ABORTED"


class SubmitTargetRef(StrEnum):
    MAIN = "main"


class SubmitVerificationPolicy(StrEnum):
    STRUCTURAL = "STRUCTURAL"


class SubmitUnknownTypePolicy(StrEnum):
    REJECT = "REJECT"


class BuilderMutationPolicy(StrEnum):
    REBUILD_ALWAYS = "REBUILD_ALWAYS"


@dataclass(frozen=True, slots=True)
class BackendArtifactRef:
    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str

    def __post_init__(self) -> None:
        if type(self.artifact_id) is not str or not self.artifact_id:
            raise ValueError("artifact_id must be a non-empty string")
        if type(self.media_type) is not str or not self.media_type:
            raise ValueError("media_type must be a non-empty string")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        if type(self.raw_sha256) is not str or not self.raw_sha256:
            raise ValueError("raw_sha256 must be a non-empty string")


@dataclass(frozen=True, slots=True)
class RepositoryArtifactRef:
    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str

    def __post_init__(self) -> None:
        if type(self.artifact_id) is not str or not self.artifact_id:
            raise ValueError("artifact_id must be a non-empty string")
        if type(self.media_type) is not str or not self.media_type:
            raise ValueError("media_type must be a non-empty string")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        if type(self.raw_sha256) is not str or not self.raw_sha256:
            raise ValueError("raw_sha256 must be a non-empty string")


@dataclass(frozen=True, slots=True)
class SubmitAttempt:
    submit_attempt_id: str
    workspace_id: str
    workspace_generation: int
    upload_revision_id: str
    preview_result_id: str
    repository_id: str
    business_baseline_node_id: str
    business_baseline_commit_id: str
    baseline_head_version: int
    repository_expected_commit_id: str
    canonical_business_digest: str
    source_digest: str
    snapshot_digest: str
    source_artifact_refs: Sequence[str]
    snapshot_table_artifact_refs: Sequence[str]
    preview_ready_closure_ref: str
    preview_ready_closure_digest: str
    canonicalization_manifest_ref: str | None
    canonicalization_manifest_digest: str | None
    repository_import_artifact_ref: BackendArtifactRef | None
    repository_artifact_ref: RepositoryArtifactRef | None
    repository_operation_id: str | None
    repository_operation_evidence: str | None
    requested_target_ref: SubmitTargetRef
    requested_verification_policy: SubmitVerificationPolicy
    requested_unknown_type_policy: SubmitUnknownTypePolicy
    builder_mutation_policy: BuilderMutationPolicy
    accept_idempotency_key: str
    accept_request_fingerprint: str
    repository_upload_idempotency_key: str
    repository_import_idempotency_key: str
    operation_id: str
    state: SubmitAttemptState
    submission_id: str | None
    optimistic_version: int
    created_by: str
    created_at: datetime
    effect_pending_at: datetime | None = None
    finalized_at: datetime | None = None
    aborted_at: datetime | None = None
    abort_code: str | None = None

    def __post_init__(self) -> None:
        from gateway_backend.domain.submission.policies import assert_submit_attempt_invariants

        _validate_non_empty_str(self.submit_attempt_id, "submit_attempt_id")
        _validate_non_empty_str(self.workspace_id, "workspace_id")
        if type(self.workspace_generation) is not int or self.workspace_generation < 0:
            raise ValueError("workspace_generation must be a non-negative integer")
        _validate_non_empty_str(self.upload_revision_id, "upload_revision_id")
        _validate_non_empty_str(self.preview_result_id, "preview_result_id")
        _validate_non_empty_str(self.repository_id, "repository_id")
        _validate_non_empty_str(self.business_baseline_node_id, "business_baseline_node_id")
        _validate_non_empty_str(self.business_baseline_commit_id, "business_baseline_commit_id")
        if type(self.baseline_head_version) is not int or self.baseline_head_version < 0:
            raise ValueError("baseline_head_version must be a non-negative integer")
        _validate_non_empty_str(self.repository_expected_commit_id, "repository_expected_commit_id")
        _validate_non_empty_str(self.canonical_business_digest, "canonical_business_digest")
        _validate_non_empty_str(self.source_digest, "source_digest")
        _validate_non_empty_str(self.snapshot_digest, "snapshot_digest")
        if type(self.source_artifact_refs) is not tuple:
            raise ValueError("source_artifact_refs must be a tuple")
        if type(self.snapshot_table_artifact_refs) is not tuple:
            raise ValueError("snapshot_table_artifact_refs must be a tuple")
        _validate_non_empty_str(self.preview_ready_closure_ref, "preview_ready_closure_ref")
        _validate_non_empty_str(
            self.preview_ready_closure_digest,
            "preview_ready_closure_digest",
        )
        _validate_non_empty_str(self.accept_idempotency_key, "accept_idempotency_key")
        _validate_non_empty_str(self.accept_request_fingerprint, "accept_request_fingerprint")
        _validate_non_empty_str(
            self.repository_upload_idempotency_key,
            "repository_upload_idempotency_key",
        )
        _validate_non_empty_str(
            self.repository_import_idempotency_key,
            "repository_import_idempotency_key",
        )
        _validate_non_empty_str(self.operation_id, "operation_id")
        if type(self.state) is not SubmitAttemptState:
            raise ValueError("state must be SubmitAttemptState")
        if type(self.optimistic_version) is not int or self.optimistic_version < 0:
            raise ValueError("optimistic_version must be a non-negative integer")
        _validate_non_empty_str(self.created_by, "created_by")
        if type(self.created_at) is not datetime:
            raise ValueError("created_at must be datetime")
        if self.repository_import_artifact_ref is not None and (
            type(self.repository_import_artifact_ref) is not BackendArtifactRef
        ):
            raise ValueError("repository_import_artifact_ref must be BackendArtifactRef or None")
        if self.repository_artifact_ref is not None and (
            type(self.repository_artifact_ref) is not RepositoryArtifactRef
        ):
            raise ValueError("repository_artifact_ref must be RepositoryArtifactRef or None")
        assert_submit_attempt_invariants(self)


@dataclass(frozen=True, slots=True)
class Submission:
    submission_id: str
    submit_attempt_id: str
    workspace_id: str
    workspace_generation: int
    upload_revision_id: str
    preview_result_id: str
    repository_id: str
    based_on_baseline_node_id: str
    business_baseline_commit_id: str
    repository_commit_id: str
    canonical_business_digest: str
    source_artifact_refs: Sequence[str]
    canonicalization_manifest_ref: str
    canonicalization_manifest_digest: str
    repository_import_artifact_raw_sha256: str
    repository_artifact_id: str
    requested_verification_policy: SubmitVerificationPolicy
    completed_verification_policy: SubmitVerificationPolicy
    requested_unknown_type_policy: SubmitUnknownTypePolicy
    target_ref: SubmitTargetRef
    created_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        _validate_non_empty_str(self.submission_id, "submission_id")
        _validate_non_empty_str(self.submit_attempt_id, "submit_attempt_id")
        _validate_non_empty_str(self.workspace_id, "workspace_id")
        if type(self.workspace_generation) is not int or self.workspace_generation < 0:
            raise ValueError("workspace_generation must be a non-negative integer")
        _validate_non_empty_str(self.upload_revision_id, "upload_revision_id")
        _validate_non_empty_str(self.preview_result_id, "preview_result_id")
        _validate_non_empty_str(self.repository_id, "repository_id")
        _validate_non_empty_str(self.based_on_baseline_node_id, "based_on_baseline_node_id")
        _validate_non_empty_str(self.business_baseline_commit_id, "business_baseline_commit_id")
        _validate_non_empty_str(self.repository_commit_id, "repository_commit_id")
        _validate_non_empty_str(self.canonical_business_digest, "canonical_business_digest")
        if type(self.source_artifact_refs) is not tuple:
            raise ValueError("source_artifact_refs must be a tuple")
        _validate_non_empty_str(self.canonicalization_manifest_ref, "canonicalization_manifest_ref")
        _validate_non_empty_str(
            self.canonicalization_manifest_digest,
            "canonicalization_manifest_digest",
        )
        _validate_non_empty_str(
            self.repository_import_artifact_raw_sha256,
            "repository_import_artifact_raw_sha256",
        )
        _validate_non_empty_str(self.repository_artifact_id, "repository_artifact_id")
        if type(self.requested_verification_policy) is not SubmitVerificationPolicy:
            raise ValueError("requested_verification_policy must be SubmitVerificationPolicy")
        if type(self.completed_verification_policy) is not SubmitVerificationPolicy:
            raise ValueError("completed_verification_policy must be SubmitVerificationPolicy")
        if type(self.requested_unknown_type_policy) is not SubmitUnknownTypePolicy:
            raise ValueError("requested_unknown_type_policy must be SubmitUnknownTypePolicy")
        if type(self.target_ref) is not SubmitTargetRef:
            raise ValueError("target_ref must be SubmitTargetRef")
        _validate_non_empty_str(self.created_by, "created_by")
        if type(self.created_at) is not datetime:
            raise ValueError("created_at must be datetime")


@dataclass(frozen=True, slots=True)
class SubmitAcceptanceRecord:
    workspace_id: str
    idempotency_key: str
    request_fingerprint: str
    submit_attempt_id: str


@dataclass(frozen=True, slots=True)
class WorkspaceSubmitOccupancy:
    workspace_id: str
    active_submit_attempt_id: str | None
    active_submission_id: str | None

    def __post_init__(self) -> None:
        has_attempt = self.active_submit_attempt_id is not None
        has_submission = self.active_submission_id is not None
        if has_attempt == has_submission:
            raise ValueError("workspace occupancy row must hold exactly one active pointer")


@dataclass(frozen=True, slots=True)
class RepositorySubmitOccupancy:
    repository_id: str
    workspace_id: str
    submit_attempt_id: str
    business_baseline_node_id: str
    baseline_head_version: int
    acquired_at: datetime


def derive_preview_canonical_business_digest(*, bundle_digest: str) -> str:
    _validate_non_empty_str(bundle_digest, "bundle_digest")
    return bundle_digest


def _validate_non_empty_str(value: object, field_name: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
