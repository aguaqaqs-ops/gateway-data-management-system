"""Submit job payload decoder and registry identity tests."""

from __future__ import annotations

import json
from typing import cast
import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value
from pydantic import ValidationError

from gateway_backend.application.payloads import PayloadDecodeError
from gateway_backend.artifacts import InMemoryArtifactStore, artifact_ref_from_dict, put_with_built_ref
from gateway_backend.application.submission.ports import RepositoryWritePort
from gateway_backend.application.submission.contracts import (
    RepositoryImportOperation,
    RepositoryImportOperationError,
    RepositoryImportOperationStatus,
)
from gateway_backend.application.submit_jobs import (
    _await_checkpoint_from_job_state,
    _load_terminal_repository_evidence,
    _prepare_checkpoint_from_job_state,
    _serialize_terminal_repository_evidence,
    _submit_state_from_job_state,
    decode_submit_payload,
    submit_payload_decoders,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_shared_kernel import DigestRef
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


def _artifact_ref_dict(artifact_id: str) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "media_type": "application/jcs",
        "size_bytes": 1,
        "raw_sha256": "sha256:" + "a" * 64,
    }


def _canonical_prepare_checkpoint_job_state() -> dict[str, object]:
    return {
        "schema_version": "backend-vnext/submit/prepare-import-checkpoint/v1",
        "attempt_id": "sa-payload-1",
        "canonicalization_manifest_ref": _artifact_ref_dict("manifest-1"),
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
    }


def _canonical_submit_request_checkpoint_job_state() -> dict[str, object]:
    return {
        "schema_version": "backend-vnext/submit/submit-import-checkpoint/v1",
        "prepare_checkpoint_ref": _artifact_ref_dict("prepare-cp-1"),
        "repository_artifact_ref": {
            "artifact_id": "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",
            "media_type": "application/vnd.gateway.repository-import.v1+tar+zstd",
            "size_bytes": 2,
            "raw_sha256": "sha256:" + "c" * 64,
        },
        "upload_idempotency_key": "p5b-upload-v1:abc",
        "request_artifact_id": "request-1",
        "request_artifact_ref": _artifact_ref_dict("request-1"),
        "request_fingerprint": "sha256:" + "e" * 64,
        "import_idempotency_key": "p5b-import-v1:abc",
        "idempotency_key": "p5b-import-v1:abc",
        "request_sent": False,
        "reconcile_started_at": "2024-06-01T12:00:00Z",
    }


def _canonical_await_terminal_checkpoint_job_state() -> dict[str, object]:
    return {
        "schema_version": "backend-vnext/submit/await-import-result-checkpoint/v1",
        "submit_checkpoint_ref": _artifact_ref_dict("submit-cp-1"),
        "operation_identity": "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",
        "reconcile_started_at": "2024-06-01T12:00:00Z",
        "last_observed_repository_status": "SUCCEEDED",
        "terminal_result_evidence_ref": _artifact_ref_dict("evidence-1"),
    }


def _canonical_terminal_evidence_object() -> dict[str, object]:
    return {
        "document_type": "submit_repository_terminal_evidence",
        "contract_version": "backend-vnext/submit/repository-terminal-evidence/v1",
        "operation_id": "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",
        "status": "SUCCEEDED",
        "result": {
            "operation_id": "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",
            "commit_id": "commit-main",
            "artifact_id": "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",
            "expected_commit_id": "commit-main",
            "canonicalization_manifest_digest": "sha256:" + "b" * 64,
            "completed_verification_policy": "STRUCTURAL",
            "unknown_type_policy": "REJECT",
            "target_ref": "main",
        },
    }


