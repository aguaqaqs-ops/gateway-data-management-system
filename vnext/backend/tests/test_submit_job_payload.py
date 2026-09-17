"""Submit job payload decoder and registry identity tests."""

from __future__ import annotations

import json
import pytest

from gateway_backend.application.payloads import PayloadDecodeError
from gateway_backend.application.submit_jobs import (
    _prepare_checkpoint_from_job_state,
    decode_submit_payload,
    submit_payload_decoders,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.submit_registry import (
    AWAIT_IMPORT_DECODER,
    AWAIT_IMPORT_HANDLER,
    PREPARE_IMPORT_DECODER,
    PREPARE_IMPORT_HANDLER,
    SUBMIT_IMPORT_DECODER,
    SUBMIT_IMPORT_HANDLER,
    submit_job_definitions,
)
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
    build_submit_job_payload,
)
from datetime import UTC, datetime

from gateway_backend.domain.submission.models import (
    BuilderMutationPolicy,
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)

pytestmark = pytest.mark.unit

_TS0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
_SNAPSHOT_TABLE_SET_DIGEST = "sha256:snapshot-set"


def _prepared_attempt() -> SubmitAttempt:
    return SubmitAttempt(
        submit_attempt_id="sa-payload-1",
        workspace_id="ws-1",
        workspace_generation=1,
        upload_revision_id="ur-1",
        preview_result_id="pr-1",
        repository_id="repo-1",
        business_baseline_node_id="node-1",
        business_baseline_commit_id="commit-base",
        baseline_head_version=1,
        repository_expected_commit_id="commit-main",
        canonical_business_digest="sha256:canonical",
        source_digest="d-source",
        snapshot_digest="d-snapshot",
        source_artifact_refs=("initial-1", "modified-1"),
        snapshot_table_artifact_refs=("snap-1",),
        preview_ready_closure_ref="closure-1",
        preview_ready_closure_digest="d-closure",
        canonicalization_manifest_ref=None,
        canonicalization_manifest_digest=None,
        repository_import_artifact_ref=None,
        repository_artifact_ref=None,
        repository_operation_id=None,
        repository_operation_evidence=None,
        requested_target_ref=SubmitTargetRef.MAIN,
        requested_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        requested_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        builder_mutation_policy=BuilderMutationPolicy.REBUILD_ALWAYS,
        accept_idempotency_key="accept-key-1",
        accept_request_fingerprint="sha256:fp",
        repository_upload_idempotency_key="p5b-upload-v1:abc",
        repository_import_idempotency_key="p5b-import-v1:abc",
        operation_id="op-1",
        state=SubmitAttemptState.PREPARED,
        submission_id=None,
        optimistic_version=0,
        created_by="actor-1",
        created_at=_TS0,
    )


def _canonical_payload_object() -> dict[str, object]:
    attempt = _prepared_attempt()
    payload_bytes = build_submit_job_payload(
        attempt=attempt,
        snapshot_table_set_digest=_SNAPSHOT_TABLE_SET_DIGEST,
        options={"trace": True},
    )
    payload_object = json.loads(payload_bytes)
    assert type(payload_object) is dict
    return payload_object


