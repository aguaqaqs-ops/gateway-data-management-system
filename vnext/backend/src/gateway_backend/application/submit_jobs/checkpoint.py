"""Submit job checkpoint state serialization, restoration, and pin helpers."""

from __future__ import annotations

import json

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from gateway_backend.application.checkpoints import (
    envelope_for_step,
    prepare_step_checkpoint,
)
from gateway_backend.application.job_definitions import JobDefinition
from gateway_backend.application.job_steps import (
    checkpoint_generation,
    load_step,
    pinned_checkpoint_builder,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.recovery import (
    ExternalEffectRequestIdentity,
    JOB_STATE_IDEMPOTENCY_KEY,
    JOB_STATE_OPERATION_IDENTITY,
    JOB_STATE_REQUEST_FINGERPRINT,
    JOB_STATE_REQUEST_SENT,
    RecoveryOutcome,
    compute_request_fingerprint,
    validate_external_effect_identity,
)
from gateway_backend.application.submission.artifact_refs import store_ref_from_backend_artifact_ref
from gateway_backend.application.submission.contracts import (
    PREPARE_IMPORT_CHECKPOINT_SCHEMA,
    PrepareImportCheckpoint,
    RepositoryImportOperation,
    RepositoryImportOperationStatus as RepositoryOperationStatus,
)
from gateway_backend.application.submission.errors import PrepareCheckpointPayloadBindingError
from gateway_backend.application.submission.import_builder import pin_prepare_import_artifacts
from gateway_backend.application.submission.ports import (
    RepositoryTerminalEvidenceDecodePort,
    RepositoryWritePort,
    SubmitControlTransaction,
    SubmitFinalizeControlTransaction,
)
from gateway_backend.artifacts.location import (
    ArtifactLocation,
    build_artifact_id,
)
from gateway_backend.artifacts.serialize import (
    artifact_ref_from_dict,
    artifact_ref_to_dict,
)
from gateway_backend.artifacts.store import (
    ArtifactStorePort,
    put_with_built_ref,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    SubmitAttempt,
)
from gateway_backend.operations.contracts import (
    OperationRecord,
    StepRecord,
)
from gateway_backend.operations.worker import LeaseSession
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.submit_jobs.payload import (
    AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA,
    SUBMIT_IMPORT_CHECKPOINT_SCHEMA,
    SubmitJobError,
    SubmitJobPayload,
    SubmitRuntimeDependencies,
    _EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
    _JCS_MEDIA_TYPE,
    _decode_checkpoint_string_tuple,
    _require_artifact_ref_dict,
    _require_mapping,
    _require_non_empty_str_value,
    _require_non_negative_int_value,
)

_JOB_STATE_SCHEMA_VERSION = "schema_version"

_JOB_STATE_ATTEMPT_ID = "attempt_id"

_JOB_STATE_MANIFEST_REF = "canonicalization_manifest_ref"

_JOB_STATE_MANIFEST_DIGEST = "canonicalization_manifest_digest"

_JOB_STATE_BACKEND_IMPORT_REF = "backend_import_artifact_ref"

_JOB_STATE_PACKAGE_RAW_SIZE = "package_raw_size"

_JOB_STATE_PACKAGE_RAW_SHA256 = "package_raw_sha256"

_JOB_STATE_CANONICAL_TABLE_SET_CLOSURE_REF = "canonical_table_set_closure_ref"

_JOB_STATE_CANONICAL_TABLE_SET_CLOSURE_DIGEST = "canonical_table_set_closure_digest"

_JOB_STATE_INPUT_MANIFEST_REF = "input_canonicalization_manifest_ref"

_JOB_STATE_INPUT_MANIFEST_DIGEST = "input_canonicalization_manifest_digest"

_JOB_STATE_EXPECTED_PARENT_COMMIT_ID = "expected_parent_commit_id"

_JOB_STATE_PARENT_MANIFEST_DIGEST = "parent_manifest_digest"

_JOB_STATE_PARENT_IS_INITIAL = "parent_is_initial"

_JOB_STATE_REMOVED_TABLES = "removed_tables"

_JOB_STATE_BUILDER_POLICY = "builder_mutation_policy"

_JOB_STATE_PREPARE_CHECKPOINT_REF = "prepare_checkpoint_ref"

_JOB_STATE_REPOSITORY_ARTIFACT_REF = "repository_artifact_ref"

_JOB_STATE_UPLOAD_KEY = "upload_idempotency_key"

_JOB_STATE_REQUEST_ARTIFACT_ID = "request_artifact_id"

_JOB_STATE_REQUEST_ARTIFACT_REF = "request_artifact_ref"

_JOB_STATE_IMPORT_KEY = "import_idempotency_key"

_JOB_STATE_SUBMIT_CHECKPOINT_REF = "submit_checkpoint_ref"

_JOB_STATE_LAST_OBSERVED_REPOSITORY_STATUS = "last_observed_repository_status"

_JOB_STATE_TERMINAL_RESULT_EVIDENCE_REF = "terminal_result_evidence_ref"

_TERMINAL_REPOSITORY_EVIDENCE_DOCUMENT_TYPE = "submit_repository_terminal_evidence"

_TERMINAL_REPOSITORY_EVIDENCE_CONTRACT_VERSION = (
    "backend-vnext/submit/repository-terminal-evidence/v1"
)

_active_submit_transaction: ContextVar[SubmitFinalizeControlTransaction | None] = ContextVar(
    "_active_submit_transaction",
    default=None,
)

@dataclass(frozen=True, slots=True)
class _SubmitCheckpointState:
    prepare_checkpoint_ref: ArtifactRef
    repository_artifact_ref: RepositoryArtifactRef
    request_artifact_ref: ArtifactRef
    request_fingerprint: str
    request_sent: bool
    repository_operation_id: str | None
    checkpoint_ref: ArtifactRef

@dataclass(frozen=True, slots=True)
class _AwaitCheckpointState:
    submit_checkpoint_ref: ArtifactRef
    repository_operation_id: str
    last_observed_repository_status: str | None
    terminal_result_evidence_ref: ArtifactRef | None

def _prepare_step_checkpoint(
    *,
    deps: SubmitRuntimeDependencies,
    definition: JobDefinition,
    operation: OperationRecord,
    step: StepRecord,
    checkpoint: PrepareImportCheckpoint,
    lease_session: LeaseSession,
    attempt: SubmitAttempt,
    operation_record: OperationRecord,
) -> ArtifactRef:
    envelope = envelope_for_step(
        key=definition.key,
        operation=operation,
        step=step,
        checkpoint_generation=checkpoint_generation(step),
        job_state=_job_state_for_prepare(checkpoint),
    )
    checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
    _pin_prepare_refs(
        deps=deps,
        attempt=attempt,
        operation=operation_record,
        checkpoint=checkpoint,
    )
    lease_session.publish_checkpoint(
        pinned_checkpoint_builder(
            checkpoint_ref=checkpoint_ref,
            extra_refs=_prepare_checkpoint_extra_refs(checkpoint),
            owner_kind="submit-checkpoint",
            active_transaction=_active_submit_transaction.get,
            transaction_missing=lambda: SubmitJobError(
                "submit checkpoint transaction is not bound"
            ),
            deduplicate_refs=False,
            intent="prepare-import-checkpoint",
        )
    )
    return checkpoint_ref

def _prepare_checkpoint_extra_refs(checkpoint: PrepareImportCheckpoint) -> tuple[ArtifactRef, ...]:
    return (
        store_ref_from_backend_artifact_ref(checkpoint.canonicalization_manifest_ref),
        store_ref_from_backend_artifact_ref(checkpoint.backend_import_artifact_ref),
    )

def _pin_prepare_refs(
    *,
    deps: SubmitRuntimeDependencies,
    attempt: SubmitAttempt,
    operation: OperationRecord,
    checkpoint: PrepareImportCheckpoint,
) -> None:
    with deps.control_transaction_factory() as unit_of_work:
        pin_prepare_import_artifacts(
            unit_of_work,
            submit_attempt_id=attempt.submit_attempt_id,
            manifest_ref=checkpoint.canonicalization_manifest_ref,
            package_ref=checkpoint.backend_import_artifact_ref,
            existing_snapshot_refs=operation.artifact_refs,
        )

def _pin_submit_checkpoint_refs(
    transaction: SubmitControlTransaction,
    *,
    step_id: str,
    checkpoint_ref: ArtifactRef,
    extra_refs: tuple[ArtifactRef, ...],
    intent: str,
) -> None:
    transaction.set_artifact_protection(
        (checkpoint_ref, *extra_refs),
        owner_kind="submit-checkpoint",
        owner_id=step_id,
        intent=intent,
    )

def _load_step(
    deps: SubmitRuntimeDependencies,
    *,
    operation_id: str,
    step_id: str,
) -> StepRecord:
    return load_step(
        deps.control_transaction_factory,
        operation_id=operation_id,
        step_id=step_id,
        mismatch_error=lambda: SubmitJobError("submit step belongs to a different operation"),
    )

def _job_state_for_prepare(checkpoint: PrepareImportCheckpoint) -> dict[str, object]:
    return {
        _JOB_STATE_SCHEMA_VERSION: PREPARE_IMPORT_CHECKPOINT_SCHEMA,
        _JOB_STATE_ATTEMPT_ID: checkpoint.attempt_id,
        _JOB_STATE_MANIFEST_REF: _backend_ref_to_dict(checkpoint.canonicalization_manifest_ref),
        _JOB_STATE_MANIFEST_DIGEST: checkpoint.canonicalization_manifest_digest,
        _JOB_STATE_BACKEND_IMPORT_REF: _backend_ref_to_dict(checkpoint.backend_import_artifact_ref),
        _JOB_STATE_PACKAGE_RAW_SIZE: checkpoint.package_raw_size,
        _JOB_STATE_PACKAGE_RAW_SHA256: checkpoint.package_raw_sha256,
        _JOB_STATE_CANONICAL_TABLE_SET_CLOSURE_REF: checkpoint.canonical_table_set_closure_ref,
        _JOB_STATE_CANONICAL_TABLE_SET_CLOSURE_DIGEST: checkpoint.canonical_table_set_closure_digest,
        _JOB_STATE_INPUT_MANIFEST_REF: checkpoint.input_canonicalization_manifest_ref,
        _JOB_STATE_INPUT_MANIFEST_DIGEST: checkpoint.input_canonicalization_manifest_digest,
        _JOB_STATE_EXPECTED_PARENT_COMMIT_ID: checkpoint.expected_parent_commit_id,
        _JOB_STATE_PARENT_MANIFEST_DIGEST: checkpoint.parent_manifest_digest,
        _JOB_STATE_PARENT_IS_INITIAL: checkpoint.parent_is_initial,
        _JOB_STATE_REMOVED_TABLES: list(checkpoint.removed_tables),
        _JOB_STATE_BUILDER_POLICY: checkpoint.builder_mutation_policy.value,
    }

_ALLOWED_PREPARE_CHECKPOINT_KEYS = frozenset(
    {
        _JOB_STATE_SCHEMA_VERSION,
        _JOB_STATE_ATTEMPT_ID,
        _JOB_STATE_MANIFEST_REF,
        _JOB_STATE_MANIFEST_DIGEST,
        _JOB_STATE_BACKEND_IMPORT_REF,
        _JOB_STATE_PACKAGE_RAW_SIZE,
        _JOB_STATE_PACKAGE_RAW_SHA256,
        _JOB_STATE_CANONICAL_TABLE_SET_CLOSURE_REF,
        _JOB_STATE_CANONICAL_TABLE_SET_CLOSURE_DIGEST,
        _JOB_STATE_INPUT_MANIFEST_REF,
        _JOB_STATE_INPUT_MANIFEST_DIGEST,
        _JOB_STATE_EXPECTED_PARENT_COMMIT_ID,
        _JOB_STATE_PARENT_MANIFEST_DIGEST,
        _JOB_STATE_PARENT_IS_INITIAL,
        _JOB_STATE_REMOVED_TABLES,
        _JOB_STATE_BUILDER_POLICY,
    }
)

_ALLOWED_SUBMIT_CHECKPOINT_REQUEST_KEYS = frozenset(
    {
        _JOB_STATE_SCHEMA_VERSION,
        _JOB_STATE_PREPARE_CHECKPOINT_REF,
        _JOB_STATE_REPOSITORY_ARTIFACT_REF,
        _JOB_STATE_UPLOAD_KEY,
        _JOB_STATE_REQUEST_ARTIFACT_ID,
        _JOB_STATE_REQUEST_ARTIFACT_REF,
        JOB_STATE_REQUEST_FINGERPRINT,
        _JOB_STATE_IMPORT_KEY,
        JOB_STATE_IDEMPOTENCY_KEY,
        JOB_STATE_REQUEST_SENT,
    }
)

_ALLOWED_SUBMIT_CHECKPOINT_SENT_KEYS = _ALLOWED_SUBMIT_CHECKPOINT_REQUEST_KEYS | frozenset(
    {JOB_STATE_OPERATION_IDENTITY}
)

_ALLOWED_AWAIT_RECONCILE_CHECKPOINT_KEYS = frozenset(
    {
        _JOB_STATE_SCHEMA_VERSION,
        _JOB_STATE_SUBMIT_CHECKPOINT_REF,
        JOB_STATE_OPERATION_IDENTITY,
    }
)

_ALLOWED_AWAIT_TERMINAL_CHECKPOINT_KEYS = _ALLOWED_AWAIT_RECONCILE_CHECKPOINT_KEYS | frozenset(
    {
        _JOB_STATE_LAST_OBSERVED_REPOSITORY_STATUS,
        _JOB_STATE_TERMINAL_RESULT_EVIDENCE_REF,
    }
)

def _require_exact_job_state_keys(
    job_state: Mapping[str, object],
    *,
    allowed_keys: frozenset[str],
) -> None:
    actual_keys = frozenset(job_state)
    missing = sorted(allowed_keys - actual_keys)
    if missing:
        raise CheckpointDecodeError(
            f"checkpoint job_state is missing keys: {', '.join(missing)}",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    unknown = sorted(actual_keys - allowed_keys)
    if unknown:
        raise CheckpointDecodeError(
            f"checkpoint job_state contains unknown keys: {', '.join(unknown)}",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )

_TERMINAL_REPOSITORY_EVIDENCE_BASE_KEYS = frozenset(
    {
        "document_type",
        "contract_version",
        "operation_id",
        "status",
    }
)

_TERMINAL_REPOSITORY_EVIDENCE_SUCCEEDED_KEYS = _TERMINAL_REPOSITORY_EVIDENCE_BASE_KEYS | frozenset(
    {"result"}
)

_TERMINAL_REPOSITORY_EVIDENCE_FAILED_KEYS = _TERMINAL_REPOSITORY_EVIDENCE_BASE_KEYS | frozenset(
    {"error"}
)

def _require_terminal_repository_status_value(value: object, *, label: str) -> str:
    status = _require_non_empty_str_value(value, label=label)
    if status not in {
        RepositoryOperationStatus.SUCCEEDED.value,
        RepositoryOperationStatus.FAILED.value,
    }:
        raise CheckpointDecodeError(
            f"{label} must be a terminal repository status",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    return status

def _job_state_for_await_reconcile(
    *,
    submit_checkpoint_ref: ArtifactRef,
    repository_operation_id: str,
) -> dict[str, object]:
    return {
        _JOB_STATE_SCHEMA_VERSION: AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA,
        _JOB_STATE_SUBMIT_CHECKPOINT_REF: artifact_ref_to_dict(submit_checkpoint_ref),
        JOB_STATE_OPERATION_IDENTITY: repository_operation_id,
    }

def _job_state_for_await_terminal(
    *,
    submit_checkpoint_ref: ArtifactRef,
    repository_operation_id: str,
    last_observed_repository_status: str,
    terminal_result_evidence_ref: ArtifactRef,
) -> dict[str, object]:
    return {
        _JOB_STATE_SCHEMA_VERSION: AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA,
        _JOB_STATE_SUBMIT_CHECKPOINT_REF: artifact_ref_to_dict(submit_checkpoint_ref),
        JOB_STATE_OPERATION_IDENTITY: repository_operation_id,
        _JOB_STATE_LAST_OBSERVED_REPOSITORY_STATUS: last_observed_repository_status,
        _JOB_STATE_TERMINAL_RESULT_EVIDENCE_REF: artifact_ref_to_dict(terminal_result_evidence_ref),
    }

def _await_checkpoint_from_job_state(
    job_state: Mapping[str, object],
    *,
    expected_submit_checkpoint_ref: ArtifactRef,
    expected_repository_operation_id: str,
) -> _AwaitCheckpointState:
    schema_version = job_state.get(_JOB_STATE_SCHEMA_VERSION)
    if schema_version != AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA:
        raise CheckpointDecodeError(
            "await checkpoint schema_version is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    has_terminal_evidence = _JOB_STATE_TERMINAL_RESULT_EVIDENCE_REF in job_state
    _require_exact_job_state_keys(
        job_state,
        allowed_keys=(
            _ALLOWED_AWAIT_TERMINAL_CHECKPOINT_KEYS
            if has_terminal_evidence
            else _ALLOWED_AWAIT_RECONCILE_CHECKPOINT_KEYS
        ),
    )
    stored_submit_ref = _require_artifact_ref_dict(
        job_state.get(_JOB_STATE_SUBMIT_CHECKPOINT_REF),
        label="submit_checkpoint_ref",
    )
    if artifact_ref_to_dict(expected_submit_checkpoint_ref) != stored_submit_ref:
        raise CheckpointDecodeError(
            "await checkpoint submit_checkpoint_ref does not match predecessor",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    repository_operation_id = _require_non_empty_str_value(
        job_state.get(JOB_STATE_OPERATION_IDENTITY),
        label="operation_identity",
    )
    if repository_operation_id != expected_repository_operation_id:
        raise CheckpointDecodeError(
            "await checkpoint operation_identity does not match submit checkpoint",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    last_observed_repository_status = None
    terminal_result_evidence_ref = None
    if has_terminal_evidence:
        last_observed_repository_status = _require_terminal_repository_status_value(
            job_state.get(_JOB_STATE_LAST_OBSERVED_REPOSITORY_STATUS),
            label="last_observed_repository_status",
        )
        terminal_result_evidence_ref = artifact_ref_from_dict(
            _require_artifact_ref_dict(
                job_state.get(_JOB_STATE_TERMINAL_RESULT_EVIDENCE_REF),
                label="terminal_result_evidence_ref",
            )
        )
    return _AwaitCheckpointState(
        submit_checkpoint_ref=expected_submit_checkpoint_ref,
        repository_operation_id=repository_operation_id,
        last_observed_repository_status=last_observed_repository_status,
        terminal_result_evidence_ref=terminal_result_evidence_ref,
    )

def _serialize_terminal_repository_evidence(
    operation: RepositoryImportOperation,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "document_type": _TERMINAL_REPOSITORY_EVIDENCE_DOCUMENT_TYPE,
        "contract_version": _TERMINAL_REPOSITORY_EVIDENCE_CONTRACT_VERSION,
        "operation_id": operation.operation_id,
        "status": operation.status.value,
    }
    if operation.result is not None:
        payload["result"] = {
            "commit_id": operation.result.commit_id,
            "target_ref": operation.result.target_ref,
            "artifact_id": operation.result.artifact_id,
            "canonicalization_manifest_digest": operation.result.canonicalization_manifest_digest,
            "expected_commit_id": operation.result.expected_commit_id,
            "completed_verification_policy": operation.result.completed_verification_policy,
            "unknown_type_policy": operation.result.unknown_type_policy,
        }
    if operation.error is not None:
        payload["error"] = {
            "code": operation.error.code,
            "message": operation.error.message,
            "details": operation.error.details,
            "request_id": operation.error.request_id,
        }
    return payload

def _persist_terminal_repository_evidence(
    store: ArtifactStorePort,
    operation: RepositoryImportOperation,
) -> ArtifactRef:
    evidence_bytes = canonicalize_json_value(_serialize_terminal_repository_evidence(operation))
    return put_with_built_ref(
        store,
        evidence_bytes,
        artifact_id=build_artifact_id(
            ArtifactLocation.DURABLE,
            "submit-repository-terminal-evidence",
            raw_blob_digest(evidence_bytes).value,
        ),
        media_type=_JCS_MEDIA_TYPE,
    )

def _load_terminal_repository_evidence(
    store: ArtifactStorePort,
    evidence_ref: ArtifactRef,
    *,
    terminal_evidence_decode: RepositoryTerminalEvidenceDecodePort,
    expected_operation_id: str | None = None,
    expected_status: str | None = None,
) -> RepositoryImportOperation:
    evidence_object = json.loads(store.locate(evidence_ref))
    if type(evidence_object) is not dict:
        raise CheckpointDecodeError(
            "terminal repository evidence must be a JSON object",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    document_type = evidence_object.get("document_type")
    if document_type != _TERMINAL_REPOSITORY_EVIDENCE_DOCUMENT_TYPE:
        raise CheckpointDecodeError(
            "terminal repository evidence document_type is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    contract_version = evidence_object.get("contract_version")
    if contract_version != _TERMINAL_REPOSITORY_EVIDENCE_CONTRACT_VERSION:
        raise CheckpointDecodeError(
            "terminal repository evidence contract_version is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    status = _require_terminal_repository_status_value(
        evidence_object.get("status"),
        label="terminal repository evidence status",
    )
    allowed_keys = (
        _TERMINAL_REPOSITORY_EVIDENCE_SUCCEEDED_KEYS
        if status == RepositoryOperationStatus.SUCCEEDED.value
        else _TERMINAL_REPOSITORY_EVIDENCE_FAILED_KEYS
    )
    _require_exact_job_state_keys(evidence_object, allowed_keys=allowed_keys)
    operation_payload = {
        "operation_id": evidence_object.get("operation_id"),
        "status": status,
        "result": evidence_object.get("result"),
        "error": evidence_object.get("error"),
    }
    operation = terminal_evidence_decode.decode_from_evidence_payload(operation_payload)
    if expected_operation_id is not None and operation.operation_id != expected_operation_id:
        raise CheckpointDecodeError(
            "terminal repository evidence operation_id does not match checkpoint",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if expected_status is not None and operation.status.value != expected_status:
        raise CheckpointDecodeError(
            "terminal repository evidence status does not match checkpoint",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    return operation

def _prepare_checkpoint_from_job_state(
    job_state: Mapping[str, object],
    *,
    expected_attempt_id: str,
) -> PrepareImportCheckpoint:
    schema_version = job_state.get(_JOB_STATE_SCHEMA_VERSION)
    if schema_version != PREPARE_IMPORT_CHECKPOINT_SCHEMA:
        raise CheckpointDecodeError(
            "prepare checkpoint schema_version is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    _require_exact_job_state_keys(job_state, allowed_keys=_ALLOWED_PREPARE_CHECKPOINT_KEYS)
    attempt_id = job_state.get(_JOB_STATE_ATTEMPT_ID)
    if type(attempt_id) is not str or attempt_id != expected_attempt_id:
        raise PrepareCheckpointPayloadBindingError()
    parent_manifest_digest = job_state.get(_JOB_STATE_PARENT_MANIFEST_DIGEST)
    parent_is_initial = job_state.get(_JOB_STATE_PARENT_IS_INITIAL)
    if parent_manifest_digest is not None and type(parent_manifest_digest) is not str:
        raise CheckpointDecodeError(
            "prepare checkpoint parent manifest digest is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if type(parent_is_initial) is not bool:
        raise CheckpointDecodeError(
            "prepare checkpoint parent status is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    return PrepareImportCheckpoint(
        schema_version=PREPARE_IMPORT_CHECKPOINT_SCHEMA,
        attempt_id=attempt_id,
        canonicalization_manifest_ref=_backend_ref_from_dict(
            _require_mapping(
                job_state.get(_JOB_STATE_MANIFEST_REF), label="canonicalization_manifest_ref"
            ),
        ),
        canonicalization_manifest_digest=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_MANIFEST_DIGEST),
            label="canonicalization_manifest_digest",
        ),
        backend_import_artifact_ref=_backend_ref_from_dict(
            _require_mapping(
                job_state.get(_JOB_STATE_BACKEND_IMPORT_REF), label="backend_import_artifact_ref"
            ),
        ),
        package_raw_size=_require_non_negative_int_value(
            job_state.get(_JOB_STATE_PACKAGE_RAW_SIZE)
        ),
        package_raw_sha256=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_PACKAGE_RAW_SHA256),
            label="package_raw_sha256",
        ),
        canonical_table_set_closure_ref=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_CANONICAL_TABLE_SET_CLOSURE_REF),
            label="canonical_table_set_closure_ref",
        ),
        canonical_table_set_closure_digest=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_CANONICAL_TABLE_SET_CLOSURE_DIGEST),
            label="canonical_table_set_closure_digest",
        ),
        input_canonicalization_manifest_ref=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_INPUT_MANIFEST_REF),
            label="input_canonicalization_manifest_ref",
        ),
        input_canonicalization_manifest_digest=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_INPUT_MANIFEST_DIGEST),
            label="input_canonicalization_manifest_digest",
        ),
        expected_parent_commit_id=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_EXPECTED_PARENT_COMMIT_ID),
            label="expected_parent_commit_id",
        ),
        parent_manifest_digest=parent_manifest_digest,
        parent_is_initial=parent_is_initial,
        removed_tables=_decode_checkpoint_string_tuple(
            job_state.get(_JOB_STATE_REMOVED_TABLES),
            label="removed_tables",
        ),
        builder_mutation_policy=BuilderMutationPolicy(
            _require_non_empty_str_value(
                job_state.get(_JOB_STATE_BUILDER_POLICY), label="builder_mutation_policy"
            )
        ),
    )