@pytest.mark.parametrize(
    ("decoder", "base_state", "mutation", "message"),
    (
        (
            _prepare_checkpoint_from_job_state,
            _canonical_prepare_checkpoint_job_state(),
            {"unexpected_field": "x"},
            "unknown keys",
        ),
        (
            _prepare_checkpoint_from_job_state,
            _canonical_prepare_checkpoint_job_state(),
            {"attempt_id": None},
            "missing keys",
        ),
    ),
)
def test_prepare_checkpoint_rejects_inexact_job_state(
    decoder: object,
    base_state: dict[str, object],
    mutation: dict[str, object],
    message: str,
) -> None:
    job_state = dict(base_state)
    job_state.update(mutation)
    if "attempt_id" in mutation and mutation["attempt_id"] is None:
        del job_state["attempt_id"]
    with pytest.raises(CheckpointDecodeError, match=message):
        decoder(job_state, expected_attempt_id="sa-payload-1")  # type: ignore[operator]


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ({"request_sent": None}, "request_sent must be a bool"),
        ({"request_sent": "false"}, "request_sent must be a bool"),
        ({"reconcile_started_at": None}, "missing keys"),
        ({"use_sent_branch": True, "operation_identity": None}, "missing keys"),
        ({"unexpected_field": "x"}, "unknown keys"),
    ),
)
def test_submit_checkpoint_rejects_inexact_job_state(
    mutation: dict[str, object],
    message: str,
) -> None:
    job_state = _canonical_submit_request_checkpoint_job_state()
    if mutation.get("use_sent_branch") is True:
        job_state["request_sent"] = True
        job_state["operation_identity"] = "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11"
    for key, value in mutation.items():
        if key == "use_sent_branch":
            continue
        if value is None:
            del job_state[key]
        else:
            job_state[key] = value
    store = InMemoryArtifactStore()
    request_ref = ArtifactRef(
        artifact_id="request-1",
        media_type="application/jcs",
        size_bytes=1,
        raw_sha256=DigestRef("sha256:" + "a" * 64),
    )
    put_with_built_ref(store, b"{}", artifact_id=request_ref.artifact_id, media_type=request_ref.media_type)
    prepare_ref = artifact_ref_from_dict(_artifact_ref_dict("prepare-cp-1"))
    checkpoint_ref = artifact_ref_from_dict(_artifact_ref_dict("submit-cp-1"))
    payload = decode_submit_payload(_canonical_payload_object())

    class _StubRepositoryWrite:
        def canonical_import_request_bytes(self, **kwargs: object) -> bytes:
            return b"{}"

    with pytest.raises(CheckpointDecodeError, match=message):
        _submit_state_from_job_state(
            store,
            job_state,
            repository_write=cast(RepositoryWritePort, _StubRepositoryWrite()),
            expected_payload=payload,
            prepare_checkpoint_ref=prepare_ref,
            checkpoint_ref=checkpoint_ref,
        )


def test_await_terminal_checkpoint_rejects_unknown_job_state_fields() -> None:
    job_state = _canonical_await_terminal_checkpoint_job_state()
    job_state["unexpected_field"] = "x"
    submit_ref = artifact_ref_from_dict(_artifact_ref_dict("submit-cp-1"))
    with pytest.raises(CheckpointDecodeError, match="unknown keys"):
        _await_checkpoint_from_job_state(
            job_state,
            expected_submit_checkpoint_ref=submit_ref,
            expected_repository_operation_id="018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",
        )


def test_await_terminal_checkpoint_rejects_non_terminal_status() -> None:
    job_state = _canonical_await_terminal_checkpoint_job_state()
    job_state["last_observed_repository_status"] = "QUEUED"
    submit_ref = artifact_ref_from_dict(_artifact_ref_dict("submit-cp-1"))
    with pytest.raises(CheckpointDecodeError, match="terminal repository status"):
        _await_checkpoint_from_job_state(
            job_state,
            expected_submit_checkpoint_ref=submit_ref,
            expected_repository_operation_id="018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",
        )


def test_terminal_evidence_rejects_unknown_fields() -> None:
    store = InMemoryArtifactStore()
    evidence = _canonical_terminal_evidence_object()
    evidence["unexpected_field"] = "x"
    evidence_ref = put_with_built_ref(
        store,
        json.dumps(evidence).encode(),
        artifact_id="evidence-1",
        media_type="application/jcs",
    )
    with pytest.raises(CheckpointDecodeError, match="unknown keys"):
        _load_terminal_repository_evidence(store, evidence_ref)


