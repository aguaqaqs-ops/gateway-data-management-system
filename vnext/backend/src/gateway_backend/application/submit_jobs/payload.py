"""Submit job payload, dependency contracts, and validation helpers."""

from __future__ import annotations

import json

from collections.abc import (
    Callable,
    Mapping,
)
from dataclasses import dataclass
from datetime import (
    UTC,
    datetime,
)
from gateway_backend.application.job_definitions import JobDefinition
from gateway_backend.application.job_steps import require_non_empty_str
from gateway_backend.application.payloads import (
    CheckpointDecodeError,
    PayloadDecodeError,
    load_job_payload_bytes,
)
from gateway_backend.application.submission.contracts import (
    SUBMIT_JOB_CONTRACT_VERSION,
    SubmitImportPublicationPort,
)
from gateway_backend.application.submission.errors import FinalizeBindingMismatch
from gateway_backend.application.submission.ports import (
    RepositoryParentCatalogPort,
    RepositoryTerminalEvidenceDecodePort,
    RepositoryWritePort,
    SubmitFinalizeControlTransaction,
)
from gateway_backend.application.submit_registry import submit_job_definitions
from gateway_backend.artifacts.location import parse_artifact_id
from gateway_backend.artifacts.serialize import artifact_ref_from_dict
from gateway_backend.artifacts.store import (
    ArtifactStorePort,
    ManifestVerificationError,
)
from gateway_backend.domain.submission.models import (
    BuilderMutationPolicy,
    SubmitAttempt,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.operations.contracts import OperationRecord
from gateway_backend.operations.recovery import (
    OperatorRecoveryRequest,
    RECONCILE_SESSION_BUDGET_SECONDS,
)
from gateway_backend.operations.state import TransitionDisposition
from typing import (
    ContextManager,
    Protocol,
    cast,
    runtime_checkable,
)

SUBMIT_IMPORT_CHECKPOINT_SCHEMA = "backend-vnext/submit/submit-import-checkpoint/v2"

AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA = "backend-vnext/submit/await-import-result-checkpoint/v2"

SUBMIT_IMPORT_POLL_DEADLINE_SECONDS = RECONCILE_SESSION_BUDGET_SECONDS

# Coupled to Repository Service Settings.import_timeout_seconds (3600 s) plus
# Settings.server_start_timeout_seconds (30 s); keep this aligned with that owner.
SUBMIT_IMPORT_WAIT_UPPER_BOUND_SECONDS = 3_600.0 + 30.0

_EXTERNAL_EFFECT_IDENTITY_MISMATCH_CHECKPOINT_CODE = "EXTERNAL_EFFECT_IDENTITY_MISMATCH"

_MAX_PREPARE_PROJECTION_MESSAGE_BYTES = 4 * 1024

_JCS_MEDIA_TYPE = "application/jcs"


class SubmitJobError(ValueError):
    """Bounded submit job failure surfaced to the operation runtime."""


@dataclass(frozen=True, slots=True)
class SubmitRepositoryPolicy:
    target_ref: SubmitTargetRef
    verification_policy: SubmitVerificationPolicy
    unknown_type_policy: SubmitUnknownTypePolicy


@dataclass(frozen=True, slots=True)
class SubmitJobPayload:
    configuration_facts_digest: str
    document_type: str
    contract_version: str
    submit_attempt_id: str
    workspace_id: str
    generation: int
    upload_revision_id: str
    preview_result_id: str
    repository_id: str
    business_baseline_node_id: str
    business_baseline_commit_id: str
    baseline_head_version: int
    repository_expected_commit_id: str
    canonical_business_digest: str
    source_artifact_refs: tuple[str, ...]
    preview_ready_closure_ref: str
    canonical_table_set_closure_ref: str
    canonical_table_set_closure_digest: str
    canonicalization_manifest_ref: str
    canonicalization_manifest_digest: str
    ruleset_version: str
    storage_projection_version: str
    canonicalization_manifest_contract_version: str
    repository_import_package_version: int
    accept_request_fingerprint: str
    repository_upload_idempotency_key: str
    repository_import_idempotency_key: str
    repository_policy: SubmitRepositoryPolicy
    builder_mutation_policy: BuilderMutationPolicy
    options: Mapping[str, object]

    def __post_init__(self) -> None:
        for artifact_id in (
            *self.source_artifact_refs,
            self.preview_ready_closure_ref,
            self.canonical_table_set_closure_ref,
            self.canonicalization_manifest_ref,
        ):
            parse_artifact_id(artifact_id)


SubmitControlTransactionFactory = Callable[[], ContextManager[SubmitFinalizeControlTransaction]]


@runtime_checkable
class OperatorRecoveryApplicationPort(Protocol):
    def execute_recovery(self, request: OperatorRecoveryRequest) -> TransitionDisposition:
        """Apply or replay one authorized operator recovery command."""


@dataclass(frozen=True, slots=True)
class SubmitRuntimeDependencies:
    artifact_store: ArtifactStorePort
    publication: SubmitImportPublicationPort
    parent_catalog: RepositoryParentCatalogPort
    repository_write: RepositoryWritePort
    terminal_evidence_decode: RepositoryTerminalEvidenceDecodePort
    control_transaction_factory: SubmitControlTransactionFactory
    submission_id_factory: Callable[[], str]
    now_factory: Callable[[], datetime] | None = None


def decode_submit_payload(payload_object: dict[str, object]) -> SubmitJobPayload:
    _reject_unknown_top_level_keys(payload_object)
    document_type = require_non_empty_str(payload_object, "document_type")
    if document_type != "submit_job_payload":
        raise PayloadDecodeError(
            "document_type must be submit_job_payload", code="PAYLOAD_SHAPE_INVALID"
        )
    contract_version = require_non_empty_str(payload_object, "contract_version")
    if contract_version != SUBMIT_JOB_CONTRACT_VERSION:
        raise PayloadDecodeError(
            f"contract_version must be {SUBMIT_JOB_CONTRACT_VERSION}",
            code="PAYLOAD_SHAPE_INVALID",
        )
    submit_attempt_id = require_non_empty_str(payload_object, "submit_attempt_id")
    workspace_id = require_non_empty_str(payload_object, "workspace_id")
    generation = _require_non_negative_int(payload_object, "generation")
    upload_revision_id = require_non_empty_str(payload_object, "upload_revision_id")
    preview_result_id = require_non_empty_str(payload_object, "preview_result_id")
    repository_id = require_non_empty_str(payload_object, "repository_id")
    business_baseline_node_id = require_non_empty_str(payload_object, "business_baseline_node_id")
    business_baseline_commit_id = require_non_empty_str(
        payload_object, "business_baseline_commit_id"
    )
    baseline_head_version = _require_non_negative_int(payload_object, "baseline_head_version")
    repository_expected_commit_id = require_non_empty_str(
        payload_object, "repository_expected_commit_id"
    )
    canonical_business_digest = require_non_empty_str(payload_object, "canonical_business_digest")
    configuration_facts_digest = require_non_empty_str(payload_object, "configuration_facts_digest")
    source_artifact_refs = _decode_string_tuple(
        payload_object.get("source_artifact_refs"), label="source_artifact_refs"
    )
    preview_ready_closure_ref = require_non_empty_str(payload_object, "preview_ready_closure_ref")
    canonical_table_set_closure_ref = require_non_empty_str(
        payload_object,
        "canonical_table_set_closure_ref",
    )
    canonical_table_set_closure_digest = require_non_empty_str(
        payload_object,
        "canonical_table_set_closure_digest",
    )
    canonicalization_manifest_ref = require_non_empty_str(
        payload_object,
        "canonicalization_manifest_ref",
    )
    canonicalization_manifest_digest = require_non_empty_str(
        payload_object,
        "canonicalization_manifest_digest",
    )
    ruleset_version = require_non_empty_str(payload_object, "ruleset_version")
    storage_projection_version = require_non_empty_str(payload_object, "storage_projection_version")
    canonicalization_manifest_contract_version = require_non_empty_str(
        payload_object,
        "canonicalization_manifest_contract_version",
    )
    repository_import_package_version = _require_non_negative_int(
        payload_object,
        "repository_import_package_version",
    )
    accept_request_fingerprint = require_non_empty_str(payload_object, "accept_request_fingerprint")
    repository_upload_idempotency_key = require_non_empty_str(
        payload_object,
        "repository_upload_idempotency_key",
    )
    repository_import_idempotency_key = require_non_empty_str(
        payload_object,
        "repository_import_idempotency_key",
    )
    repository_policy = _decode_repository_policy(payload_object.get("repository_policy"))
    builder_mutation_policy = _decode_builder_mutation_policy(
        payload_object.get("builder_mutation_policy")
    )
    options = _decode_object_map(payload_object.get("options"), label="options")
    _validate_policy_constants(
        ruleset_version=ruleset_version,
        storage_projection_version=storage_projection_version,
        canonicalization_manifest_contract_version=canonicalization_manifest_contract_version,
        repository_import_package_version=repository_import_package_version,
        repository_policy=repository_policy,
        builder_mutation_policy=builder_mutation_policy,
    )
    try:
        return SubmitJobPayload(
            configuration_facts_digest=configuration_facts_digest,
            document_type=document_type,
            contract_version=contract_version,
            submit_attempt_id=submit_attempt_id,
            workspace_id=workspace_id,
            generation=generation,
            upload_revision_id=upload_revision_id,
            preview_result_id=preview_result_id,
            repository_id=repository_id,
            business_baseline_node_id=business_baseline_node_id,
            business_baseline_commit_id=business_baseline_commit_id,
            baseline_head_version=baseline_head_version,
            repository_expected_commit_id=repository_expected_commit_id,
            canonical_business_digest=canonical_business_digest,
            source_artifact_refs=source_artifact_refs,
            preview_ready_closure_ref=preview_ready_closure_ref,
            canonical_table_set_closure_ref=canonical_table_set_closure_ref,
            canonical_table_set_closure_digest=canonical_table_set_closure_digest,
            canonicalization_manifest_ref=canonicalization_manifest_ref,
            canonicalization_manifest_digest=canonicalization_manifest_digest,
            ruleset_version=ruleset_version,
            storage_projection_version=storage_projection_version,
            canonicalization_manifest_contract_version=canonicalization_manifest_contract_version,
            repository_import_package_version=repository_import_package_version,
            accept_request_fingerprint=accept_request_fingerprint,
            repository_upload_idempotency_key=repository_upload_idempotency_key,
            repository_import_idempotency_key=repository_import_idempotency_key,
            repository_policy=repository_policy,
            builder_mutation_policy=builder_mutation_policy,
            options=options,
        )
    except ValueError as exc:
        raise PayloadDecodeError(
            "submit payload contains an invalid backend artifact ID", code="PAYLOAD_SHAPE_INVALID"
        ) from exc


def _load_submit_payload(operation: OperationRecord, store: ArtifactStorePort) -> SubmitJobPayload:
    payload_bytes = load_job_payload_bytes(operation, store)
    try:
        payload_object = json.loads(payload_bytes)
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise PayloadDecodeError(
            "job_payload must be canonical JSON bytes",
            code="PAYLOAD_SHAPE_INVALID",
        ) from exc
    if type(payload_object) is not dict:
        raise PayloadDecodeError("job_payload must be a JSON object", code="PAYLOAD_SHAPE_INVALID")
    return decode_submit_payload(cast(dict[str, object], payload_object))


def _load_submit_attempt(deps: SubmitRuntimeDependencies, submit_attempt_id: str) -> SubmitAttempt:
    with deps.control_transaction_factory() as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
    if attempt is None:
        raise SubmitJobError("submit attempt is missing")
    return attempt


def _assert_payload_matches_attempt(payload: SubmitJobPayload, attempt: SubmitAttempt) -> None:
    mismatches: list[str] = []
    if payload.submit_attempt_id != attempt.submit_attempt_id:
        mismatches.append("submit_attempt_id")
    if payload.workspace_id != attempt.workspace_id:
        mismatches.append("workspace_id")
    if payload.generation != attempt.workspace_generation:
        mismatches.append("generation")
    if payload.upload_revision_id != attempt.upload_revision_id:
        mismatches.append("upload_revision_id")
    if payload.preview_result_id != attempt.preview_result_id:
        mismatches.append("preview_result_id")
    if payload.repository_id != attempt.repository_id:
        mismatches.append("repository_id")
    if payload.business_baseline_node_id != attempt.business_baseline_node_id:
        mismatches.append("business_baseline_node_id")
    if payload.business_baseline_commit_id != attempt.business_baseline_commit_id:
        mismatches.append("business_baseline_commit_id")
    if payload.baseline_head_version != attempt.baseline_head_version:
        mismatches.append("baseline_head_version")
    if payload.repository_expected_commit_id != attempt.repository_expected_commit_id:
        mismatches.append("repository_expected_commit_id")
    if payload.configuration_facts_digest != attempt.configuration_facts.facts_digest:
        mismatches.append("configuration_facts_digest")
    if payload.canonical_business_digest != attempt.canonical_business_digest:
        mismatches.append("canonical_business_digest")
    if payload.source_artifact_refs != attempt.source_artifact_refs:
        mismatches.append("source_artifact_refs")
    if payload.preview_ready_closure_ref != attempt.preview_ready_closure_ref:
        mismatches.append("preview_ready_closure_ref")
    if payload.canonical_table_set_closure_ref != attempt.canonical_table_set_closure_ref:
        mismatches.append("canonical_table_set_closure_ref")
    if payload.canonical_table_set_closure_digest != attempt.canonical_table_set_closure_digest:
        mismatches.append("canonical_table_set_closure_digest")
    if payload.canonicalization_manifest_ref != attempt.canonicalization_manifest_ref:
        mismatches.append("canonicalization_manifest_ref")
    if payload.canonicalization_manifest_digest != attempt.canonicalization_manifest_digest:
        mismatches.append("canonicalization_manifest_digest")
    if payload.accept_request_fingerprint != attempt.accept_request_fingerprint:
        mismatches.append("accept_request_fingerprint")
    if payload.repository_upload_idempotency_key != attempt.repository_upload_idempotency_key:
        mismatches.append("repository_upload_idempotency_key")
    if payload.repository_import_idempotency_key != attempt.repository_import_idempotency_key:
        mismatches.append("repository_import_idempotency_key")
    if payload.repository_policy.target_ref is not attempt.requested_target_ref:
        mismatches.append("repository_policy.target_ref")
    if payload.repository_policy.verification_policy is not attempt.requested_verification_policy:
        mismatches.append("repository_policy.verification_policy")
    if payload.repository_policy.unknown_type_policy is not attempt.requested_unknown_type_policy:
        mismatches.append("repository_policy.unknown_type_policy")
    if payload.builder_mutation_policy is not attempt.builder_mutation_policy:
        mismatches.append("builder_mutation_policy")
    if mismatches:
        raise PayloadDecodeError(
            f"submit payload does not match attempt: {', '.join(mismatches)}",
            code="PAYLOAD_ATTEMPT_MISMATCH",
        )


def _submit_attempt_id_from_operation(operation: OperationRecord) -> str:
    for business_ref in operation.business_refs:
        if business_ref.kind == "submit_attempt":
            return business_ref.value
    raise ValueError("submit operation is missing submit_attempt business ref")


def _definition_for_step(step_name: str) -> JobDefinition:
    for definition in submit_job_definitions():
        if definition.key.step_name == step_name:
            return definition
    raise SubmitJobError(f"submit step definition is missing: {step_name}")


def _submit_now(deps: SubmitRuntimeDependencies) -> datetime:
    now = deps.now_factory() if deps.now_factory is not None else datetime.now(UTC)
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() != UTC.utcoffset(now):
        raise ValueError("Submit clock must return a timezone-aware UTC datetime")
    return now


def _iso_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _verification_policy_from_repository(value: str) -> SubmitVerificationPolicy:
    if value == SubmitVerificationPolicy.STRUCTURAL.value:
        return SubmitVerificationPolicy.STRUCTURAL
    raise FinalizeBindingMismatch(f"completed verification policy {value!r} is not supported")


def _unknown_type_policy_from_repository(value: str) -> SubmitUnknownTypePolicy:
    if value == SubmitUnknownTypePolicy.REJECT.value:
        return SubmitUnknownTypePolicy.REJECT
    raise FinalizeBindingMismatch(f"completed unknown type policy {value!r} is not supported")


def _target_ref_from_repository(value: str) -> SubmitTargetRef:
    if value == SubmitTargetRef.MAIN.value:
        return SubmitTargetRef.MAIN
    raise FinalizeBindingMismatch("completed target ref must be main")


def _wire_repository_raw_sha256(value: str) -> str:
    return value.removeprefix("sha256:")


def _validate_policy_constants(
    *,
    ruleset_version: str,
    storage_projection_version: str,
    canonicalization_manifest_contract_version: str,
    repository_import_package_version: int,
    repository_policy: SubmitRepositoryPolicy,
    builder_mutation_policy: BuilderMutationPolicy,
) -> None:
    if ruleset_version != "v1":
        raise PayloadDecodeError("ruleset_version must be v1", code="PAYLOAD_SHAPE_INVALID")
    if storage_projection_version != "v1":
        raise PayloadDecodeError(
            "storage_projection_version must be v1",
            code="PAYLOAD_SHAPE_INVALID",
        )
    if canonicalization_manifest_contract_version != "v1":
        raise PayloadDecodeError(
            "canonicalization_manifest_contract_version must be v1",
            code="PAYLOAD_SHAPE_INVALID",
        )
    if repository_import_package_version != 1:
        raise PayloadDecodeError(
            "repository_import_package_version must be 1",
            code="PAYLOAD_SHAPE_INVALID",
        )
    if repository_policy.target_ref is not SubmitTargetRef.MAIN:
        raise PayloadDecodeError(
            "repository_policy.target_ref must be main", code="PAYLOAD_SHAPE_INVALID"
        )
    if repository_policy.verification_policy is not SubmitVerificationPolicy.STRUCTURAL:
        raise PayloadDecodeError(
            "repository_policy.verification_policy must be STRUCTURAL",
            code="PAYLOAD_SHAPE_INVALID",
        )
    if repository_policy.unknown_type_policy is not SubmitUnknownTypePolicy.REJECT:
        raise PayloadDecodeError(
            "repository_policy.unknown_type_policy must be REJECT",
            code="PAYLOAD_SHAPE_INVALID",
        )
    if builder_mutation_policy is not BuilderMutationPolicy.ADAPTIVE_PATCH:
        raise PayloadDecodeError(
            "builder_mutation_policy must be ADAPTIVE_PATCH",
            code="PAYLOAD_SHAPE_INVALID",
        )


_ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "document_type",
        "contract_version",
        "submit_attempt_id",
        "workspace_id",
        "generation",
        "upload_revision_id",
        "preview_result_id",
        "repository_id",
        "business_baseline_node_id",
        "business_baseline_commit_id",
        "baseline_head_version",
        "repository_expected_commit_id",
        "canonical_business_digest",
        "configuration_facts_digest",
        "source_artifact_refs",
        "preview_ready_closure_ref",
        "canonical_table_set_closure_ref",
        "canonical_table_set_closure_digest",
        "canonicalization_manifest_ref",
        "canonicalization_manifest_digest",
        "ruleset_version",
        "storage_projection_version",
        "canonicalization_manifest_contract_version",
        "repository_import_package_version",
        "accept_request_fingerprint",
        "repository_upload_idempotency_key",
        "repository_import_idempotency_key",
        "repository_policy",
        "builder_mutation_policy",
        "options",
    }
)