def _job_state_for_submit_request(
    *,
    prepare_checkpoint_ref: ArtifactRef,
    repository_artifact_ref: RepositoryArtifactRef,
    payload: SubmitJobPayload,
    request_artifact_ref: ArtifactRef,
    request_fingerprint: str,
) -> dict[str, object]:
    return {
        _JOB_STATE_SCHEMA_VERSION: SUBMIT_IMPORT_CHECKPOINT_SCHEMA,
        _JOB_STATE_PREPARE_CHECKPOINT_REF: artifact_ref_to_dict(prepare_checkpoint_ref),
        _JOB_STATE_REPOSITORY_ARTIFACT_REF: _repository_ref_to_dict(repository_artifact_ref),
        _JOB_STATE_UPLOAD_KEY: payload.repository_upload_idempotency_key,
        _JOB_STATE_REQUEST_ARTIFACT_ID: request_artifact_ref.artifact_id,
        _JOB_STATE_REQUEST_ARTIFACT_REF: artifact_ref_to_dict(request_artifact_ref),
        JOB_STATE_REQUEST_FINGERPRINT: request_fingerprint,
        _JOB_STATE_IMPORT_KEY: payload.repository_import_idempotency_key,
        JOB_STATE_IDEMPOTENCY_KEY: payload.repository_import_idempotency_key,
        JOB_STATE_REQUEST_SENT: False,
    }