_FAILED_TERMINAL_EVIDENCE_GOLDEN = (
    b'{"contract_version":"backend-vnext/submit/repository-terminal-evidence/v1",'
    b'"document_type":"submit_repository_terminal_evidence",'
    b'"error":{"code":"IMPORT_REJECTED","details":{"table":"t1"},"message":"rejected","request_id":null},'
    b'"operation_id":"018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",'
    b'"status":"FAILED"}'
)


def test_failed_terminal_evidence_bytes_match_base_golden() -> None:
    operation = RepositoryImportOperation(
        operation_id="018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",
        status=RepositoryImportOperationStatus.FAILED,
        error=RepositoryImportOperationError(
            code="IMPORT_REJECTED",
            message="rejected",
            details={"table": "t1"},
            request_id=None,
        ),
    )
    evidence_bytes = canonicalize_json_value(_serialize_terminal_repository_evidence(operation))
    assert evidence_bytes == _FAILED_TERMINAL_EVIDENCE_GOLDEN


def _failed_terminal_evidence_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "document_type": "submit_repository_terminal_evidence",
        "contract_version": "backend-vnext/submit/repository-terminal-evidence/v1",
        "operation_id": "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",
        "status": "FAILED",
        "error": {
            "code": "IMPORT_REJECTED",
            "message": "rejected",
            "request_id": None,
        },
    }
    document.update(overrides)
    return document


MALFORMED_TERMINAL_EVIDENCE_SHAPES: tuple[tuple[dict[str, object], type[Exception]], ...] = (
    (
        _failed_terminal_evidence_document(
            error={"code": "SOMETHING_ELSE", "message": "nope", "request_id": None}
        ),
        ValidationError,
    ),
    (
        _failed_terminal_evidence_document(operation_id="not-a-uuid"),
        ValidationError,
    ),
    (
        _failed_terminal_evidence_document(error={"code": "IMPORT_REJECTED"}),
        ValidationError,
    ),
    (
        _failed_terminal_evidence_document(
            error={
                "code": "IMPORT_REJECTED",
                "message": "rejected",
                "request_id": None,
                "extra": "x",
            }
        ),
        ValidationError,
    ),
    (
        _failed_terminal_evidence_document(
            error={
                "code": "IMPORT_REJECTED",
                "message": "rejected",
                "request_id": "req-1",
            }
        ),
        ValidationError,
    ),
)


@pytest.mark.parametrize(
    ("evidence", "expected_error"),
    MALFORMED_TERMINAL_EVIDENCE_SHAPES,
)
def test_terminal_evidence_rejects_malformed_operation_payload(
    evidence: dict[str, object],
    expected_error: type[Exception],
) -> None:
    store = InMemoryArtifactStore()
    evidence_ref = put_with_built_ref(
        store,
        json.dumps(evidence).encode(),
        artifact_id="evidence-1",
        media_type="application/jcs",
    )
    with pytest.raises(expected_error):
        _load_terminal_repository_evidence(store, evidence_ref)


def test_terminal_evidence_rejects_checkpoint_status_mismatch() -> None:
    store = InMemoryArtifactStore()
    evidence = _canonical_terminal_evidence_object()
    evidence["status"] = "FAILED"
    evidence["error"] = {
        "code": "IMPORT_REJECTED",
        "message": "rejected",
    }
    del evidence["result"]
    evidence_ref = put_with_built_ref(
        store,
        json.dumps(evidence).encode(),
        artifact_id="evidence-1",
        media_type="application/jcs",
    )
    with pytest.raises(CheckpointDecodeError, match="status does not match checkpoint"):
        _load_terminal_repository_evidence(
            store,
            evidence_ref,
            expected_operation_id="018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11",
            expected_status="SUCCEEDED",
        )


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
