"""Application command and result contracts for submit use cases."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositorySubmitOccupancy as RepositorySubmitOccupancy,
    SubmitAcceptanceRecord as SubmitAcceptanceRecord,
    SubmitAttempt,
    IdentityConfirmationAction,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
    Submission,
    WorkspaceSubmitOccupancy as WorkspaceSubmitOccupancy,
)
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    IdentityContext,
    PreviewResult,
    UploadRevision,
    Workspace,
)
from gateway_backend.domain.submission.reasons import validate_submission_reason
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.submission.errors import PreviewBindingConflict

SUBMIT_JOB_CONTRACT_VERSION = "backend-vnext/submit/v1"
PREPARE_IMPORT_CHECKPOINT_SCHEMA = "backend-vnext/submit/prepare-import-checkpoint/v2"
ACCEPT_SUBMIT_REQUEST_PREFIX = b"gateway-vnext:accept-submit-request:v1\0"
REPOSITORY_UPLOAD_KEY_PREFIX = "p5b-upload-v1:"
REPOSITORY_IMPORT_KEY_PREFIX = "p5b-import-v1:"
_SHA256_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class IdentityConfirmationRequest:
    action: IdentityConfirmationAction
    assessment_set_digest: str
    reason: str

    def __post_init__(self) -> None:
        if type(self.action) is not IdentityConfirmationAction:
            raise ValueError("action must be IdentityConfirmationAction")
        if type(self.assessment_set_digest) is not str or not _SHA256_DIGEST_PATTERN.fullmatch(
            self.assessment_set_digest
        ):
            raise ValueError("assessment_set_digest must be a sha256 digest")
        validate_submission_reason(self.reason, allow_multiline=True)


@dataclass(frozen=True, slots=True)
class SnapshotTableBinding:
    table_name: str
    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str

    def __post_init__(self) -> None:
        if type(self.table_name) is not str or not self.table_name:
            raise ValueError("table_name must be a non-empty string")
        if type(self.artifact_id) is not str or not self.artifact_id:
            raise ValueError("artifact_id must be a non-empty string")
        if type(self.media_type) is not str or not self.media_type:
            raise ValueError("media_type must be a non-empty string")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        if type(self.raw_sha256) is not str or not self.raw_sha256:
            raise ValueError("raw_sha256 must be a non-empty string")


@dataclass(frozen=True, slots=True)
class PrepareImportBuildInput:
    submit_attempt_id: str
    builder_mutation_policy: BuilderMutationPolicy
    canonical_table_set_closure_ref: ArtifactRef
    canonical_table_set_closure_digest: str
    canonicalization_manifest_ref: ArtifactRef
    canonicalization_manifest_digest: str
    expected_parent_commit_id: str
    removed_tables: tuple[str, ...]
    source_artifact_digest: str
    repository_base_digest: str
    storage_projection_version: str
    ruleset_id: str
    ruleset_version: str
    ruleset_digest: str
    snapshot_tables: tuple[SnapshotTableBinding, ...]

    def __post_init__(self) -> None:
        if type(self.submit_attempt_id) is not str or not self.submit_attempt_id:
            raise ValueError("submit_attempt_id must be a non-empty string")
        if type(self.builder_mutation_policy) is not BuilderMutationPolicy:
            raise ValueError("builder_mutation_policy must be BuilderMutationPolicy")
        for field_name in (
            "canonicalization_manifest_digest",
            "expected_parent_commit_id",
            "source_artifact_digest",
            "repository_base_digest",
            "storage_projection_version",
            "ruleset_id",
            "ruleset_version",
            "ruleset_digest",
        ):
            if type(getattr(self, field_name)) is not str or not getattr(self, field_name):
                raise ValueError(f"{field_name} must be a non-empty string")
        if type(self.canonical_table_set_closure_ref) is not ArtifactRef:
            raise ValueError("canonical_table_set_closure_ref must be ArtifactRef")
        if type(self.canonicalization_manifest_ref) is not ArtifactRef:
            raise ValueError("canonicalization_manifest_ref must be ArtifactRef")
        if self.canonical_table_set_closure_ref.raw_sha256.value != self.canonical_table_set_closure_digest:
            raise ValueError("canonical table closure artifact ref raw SHA must match digest")
        if type(self.removed_tables) is not tuple:
            raise ValueError("removed_tables must be a tuple")
        if any(type(name) is not str or not name for name in self.removed_tables):
            raise ValueError("removed_tables must contain non-empty table names")
        if self.removed_tables != tuple(
            sorted(set(self.removed_tables), key=lambda name: name.encode("utf-8"))
        ):
            raise ValueError("removed_tables must contain sorted unique table names")
        if type(self.snapshot_tables) is not tuple:
            raise ValueError("snapshot_tables must be a tuple")
        for item in self.snapshot_tables:
            if type(item) is not SnapshotTableBinding:
                raise ValueError("snapshot_tables must contain SnapshotTableBinding")
        table_names = tuple(item.table_name for item in self.snapshot_tables)
        if table_names != tuple(sorted(set(table_names), key=lambda name: name.encode("utf-8"))):
            raise ValueError("snapshot_tables must contain sorted unique table names")
        if set(table_names) & set(self.removed_tables):
            raise ValueError("removed_tables must be disjoint from snapshot_tables")


@dataclass(frozen=True, slots=True)
class PrepareImportCheckpoint:
    schema_version: str
    attempt_id: str
    canonical_table_set_closure_ref: str
    canonical_table_set_closure_digest: str
    input_canonicalization_manifest_ref: str
    input_canonicalization_manifest_digest: str
    expected_parent_commit_id: str
    removed_tables: tuple[str, ...]
    canonicalization_manifest_ref: BackendArtifactRef
    canonicalization_manifest_digest: str
    backend_import_artifact_ref: BackendArtifactRef
    package_raw_size: int
    package_raw_sha256: str
    builder_mutation_policy: BuilderMutationPolicy

    def __post_init__(self) -> None:
        if self.schema_version != PREPARE_IMPORT_CHECKPOINT_SCHEMA:
            raise ValueError("unsupported prepare import checkpoint schema")
        if type(self.attempt_id) is not str or not self.attempt_id:
            raise ValueError("attempt_id must be a non-empty string")
        for field_name in (
            "canonical_table_set_closure_ref",
            "canonical_table_set_closure_digest",
            "input_canonicalization_manifest_ref",
            "input_canonicalization_manifest_digest",
            "expected_parent_commit_id",
        ):
            if type(getattr(self, field_name)) is not str or not getattr(self, field_name):
                raise ValueError(f"{field_name} must be a non-empty string")
        if type(self.removed_tables) is not tuple:
            raise ValueError("removed_tables must be a tuple")
        if any(type(name) is not str or not name for name in self.removed_tables):
            raise ValueError("removed_tables must contain non-empty table names")
        if self.removed_tables != tuple(
            sorted(set(self.removed_tables), key=lambda name: name.encode("utf-8"))
        ):
            raise ValueError("removed_tables must contain sorted unique table names")
        if type(self.canonicalization_manifest_ref) is not BackendArtifactRef:
            raise ValueError("canonicalization_manifest_ref must be BackendArtifactRef")
        if type(self.canonicalization_manifest_digest) is not str or not self.canonicalization_manifest_digest:
            raise ValueError("canonicalization_manifest_digest must be a non-empty string")
        if type(self.backend_import_artifact_ref) is not BackendArtifactRef:
            raise ValueError("backend_import_artifact_ref must be BackendArtifactRef")
        if type(self.package_raw_size) is not int or self.package_raw_size < 0:
            raise ValueError("package_raw_size must be a non-negative integer")
        if type(self.package_raw_sha256) is not str or not self.package_raw_sha256:
            raise ValueError("package_raw_sha256 must be a non-empty string")
        if self.backend_import_artifact_ref.raw_sha256 != self.package_raw_sha256:
            raise ValueError("package_raw_sha256 must match backend_import_artifact_ref.raw_sha256")
        if type(self.builder_mutation_policy) is not BuilderMutationPolicy:
            raise ValueError("builder_mutation_policy must be BuilderMutationPolicy")


@dataclass(frozen=True, slots=True)
class PrepareImportPublicationResult:
    checkpoint: PrepareImportCheckpoint
    replay: bool = False


class SubmitImportPublicationPort(Protocol):
    def build_and_publish(
        self,
        *,
        build_input: PrepareImportBuildInput,
        store: ArtifactStorePort,
    ) -> PrepareImportPublicationResult: ...

    def read_back_package(
        self,
        *,
        checkpoint: PrepareImportCheckpoint,
        store: ArtifactStorePort,
    ) -> bytes: ...

    def verify_checkpoint_semantic_binding(
        self,
        *,
        checkpoint: PrepareImportCheckpoint,
        store: ArtifactStorePort,
    ) -> None: ...


def assert_preview_ready_closure_digest(preview_ready_closure_digest: str) -> None:
    if type(preview_ready_closure_digest) is not str or not preview_ready_closure_digest:
        raise PreviewBindingConflict("preview ready closure digest is required")


@dataclass(frozen=True, slots=True)
class AcceptSubmitCommand:
    context: IdentityContext
    workspace_id: str
    expected_workspace_version: int
    upload_revision_id: str
    preview_result_id: str
    generation: int
    expected_baseline_node_id: str
    expected_baseline_head_version: int
    idempotency_key: str
    options: Mapping[str, object]
    identity_confirmations: tuple[IdentityConfirmationRequest, ...] = ()

    def __post_init__(self) -> None:
        if type(self.identity_confirmations) is not tuple or any(
            type(item) is not IdentityConfirmationRequest for item in self.identity_confirmations
        ):
            raise ValueError("identity_confirmations must contain IdentityConfirmationRequest")
        actions = tuple(item.action for item in self.identity_confirmations)
        if len(actions) > 2 or len(set(actions)) != len(actions):
            raise ValueError("identity_confirmations must have unique actions and at most two entries")


@dataclass(frozen=True, slots=True)
class AcceptSubmitValidationResult:
    workspace: Workspace
    upload_revision: UploadRevision
    preview_result: PreviewResult
    baseline_head: BaselineHead
    repository_expected_commit_id: str
    canonical_business_digest: str
    accept_request_fingerprint: str
    replay: bool
    prior_attempt: SubmitAttempt | None


class RepositoryOperationTerminalStatus(StrEnum):
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class MatchingFinalizeFacts:
    repository_id: str
    repository_operation_id: str
    repository_commit_id: str
    repository_expected_parent_commit_id: str
    repository_artifact_id: str
    repository_import_artifact_raw_sha256: str
    canonicalization_manifest_ref: str
    canonicalization_manifest_digest: str
    completed_verification_policy: SubmitVerificationPolicy
    completed_unknown_type_policy: SubmitUnknownTypePolicy
    target_ref: SubmitTargetRef


@dataclass(frozen=True, slots=True)
class MatchingAbortProof:
    repository_id: str
    repository_operation_id: str
    terminal_status: RepositoryOperationTerminalStatus
    stable_failure_code: str


@dataclass(frozen=True, slots=True)
class FinalizeSubmitCommand:
    attempt: SubmitAttempt
    facts: MatchingFinalizeFacts
    submission_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class FinalizeSubmitResult:
    attempt: SubmitAttempt
    submission: Submission
    replay: bool


def derive_repository_upload_idempotency_key(submit_attempt_id: str) -> str:
    if type(submit_attempt_id) is not str or not submit_attempt_id:
        raise ValueError("submit_attempt_id must be a non-empty string")
    digest = hashlib.sha256(submit_attempt_id.encode("utf-8")).hexdigest()
    return f"{REPOSITORY_UPLOAD_KEY_PREFIX}{digest}"


def derive_repository_import_idempotency_key(submit_attempt_id: str) -> str:
    if type(submit_attempt_id) is not str or not submit_attempt_id:
        raise ValueError("submit_attempt_id must be a non-empty string")
    digest = hashlib.sha256(submit_attempt_id.encode("utf-8")).hexdigest()
    return f"{REPOSITORY_IMPORT_KEY_PREFIX}{digest}"


def compute_accept_request_fingerprint(
    *,
    workspace_id: str,
    owner_actor_id: str,
    gateway_device_external_key: str,
    business_project_id: str,
    repository_id: str,
    expected_workspace_version: int,
    upload_revision_id: str,
    preview_result_id: str,
    generation: int,
    expected_baseline_node_id: str,
    expected_baseline_head_version: int,
    business_baseline_commit_id: str,
    canonical_business_digest: str,
    source_digest: str,
    snapshot_digest: str,
    source_artifact_refs: tuple[str, ...],
    canonical_table_set_closure_ref: str,
    canonical_table_set_closure_digest: str,
    canonicalization_manifest_ref: str,
    canonicalization_manifest_digest: str,
    preview_ready_closure_ref: str,
    preview_ready_closure_digest: str,
    repository_expected_commit_id: str,
    options: Mapping[str, object],
    identity_confirmations: tuple[IdentityConfirmationRequest, ...] = (),
) -> str:
    payload = {
        "workspace_id": workspace_id,
        "owner_actor_id": owner_actor_id,
        "gateway_device_external_key": gateway_device_external_key,
        "business_project_id": business_project_id,
        "repository_id": repository_id,
        "expected_workspace_version": expected_workspace_version,
        "upload_revision_id": upload_revision_id,
        "preview_result_id": preview_result_id,
        "generation": generation,
        "expected_baseline_node_id": expected_baseline_node_id,
        "expected_baseline_head_version": expected_baseline_head_version,
        "business_baseline_commit_id": business_baseline_commit_id,
        "canonical_business_digest": canonical_business_digest,
        "source_digest": source_digest,
        "snapshot_digest": snapshot_digest,
        "source_artifact_refs": list(source_artifact_refs),
        "canonical_table_set_closure_ref": canonical_table_set_closure_ref,
        "canonical_table_set_closure_digest": canonical_table_set_closure_digest,
        "canonicalization_manifest_ref": canonicalization_manifest_ref,
        "canonicalization_manifest_digest": canonicalization_manifest_digest,
        "preview_ready_closure_ref": preview_ready_closure_ref,
        "preview_ready_closure_digest": preview_ready_closure_digest,
        "repository_expected_commit_id": repository_expected_commit_id,
        "requested_target_ref": SubmitTargetRef.MAIN.value,
        "requested_verification_policy": SubmitVerificationPolicy.STRUCTURAL.value,
        "requested_unknown_type_policy": SubmitUnknownTypePolicy.REJECT.value,
        "builder_mutation_policy": BuilderMutationPolicy.REBUILD_ALWAYS.value,
        "job_contract_version": SUBMIT_JOB_CONTRACT_VERSION,
        "options": dict(sorted(options.items())),
        "identity_confirmations": [
            {
                "action": item.action.value,
                "assessment_set_digest": item.assessment_set_digest,
                "reason": item.reason,
            }
            for item in sorted(identity_confirmations, key=lambda item: item.action.value)
        ],
    }
    digest = hashlib.sha256(
        ACCEPT_SUBMIT_REQUEST_PREFIX + canonicalize_json_value(payload)
    ).hexdigest()
    return f"sha256:{digest}"


def preview_canonical_business_digest(preview_result: PreviewResult) -> str:
    return preview_result.canonical.modified_canonical_state_digest.value


def _source_artifact_refs(upload_revision: UploadRevision) -> tuple[str, ...]:
    return tuple(
        binding.artifact_id
        for _role, binding in sorted(
            upload_revision.source_artifacts.items(),
            key=lambda item: item[0].value,
        )
    )


def compute_new_accept_fingerprint(
    *,
    command: AcceptSubmitCommand,
    workspace: Workspace,
    preview_result: PreviewResult,
    upload_revision: UploadRevision,
    baseline_head: BaselineHead,
    repository_expected_commit_id: str,
    preview_ready_closure_digest: str,
) -> str:
    assert_preview_ready_closure_digest(preview_ready_closure_digest)
    return compute_accept_request_fingerprint(
        workspace_id=workspace.workspace_id,
        owner_actor_id=workspace.owner_actor_id,
        gateway_device_external_key=workspace.gateway_device_external_key,
        business_project_id=workspace.business_project_id,
        repository_id=workspace.repository_id,
        expected_workspace_version=command.expected_workspace_version,
        upload_revision_id=command.upload_revision_id,
        preview_result_id=command.preview_result_id,
        generation=command.generation,
        expected_baseline_node_id=command.expected_baseline_node_id,
        expected_baseline_head_version=command.expected_baseline_head_version,
        business_baseline_commit_id=baseline_head.business_baseline_commit_id,
        canonical_business_digest=preview_canonical_business_digest(preview_result),
        source_digest=preview_result.digests.source_digest,
        snapshot_digest=preview_result.digests.snapshot_digest,
        source_artifact_refs=_source_artifact_refs(upload_revision),
        canonical_table_set_closure_ref=(
            preview_result.canonical.canonical_table_set_closure_ref.artifact_id
        ),
        canonical_table_set_closure_digest=(
            preview_result.canonical.canonical_table_set_closure_digest.value
        ),
        canonicalization_manifest_ref=(
            preview_result.canonical.canonicalization_manifest_ref.artifact_id
        ),
        canonicalization_manifest_digest=(
            preview_result.canonical.canonicalization_manifest_digest.value
        ),
        preview_ready_closure_ref=preview_result.ready_closure_artifact_id,
        preview_ready_closure_digest=preview_ready_closure_digest,
        repository_expected_commit_id=repository_expected_commit_id,
        options=command.options,
        identity_confirmations=command.identity_confirmations,
    )


def compute_replay_accept_fingerprint(
    *,
    command: AcceptSubmitCommand,
    attempt: SubmitAttempt,
    workspace: Workspace,
) -> str:
    return compute_accept_request_fingerprint(
        workspace_id=workspace.workspace_id,
        owner_actor_id=workspace.owner_actor_id,
        gateway_device_external_key=workspace.gateway_device_external_key,
        business_project_id=workspace.business_project_id,
        repository_id=attempt.repository_id,
        expected_workspace_version=command.expected_workspace_version,
        upload_revision_id=command.upload_revision_id,
        preview_result_id=command.preview_result_id,
        generation=command.generation,
        expected_baseline_node_id=command.expected_baseline_node_id,
        expected_baseline_head_version=command.expected_baseline_head_version,
        business_baseline_commit_id=attempt.business_baseline_commit_id,
        canonical_business_digest=attempt.canonical_business_digest,
        source_digest=attempt.source_digest,
        snapshot_digest=attempt.snapshot_digest,
        source_artifact_refs=tuple(attempt.source_artifact_refs),
        canonical_table_set_closure_ref=attempt.canonical_table_set_closure_ref,
        canonical_table_set_closure_digest=attempt.canonical_table_set_closure_digest,
        canonicalization_manifest_ref=attempt.canonicalization_manifest_ref,
        canonicalization_manifest_digest=attempt.canonicalization_manifest_digest,
        preview_ready_closure_ref=attempt.preview_ready_closure_ref,
        preview_ready_closure_digest=attempt.preview_ready_closure_digest,
        repository_expected_commit_id=attempt.repository_expected_commit_id,
        options=command.options,
        identity_confirmations=command.identity_confirmations,
    )

ALLOWED_ABORT_CODES = frozenset({
    "IMPORT_REJECTED",
    "EXPECTED_COMMIT_MISMATCH",
    "VERIFICATION_FAILED_NOT_PUBLISHED",
})


class RepositoryImportOperationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RepositoryImportOperationResult:
    commit_id: str
    target_ref: str
    artifact_id: str
    canonicalization_manifest_digest: str
    expected_commit_id: str
    completed_verification_policy: str
    unknown_type_policy: str


@dataclass(frozen=True, slots=True)
class RepositoryImportOperationError:
    code: str
    message: str
    details: dict[str, object] | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class RepositoryImportOperation:
    operation_id: str
    status: RepositoryImportOperationStatus
    result: RepositoryImportOperationResult | None = None
    error: RepositoryImportOperationError | None = None

