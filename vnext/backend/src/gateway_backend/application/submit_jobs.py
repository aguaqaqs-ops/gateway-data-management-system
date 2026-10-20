"""Submit JobDefinition handlers, decoders, and recovery composition."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import ContextManager, Protocol, cast, runtime_checkable

from gateway_backend.application.submission.contracts import (
    RepositoryImportOperation,
    RepositoryImportOperationStatus as RepositoryOperationStatus,
)
from gateway_backend.application.submission.ports import RepositoryTerminalEvidenceDecodePort
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    load_ready_closure,
    prepare_step_checkpoint,
)
from gateway_backend.application.job_definitions import JobDefinition
from gateway_backend.application.job_steps import pinned_checkpoint_builder, unique_artifact_refs
from gateway_backend.application.payloads import (
    CheckpointDecodeError,
    PayloadDecodeError,
    PayloadDecoder,
    load_job_payload_bytes,
)
from gateway_backend.application.recovery import (
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    DIAGNOSTIC_RECONCILE_TIMEOUT,
    JOB_STATE_IDEMPOTENCY_KEY,
    JOB_STATE_OPERATION_IDENTITY,
    JOB_STATE_RECONCILE_STARTED_AT,
    JOB_STATE_REQUEST_FINGERPRINT,
    JOB_STATE_REQUEST_SENT,
    ExternalEffectRequestIdentity,
    RecoveryOutcome,
    RecoveryOutcomeDisposition,
    RecoveryPort,
    compute_request_fingerprint,
    validate_external_effect_identity,
)
from gateway_backend.application.submit_registry import (
    AWAIT_IMPORT_DECODER,
    AWAIT_IMPORT_HANDLER,
    PREPARE_IMPORT_DECODER,
    PREPARE_IMPORT_HANDLER,
    SUBMIT_IMPORT_DECODER,
    SUBMIT_IMPORT_HANDLER,
    submit_job_definitions,
)
from gateway_backend.application.submission.abort import ALLOWED_ABORT_CODES, validate_abort_proof
from gateway_backend.application.submission.abort_transaction import (
    AbortPreparedSubmitRequest,
    AbortSubmitTransactionRequest,
    abort_prepared_submit_in_control_transaction,
    abort_submit_in_control_transaction,
    abort_submit_transaction,
)
from gateway_backend.application.submission.contracts import (
    PREPARE_IMPORT_CHECKPOINT_SCHEMA,
    SUBMIT_JOB_CONTRACT_VERSION,
    MatchingAbortProof,
    MatchingFinalizeFacts,
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    RepositoryOperationTerminalStatus,
    SubmitImportPublicationPort,
)
from gateway_backend.application.submission.effect_pending_transaction import (
    BindRepositoryOperationRequest,
    EffectPendingTransactionRequest,
    bind_repository_operation_identity,
    mark_submit_attempt_effect_pending,
)
from gateway_backend.application.submission.finalize_transaction import (
    FinalizeSubmitTransactionRequest,
    finalize_submit_transaction,
)
from gateway_backend.application.submission.import_builder import (
    SubmitImportBuilderError,
    derive_removed_tables,
    pin_prepare_import_artifacts,
    publish_prepare_import_package,
    resolve_canonical_snapshot_bindings,
    reuse_prepare_import_checkpoint,
)
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
    submit_successor_step_id as _successor_step_id,
)
from gateway_backend.application.submission.errors import (
    AbortProofNotSatisfied,
    FinalizeBindingMismatch,
    FinalizeRecoveryRequired,
    RepositoryUploadMetadataMismatch,
    RepositoryWriteTimeoutError,
    RepositoryWriteTransportError,
)
from gateway_backend.application.submission.ports import (
    RepositoryAbortEvidencePort,
    RepositoryParentCatalogPort,
    RepositoryWritePort,
    SubmitControlTransaction,
    SubmitControlUnitOfWorkFactory,
    SubmitFinalizeControlTransaction,
)
from gateway_backend.application.submission.artifact_refs import store_ref_from_backend_artifact_ref
from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.store import ArtifactStorePort, ManifestVerificationError, put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    SubmitAttempt,
    SubmitAttemptState,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
)
from gateway_backend.operations.contracts import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.recovery import (
    DIAGNOSTIC_RETRY_SCHEDULED,
    OperatorRecoveryCommand,
    OperatorRecoveryRequest,
    RecoveryCapabilityLookup,
    RecoveryCapabilityValue,
    RecoveryPolicyOutcomeDisposition,
    build_authorized_operator_recovery,
    transition_for_outcome,
)
from gateway_backend.operations.state import TransitionDisposition
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
    WriteUnitOfWorkFactory,
)
from gateway_backend.capabilities.storage_projection import STORAGE_PROJECTION_VERSION
from gateway_backend.application.submission.errors import (
    PrepareCheckpointPayloadBindingError,
    SubmitImportPublicationError,
)
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot

SUBMIT_IMPORT_CHECKPOINT_SCHEMA = "backend-vnext/submit/submit-import-checkpoint/v1"
AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA = "backend-vnext/submit/await-import-result-checkpoint/v1"
_MAX_PREPARE_PROJECTION_MESSAGE_BYTES = 4 * 1024

_JCS_MEDIA_TYPE = "application/jcs"

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
_TERMINAL_REPOSITORY_EVIDENCE_CONTRACT_VERSION = "backend-vnext/submit/repository-terminal-evidence/v1"

_active_submit_transaction: ContextVar[SubmitFinalizeControlTransaction | None] = ContextVar(
    "_active_submit_transaction",
    default=None,
)


class SubmitJobError(ValueError):
    """Bounded submit job failure surfaced to the operation runtime."""


@dataclass(frozen=True, slots=True)
class SubmitRepositoryPolicy:
    target_ref: SubmitTargetRef
    verification_policy: SubmitVerificationPolicy
    unknown_type_policy: SubmitUnknownTypePolicy


@dataclass(frozen=True, slots=True)
class SubmitJobPayload:
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
    reconcile_started_at: str
    last_observed_repository_status: str | None
    terminal_result_evidence_ref: ArtifactRef | None


def decode_submit_payload(payload_object: dict[str, object]) -> SubmitJobPayload:
    _reject_unknown_top_level_keys(payload_object)
    document_type = _require_non_empty_str(payload_object, "document_type")
    if document_type != "submit_job_payload":
        raise PayloadDecodeError("document_type must be submit_job_payload", code="PAYLOAD_SHAPE_INVALID")
    contract_version = _require_non_empty_str(payload_object, "contract_version")
    if contract_version != SUBMIT_JOB_CONTRACT_VERSION:
        raise PayloadDecodeError(
            f"contract_version must be {SUBMIT_JOB_CONTRACT_VERSION}",
            code="PAYLOAD_SHAPE_INVALID",
        )
    submit_attempt_id = _require_non_empty_str(payload_object, "submit_attempt_id")
    workspace_id = _require_non_empty_str(payload_object, "workspace_id")
    generation = _require_non_negative_int(payload_object, "generation")
    upload_revision_id = _require_non_empty_str(payload_object, "upload_revision_id")
    preview_result_id = _require_non_empty_str(payload_object, "preview_result_id")
    repository_id = _require_non_empty_str(payload_object, "repository_id")
    business_baseline_node_id = _require_non_empty_str(payload_object, "business_baseline_node_id")
    business_baseline_commit_id = _require_non_empty_str(payload_object, "business_baseline_commit_id")
    baseline_head_version = _require_non_negative_int(payload_object, "baseline_head_version")
    repository_expected_commit_id = _require_non_empty_str(payload_object, "repository_expected_commit_id")
    canonical_business_digest = _require_non_empty_str(payload_object, "canonical_business_digest")
    source_artifact_refs = _decode_string_tuple(payload_object.get("source_artifact_refs"), label="source_artifact_refs")
    preview_ready_closure_ref = _require_non_empty_str(payload_object, "preview_ready_closure_ref")
    canonical_table_set_closure_ref = _require_non_empty_str(
        payload_object,
        "canonical_table_set_closure_ref",
    )
    canonical_table_set_closure_digest = _require_non_empty_str(
        payload_object,
        "canonical_table_set_closure_digest",
    )
    canonicalization_manifest_ref = _require_non_empty_str(
        payload_object,
        "canonicalization_manifest_ref",
    )
    canonicalization_manifest_digest = _require_non_empty_str(
        payload_object,
        "canonicalization_manifest_digest",
    )
    ruleset_version = _require_non_empty_str(payload_object, "ruleset_version")
    storage_projection_version = _require_non_empty_str(payload_object, "storage_projection_version")
    canonicalization_manifest_contract_version = _require_non_empty_str(
        payload_object,
        "canonicalization_manifest_contract_version",
    )
    repository_import_package_version = _require_non_negative_int(
        payload_object,
        "repository_import_package_version",
    )
    accept_request_fingerprint = _require_non_empty_str(payload_object, "accept_request_fingerprint")
    repository_upload_idempotency_key = _require_non_empty_str(
        payload_object,
        "repository_upload_idempotency_key",
    )
    repository_import_idempotency_key = _require_non_empty_str(
        payload_object,
        "repository_import_idempotency_key",
    )
    repository_policy = _decode_repository_policy(payload_object.get("repository_policy"))
    builder_mutation_policy = _decode_builder_mutation_policy(payload_object.get("builder_mutation_policy"))
    options = _decode_object_map(payload_object.get("options"), label="options")
    _validate_policy_constants(
        ruleset_version=ruleset_version,
        storage_projection_version=storage_projection_version,
        canonicalization_manifest_contract_version=canonicalization_manifest_contract_version,
        repository_import_package_version=repository_import_package_version,
        repository_policy=repository_policy,
        builder_mutation_policy=builder_mutation_policy,
    )
    return SubmitJobPayload(
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


def submit_payload_decoders() -> Mapping[str, PayloadDecoder]:
    decoder: PayloadDecoder = decode_submit_payload
    return {
        PREPARE_IMPORT_DECODER: decoder,
        SUBMIT_IMPORT_DECODER: decoder,
        AWAIT_IMPORT_DECODER: decoder,
    }


def bind_submit_control_transaction_factory(
    inner: SubmitControlTransactionFactory,
) -> SubmitControlTransactionFactory:
    """Bind the active submit transaction for checkpoint and crossing writes."""

    class _BoundUnitOfWork:
        def __init__(self, wrapped: ContextManager[SubmitFinalizeControlTransaction]) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> SubmitFinalizeControlTransaction:
            transaction = self._wrapped.__enter__()
            _active_submit_transaction.set(transaction)
            return transaction

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool | None:
            _active_submit_transaction.set(None)
            return self._wrapped.__exit__(exc_type, exc, tb)

    def factory() -> ContextManager[SubmitFinalizeControlTransaction]:
        return _BoundUnitOfWork(inner())

    return factory


def submit_composition_bundle(
    deps: SubmitRuntimeDependencies,
) -> tuple[
    tuple[JobDefinition, ...],
    Mapping[str, ClaimedExecutor],
    Mapping[str, PayloadDecoder],
    SubmitRuntimeDependencies,
]:
    bound_deps = SubmitRuntimeDependencies(
        artifact_store=deps.artifact_store,
        publication=deps.publication,
        parent_catalog=deps.parent_catalog,
        repository_write=deps.repository_write,
        terminal_evidence_decode=deps.terminal_evidence_decode,
        control_transaction_factory=bind_submit_control_transaction_factory(
            deps.control_transaction_factory
        ),
        submission_id_factory=deps.submission_id_factory,
    )
    return (
        submit_job_definitions(),
        {
            PREPARE_IMPORT_HANDLER: build_prepare_import_handler(bound_deps),
            SUBMIT_IMPORT_HANDLER: build_submit_import_handler(bound_deps),
            AWAIT_IMPORT_HANDLER: build_await_import_result_handler(bound_deps),
        },
        dict(submit_payload_decoders()),
        bound_deps,
    )


def build_prepare_import_handler(deps: SubmitRuntimeDependencies) -> ClaimedExecutor:
    prepare_definition = _definition_for_step(SUBMIT_STEP_PREPARE)

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        payload = _load_submit_payload(operation, deps.artifact_store)
        attempt = _load_submit_attempt(deps, payload.submit_attempt_id)
        _assert_payload_matches_attempt(payload, attempt)
        if attempt.state is not SubmitAttemptState.PREPARED:
            raise SubmitJobError("prepare_import requires PREPARED attempt")

        try:
            if step.checkpoint_ref is not None:
                envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
                if not definition_matches_checkpoint(prepare_definition, envelope):
                    raise CheckpointDecodeError(
                        "checkpoint envelope does not match the prepare_import JobDefinition",
                        code="CHECKPOINT_IDENTITY_MISMATCH",
                    )
                prepare_checkpoint = _prepare_checkpoint_from_job_state(
                    envelope.job_state,
                    expected_attempt_id=payload.submit_attempt_id,
                )
                build_input = _build_prepare_import_build_input(
                    payload=payload,
                    attempt=attempt,
                    operation=operation,
                    store=deps.artifact_store,
                    parent_catalog=deps.parent_catalog,
                )
                reuse_prepare_import_checkpoint(
                    build_input=build_input,
                    checkpoint=prepare_checkpoint,
                    publication=deps.publication,
                    store=deps.artifact_store,
                )
                _pin_prepare_refs(
                    deps=deps,
                    attempt=attempt,
                    operation=operation,
                    checkpoint=prepare_checkpoint,
                )
                with deps.control_transaction_factory() as unit_of_work:
                    _pin_submit_checkpoint_refs(
                        unit_of_work,
                        step_id=step.step_id,
                        checkpoint_ref=step.checkpoint_ref,
                        extra_refs=_prepare_checkpoint_extra_refs(prepare_checkpoint),
                        intent="prepare-import-checkpoint",
                    )
            else:
                build_input = _build_prepare_import_build_input(
                    payload=payload,
                    attempt=attempt,
                    operation=operation,
                    store=deps.artifact_store,
                    parent_catalog=deps.parent_catalog,
                )
                publication = publish_prepare_import_package(
                    build_input=build_input,
                    publication=deps.publication,
                    store=deps.artifact_store,
                )
                _prepare_step_checkpoint(
                    deps=deps,
                    definition=prepare_definition,
                    operation=operation,
                    step=step,
                    checkpoint=publication.checkpoint,
                    lease_session=lease_session,
                    attempt=attempt,
                    operation_record=operation,
                )
        except SubmitImportPublicationError as exc:
            _publish_prepare_projection_failure(lease_session, exc)
            return ExecutorAcknowledgment.PUBLISHED
        except PrepareCheckpointPayloadBindingError:
            _publish_prepare_binding_failure(lease_session)
            return ExecutorAcknowledgment.PUBLISHED

        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        lease_session.publish_successor(
            _make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=SUBMIT_STEP_SUBMIT,
                successor_step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_SUBMIT),
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return execute


def build_submit_import_handler(deps: SubmitRuntimeDependencies) -> ClaimedExecutor:
    prepare_definition = _definition_for_step(SUBMIT_STEP_PREPARE)
    submit_definition = _definition_for_step(SUBMIT_STEP_SUBMIT)

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        lease_session.refresh_control()
        if step.checkpoint_ref is None and control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        payload = _load_submit_payload(operation, deps.artifact_store)
        attempt = _load_submit_attempt(deps, payload.submit_attempt_id)
        _assert_payload_matches_attempt(payload, attempt)

        prepare_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_PREPARE),
        )
        if prepare_step.checkpoint_ref is None:
            raise SubmitJobError("prepare_import checkpoint is missing")
        prepare_envelope = load_checkpoint_envelope(deps.artifact_store, prepare_step.checkpoint_ref)
        if not definition_matches_checkpoint(prepare_definition, prepare_envelope):
            raise CheckpointDecodeError(
                "prepare checkpoint does not match the prepare_import JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        prepare_checkpoint = _prepare_checkpoint_from_job_state(
            prepare_envelope.job_state,
            expected_attempt_id=payload.submit_attempt_id,
        )

        request_state: _SubmitCheckpointState
        last_checkpoint_generation = None

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(submit_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the submit_import JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            request_state = _submit_state_from_job_state(
                deps.artifact_store,
                envelope.job_state,
                repository_write=deps.repository_write,
                expected_payload=payload,
                prepare_checkpoint_ref=prepare_step.checkpoint_ref,
                checkpoint_ref=step.checkpoint_ref,
            )
        else:
            request_state, last_checkpoint_generation = _materialize_submit_checkpoint_state(
                deps=deps,
                submit_definition=submit_definition,
                operation=operation,
                step=step,
                lease_session=lease_session,
                payload=payload,
                attempt=attempt,
                prepare_checkpoint=prepare_checkpoint,
                prepare_checkpoint_ref=prepare_step.checkpoint_ref,
            )

        if not request_state.request_sent:
            lease_session.refresh_control()
            if control.cancel_requested:
                # unreachable until submit cancel source exists (effect boundary crossed)
                lease_session.publish_operation(_make_cancelled_terminal_builder())
                return ExecutorAcknowledgment.PUBLISHED
            repository_operation_id = deps.repository_write.submit_versioned_import(
                repository_id=payload.repository_id,
                idempotency_key=payload.repository_import_idempotency_key,
                artifact_ref=request_state.repository_artifact_ref,
                expected_commit_id=payload.repository_expected_commit_id,
            )
            with deps.control_transaction_factory() as unit_of_work:
                fresh_attempt = unit_of_work.submission.get_submit_attempt(payload.submit_attempt_id)
                if fresh_attempt is None:
                    raise SubmitJobError("submit attempt is missing")
                bind_repository_operation_identity(
                    request=BindRepositoryOperationRequest(
                        submit_attempt_id=payload.submit_attempt_id,
                        repository_operation_id=repository_operation_id,
                        expected_attempt_version=fresh_attempt.optimistic_version,
                    ),
                    unit_of_work=unit_of_work,
                )
            sent_envelope = envelope_for_step(
                key=submit_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state=_job_state_for_submit_sent(
                    prepare_checkpoint_ref=request_state.prepare_checkpoint_ref,
                    repository_artifact_ref=request_state.repository_artifact_ref,
                    payload=payload,
                    request_artifact_ref=request_state.request_artifact_ref,
                    request_fingerprint=request_state.request_fingerprint,
                    repository_operation_id=repository_operation_id,
                    reconcile_started_at=_iso_utc_timestamp(datetime.now(UTC)),
                ),
            )
            sent_checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, sent_envelope)
            last_checkpoint_generation = lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=sent_checkpoint_ref,
                    extra_refs=(
                        request_state.prepare_checkpoint_ref,
                        request_state.request_artifact_ref,
                    ),
                    owner_kind="submit-checkpoint",
                    active_transaction=_active_submit_transaction.get,
                    transaction_missing=lambda: SubmitJobError("submit checkpoint transaction is not bound"),
                    deduplicate_refs=False,
                    intent="submit-import-checkpoint",
                )
            )
            request_state = dataclasses.replace(
                request_state,
                request_sent=True,
                repository_operation_id=repository_operation_id,
                checkpoint_ref=sent_checkpoint_ref,
            )

        lease_session.refresh_control()
        if control.cancel_requested:
            # unreachable until submit cancel source exists (post-effect publish path)
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        lease_session.publish_successor(
            _make_successor_builder(
                operation_id=operation.operation_id,
                successor_step_name=SUBMIT_STEP_AWAIT,
                successor_step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_AWAIT),
            )
        )
        if last_checkpoint_generation is not None:
            del last_checkpoint_generation
        return ExecutorAcknowledgment.PUBLISHED

    return execute


def build_await_import_result_handler(deps: SubmitRuntimeDependencies) -> ClaimedExecutor:
    submit_definition = _definition_for_step(SUBMIT_STEP_SUBMIT)
    await_definition = _definition_for_step(SUBMIT_STEP_AWAIT)

    def execute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> ExecutorAcknowledgment:
        payload = _load_submit_payload(operation, deps.artifact_store)
        with deps.control_transaction_factory() as unit_of_work:
            fresh_attempt = unit_of_work.submission.get_submit_attempt(payload.submit_attempt_id)
        if fresh_attempt is None:
            raise SubmitJobError("submit attempt is missing")
        _assert_payload_matches_attempt(payload, fresh_attempt)

        lease_session.refresh_control()
        if step.checkpoint_ref is None and control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        attempt = fresh_attempt
        if attempt.state is not SubmitAttemptState.EFFECT_PENDING:
            raise SubmitJobError("await_import_result requires EFFECT_PENDING attempt")

        submit_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_SUBMIT),
        )
        if submit_step.checkpoint_ref is None:
            raise SubmitJobError("submit_import checkpoint is missing")
        submit_envelope = load_checkpoint_envelope(deps.artifact_store, submit_step.checkpoint_ref)
        if not definition_matches_checkpoint(submit_definition, submit_envelope):
            raise CheckpointDecodeError(
                "submit checkpoint does not match the submit_import JobDefinition",
                code="CHECKPOINT_IDENTITY_MISMATCH",
            )
        submit_state = _submit_state_from_job_state(
            deps.artifact_store,
            submit_envelope.job_state,
            repository_write=deps.repository_write,
            expected_payload=payload,
            prepare_checkpoint_ref=artifact_ref_from_dict(
                _require_artifact_ref_dict(
                    submit_envelope.job_state.get(_JOB_STATE_PREPARE_CHECKPOINT_REF),
                    label="prepare_checkpoint_ref",
                )
            ),
            checkpoint_ref=submit_step.checkpoint_ref,
        )
        if not submit_state.request_sent or submit_state.repository_operation_id is None:
            raise SubmitJobError("submit_import checkpoint is missing durable repository operation identity")

        prepare_step = _load_step(
            deps,
            operation_id=operation.operation_id,
            step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_PREPARE),
        )
        if prepare_step.checkpoint_ref is None:
            raise SubmitJobError("prepare_import checkpoint is missing")
        prepare_envelope = load_checkpoint_envelope(deps.artifact_store, prepare_step.checkpoint_ref)
        prepare_checkpoint = _prepare_checkpoint_from_job_state(
            prepare_envelope.job_state,
            expected_attempt_id=payload.submit_attempt_id,
        )

        await_checkpoint_ref = step.checkpoint_ref
        await_checkpoint_state: _AwaitCheckpointState | None = None
        if await_checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, await_checkpoint_ref)
            if not definition_matches_checkpoint(await_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the await_import_result JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            await_checkpoint_state = _await_checkpoint_from_job_state(
                envelope.job_state,
                expected_submit_checkpoint_ref=submit_step.checkpoint_ref,
                expected_repository_operation_id=submit_state.repository_operation_id,
            )
        else:
            reconcile_started_at = _iso_utc_timestamp(datetime.now(UTC))
            envelope = envelope_for_step(
                key=await_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state=_job_state_for_await_reconcile(
                    submit_checkpoint_ref=submit_step.checkpoint_ref,
                    repository_operation_id=submit_state.repository_operation_id,
                    reconcile_started_at=reconcile_started_at,
                ),
            )
            await_checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
            lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=await_checkpoint_ref,
                    extra_refs=(),
                    owner_kind="submit-checkpoint",
                    active_transaction=_active_submit_transaction.get,
                    transaction_missing=lambda: SubmitJobError("submit checkpoint transaction is not bound"),
                    deduplicate_refs=False,
                    intent="await-import-reconcile-checkpoint",
                )
            )
            await_checkpoint_state = _AwaitCheckpointState(
                submit_checkpoint_ref=submit_step.checkpoint_ref,
                repository_operation_id=submit_state.repository_operation_id,
                reconcile_started_at=reconcile_started_at,
                last_observed_repository_status=None,
                terminal_result_evidence_ref=None,
            )

        repository_operation: RepositoryImportOperation | None = None
        if (
            await_checkpoint_state is not None
            and await_checkpoint_state.terminal_result_evidence_ref is not None
        ):
            repository_operation = _load_terminal_repository_evidence(
                deps.artifact_store,
                await_checkpoint_state.terminal_result_evidence_ref,
                terminal_evidence_decode=deps.terminal_evidence_decode,
                expected_operation_id=submit_state.repository_operation_id,
                expected_status=await_checkpoint_state.last_observed_repository_status,
            )
        else:
            try:
                repository_operation = deps.repository_write.wait_operation(
                    repository_id=payload.repository_id,
                    operation_id=submit_state.repository_operation_id,
                )
            except (TimeoutError, RepositoryWriteTimeoutError):
                now = datetime.now(UTC)
                # One bounded poll timeout does not prove the Repository operation failed.
                # Schedule a checkpointed retry; the existing R5 attempt budget bounds repeats.
                intent = transition_for_outcome(
                    RecoveryPolicyOutcomeDisposition.RECONCILE_PENDING,
                    capability=RecoveryCapabilityValue.EXTERNAL_EFFECT,
                    attempt_count=step.attempt_count,
                    reconcile_elapsed_seconds=0.0,
                    effect_boundary_crossed=True,
                    cancel_requested=control.cancel_requested,
                    now=now,
                    jitter=lambda base, _cap: base,
                )
                if intent.step_target is StepStatus.RETRY_WAIT:
                    diagnostic = OperationDiagnostic(
                        code=DIAGNOSTIC_RETRY_SCHEDULED.upper(),
                        message="repository import poll timed out; reconcile retry scheduled",
                    )
                else:
                    diagnostic = OperationDiagnostic(
                        code=DIAGNOSTIC_RECONCILE_TIMEOUT.upper(),
                        message="repository import reconcile session budget exhausted",
                    )
                return lease_session.publish_recovery_release(
                    intent,
                    diagnostic=diagnostic,
                )

        if repository_operation.status in {
            RepositoryOperationStatus.QUEUED,
            RepositoryOperationStatus.RUNNING,
        }:
            if await_checkpoint_ref is None:
                raise SubmitJobError("await_import_result checkpoint is missing for reconcile handoff")
            checkpoint_generation = lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=await_checkpoint_ref,
                    extra_refs=(),
                    owner_kind="submit-checkpoint",
                    active_transaction=_active_submit_transaction.get,
                    transaction_missing=lambda: SubmitJobError("submit checkpoint transaction is not bound"),
                    deduplicate_refs=False,
                    intent="await-import-reconcile-checkpoint",
                )
            )
            return lease_session.acknowledge_safe_handoff(checkpoint_generation)

        if (
            await_checkpoint_state is not None
            and await_checkpoint_state.terminal_result_evidence_ref is None
            and await_checkpoint_ref is not None
        ):
            evidence_ref = _persist_terminal_repository_evidence(
                deps.artifact_store,
                repository_operation,
            )
            terminal_envelope = envelope_for_step(
                key=await_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state=_job_state_for_await_terminal(
                    submit_checkpoint_ref=submit_step.checkpoint_ref,
                    repository_operation_id=submit_state.repository_operation_id,
                    reconcile_started_at=await_checkpoint_state.reconcile_started_at,
                    last_observed_repository_status=repository_operation.status.value,
                    terminal_result_evidence_ref=evidence_ref,
                ),
            )
            await_checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, terminal_envelope)
            lease_session.publish_checkpoint(
                pinned_checkpoint_builder(
                    checkpoint_ref=await_checkpoint_ref,
                    extra_refs=(evidence_ref,),
                    owner_kind="submit-checkpoint",
                    active_transaction=_active_submit_transaction.get,
                    transaction_missing=lambda: SubmitJobError("submit checkpoint transaction is not bound"),
                    deduplicate_refs=False,
                    intent="await-import-terminal-checkpoint",
                )
            )
            await_checkpoint_state = _AwaitCheckpointState(
                submit_checkpoint_ref=submit_step.checkpoint_ref,
                repository_operation_id=submit_state.repository_operation_id,
                reconcile_started_at=await_checkpoint_state.reconcile_started_at,
                last_observed_repository_status=repository_operation.status.value,
                terminal_result_evidence_ref=evidence_ref,
            )

        if repository_operation.status is RepositoryOperationStatus.SUCCEEDED:
            try:
                facts = _matching_finalize_facts(
                    payload=payload,
                    prepare_checkpoint=prepare_checkpoint,
                    repository_operation=repository_operation,
                    repository_operation_id=submit_state.repository_operation_id,
                )
            except FinalizeBindingMismatch as exc:
                lease_session.publish_operation(
                    _make_manual_recovery_terminal_builder(
                        submit_state.repository_operation_id,
                        diagnostic=OperationDiagnostic(
                            code=FinalizeBindingMismatch.stable_code,
                            message=str(exc),
                        ),
                    )
                )
                return ExecutorAcknowledgment.PUBLISHED
            lease_session.publish_operation(
                _make_finalize_success_builder(
                    submit_attempt_id=payload.submit_attempt_id,
                    facts=facts,
                    submission_id_factory=deps.submission_id_factory,
                )
            )
            return ExecutorAcknowledgment.PUBLISHED

        if repository_operation.status is RepositoryOperationStatus.FAILED:
            if repository_operation.error is None:
                raise SubmitJobError("repository FAILED operation is missing error evidence")
            if repository_operation.error.code not in ALLOWED_ABORT_CODES:
                lease_session.publish_operation(
                    _make_manual_recovery_terminal_builder(
                        submit_state.repository_operation_id,
                        diagnostic=OperationDiagnostic(
                            code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED.upper(),
                            message=(
                                "repository failure code is not an allowed stable abort: "
                                f"{repository_operation.error.code}"
                            ),
                        ),
                    )
                )
                return ExecutorAcknowledgment.PUBLISHED
            proof = MatchingAbortProof(
                repository_id=payload.repository_id,
                repository_operation_id=submit_state.repository_operation_id,
                terminal_status=RepositoryOperationTerminalStatus.FAILED,
                stable_failure_code=repository_operation.error.code,
            )
            lease_session.publish_operation(
                _make_stable_abort_builder(
                    request=AbortSubmitTransactionRequest(
                        submit_attempt_id=payload.submit_attempt_id,
                        proof=proof,
                        aborted_at=datetime.now(UTC),
                        worker_id=step.worker_id,
                        lease_token=step.lease_token,
                    ),
                    evidence=_StaticAbortEvidence(repository_operation),
                )
            )
            return ExecutorAcknowledgment.PUBLISHED

        raise SubmitJobError("repository operation returned an unsupported terminal status")

    return execute


def build_submit_recovery_port(deps: SubmitRuntimeDependencies) -> RecoveryPort:
    submit_handler = build_submit_import_handler(deps)
    await_handler = build_await_import_result_handler(deps)

    class _SubmitRecoveryPort:
        def recover(
            self,
            operation: OperationRecord,
            step: StepRecord,
            control: ExecutionControl,
            lease_session: LeaseSession,
        ) -> RecoveryOutcome:
            if step.step_name == SUBMIT_STEP_SUBMIT:
                return _recover_external_effect_step(
                    deps=deps,
                    handler=submit_handler,
                    operation=operation,
                    step=step,
                    control=control,
                    lease_session=lease_session,
                )
            if step.step_name == SUBMIT_STEP_AWAIT:
                return _recover_external_effect_step(
                    deps=deps,
                    handler=await_handler,
                    operation=operation,
                    step=step,
                    control=control,
                    lease_session=lease_session,
                )
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason="submit recovery requires submit_import or await_import_result",
            )

    return cast(RecoveryPort, _SubmitRecoveryPort())


def build_submit_operator_recovery_port(
    *,
    write_uow_factory: WriteUnitOfWorkFactory,
    capability_lookup: RecoveryCapabilityLookup,
    submit_control_uow_factory: SubmitControlUnitOfWorkFactory,
    abort_evidence: RepositoryAbortEvidencePort,
    submit_deps: SubmitRuntimeDependencies,
) -> OperatorRecoveryApplicationPort:
    del submit_deps
    authorized = build_authorized_operator_recovery(
        write_uow_factory=write_uow_factory,
        capability_lookup=capability_lookup,
    )

    class _SubmitOperatorRecoveryPort:
        def execute_recovery(self, request: OperatorRecoveryRequest) -> TransitionDisposition:
            disposition = authorized.execute(request)
            if request.command is not OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE:
                return disposition
            with submit_control_uow_factory(read_only=True) as unit_of_work:
                operation = unit_of_work.operations.get_operation(request.operation_id)
                submit_attempt_id = _submit_attempt_id_from_operation(operation)
                attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
                if attempt is None:
                    raise ValueError("submit attempt is missing")
                if attempt.repository_operation_id is None:
                    raise ValueError("matching repository operation identity is required for business abort")
                stable_failure_code = abort_evidence.resolve_stable_failure_code(
                    repository_id=attempt.repository_id,
                    repository_operation_id=attempt.repository_operation_id,
                )
                proof = MatchingAbortProof(
                    repository_id=attempt.repository_id,
                    repository_operation_id=attempt.repository_operation_id,
                    terminal_status=RepositoryOperationTerminalStatus.FAILED,
                    stable_failure_code=stable_failure_code,
                )
            abort_submit_transaction(
                request=AbortSubmitTransactionRequest(
                    submit_attempt_id=submit_attempt_id,
                    proof=proof,
                    aborted_at=datetime.now(UTC),
                ),
                evidence=abort_evidence,
                unit_of_work_factory=submit_control_uow_factory,
            )
            return disposition

    return cast(OperatorRecoveryApplicationPort, _SubmitOperatorRecoveryPort())


def _materialize_submit_checkpoint_state(
    *,
    deps: SubmitRuntimeDependencies,
    submit_definition: JobDefinition,
    operation: OperationRecord,
    step: StepRecord,
    lease_session: LeaseSession,
    payload: SubmitJobPayload,
    attempt: SubmitAttempt,
    prepare_checkpoint: PrepareImportCheckpoint,
    prepare_checkpoint_ref: ArtifactRef,
) -> tuple[_SubmitCheckpointState, object | None]:
    if (
        attempt.state is SubmitAttemptState.EFFECT_PENDING
        and attempt.repository_artifact_ref is not None
    ):
        repository_artifact_ref = attempt.repository_artifact_ref
        request_bytes = deps.repository_write.canonical_import_request_bytes(repository_id=payload.repository_id, artifact_ref=repository_artifact_ref, expected_commit_id=payload.repository_expected_commit_id)
        request_ref = put_with_built_ref(
            deps.artifact_store,
            request_bytes,
            artifact_id=_import_request_artifact_id(request_bytes),
            media_type=_JCS_MEDIA_TYPE,
        )
        request_fingerprint = compute_request_fingerprint(request_bytes)
        reconcile_started_at = _iso_utc_timestamp(attempt.effect_pending_at or datetime.now(UTC))
        if attempt.repository_operation_id is not None:
            envelope = envelope_for_step(
                key=submit_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state=_job_state_for_submit_sent(
                    prepare_checkpoint_ref=prepare_checkpoint_ref,
                    repository_artifact_ref=repository_artifact_ref,
                    payload=payload,
                    request_artifact_ref=request_ref,
                    request_fingerprint=request_fingerprint,
                    repository_operation_id=attempt.repository_operation_id,
                    reconcile_started_at=reconcile_started_at,
                ),
            )
            request_sent = True
            repository_operation_id = attempt.repository_operation_id
        else:
            envelope = envelope_for_step(
                key=submit_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state=_job_state_for_submit_request(
                    prepare_checkpoint_ref=prepare_checkpoint_ref,
                    repository_artifact_ref=repository_artifact_ref,
                    payload=payload,
                    request_artifact_ref=request_ref,
                    request_fingerprint=request_fingerprint,
                    reconcile_started_at=reconcile_started_at,
                ),
            )
            request_sent = False
            repository_operation_id = None
        checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
        checkpoint_generation = lease_session.publish_checkpoint(
            pinned_checkpoint_builder(
                checkpoint_ref=checkpoint_ref,
                extra_refs=(prepare_checkpoint_ref, request_ref),
                owner_kind="submit-checkpoint",
                active_transaction=_active_submit_transaction.get,
                transaction_missing=lambda: SubmitJobError("submit checkpoint transaction is not bound"),
                deduplicate_refs=False,
                intent="submit-import-checkpoint",
            )
        )
        return (
            _SubmitCheckpointState(
                prepare_checkpoint_ref=prepare_checkpoint_ref,
                repository_artifact_ref=repository_artifact_ref,
                request_artifact_ref=request_ref,
                request_fingerprint=request_fingerprint,
                request_sent=request_sent,
                repository_operation_id=repository_operation_id,
                checkpoint_ref=checkpoint_ref,
            ),
            checkpoint_generation,
        )

    package_bytes = deps.publication.read_back_package(
        checkpoint=prepare_checkpoint,
        store=deps.artifact_store,
    )
    repository_artifact_ref = deps.repository_write.upload_artifact(
        repository_id=payload.repository_id,
        idempotency_key=payload.repository_upload_idempotency_key,
        media_type=prepare_checkpoint.backend_import_artifact_ref.media_type,
        raw_sha256=prepare_checkpoint.package_raw_sha256,
        body=package_bytes,
    )
    request_bytes = deps.repository_write.canonical_import_request_bytes(repository_id=payload.repository_id, artifact_ref=repository_artifact_ref, expected_commit_id=payload.repository_expected_commit_id)
    request_ref = put_with_built_ref(
        deps.artifact_store,
        request_bytes,
        artifact_id=_import_request_artifact_id(request_bytes),
        media_type=_JCS_MEDIA_TYPE,
    )
    request_fingerprint = compute_request_fingerprint(request_bytes)
    effect_pending_at = datetime.now(UTC)
    with deps.control_transaction_factory() as unit_of_work:
        fresh_attempt = unit_of_work.submission.get_submit_attempt(payload.submit_attempt_id)
        if fresh_attempt is None:
            raise SubmitJobError("submit attempt is missing")
        mark_submit_attempt_effect_pending(
            request=EffectPendingTransactionRequest(
                submit_attempt_id=payload.submit_attempt_id,
                checkpoint=prepare_checkpoint,
                repository_artifact_ref=repository_artifact_ref,
                effect_pending_at=effect_pending_at,
                expected_attempt_version=fresh_attempt.optimistic_version,
            ),
            unit_of_work=unit_of_work,
        )
    envelope = envelope_for_step(
        key=submit_definition.key,
        operation=operation,
        step=step,
        checkpoint_generation=_checkpoint_generation(step),
        job_state=_job_state_for_submit_request(
            prepare_checkpoint_ref=prepare_checkpoint_ref,
            repository_artifact_ref=repository_artifact_ref,
            payload=payload,
            request_artifact_ref=request_ref,
            request_fingerprint=request_fingerprint,
            reconcile_started_at=_iso_utc_timestamp(effect_pending_at),
        ),
    )
    checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
    checkpoint_generation = lease_session.publish_checkpoint(
        pinned_checkpoint_builder(
            checkpoint_ref=checkpoint_ref,
            extra_refs=(prepare_checkpoint_ref, request_ref),
            owner_kind="submit-checkpoint",
            active_transaction=_active_submit_transaction.get,
            transaction_missing=lambda: SubmitJobError("submit checkpoint transaction is not bound"),
            deduplicate_refs=False,
            intent="submit-import-checkpoint",
        )
    )
    return (
        _SubmitCheckpointState(
            prepare_checkpoint_ref=prepare_checkpoint_ref,
            repository_artifact_ref=repository_artifact_ref,
            request_artifact_ref=request_ref,
            request_fingerprint=request_fingerprint,
            request_sent=False,
            repository_operation_id=None,
            checkpoint_ref=checkpoint_ref,
        ),
        checkpoint_generation,
    )


def _submit_may_invoke_handler_without_checkpoint(
    deps: SubmitRuntimeDependencies,
    operation: OperationRecord,
    step: StepRecord,
) -> bool:
    if step.step_name != SUBMIT_STEP_SUBMIT:
        return False
    try:
        payload = _load_submit_payload(operation, deps.artifact_store)
        attempt = _load_submit_attempt(deps, payload.submit_attempt_id)
    except Exception:
        return False
    if (
        attempt.state is SubmitAttemptState.EFFECT_PENDING
        and attempt.repository_artifact_ref is not None
    ):
        return True
    if attempt.state is SubmitAttemptState.PREPARED:
        try:
            prepare_step = _load_step(
                deps,
                operation_id=operation.operation_id,
                step_id=_successor_step_id(operation.operation_id, SUBMIT_STEP_PREPARE),
            )
        except Exception:
            return False
        return prepare_step.checkpoint_ref is not None
    return False


def _map_handler_failure_to_recovery_outcome(
    exc: BaseException,
) -> RecoveryOutcome | None:
    if isinstance(exc, (RepositoryWriteTimeoutError, TimeoutError)):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_RECONCILE_TIMEOUT,
            reason=str(exc),
        )
    if isinstance(exc, RepositoryWriteTransportError):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason=str(exc),
        )
    if isinstance(exc, RepositoryUploadMetadataMismatch):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason=str(exc),
        )
    if isinstance(
        exc,
        (
            SubmitJobError,
            CheckpointDecodeError,
            PayloadDecodeError,
            SubmitImportBuilderError,
            FinalizeBindingMismatch,
            AbortProofNotSatisfied,
            FinalizeRecoveryRequired,
            ValueError,
        ),
    ):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason=str(exc),
        )
    return None


@dataclass(frozen=True, slots=True)
class _StaticAbortEvidence:
    operation: RepositoryImportOperation

    def resolve_stable_failure_code(
        self,
        *,
        repository_id: str,
        repository_operation_id: str,
    ) -> str:
        del repository_id
        if str(self.operation.operation_id) != repository_operation_id:
            raise ValueError("repository operation identity does not match proof")
        if self.operation.status is not RepositoryOperationStatus.FAILED:
            raise ValueError("repository operation is not FAILED")
        if self.operation.error is None:
            raise ValueError("repository FAILED operation is missing error evidence")
        return self.operation.error.code

    def validate_matching_stable_failure(
        self,
        *,
        attempt: SubmitAttempt,
        proof: MatchingAbortProof,
    ) -> None:
        del attempt
        if str(self.operation.operation_id) != proof.repository_operation_id:
            raise ValueError("repository operation identity does not match proof")
        if self.operation.status is not RepositoryOperationStatus.FAILED:
            raise ValueError("repository operation is not FAILED")
        if self.operation.error is None or self.operation.error.code != proof.stable_failure_code:
            raise ValueError("abort proof stable failure code does not match repository")


def _recover_external_effect_step(
    *,
    deps: SubmitRuntimeDependencies,
    handler: ClaimedExecutor,
    operation: OperationRecord,
    step: StepRecord,
    control: ExecutionControl,
    lease_session: LeaseSession,
) -> RecoveryOutcome:
    if (
        operation.status is OperationStatus.SUCCEEDED
        and step.status is StepStatus.SUCCEEDED
    ):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.PUBLISHED,
            diagnostic_code=None,
            reason=None,
        )

    lease_session.refresh_control()
    if step.checkpoint_ref is None and control.cancel_requested:
        lease_session.publish_operation(_make_cancelled_terminal_builder())
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.CANCELLED,
            diagnostic_code=None,
            reason=None,
        )

    if step.checkpoint_ref is None and not _submit_may_invoke_handler_without_checkpoint(
        deps,
        operation,
        step,
    ):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason="submit external-effect recovery requires a durable checkpoint",
        )

    try:
        acknowledgment = handler(operation, step, control, lease_session)
    except Exception as exc:
        outcome = _map_handler_failure_to_recovery_outcome(exc)
        if outcome is None:
            raise
        return outcome

    if acknowledgment is ExecutorAcknowledgment.PUBLISHED:
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.PUBLISHED,
            diagnostic_code=None,
            reason=None,
        )
    return RecoveryOutcome(
        disposition=RecoveryOutcomeDisposition.RECONCILE_PENDING,
        diagnostic_code=None,
        reason=None,
    )


def _capability_storage_projection_version(contract_version: str) -> str:
    if contract_version == "v1":
        return STORAGE_PROJECTION_VERSION
    raise SubmitImportBuilderError("unsupported storage_projection_version")


def _build_prepare_import_build_input(
    *,
    payload: SubmitJobPayload,
    attempt: SubmitAttempt,
    operation: OperationRecord,
    store: ArtifactStorePort,
    parent_catalog: RepositoryParentCatalogPort,
) -> PrepareImportBuildInput:
    ruleset = migrated_table_ruleset_snapshot()
    if ruleset.ruleset_digest is None:
        raise SubmitImportBuilderError("ruleset digest is required")
    try:
        ready_closure_ref = next(
            (
                ref
                for ref in operation.artifact_refs
                if ref.artifact_id == attempt.preview_ready_closure_ref
            ),
            None,
        )
        if ready_closure_ref is None:
            raise SubmitImportBuilderError("operation is missing the preview ready closure ref")
        ready_closure_refs = load_ready_closure(store, ready_closure_ref).artifact_refs()
        snapshot_tables, canonical_refs = resolve_canonical_snapshot_bindings(
            operation_artifact_refs=unique_artifact_refs(
                (*operation.artifact_refs, *ready_closure_refs)
            ),
            canonical_table_set_closure_ref=attempt.canonical_table_set_closure_ref,
            canonical_table_set_closure_digest=attempt.canonical_table_set_closure_digest,
            canonicalization_manifest_ref=attempt.canonicalization_manifest_ref,
            canonicalization_manifest_digest=attempt.canonicalization_manifest_digest,
            read_artifact=store.locate,
        )
        canonical_refs_by_id = {ref.artifact_id: ref for ref in canonical_refs}
        closure_ref = canonical_refs_by_id[attempt.canonical_table_set_closure_ref]
        manifest_ref = canonical_refs_by_id[attempt.canonicalization_manifest_ref]
        parent_table_names = parent_catalog.get_table_names(
            repository_id=attempt.repository_id,
            commit_id=attempt.repository_expected_commit_id,
        )
        removed_tables = derive_removed_tables(
            parent_table_names=parent_table_names,
            snapshot_tables=snapshot_tables,
        )
    except SubmitImportBuilderError as exc:
        raise SubmitImportPublicationError(str(exc)) from exc
    return PrepareImportBuildInput(
        submit_attempt_id=payload.submit_attempt_id,
        builder_mutation_policy=payload.builder_mutation_policy,
        canonical_table_set_closure_ref=closure_ref,
        canonical_table_set_closure_digest=payload.canonical_table_set_closure_digest,
        canonicalization_manifest_ref=manifest_ref,
        canonicalization_manifest_digest=payload.canonicalization_manifest_digest,
        expected_parent_commit_id=payload.repository_expected_commit_id,
        removed_tables=removed_tables,
        source_artifact_digest=attempt.snapshot_digest,
        repository_base_digest=attempt.source_digest,
        storage_projection_version=_capability_storage_projection_version(
            payload.storage_projection_version
        ),
        ruleset_id=ruleset.ruleset_id,
        ruleset_version=ruleset.ruleset_version,
        ruleset_digest=ruleset.ruleset_digest.value,
        snapshot_tables=snapshot_tables,
    )


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
        checkpoint_generation=_checkpoint_generation(step),
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
            transaction_missing=lambda: SubmitJobError("submit checkpoint transaction is not bound"),
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
        JOB_STATE_RECONCILE_STARTED_AT,
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
        JOB_STATE_RECONCILE_STARTED_AT,
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
_TERMINAL_REPOSITORY_EVIDENCE_FAILED_KEYS = _TERMINAL_REPOSITORY_EVIDENCE_BASE_KEYS | frozenset({"error"})


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
    reconcile_started_at: str,
) -> dict[str, object]:
    return {
        _JOB_STATE_SCHEMA_VERSION: AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA,
        _JOB_STATE_SUBMIT_CHECKPOINT_REF: artifact_ref_to_dict(submit_checkpoint_ref),
        JOB_STATE_OPERATION_IDENTITY: repository_operation_id,
        JOB_STATE_RECONCILE_STARTED_AT: reconcile_started_at,
    }


def _job_state_for_await_terminal(
    *,
    submit_checkpoint_ref: ArtifactRef,
    repository_operation_id: str,
    reconcile_started_at: str,
    last_observed_repository_status: str,
    terminal_result_evidence_ref: ArtifactRef,
) -> dict[str, object]:
    return {
        _JOB_STATE_SCHEMA_VERSION: AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA,
        _JOB_STATE_SUBMIT_CHECKPOINT_REF: artifact_ref_to_dict(submit_checkpoint_ref),
        JOB_STATE_OPERATION_IDENTITY: repository_operation_id,
        JOB_STATE_RECONCILE_STARTED_AT: reconcile_started_at,
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
    reconcile_started_at = _require_non_empty_str_value(
        job_state.get(JOB_STATE_RECONCILE_STARTED_AT),
        label="reconcile_started_at",
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
        reconcile_started_at=reconcile_started_at,
        last_observed_repository_status=last_observed_repository_status,
        terminal_result_evidence_ref=terminal_result_evidence_ref,
    )


def _serialize_terminal_repository_evidence(operation: RepositoryImportOperation) -> dict[str, object]:
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
        artifact_id=f"submit-repository-terminal-evidence:{raw_blob_digest(evidence_bytes).value}",
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
    return PrepareImportCheckpoint(
        schema_version=PREPARE_IMPORT_CHECKPOINT_SCHEMA,
        attempt_id=attempt_id,
        canonicalization_manifest_ref=_backend_ref_from_dict(
            _require_mapping(job_state.get(_JOB_STATE_MANIFEST_REF), label="canonicalization_manifest_ref"),
        ),
        canonicalization_manifest_digest=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_MANIFEST_DIGEST),
            label="canonicalization_manifest_digest",
        ),
        backend_import_artifact_ref=_backend_ref_from_dict(
            _require_mapping(job_state.get(_JOB_STATE_BACKEND_IMPORT_REF), label="backend_import_artifact_ref"),
        ),
        package_raw_size=_require_non_negative_int_value(job_state.get(_JOB_STATE_PACKAGE_RAW_SIZE)),
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
        removed_tables=_decode_checkpoint_string_tuple(
            job_state.get(_JOB_STATE_REMOVED_TABLES),
            label="removed_tables",
        ),
        builder_mutation_policy=BuilderMutationPolicy(
            _require_non_empty_str_value(job_state.get(_JOB_STATE_BUILDER_POLICY), label="builder_mutation_policy")
        ),
    )


def _job_state_for_submit_request(
    *,
    prepare_checkpoint_ref: ArtifactRef,
    repository_artifact_ref: RepositoryArtifactRef,
    payload: SubmitJobPayload,
    request_artifact_ref: ArtifactRef,
    request_fingerprint: str,
    reconcile_started_at: str,
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
        JOB_STATE_RECONCILE_STARTED_AT: reconcile_started_at,
    }


def _job_state_for_submit_sent(
    *,
    prepare_checkpoint_ref: ArtifactRef,
    repository_artifact_ref: RepositoryArtifactRef,
    payload: SubmitJobPayload,
    request_artifact_ref: ArtifactRef,
    request_fingerprint: str,
    repository_operation_id: str,
    reconcile_started_at: str,
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
        JOB_STATE_RECONCILE_STARTED_AT: reconcile_started_at,
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
    _require_non_empty_str_value(
        job_state.get(JOB_STATE_RECONCILE_STARTED_AT),
        label="reconcile_started_at",
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
        _require_mapping(job_state.get(_JOB_STATE_REPOSITORY_ARTIFACT_REF), label="repository_artifact_ref"),
    )
    upload_key = job_state.get(_JOB_STATE_UPLOAD_KEY)
    if upload_key != expected_payload.repository_upload_idempotency_key:
        raise CheckpointDecodeError(
            "submit checkpoint upload_idempotency_key does not match payload",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    import_key = job_state.get(_JOB_STATE_IMPORT_KEY)
    if import_key != expected_payload.repository_import_idempotency_key:
        raise CheckpointDecodeError(
            "submit checkpoint import_idempotency_key does not match payload",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    request_artifact_id = _require_non_empty_str_value(
        job_state.get(_JOB_STATE_REQUEST_ARTIFACT_ID),
        label="request_artifact_id",
    )
    request_artifact_ref = artifact_ref_from_dict(
        _require_artifact_ref_dict(job_state.get(_JOB_STATE_REQUEST_ARTIFACT_REF), label="request_artifact_ref"),
    )
    if request_artifact_ref.artifact_id != request_artifact_id:
        raise CheckpointDecodeError(
            "submit checkpoint request_artifact_id does not match request_artifact_ref",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
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
            code="CHECKPOINT_JOB_STATE_MISMATCH",
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
                code="CHECKPOINT_JOB_STATE_MISMATCH",
            )
    request_fingerprint = compute_request_fingerprint(request_bytes)
    stored_fingerprint = job_state.get(JOB_STATE_REQUEST_FINGERPRINT)
    if type(stored_fingerprint) is not str or stored_fingerprint != request_fingerprint:
        raise CheckpointDecodeError(
            "submit checkpoint request_fingerprint does not match payload semantics",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
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


def _verification_policy_from_repository(value: str) -> SubmitVerificationPolicy:
    if value == SubmitVerificationPolicy.STRUCTURAL.value:
        return SubmitVerificationPolicy.STRUCTURAL
    raise FinalizeBindingMismatch(
        f"completed verification policy {value!r} is not supported"
    )


def _unknown_type_policy_from_repository(value: str) -> SubmitUnknownTypePolicy:
    if value == SubmitUnknownTypePolicy.REJECT.value:
        return SubmitUnknownTypePolicy.REJECT
    raise FinalizeBindingMismatch(
        f"completed unknown type policy {value!r} is not supported"
    )


def _target_ref_from_repository(value: str) -> SubmitTargetRef:
    if value == SubmitTargetRef.MAIN.value:
        return SubmitTargetRef.MAIN
    raise FinalizeBindingMismatch("completed target ref must be main")


def _matching_finalize_facts(
    *,
    payload: SubmitJobPayload,
    prepare_checkpoint: PrepareImportCheckpoint,
    repository_operation: RepositoryImportOperation,
    repository_operation_id: str,
) -> MatchingFinalizeFacts:
    if repository_operation.operation_id != repository_operation_id:
        raise FinalizeBindingMismatch("repository operation identity does not match checkpoint")
    if repository_operation.result is None:
        raise SubmitJobError("repository SUCCEEDED operation is missing result")
    result = repository_operation.result
    manifest_digest = str(result.canonicalization_manifest_digest)
    if manifest_digest != prepare_checkpoint.canonicalization_manifest_digest:
        raise FinalizeBindingMismatch("repository manifest digest does not match prepare checkpoint")
    expected_commit_id = str(result.expected_commit_id)
    if expected_commit_id != payload.repository_expected_commit_id:
        raise FinalizeBindingMismatch("repository expected commit does not match payload")
    completed_verification_policy = _verification_policy_from_repository(
        result.completed_verification_policy
    )
    if completed_verification_policy is not payload.repository_policy.verification_policy:
        raise FinalizeBindingMismatch("completed verification policy does not match request")
    completed_unknown_type_policy = _unknown_type_policy_from_repository(
        result.unknown_type_policy
    )
    if completed_unknown_type_policy is not payload.repository_policy.unknown_type_policy:
        raise FinalizeBindingMismatch("completed unknown type policy does not match request")
    target_ref = _target_ref_from_repository(str(result.target_ref))
    if target_ref is not payload.repository_policy.target_ref:
        raise FinalizeBindingMismatch("completed target ref does not match request")
    return MatchingFinalizeFacts(
        repository_id=payload.repository_id,
        repository_operation_id=repository_operation_id,
        repository_commit_id=str(result.commit_id),
        repository_expected_parent_commit_id=expected_commit_id,
        repository_artifact_id=str(result.artifact_id),
        repository_import_artifact_raw_sha256=prepare_checkpoint.package_raw_sha256,
        canonicalization_manifest_ref=prepare_checkpoint.canonicalization_manifest_ref.artifact_id,
        canonicalization_manifest_digest=manifest_digest,
        completed_verification_policy=completed_verification_policy,
        completed_unknown_type_policy=completed_unknown_type_policy,
        target_ref=target_ref,
    )


def _wire_repository_raw_sha256(value: str) -> str:
    return value.removeprefix("sha256:")



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


def _load_step(
    deps: SubmitRuntimeDependencies,
    *,
    operation_id: str,
    step_id: str,
) -> StepRecord:
    with deps.control_transaction_factory() as unit_of_work:
        step = unit_of_work.operations.get_step(step_id)
    if step.operation_id != operation_id:
        raise SubmitJobError("submit step belongs to a different operation")
    return step


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


def read_write_factory(
    factory: SubmitControlTransactionFactory,
) -> SubmitControlUnitOfWorkFactory:
    def unit_of_work_factory(*, read_only: bool = False) -> ContextManager[SubmitControlTransaction]:
        del read_only
        return factory()

    return unit_of_work_factory


def _definition_for_step(step_name: str) -> JobDefinition:
    for definition in submit_job_definitions():
        if definition.key.step_name == step_name:
            return definition
    raise SubmitJobError(f"submit step definition is missing: {step_name}")


def _make_successor_builder(
    *,
    operation_id: str,
    successor_step_name: str,
    successor_step_id: str,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, StepRecord]]:
    def builder(
        operation: OperationRecord,
        current_step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, StepRecord]:
        terminal_step = _terminal_step(current_step, transaction_now, status=StepStatus.SUCCEEDED)
        successor = StepRecord(
            contract_version=OPERATION_RUNTIME_CONTRACT_VERSION,
            step_id=successor_step_id,
            operation_id=operation_id,
            step_name=successor_step_name,
            status=StepStatus.PENDING,
            attempt_count=0,
            diagnostic=None,
            cancel_requested=False,
            retry_not_before=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            checkpoint_ref=None,
            prior_output_refs=(),
            created_at=transaction_now,
            updated_at=transaction_now,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        return terminal_step, successor

    return builder


def _terminal_step(step: StepRecord, transaction_now: datetime, *, status: StepStatus) -> StepRecord:
    return dataclasses.replace(
        step,
        status=status,
        worker_id=None,
        lease_token=None,
        lease_expires_at=None,
        completed_at=transaction_now,
        updated_at=transaction_now,
        optimistic_version=step.optimistic_version + 1,
    )


def _make_stable_abort_builder(
    *,
    request: AbortSubmitTransactionRequest,
    evidence: RepositoryAbortEvidencePort,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_submit_transaction.get()
        if transaction is None:
            raise SubmitJobError("submit abort transaction is not bound")
        attempt = transaction.submission.get_submit_attempt(request.submit_attempt_id)
        if attempt is None:
            raise SubmitJobError("submit attempt is missing")
        validate_abort_proof(attempt=attempt, proof=request.proof, evidence=evidence)
        abort_submit_in_control_transaction(
            request=AbortSubmitTransactionRequest(
                submit_attempt_id=request.submit_attempt_id,
                proof=request.proof,
                aborted_at=transaction_now,
                worker_id=step.worker_id,
                lease_token=step.lease_token,
                expected_attempt_version=attempt.optimistic_version,
                expected_await_step_version=step.optimistic_version,
                expected_operation_version=operation.optimistic_version,
                defer_operation_terminal=True,
            ),
            unit_of_work=transaction,
        )
        abort_code = request.proof.stable_failure_code
        diagnostic = OperationDiagnostic(code=abort_code, message="submit attempt aborted")
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder


def _make_finalize_success_builder(
    *,
    submit_attempt_id: str,
    facts: MatchingFinalizeFacts,
    submission_id_factory: Callable[[], str],
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_submit_transaction.get()
        if transaction is None:
            raise SubmitJobError("submit finalize transaction is not bound")
        attempt = transaction.submission.get_submit_attempt(submit_attempt_id)
        if attempt is None:
            raise SubmitJobError("submit attempt is missing")
        finalize_submit_transaction(
            request=FinalizeSubmitTransactionRequest(
                submit_attempt_id=submit_attempt_id,
                facts=facts,
                submission_id=submission_id_factory(),
                created_at=transaction_now,
                expected_attempt_version=attempt.optimistic_version,
                expected_await_step_version=step.optimistic_version,
                expected_operation_version=operation.optimistic_version,
                worker_id=step.worker_id,
                lease_token=step.lease_token,
                defer_operation_terminal=True,
            ),
            unit_of_work=transaction,
        )
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.SUCCEEDED,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.SUCCEEDED,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder


def _prepare_projection_failure_diagnostic(exc: SubmitImportPublicationError) -> OperationDiagnostic:
    message = str(exc)
    encoded = message.encode("utf-8")
    if len(encoded) > _MAX_PREPARE_PROJECTION_MESSAGE_BYTES:
        message = encoded[:_MAX_PREPARE_PROJECTION_MESSAGE_BYTES].decode("utf-8", errors="ignore")
    code = "UNSUPPORTED_TABLE" if "UNSUPPORTED_TABLE" in message else "STORAGE_PROJECTION_FAILED"
    return OperationDiagnostic(code=code, message=message)


def _make_prepare_projection_failure_builder(
    diagnostic: OperationDiagnostic,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_submit_transaction.get()
        if transaction is None:
            raise SubmitJobError("submit prepare failure transaction is not bound")
        submit_attempt_id = _submit_attempt_id_from_operation(operation)
        abort_prepared_submit_in_control_transaction(
            request=AbortPreparedSubmitRequest(
                submit_attempt_id=submit_attempt_id,
                abort_code=diagnostic.code,
                aborted_at=transaction_now,
            ),
            unit_of_work=transaction,
        )
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.FAILED,
            diagnostic=diagnostic,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.FAILED,
            diagnostic=diagnostic,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder


def _publish_prepare_terminal_abort(
    lease_session: LeaseSession,
    diagnostic: OperationDiagnostic,
) -> None:
    lease_session.publish_operation(_make_prepare_projection_failure_builder(diagnostic))


def _publish_prepare_projection_failure(
    lease_session: LeaseSession,
    exc: SubmitImportPublicationError,
) -> None:
    _publish_prepare_terminal_abort(
        lease_session,
        _prepare_projection_failure_diagnostic(exc),
    )


_PREPARE_CHECKPOINT_BINDING_DIAGNOSTIC = OperationDiagnostic(
    code="CHECKPOINT_ATTEMPT_BINDING_MISMATCH",
    message="prepare checkpoint attempt_id does not match submit payload",
)


def _publish_prepare_binding_failure(lease_session: LeaseSession) -> None:
    _publish_prepare_terminal_abort(lease_session, _PREPARE_CHECKPOINT_BINDING_DIAGNOSTIC)


def _make_cancelled_terminal_builder() -> Callable[
    [OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]
]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        transaction = _active_submit_transaction.get()
        if transaction is None:
            raise SubmitJobError("submit cancellation transaction is not bound")
        if operation.ready_closure_ref is not None:
            raise CheckpointPublicationError(
                "ready_closure_ref is already set",
                code="CLOSURE_ALREADY_SET",
            )
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.CANCELLED,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.CANCELLED,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder


def _make_manual_recovery_terminal_builder(
    repository_operation_id: str | None,
    *,
    diagnostic: OperationDiagnostic,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        if operation.ready_closure_ref is not None:
            raise CheckpointPublicationError(
                "ready_closure_ref is already set",
                code="CLOSURE_ALREADY_SET",
            )
        terminal_step = dataclasses.replace(
            step,
            status=StepStatus.MANUAL_RECOVERY_REQUIRED,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
            diagnostic=diagnostic,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            repository_operation_id=repository_operation_id,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
            diagnostic=diagnostic,
        )
        return terminal_step, terminal_operation

    return builder


def _import_request_artifact_id(request_bytes: bytes) -> str:
    return f"submit-import-request:{raw_blob_digest(request_bytes).value}"


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


def _expected_operation_identity_placeholder(request_bytes: bytes) -> str:
    del request_bytes
    return "pending"


def _checkpoint_generation(step: StepRecord) -> int:
    attempt_count = step.attempt_count
    if type(attempt_count) is not int or isinstance(attempt_count, bool) or attempt_count < 1:
        raise ValueError("attempt_count must be a positive int for checkpoint generation")
    return attempt_count


def _iso_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        raise PayloadDecodeError("repository_policy.target_ref must be main", code="PAYLOAD_SHAPE_INVALID")
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
    if builder_mutation_policy is not BuilderMutationPolicy.REBUILD_ALWAYS:
        raise PayloadDecodeError(
            "builder_mutation_policy must be REBUILD_ALWAYS",
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


def _require_non_empty_str(payload_object: dict[str, object], key: str) -> str:
    value = payload_object.get(key)
    if type(value) is not str or not value:
        raise PayloadDecodeError(f"{key} must be a non-empty string", code="PAYLOAD_SHAPE_INVALID")
    return value


def _require_non_negative_int(payload_object: dict[str, object], key: str) -> int:
    value = payload_object.get(key)
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise PayloadDecodeError(f"{key} must be a non-negative int", code="PAYLOAD_SHAPE_INVALID")
    return value


def _require_non_empty_str_value(value: object, *, label: str) -> str:
    if type(value) is not str or not value:
        raise CheckpointDecodeError(f"{label} must be a non-empty string", code="CHECKPOINT_JOB_STATE_MISMATCH")
    return value


def _require_non_negative_int_value(value: object) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise CheckpointDecodeError("checkpoint integer field is invalid", code="CHECKPOINT_JOB_STATE_MISMATCH")
    return value


def _require_mapping(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise CheckpointDecodeError(f"{label} must be an object", code="CHECKPOINT_JOB_STATE_MISMATCH")
    return value


def _require_artifact_ref_dict(value: object, *, label: str) -> dict[str, object]:
    mapping = _require_mapping(value, label=label)
    try:
        artifact_ref_from_dict(mapping)
    except (TypeError, ValueError, KeyError, ManifestVerificationError) as exc:
        raise CheckpointDecodeError(f"{label} is invalid", code="CHECKPOINT_JOB_STATE_MISMATCH") from exc
    return mapping


def _decode_string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise PayloadDecodeError(f"{label} must be an array", code="PAYLOAD_SHAPE_INVALID")
    decoded: list[str] = []
    for item in value:
        if type(item) is not str or not item:
            raise PayloadDecodeError(f"{label} must contain non-empty strings", code="PAYLOAD_SHAPE_INVALID")
        decoded.append(item)
    return tuple(decoded)


def _decode_checkpoint_string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if type(value) is not list:
        raise CheckpointDecodeError(f"{label} must be an array", code="CHECKPOINT_JOB_STATE_MISMATCH")
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
        raise PayloadDecodeError("repository_policy must be an object", code="PAYLOAD_SHAPE_INVALID")
    target_ref = value.get("target_ref")
    verification_policy = value.get("verification_policy")
    unknown_type_policy = value.get("unknown_type_policy")
    if type(target_ref) is not str:
        raise PayloadDecodeError("repository_policy.target_ref must be a string", code="PAYLOAD_SHAPE_INVALID")
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
        raise PayloadDecodeError("repository_policy contains invalid enum values", code="PAYLOAD_SHAPE_INVALID") from exc


def _decode_builder_mutation_policy(value: object) -> BuilderMutationPolicy:
    if type(value) is not str:
        raise PayloadDecodeError("builder_mutation_policy must be a string", code="PAYLOAD_SHAPE_INVALID")
    try:
        return BuilderMutationPolicy(value)
    except ValueError as exc:
        raise PayloadDecodeError("builder_mutation_policy is invalid", code="PAYLOAD_SHAPE_INVALID") from exc


__all__ = [
    "AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA",
    "OperatorRecoveryApplicationPort",
    "SUBMIT_IMPORT_CHECKPOINT_SCHEMA",
    "SubmitJobPayload",
    "SubmitRepositoryPolicy",
    "SubmitRuntimeDependencies",
    "build_await_import_result_handler",
    "bind_submit_control_transaction_factory",
    "build_prepare_import_handler",
    "build_submit_import_handler",
    "build_submit_operator_recovery_port",
    "build_submit_recovery_port",
    "decode_submit_payload",
    "submit_composition_bundle",
    "submit_payload_decoders",
]