def _job_state_for_submit_sent(
    *,
    prepare_checkpoint_ref: ArtifactRef,
    repository_artifact_ref: RepositoryArtifactRef,
    payload: SubmitJobPayload,
    request_artifact_ref: ArtifactRef,
    request_fingerprint: str,
    repository_operation_id: str,
) -> dict[str, object]:
    return {
        _JOB_STATE_SCHEMA_VERSION: SUBMIT_IMPORT_CHECKPOINT_SCHEMA,
        _JOB_STATE_PREPARE_CHECKPOINT_REF: artifact_ref_to_dict(prepare_checkpoint_ref),
        _JOB_STATE_REPOSITORY_ARTIFACT_REF: _repository_ref_to_dict(repository_artifact_ref),
        _JOB_STATE_UPLOAD_KEY: payload.repository_upload_idempotency_key,
        _JOB_STATE_REQUEST_ARTIFACT_ID: request_artifact_ref.artifact_id,
        _JOB_STATE_REQUEST_ARTIFACT_REF: artifact_ref_to_dict(request_artifact_ref),
        JOB_STATE_REQUEST_FINGERPRINT: request_fingerprint,
        _JOB_STATE_IMPORT_KEY: payload.repository_import_idempotency_key,
        JOB_STATE_IDEMPOTENCY_KEY: payload.repository_import_idempotency_key,
        JOB_STATE_REQUEST_SENT: True,
        JOB_STATE_OPERATION_IDENTITY: repository_operation_id,
    }