def _reject_unknown_top_level_keys(payload_object: dict[str, object]) -> None:
    unknown = sorted(set(payload_object) - _ALLOWED_PAYLOAD_KEYS)
    if unknown:
        raise PayloadDecodeError(
            f"unknown submit payload keys: {', '.join(unknown)}",
            code="PAYLOAD_SHAPE_INVALID",
        )


def _require_non_negative_int(payload_object: dict[str, object], key: str) -> int:
    value = payload_object.get(key)
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise PayloadDecodeError(f"{key} must be a non-negative int", code="PAYLOAD_SHAPE_INVALID")
    return value


def _require_non_empty_str_value(value: object, *, label: str) -> str:
    if type(value) is not str or not value:
        raise CheckpointDecodeError(
            f"{label} must be a non-empty string", code="CHECKPOINT_JOB_STATE_MISMATCH"
        )
    return value


def _require_non_negative_int_value(value: object) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise CheckpointDecodeError(
            "checkpoint integer field is invalid", code="CHECKPOINT_JOB_STATE_MISMATCH"
        )
    return value


def _require_mapping(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise CheckpointDecodeError(
            f"{label} must be an object", code="CHECKPOINT_JOB_STATE_MISMATCH"
        )
    return value


def _require_artifact_ref_dict(value: object, *, label: str) -> dict[str, object]:
    mapping = _require_mapping(value, label=label)
    try:
        artifact_ref_from_dict(mapping)
    except (TypeError, ValueError, KeyError, ManifestVerificationError) as exc:
        raise CheckpointDecodeError(
            f"{label} is invalid", code="CHECKPOINT_JOB_STATE_MISMATCH"
        ) from exc
    return mapping


def _decode_string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise PayloadDecodeError(f"{label} must be an array", code="PAYLOAD_SHAPE_INVALID")
    decoded: list[str] = []
    for item in value:
        if type(item) is not str or not item:
            raise PayloadDecodeError(
                f"{label} must contain non-empty strings", code="PAYLOAD_SHAPE_INVALID"
            )
        decoded.append(item)
    return tuple(decoded)


def _decode_checkpoint_string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise CheckpointDecodeError(
            f"{label} must be an array", code="CHECKPOINT_JOB_STATE_MISMATCH"
        )
    decoded: list[str] = []
    for item in value:
        if type(item) is not str or not item:
            raise CheckpointDecodeError(
                f"{label} must contain non-empty strings",
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
        decoded.append(item)
    result = tuple(decoded)
    if result != tuple(sorted(set(result), key=lambda name: name.encode("utf-8"))):
        raise CheckpointDecodeError(
            f"{label} must contain sorted unique strings",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    return result


def _decode_object_map(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise PayloadDecodeError(f"{label} must be an object", code="PAYLOAD_SHAPE_INVALID")
    return dict(value)


def _decode_repository_policy(value: object) -> SubmitRepositoryPolicy:
    if type(value) is not dict:
        raise PayloadDecodeError(
            "repository_policy must be an object", code="PAYLOAD_SHAPE_INVALID"
        )
    target_ref = value.get("target_ref")
    verification_policy = value.get("verification_policy")
    unknown_type_policy = value.get("unknown_type_policy")
    if type(target_ref) is not str:
        raise PayloadDecodeError(
            "repository_policy.target_ref must be a string", code="PAYLOAD_SHAPE_INVALID"
        )
    if type(verification_policy) is not str:
        raise PayloadDecodeError(
            "repository_policy.verification_policy must be a string",
            code="PAYLOAD_SHAPE_INVALID",
        )
    if type(unknown_type_policy) is not str:
        raise PayloadDecodeError(
            "repository_policy.unknown_type_policy must be a string",
            code="PAYLOAD_SHAPE_INVALID",
        )
    try:
        return SubmitRepositoryPolicy(
            target_ref=SubmitTargetRef(target_ref),
            verification_policy=SubmitVerificationPolicy(verification_policy),
            unknown_type_policy=SubmitUnknownTypePolicy(unknown_type_policy),
        )
    except ValueError as exc:
        raise PayloadDecodeError(
            "repository_policy contains invalid enum values", code="PAYLOAD_SHAPE_INVALID"
        ) from exc


def _decode_builder_mutation_policy(value: object) -> BuilderMutationPolicy:
    if type(value) is not str:
        raise PayloadDecodeError(
            "builder_mutation_policy must be a string", code="PAYLOAD_SHAPE_INVALID"
        )
    try:
        return BuilderMutationPolicy(value)
    except ValueError as exc:
        raise PayloadDecodeError(
            "builder_mutation_policy is invalid", code="PAYLOAD_SHAPE_INVALID"
        ) from exc


__all__ = [
    "SUBMIT_IMPORT_CHECKPOINT_SCHEMA",
    "AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA",
    "SUBMIT_IMPORT_POLL_DEADLINE_SECONDS",
    "SUBMIT_IMPORT_WAIT_UPPER_BOUND_SECONDS",
    "SubmitJobError",
    "SubmitRepositoryPolicy",
    "SubmitJobPayload",
    "SubmitControlTransactionFactory",
    "OperatorRecoveryApplicationPort",
    "SubmitRuntimeDependencies",
    "decode_submit_payload",
]
