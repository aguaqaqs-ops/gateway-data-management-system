"""SubmitAttempt and Submission domain records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re

from gateway_backend.domain.submission.errors import SubmitAttemptInvariantViolation
from gateway_backend.domain.submission.reasons import validate_submission_reason


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
    ADAPTIVE_PATCH = "ADAPTIVE_PATCH"


class IdentityConfirmationAction(StrEnum):
    ACCEPT_DATASET_REPLACEMENT = "ACCEPT_DATASET_REPLACEMENT"
    ACCEPT_UNVERIFIABLE_DETAILED_RESULT = "ACCEPT_UNVERIFIABLE_DETAILED_RESULT"


_SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SubmitIdentityConfirmation:
    action: IdentityConfirmationAction
    assessment_set_digest: str
    reason: str
    actor_id: str
    confirmed_at: datetime

    def __post_init__(self) -> None:
        if type(self.action) is not IdentityConfirmationAction:
            raise ValueError("action must be IdentityConfirmationAction")
        if type(self.assessment_set_digest) is not str or not _SHA256_DIGEST_PATTERN.fullmatch(
            self.assessment_set_digest
        ):
            raise ValueError("assessment_set_digest must be a sha256 digest")
        validate_submission_reason(self.reason, allow_multiline=True)
        _validate_non_empty_str(self.actor_id, "actor_id")
        if type(self.confirmed_at) is not datetime:
            raise ValueError("confirmed_at must be datetime")


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
    canonical_table_set_closure_ref: str
    canonical_table_set_closure_digest: str
    preview_ready_closure_ref: str
    preview_ready_closure_digest: str
    canonicalization_manifest_ref: str
    canonicalization_manifest_digest: str
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
    prepared_canonicalization_manifest_ref: str | None = None
    prepared_canonicalization_manifest_digest: str | None = None
    effect_pending_at: datetime | None = None
    finalized_at: datetime | None = None
    aborted_at: datetime | None = None
    abort_code: str | None = None
    identity_confirmations: tuple[SubmitIdentityConfirmation, ...] = ()

    def __post_init__(self) -> None:

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
        _validate_non_empty_str(
            self.canonical_table_set_closure_ref,
            "canonical_table_set_closure_ref",
        )
        _validate_non_empty_str(
            self.canonical_table_set_closure_digest,
            "canonical_table_set_closure_digest",
        )
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
        _validate_identity_confirmations(self.identity_confirmations)
        if (self.prepared_canonicalization_manifest_ref is None) != (
            self.prepared_canonicalization_manifest_digest is None
        ):
            raise ValueError("prepared canonicalization manifest ref and digest must appear together")
        if self.prepared_canonicalization_manifest_ref is not None:
            _validate_non_empty_str(
                self.prepared_canonicalization_manifest_ref,
                "prepared_canonicalization_manifest_ref",
            )
            _validate_non_empty_str(
                self.prepared_canonicalization_manifest_digest,
                "prepared_canonicalization_manifest_digest",
            )
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
    identity_confirmations: tuple[SubmitIdentityConfirmation, ...] = ()

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
        _validate_identity_confirmations(self.identity_confirmations)


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



def assert_submit_attempt_invariants(attempt: SubmitAttempt) -> None:
    _validate_non_empty_str(attempt.canonicalization_manifest_ref, "canonicalization_manifest_ref")
    _validate_non_empty_str(
        attempt.canonicalization_manifest_digest,
        "canonicalization_manifest_digest",
    )

    if attempt.repository_artifact_ref is not None and attempt.repository_import_artifact_ref is None:
        raise SubmitAttemptInvariantViolation(
            "repository artifact ref requires backend import artifact ref"
        )
    if attempt.repository_import_artifact_ref is not None and (
        attempt.prepared_canonicalization_manifest_ref is None
        or attempt.prepared_canonicalization_manifest_digest is None
    ):
        raise SubmitAttemptInvariantViolation(
            "backend import artifact ref requires prepared canonicalization manifest"
        )

    if attempt.repository_operation_id is not None and attempt.repository_artifact_ref is None:
        raise SubmitAttemptInvariantViolation(
            "repository operation identity requires repository artifact ref"
        )

    if attempt.state is SubmitAttemptState.FINALIZED:
        if attempt.submission_id is None:
            raise SubmitAttemptInvariantViolation("FINALIZED attempt requires submission_id")
        if attempt.finalized_at is None:
            raise SubmitAttemptInvariantViolation("FINALIZED attempt requires finalized_at")
        if attempt.abort_code is not None or attempt.aborted_at is not None:
            raise SubmitAttemptInvariantViolation("FINALIZED attempt must not carry abort fields")
    elif attempt.submission_id is not None:
        raise SubmitAttemptInvariantViolation("submission_id is only allowed in FINALIZED state")

    if attempt.state is SubmitAttemptState.ABORTED:
        if attempt.abort_code is None:
            raise SubmitAttemptInvariantViolation("ABORTED attempt requires abort_code")
        if attempt.aborted_at is None:
            raise SubmitAttemptInvariantViolation("ABORTED attempt requires aborted_at")
        if attempt.submission_id is not None or attempt.finalized_at is not None:
            raise SubmitAttemptInvariantViolation("ABORTED attempt must not carry finalize fields")
    elif attempt.abort_code is not None or attempt.aborted_at is not None:
        raise SubmitAttemptInvariantViolation("abort fields are only allowed in ABORTED state")

    if attempt.state is SubmitAttemptState.EFFECT_PENDING and attempt.effect_pending_at is None:
        raise SubmitAttemptInvariantViolation("EFFECT_PENDING attempt requires effect_pending_at")

def _validate_non_empty_str(value: object, field_name: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_identity_confirmations(value: object) -> None:
    if type(value) is not tuple or any(type(item) is not SubmitIdentityConfirmation for item in value):
        raise ValueError("identity_confirmations must contain SubmitIdentityConfirmation")
    actions = tuple(item.action for item in value)
    if len(actions) > 2 or len(set(actions)) != len(actions):
        raise ValueError("identity_confirmations must have unique actions and at most two entries")
