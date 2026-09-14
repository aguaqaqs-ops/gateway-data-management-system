"""Application command and result contracts for submit use cases."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from gateway_backend.domain.submission.models import (
    BuilderMutationPolicy,
    SubmitAttempt,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
    Submission,
    derive_preview_canonical_business_digest,
)
from gateway_backend.domain.workspace.models import (
    BaselineHead,
    IdentityContext,
    PreviewResult,
    UploadRevision,
    Workspace,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.submission.errors import PreviewBindingConflict

SUBMIT_JOB_CONTRACT_VERSION = "backend-vnext/submit/v1"
ACCEPT_SUBMIT_REQUEST_PREFIX = b"gateway-vnext:accept-submit-request:v1\0"
REPOSITORY_UPLOAD_KEY_PREFIX = "p5b-upload-v1:"
REPOSITORY_IMPORT_KEY_PREFIX = "p5b-import-v1:"


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
    snapshot_table_artifact_refs: tuple[str, ...],
    preview_ready_closure_ref: str,
    preview_ready_closure_digest: str,
    repository_expected_commit_id: str,
    options: Mapping[str, object],
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
        "snapshot_table_artifact_refs": list(snapshot_table_artifact_refs),
        "preview_ready_closure_ref": preview_ready_closure_ref,
        "preview_ready_closure_digest": preview_ready_closure_digest,
        "repository_expected_commit_id": repository_expected_commit_id,
        "requested_target_ref": SubmitTargetRef.MAIN.value,
        "requested_verification_policy": SubmitVerificationPolicy.STRUCTURAL.value,
        "requested_unknown_type_policy": SubmitUnknownTypePolicy.REJECT.value,
        "builder_mutation_policy": BuilderMutationPolicy.REBUILD_ALWAYS.value,
        "job_contract_version": SUBMIT_JOB_CONTRACT_VERSION,
        "options": dict(sorted(options.items())),
    }
    digest = hashlib.sha256(
        ACCEPT_SUBMIT_REQUEST_PREFIX + canonicalize_json_value(payload)
    ).hexdigest()
    return f"sha256:{digest}"


def preview_canonical_business_digest(preview_result: PreviewResult) -> str:
    return derive_preview_canonical_business_digest(
        bundle_digest=preview_result.digests.bundle_digest
    )


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
    snapshot_table_artifact_refs: tuple[str, ...],
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
        snapshot_table_artifact_refs=snapshot_table_artifact_refs,
        preview_ready_closure_ref=preview_result.ready_closure_artifact_id,
        preview_ready_closure_digest=preview_ready_closure_digest,
        repository_expected_commit_id=repository_expected_commit_id,
        options=command.options,
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
        snapshot_table_artifact_refs=tuple(attempt.snapshot_table_artifact_refs),
        preview_ready_closure_ref=attempt.preview_ready_closure_ref,
        preview_ready_closure_digest=attempt.preview_ready_closure_digest,
        repository_expected_commit_id=attempt.repository_expected_commit_id,
        options=command.options,
    )