def _submit_state_from_job_state(
    store: ArtifactStorePort,
    job_state: Mapping[str, object],
    *,
    repository_write: RepositoryWritePort,
    expected_payload: SubmitJobPayload,
    prepare_checkpoint_ref: ArtifactRef,
    checkpoint_ref: ArtifactRef,
) -> _SubmitCheckpointState:
    if job_state.get(_JOB_STATE_SCHEMA_VERSION) != SUBMIT_IMPORT_CHECKPOINT_SCHEMA:
        raise CheckpointDecodeError(
            "submit checkpoint schema_version is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    request_sent_value = job_state.get(JOB_STATE_REQUEST_SENT)
    if type(request_sent_value) is not bool:
        raise CheckpointDecodeError(
            "submit checkpoint request_sent must be a bool",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    request_sent = request_sent_value
    _require_exact_job_state_keys(
        job_state,
        allowed_keys=(
            _ALLOWED_SUBMIT_CHECKPOINT_SENT_KEYS
            if request_sent
            else _ALLOWED_SUBMIT_CHECKPOINT_REQUEST_KEYS
        ),
    )
    stored_prepare_ref = _require_artifact_ref_dict(
        job_state.get(_JOB_STATE_PREPARE_CHECKPOINT_REF),
        label="prepare_checkpoint_ref",
    )
    if artifact_ref_to_dict(prepare_checkpoint_ref) != stored_prepare_ref:
        raise CheckpointDecodeError(
            "submit checkpoint prepare_checkpoint_ref does not match predecessor",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    repository_artifact_ref = _repository_ref_from_dict(
        _require_mapping(
            job_state.get(_JOB_STATE_REPOSITORY_ARTIFACT_REF), label="repository_artifact_ref"
        ),
    )
    upload_key = job_state.get(_JOB_STATE_UPLOAD_KEY)
    if upload_key != expected_payload.repository_upload_idempotency_key:
        raise CheckpointDecodeError(
            "submit checkpoint upload_idempotency_key does not match payload",
            code=_EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
        )
    import_key = job_state.get(_JOB_STATE_IMPORT_KEY)
    if import_key != expected_payload.repository_import_idempotency_key:
        raise CheckpointDecodeError(
            "submit checkpoint import_idempotency_key does not match payload",
            code=_EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
        )
    request_artifact_id = _require_non_empty_str_value(
        job_state.get(_JOB_STATE_REQUEST_ARTIFACT_ID),
        label="request_artifact_id",
    )
    request_artifact_ref = artifact_ref_from_dict(
        _require_artifact_ref_dict(
            job_state.get(_JOB_STATE_REQUEST_ARTIFACT_REF), label="request_artifact_ref"
        ),
    )
    if request_artifact_ref.artifact_id != request_artifact_id:
        raise CheckpointDecodeError(
            "submit checkpoint request_artifact_id does not match request_artifact_ref",
            code=_EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
        )
    request_bytes = store.locate(request_artifact_ref)
    expected_request_bytes = repository_write.canonical_import_request_bytes(
        repository_id=expected_payload.repository_id,
        artifact_ref=repository_artifact_ref,
        expected_commit_id=expected_payload.repository_expected_commit_id,
    )
    if request_bytes != expected_request_bytes:
        raise CheckpointDecodeError(
            "submit checkpoint request bytes do not match payload semantics",
            code=_EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
        )
    if job_state.get(JOB_STATE_REQUEST_SENT) is True:
        expected_operation_identity = _require_non_empty_str_value(
            job_state.get(JOB_STATE_OPERATION_IDENTITY),
            label="operation_identity",
        )
    else:
        expected_operation_identity = _expected_operation_identity_placeholder(request_bytes)
    identity_result = validate_external_effect_identity(
        idempotency_key=expected_payload.repository_import_idempotency_key,
        request_bytes=request_bytes,
        job_state=job_state,
        expected_operation_identity=expected_operation_identity,
    )
    if isinstance(identity_result, RecoveryOutcome):
        if job_state.get(JOB_STATE_REQUEST_SENT) is True:
            raise CheckpointDecodeError(
                identity_result.reason or "submit checkpoint identity mismatch",
                code=_EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
            )
    request_fingerprint = compute_request_fingerprint(request_bytes)
    stored_fingerprint = job_state.get(JOB_STATE_REQUEST_FINGERPRINT)
    if type(stored_fingerprint) is not str or stored_fingerprint != request_fingerprint:
        raise CheckpointDecodeError(
            "submit checkpoint request_fingerprint does not match payload semantics",
            code=_EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE,
        )
    repository_operation_id = None
    if request_sent:
        if isinstance(identity_result, ExternalEffectRequestIdentity):
            repository_operation_id = identity_result.repository_operation_id
        else:
            stored_identity = job_state.get(JOB_STATE_OPERATION_IDENTITY)
            if type(stored_identity) is not str or not stored_identity:
                raise CheckpointDecodeError(
                    "submit checkpoint operation_identity is invalid",
                    code="CHECKPOINT_JOB_STATE_MISMATCH",
                )
            repository_operation_id = stored_identity
    return _SubmitCheckpointState(
        prepare_checkpoint_ref=prepare_checkpoint_ref,
        repository_artifact_ref=repository_artifact_ref,
        request_artifact_ref=request_artifact_ref,
        request_fingerprint=request_fingerprint,
        request_sent=request_sent,
        repository_operation_id=repository_operation_id,
        checkpoint_ref=checkpoint_ref,
    )

def _expected_operation_identity_placeholder(request_bytes: bytes) -> str:
    del request_bytes
    return "pending"

def _backend_ref_to_dict(ref: BackendArtifactRef) -> dict[str, object]:
    return {
        "artifact_id": ref.artifact_id,
        "media_type": ref.media_type,
        "size_bytes": ref.size_bytes,
        "raw_sha256": ref.raw_sha256,
    }

def _backend_ref_from_dict(raw: dict[str, object]) -> BackendArtifactRef:
    return BackendArtifactRef(
        artifact_id=_require_non_empty_str_value(raw.get("artifact_id"), label="artifact_id"),
        media_type=_require_non_empty_str_value(raw.get("media_type"), label="media_type"),
        size_bytes=_require_non_negative_int_value(raw.get("size_bytes")),
        raw_sha256=_require_non_empty_str_value(raw.get("raw_sha256"), label="raw_sha256"),
    )

def _repository_ref_to_dict(ref: RepositoryArtifactRef) -> dict[str, object]:
    return {
        "artifact_id": ref.artifact_id,
        "media_type": ref.media_type,
        "size_bytes": ref.size_bytes,
        "raw_sha256": ref.raw_sha256,
    }

def _repository_ref_from_dict(raw: dict[str, object]) -> RepositoryArtifactRef:
    return RepositoryArtifactRef(
        artifact_id=_require_non_empty_str_value(raw.get("artifact_id"), label="artifact_id"),
        media_type=_require_non_empty_str_value(raw.get("media_type"), label="media_type"),
        size_bytes=_require_non_negative_int_value(raw.get("size_bytes")),
        raw_sha256=_require_non_empty_str_value(raw.get("raw_sha256"), label="raw_sha256"),
    )