def test_decode_submit_payload_accepts_canonical_payload_from_build_submit_job_payload() -> None:
    attempt = _prepared_attempt()
    payload_object = _canonical_payload_object()
    decoded = decode_submit_payload(payload_object)

    assert decoded.document_type == "submit_job_payload"
    assert decoded.submit_attempt_id == attempt.submit_attempt_id
    assert decoded.workspace_id == attempt.workspace_id
    assert decoded.generation == attempt.workspace_generation
    assert decoded.snapshot_table_set_digest == _SNAPSHOT_TABLE_SET_DIGEST
    assert decoded.accept_request_fingerprint == attempt.accept_request_fingerprint
    assert decoded.repository_upload_idempotency_key == attempt.repository_upload_idempotency_key
    assert decoded.repository_import_idempotency_key == attempt.repository_import_idempotency_key
    assert decoded.repository_policy.target_ref is attempt.requested_target_ref
    assert decoded.repository_policy.verification_policy is attempt.requested_verification_policy
    assert decoded.repository_policy.unknown_type_policy is attempt.requested_unknown_type_policy
    assert decoded.builder_mutation_policy is attempt.builder_mutation_policy
    assert decoded.options == {"trace": True}


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ({"unexpected_field": "x"}, "unknown submit payload keys"),
        ({"ruleset_version": "v2"}, "ruleset_version must be v1"),
        ({"storage_projection_version": "v2"}, "storage_projection_version must be v1"),
        (
            {"canonicalization_manifest_contract_version": "v2"},
            "canonicalization_manifest_contract_version must be v1",
        ),
        ({"repository_import_package_version": 2}, "repository_import_package_version must be 1"),
        (
            {
                "repository_policy": {
                    "target_ref": "branch",
                    "verification_policy": "STRUCTURAL",
                    "unknown_type_policy": "REJECT",
                }
            },
            "repository_policy contains invalid enum values",
        ),
        (
            {
                "repository_policy": {
                    "target_ref": "main",
                    "verification_policy": "FULL",
                    "unknown_type_policy": "REJECT",
                }
            },
            "repository_policy contains invalid enum values",
        ),
        (
            {
                "repository_policy": {
                    "target_ref": "main",
                    "verification_policy": "STRUCTURAL",
                    "unknown_type_policy": "ACCEPT",
                }
            },
            "repository_policy contains invalid enum values",
        ),
        ({"builder_mutation_policy": "REUSE_PINNED"}, "builder_mutation_policy is invalid"),
    ),
)
def test_rejects_unknown_keys_and_policy_drift(
    mutation: dict[str, object],
    message: str,
) -> None:
    payload_object = _canonical_payload_object()
    payload_object.update(mutation)
    with pytest.raises(PayloadDecodeError, match=message):
        decode_submit_payload(payload_object)


def test_decode_submit_payload_rejects_unsupported_contract_version() -> None:
    payload_object = _canonical_payload_object()
    payload_object["contract_version"] = "backend-vnext/submit/v999"
    with pytest.raises(PayloadDecodeError, match="contract_version must be"):
        decode_submit_payload(payload_object)


def test_prepare_checkpoint_rejects_unknown_job_state_fields() -> None:
    job_state = {
        "schema_version": "backend-vnext/submit/prepare-import-checkpoint/v1",
        "attempt_id": "sa-payload-1",
        "canonicalization_manifest_ref": {
            "artifact_id": "manifest-1",
            "media_type": "application/jcs",
            "size_bytes": 1,
            "raw_sha256": "sha256:" + "a" * 64,
        },
        "canonicalization_manifest_digest": "sha256:" + "b" * 64,
        "backend_import_artifact_ref": {
            "artifact_id": "backend-1",
            "media_type": "application/vnd.gateway.repository-import.v1+tar+zstd",
            "size_bytes": 2,
            "raw_sha256": "sha256:" + "c" * 64,
        },
        "package_raw_size": 2,
        "package_raw_sha256": "sha256:" + "c" * 64,
        "input_closure_digest": "sha256:" + "d" * 64,
        "builder_mutation_policy": "REBUILD_ALWAYS",
        "unexpected_field": "x",
    }
    with pytest.raises(CheckpointDecodeError, match="unknown keys"):
        _prepare_checkpoint_from_job_state(job_state, expected_attempt_id="sa-payload-1")


def test_submit_job_definitions_identities_match_submit_registry_constants() -> None:
    by_step = {definition.key.step_name: definition for definition in submit_job_definitions()}
    assert by_step[SUBMIT_STEP_PREPARE].decoder_identity == PREPARE_IMPORT_DECODER
    assert by_step[SUBMIT_STEP_PREPARE].handler_identity == PREPARE_IMPORT_HANDLER
    assert by_step[SUBMIT_STEP_SUBMIT].decoder_identity == SUBMIT_IMPORT_DECODER
    assert by_step[SUBMIT_STEP_SUBMIT].handler_identity == SUBMIT_IMPORT_HANDLER
    assert by_step[SUBMIT_STEP_AWAIT].decoder_identity == AWAIT_IMPORT_DECODER
    assert by_step[SUBMIT_STEP_AWAIT].handler_identity == AWAIT_IMPORT_HANDLER

    decoders = submit_payload_decoders()
    assert set(decoders) == {
        PREPARE_IMPORT_DECODER,
        SUBMIT_IMPORT_DECODER,
        AWAIT_IMPORT_DECODER,
    }
    decoder_fn = decoders[PREPARE_IMPORT_DECODER]
    assert decoders[SUBMIT_IMPORT_DECODER] is decoder_fn
    assert decoders[AWAIT_IMPORT_DECODER] is decoder_fn
