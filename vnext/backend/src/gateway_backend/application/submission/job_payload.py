"""Closed Submit job payload builder for T1 Operation insertion."""

from __future__ import annotations

from collections.abc import Mapping

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.job_steps import successor_step_id
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.domain.submission.models import BuilderMutationPolicy, SubmitAttempt

SUBMIT_JOB_KIND = "backend-vnext/submit"
SUBMIT_STEP_PREPARE = "prepare_import"
SUBMIT_STEP_SUBMIT = "submit_import"
SUBMIT_STEP_AWAIT = "await_import_result"

_SUBMIT_STEP_SUFFIX: dict[str, str] = {
    SUBMIT_STEP_PREPARE: "1",
    SUBMIT_STEP_SUBMIT: "2",
    SUBMIT_STEP_AWAIT: "3",
}


def submit_successor_step_id(operation_id: str, step_name: str) -> str:
    return successor_step_id(operation_id, step_name, _SUBMIT_STEP_SUFFIX)


def build_submit_job_payload(
    *,
    attempt: SubmitAttempt,
    options: Mapping[str, object] | None = None,
) -> bytes:
    payload = {
        "document_type": "submit_job_payload",
        "contract_version": SUBMIT_JOB_CONTRACT_VERSION,
        "submit_attempt_id": attempt.submit_attempt_id,
        "workspace_id": attempt.workspace_id,
        "generation": attempt.workspace_generation,
        "upload_revision_id": attempt.upload_revision_id,
        "preview_result_id": attempt.preview_result_id,
        "repository_id": attempt.repository_id,
        "business_baseline_node_id": attempt.business_baseline_node_id,
        "business_baseline_commit_id": attempt.business_baseline_commit_id,
        "baseline_head_version": attempt.baseline_head_version,
        "repository_expected_commit_id": attempt.repository_expected_commit_id,
        "canonical_business_digest": attempt.canonical_business_digest,
        "source_artifact_refs": list(attempt.source_artifact_refs),
        "preview_ready_closure_ref": attempt.preview_ready_closure_ref,
        "canonical_table_set_closure_ref": attempt.canonical_table_set_closure_ref,
        "canonical_table_set_closure_digest": attempt.canonical_table_set_closure_digest,
        "canonicalization_manifest_ref": attempt.canonicalization_manifest_ref,
        "canonicalization_manifest_digest": attempt.canonicalization_manifest_digest,
        "ruleset_version": "v1",
        "storage_projection_version": "v1",
        "canonicalization_manifest_contract_version": "v1",
        "repository_import_package_version": 1,
        "accept_request_fingerprint": attempt.accept_request_fingerprint,
        "repository_upload_idempotency_key": attempt.repository_upload_idempotency_key,
        "repository_import_idempotency_key": attempt.repository_import_idempotency_key,
        "repository_policy": {
            "target_ref": attempt.requested_target_ref.value,
            "verification_policy": attempt.requested_verification_policy.value,
            "unknown_type_policy": attempt.requested_unknown_type_policy.value,
        },
        "builder_mutation_policy": BuilderMutationPolicy.REBUILD_ALWAYS.value,
        "options": dict(options or {}),
    }
    return canonicalize_json_value(payload)
