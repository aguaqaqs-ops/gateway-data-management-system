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
from uuid import UUID

import httpx
from gateway_repository_contracts import (
    OperationStatus as RepositoryOperationStatus,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    RepositoryArtifactRef as WireRepositoryArtifactRef,
    SubmitVersionedImportRequest,
    UnknownTypePolicy,
    VerificationPolicy,
    VersionedOperation,
)
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    make_checkpoint_step_builder,
    prepare_step_checkpoint,
)
from gateway_backend.application.job_definitions import JobDefinition
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
from gateway_backend.application.submission.abort import ALLOWED_ABORT_CODES
from gateway_backend.application.submission.abort_transaction import (
    AbortSubmitTransactionRequest,
    abort_submit_transaction,
)
from gateway_backend.application.submission.contracts import (
    PREPARE_IMPORT_CHECKPOINT_SCHEMA,
    MatchingAbortProof,
    MatchingFinalizeFacts,
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    RepositoryOperationTerminalStatus,
    SnapshotTableBinding,
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
    pin_prepare_import_artifacts,
    publish_prepare_import_package,
    reuse_prepare_import_checkpoint,
)
from gateway_backend.application.submission.job_payload import (
    SUBMIT_STEP_AWAIT,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.application.submission.errors import (
    AbortProofNotSatisfied,
    FinalizeBindingMismatch,
    FinalizeRecoveryRequired,
    RepositoryWriteTimeoutError,
)
from gateway_backend.application.submission.ports import (
    RepositoryAbortEvidencePort,
    RepositoryWritePort,
    SubmitControlTransaction,
    SubmitControlUnitOfWorkFactory,
)
from gateway_backend.artifacts.nominal_refs import store_ref_from_backend_artifact_ref
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
    OperatorRecoveryCommand,
    OperatorRecoveryRequest,
    RecoveryCapabilityLookup,
    build_authorized_operator_recovery,
)
from gateway_backend.operations.state import TransitionDisposition
from gateway_backend.operations.worker import (
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
    WriteUnitOfWorkFactory,
)
from gateway_backend.capabilities.table_rules.registry import migrated_table_ruleset_snapshot

SUBMIT_IMPORT_CHECKPOINT_SCHEMA = "backend-vnext/submit/submit-import-checkpoint/v1"
AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA = "backend-vnext/submit/await-import-result-checkpoint/v1"

_JCS_MEDIA_TYPE = "application/jcs"

_JOB_STATE_SCHEMA_VERSION = "schema_version"
_JOB_STATE_ATTEMPT_ID = "attempt_id"
_JOB_STATE_MANIFEST_REF = "canonicalization_manifest_ref"
_JOB_STATE_MANIFEST_DIGEST = "canonicalization_manifest_digest"
_JOB_STATE_BACKEND_IMPORT_REF = "backend_import_artifact_ref"
_JOB_STATE_PACKAGE_RAW_SIZE = "package_raw_size"
_JOB_STATE_PACKAGE_RAW_SHA256 = "package_raw_sha256"
_JOB_STATE_INPUT_CLOSURE_DIGEST = "input_closure_digest"
_JOB_STATE_BUILDER_POLICY = "builder_mutation_policy"

_JOB_STATE_PREPARE_CHECKPOINT_REF = "prepare_checkpoint_ref"
_JOB_STATE_REPOSITORY_ARTIFACT_REF = "repository_artifact_ref"
_JOB_STATE_UPLOAD_KEY = "upload_idempotency_key"
_JOB_STATE_REQUEST_ARTIFACT_ID = "request_artifact_id"
_JOB_STATE_REQUEST_ARTIFACT_REF = "request_artifact_ref"
_JOB_STATE_IMPORT_KEY = "import_idempotency_key"
_JOB_STATE_SUBMIT_CHECKPOINT_REF = "submit_checkpoint_ref"

_active_submit_transaction: ContextVar[SubmitControlTransaction | None] = ContextVar(
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
    snapshot_table_set_digest: str
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


SubmitControlTransactionFactory = Callable[[], ContextManager[SubmitControlTransaction]]


@runtime_checkable
class OperatorRecoveryApplicationPort(Protocol):
    def execute_recovery(self, request: OperatorRecoveryRequest) -> TransitionDisposition:
        """Apply or replay one authorized operator recovery command."""


@dataclass(frozen=True, slots=True)
class SubmitRuntimeDependencies:
    artifact_store: ArtifactStorePort
    publication: SubmitImportPublicationPort
    repository_write: RepositoryWritePort
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


def decode_submit_payload(payload_object: dict[str, object]) -> SubmitJobPayload:
    _reject_unknown_top_level_keys(payload_object)
    document_type = _require_non_empty_str(payload_object, "document_type")
    if document_type != "submit_job_payload":
        raise PayloadDecodeError("document_type must be submit_job_payload", code="PAYLOAD_SHAPE_INVALID")
    contract_version = _require_non_empty_str(payload_object, "contract_version")
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
    snapshot_table_set_digest = _require_non_empty_str(payload_object, "snapshot_table_set_digest")
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
        snapshot_table_set_digest=snapshot_table_set_digest,
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
        def __init__(self, wrapped: ContextManager[SubmitControlTransaction]) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> SubmitControlTransaction:
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

    def factory() -> ContextManager[SubmitControlTransaction]:
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
        repository_write=deps.repository_write,
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
                checkpoint_ref=step.checkpoint_ref,
            )
        else:
            build_input = _build_prepare_import_build_input(
                payload=payload,
                attempt=attempt,
                operation=operation,
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
                _pinned_checkpoint_builder(
                    checkpoint_ref=sent_checkpoint_ref,
                    extra_refs=(
                        request_state.prepare_checkpoint_ref,
                        request_state.request_artifact_ref,
                    ),
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
        lease_session.refresh_control()
        if step.checkpoint_ref is None and control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        payload = _load_submit_payload(operation, deps.artifact_store)
        attempt = _load_submit_attempt(deps, payload.submit_attempt_id)
        _assert_payload_matches_attempt(payload, attempt)
        if attempt.state is not SubmitAttemptState.EFFECT_PENDING:
            if attempt.state is SubmitAttemptState.FINALIZED and operation.status is OperationStatus.SUCCEEDED:
                return ExecutorAcknowledgment.PUBLISHED
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

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(deps.artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(await_definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the await_import_result JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
        else:
            reconcile_started_at = _iso_utc_timestamp(datetime.now(UTC))
            envelope = envelope_for_step(
                key=await_definition.key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state={
                    _JOB_STATE_SCHEMA_VERSION: AWAIT_IMPORT_RESULT_CHECKPOINT_SCHEMA,
                    _JOB_STATE_SUBMIT_CHECKPOINT_REF: artifact_ref_to_dict(submit_step.checkpoint_ref),
                    JOB_STATE_OPERATION_IDENTITY: submit_state.repository_operation_id,
                    JOB_STATE_RECONCILE_STARTED_AT: reconcile_started_at,
                },
            )
            checkpoint_ref = prepare_step_checkpoint(deps.artifact_store, envelope)
            lease_session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))

        try:
            repository_operation = deps.repository_write.wait_operation(
                repository_id=payload.repository_id,
                operation_id=submit_state.repository_operation_id,
            )
        except (TimeoutError, RepositoryWriteTimeoutError):
            lease_session.publish_operation(
                _make_manual_recovery_terminal_builder(
                    submit_state.repository_operation_id,
                    diagnostic=OperationDiagnostic(
                        code=DIAGNOSTIC_RECONCILE_TIMEOUT.upper(),
                        message="repository import reconcile session budget exhausted",
                    ),
                )
            )
            return ExecutorAcknowledgment.PUBLISHED

        if repository_operation.status in {
            RepositoryOperationStatus.QUEUED,
            RepositoryOperationStatus.RUNNING,
        }:
            if step.checkpoint_ref is None:
                raise SubmitJobError("await_import_result checkpoint is missing for reconcile handoff")
            checkpoint_generation = lease_session.publish_checkpoint(
                make_checkpoint_step_builder(checkpoint_ref=step.checkpoint_ref)
            )
            return lease_session.acknowledge_safe_handoff(checkpoint_generation)

        if repository_operation.status is RepositoryOperationStatus.SUCCEEDED:
            facts = _matching_finalize_facts(
                payload=payload,
                prepare_checkpoint=prepare_checkpoint,
                repository_operation=repository_operation,
                repository_operation_id=submit_state.repository_operation_id,
            )
            with deps.control_transaction_factory() as unit_of_work:
                fresh_attempt = unit_of_work.submission.get_submit_attempt(payload.submit_attempt_id)
                if fresh_attempt is None:
                    raise SubmitJobError("submit attempt is missing")
                fresh_operation = unit_of_work.operations.get_operation(operation.operation_id)
                steps, _cursor = unit_of_work.operations.list_steps(operation.operation_id)
                await_step = next(item for item in steps if item.step_name == SUBMIT_STEP_AWAIT)
                finalize_submit_transaction(
                    request=FinalizeSubmitTransactionRequest(
                        submit_attempt_id=payload.submit_attempt_id,
                        facts=facts,
                        submission_id=deps.submission_id_factory(),
                        created_at=unit_of_work.transaction_now,
                        expected_attempt_version=fresh_attempt.optimistic_version,
                        expected_await_step_version=await_step.optimistic_version,
                        expected_operation_version=fresh_operation.optimistic_version,
                        worker_id=step.worker_id,
                        lease_token=step.lease_token,
                    ),
                    unit_of_work=unit_of_work,
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
            abort_submit_transaction(
                request=AbortSubmitTransactionRequest(
                    submit_attempt_id=payload.submit_attempt_id,
                    proof=proof,
                    aborted_at=datetime.now(UTC),
                    worker_id=step.worker_id,
                    lease_token=step.lease_token,
                ),
                evidence=_StaticAbortEvidence(repository_operation),
                unit_of_work_factory=_read_write_factory(deps.control_transaction_factory),
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
        request_bytes = _build_import_request_bytes(payload, repository_artifact_ref)
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
            _pinned_checkpoint_builder(
                checkpoint_ref=checkpoint_ref,
                extra_refs=(prepare_checkpoint_ref, request_ref),
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
    request_bytes = _build_import_request_bytes(payload, repository_artifact_ref)
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
        _pinned_checkpoint_builder(
            checkpoint_ref=checkpoint_ref,
            extra_refs=(prepare_checkpoint_ref, request_ref),
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
    payload = _load_submit_payload(operation, deps.artifact_store)
    attempt = _load_submit_attempt(deps, payload.submit_attempt_id)
    return (
        attempt.state is SubmitAttemptState.EFFECT_PENDING
        and attempt.repository_artifact_ref is not None
    )


def _map_handler_failure_to_recovery_outcome(exc: BaseException) -> RecoveryOutcome:
    if isinstance(exc, (RepositoryWriteTimeoutError, TimeoutError)):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_RECONCILE_TIMEOUT,
            reason=str(exc),
        )
    if isinstance(exc, httpx.TransportError):
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
    return RecoveryOutcome(
        disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
        diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
        reason=str(exc),
    )


@dataclass(frozen=True, slots=True)
class _StaticAbortEvidence:
    operation: VersionedOperation

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
        return _map_handler_failure_to_recovery_outcome(exc)

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


def _build_prepare_import_build_input(
    *,
    payload: SubmitJobPayload,
    attempt: SubmitAttempt,
    operation: OperationRecord,
) -> PrepareImportBuildInput:
    ruleset = migrated_table_ruleset_snapshot()
    if ruleset.ruleset_digest is None:
        raise SubmitImportBuilderError("ruleset digest is required")
    snapshot_tables = _snapshot_bindings_from_operation(operation, attempt)
    return PrepareImportBuildInput(
        submit_attempt_id=payload.submit_attempt_id,
        builder_mutation_policy=payload.builder_mutation_policy,
        input_closure_digest=payload.snapshot_table_set_digest,
        source_artifact_digest=attempt.snapshot_digest,
        repository_base_digest=attempt.source_digest,
        storage_projection_version=payload.storage_projection_version,
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
        checkpoint_ref=checkpoint_ref,
    )
    lease_session.publish_checkpoint(
        _pinned_checkpoint_builder(
            checkpoint_ref=checkpoint_ref,
            extra_refs=(
                store_ref_from_backend_artifact_ref(checkpoint.canonicalization_manifest_ref),
                store_ref_from_backend_artifact_ref(checkpoint.backend_import_artifact_ref),
            ),
            intent="prepare-import-checkpoint",
        )
    )
    return checkpoint_ref


def _pin_prepare_refs(
    *,
    deps: SubmitRuntimeDependencies,
    attempt: SubmitAttempt,
    operation: OperationRecord,
    checkpoint: PrepareImportCheckpoint,
    checkpoint_ref: ArtifactRef,
) -> None:
    snapshot_refs = tuple(
        ref
        for ref in operation.artifact_refs
        if ref.artifact_id in frozenset(attempt.snapshot_table_artifact_refs)
    )
    with deps.control_transaction_factory() as unit_of_work:
        pin_prepare_import_artifacts(
            unit_of_work,
            submit_attempt_id=attempt.submit_attempt_id,
            manifest_ref=checkpoint.canonicalization_manifest_ref,
            package_ref=checkpoint.backend_import_artifact_ref,
            existing_snapshot_refs=snapshot_refs,
        )
        unit_of_work.set_artifact_protection(
            (checkpoint_ref,),
            owner_kind="submit-checkpoint",
            owner_id=attempt.submit_attempt_id,
            intent="prepare-import-checkpoint",
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
        _JOB_STATE_INPUT_CLOSURE_DIGEST: checkpoint.input_closure_digest,
        _JOB_STATE_BUILDER_POLICY: checkpoint.builder_mutation_policy.value,
    }


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
    attempt_id = job_state.get(_JOB_STATE_ATTEMPT_ID)
    if type(attempt_id) is not str or attempt_id != expected_attempt_id:
        raise CheckpointDecodeError(
            "prepare checkpoint attempt_id does not match payload",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
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
        input_closure_digest=_require_non_empty_str_value(
            job_state.get(_JOB_STATE_INPUT_CLOSURE_DIGEST),
            label="input_closure_digest",
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
    expected_payload: SubmitJobPayload,
    prepare_checkpoint_ref: ArtifactRef,
    checkpoint_ref: ArtifactRef,
) -> _SubmitCheckpointState:
    if job_state.get(_JOB_STATE_SCHEMA_VERSION) != SUBMIT_IMPORT_CHECKPOINT_SCHEMA:
        raise CheckpointDecodeError(
            "submit checkpoint schema_version is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
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
    request_artifact_ref = artifact_ref_from_dict(
        _require_artifact_ref_dict(job_state.get(_JOB_STATE_REQUEST_ARTIFACT_REF), label="request_artifact_ref"),
    )
    request_bytes = store.locate(request_artifact_ref)
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
    request_sent = job_state.get(JOB_STATE_REQUEST_SENT) is True
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


def _matching_finalize_facts(
    *,
    payload: SubmitJobPayload,
    prepare_checkpoint: PrepareImportCheckpoint,
    repository_operation: VersionedOperation,
    repository_operation_id: str,
) -> MatchingFinalizeFacts:
    if repository_operation.result is None:
        raise SubmitJobError("repository SUCCEEDED operation is missing result")
    result = repository_operation.result
    manifest_digest = str(result.canonicalization_manifest_digest)
    if manifest_digest != prepare_checkpoint.canonicalization_manifest_digest:
        raise SubmitJobError("repository manifest digest does not match prepare checkpoint")
    return MatchingFinalizeFacts(
        repository_id=payload.repository_id,
        repository_operation_id=repository_operation_id,
        repository_commit_id=str(result.commit_id),
        repository_expected_parent_commit_id=payload.repository_expected_commit_id,
        repository_artifact_id=str(result.artifact_id),
        repository_import_artifact_raw_sha256=prepare_checkpoint.package_raw_sha256,
        canonicalization_manifest_ref=prepare_checkpoint.canonicalization_manifest_ref.artifact_id,
        canonicalization_manifest_digest=manifest_digest,
        completed_verification_policy=SubmitVerificationPolicy.STRUCTURAL,
        completed_unknown_type_policy=SubmitUnknownTypePolicy.REJECT,
        target_ref=SubmitTargetRef.MAIN,
    )


def _wire_repository_raw_sha256(value: str) -> str:
    return value.removeprefix("sha256:")


def _build_import_request_bytes(
    payload: SubmitJobPayload,
    repository_artifact_ref: RepositoryArtifactRef,
) -> bytes:
    request = SubmitVersionedImportRequest(
        repository_id=UUID(payload.repository_id),
        artifact_ref=WireRepositoryArtifactRef(
            artifact_id=UUID(repository_artifact_ref.artifact_id),
            media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
            size_bytes=repository_artifact_ref.size_bytes,
            raw_sha256=_wire_repository_raw_sha256(repository_artifact_ref.raw_sha256),
        ),
        target_ref="main",
        expected_commit_id=payload.repository_expected_commit_id,
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    if str(request.repository_id) != payload.repository_id:
        raise SubmitJobError("import request repository_id must match payload repository_id")
    if str(request.artifact_ref.media_type) != REPOSITORY_IMPORT_MEDIA_TYPE:
        raise SubmitJobError("import request artifact media type is invalid")
    return canonicalize_json_value(request.model_dump(mode="json"))


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


def _snapshot_bindings_from_operation(
    operation: OperationRecord,
    attempt: SubmitAttempt,
) -> tuple[SnapshotTableBinding, ...]:
    required_ids = frozenset(attempt.snapshot_table_artifact_refs)
    bindings: list[SnapshotTableBinding] = []
    for ref in operation.artifact_refs:
        if ref.artifact_id not in required_ids:
            continue
        bindings.append(
            SnapshotTableBinding(
                artifact_id=ref.artifact_id,
                media_type=ref.media_type,
                size_bytes=ref.size_bytes,
                raw_sha256=ref.raw_sha256.value,
            )
        )
    if frozenset(item.artifact_id for item in bindings) != required_ids:
        raise SubmitImportBuilderError("operation artifact refs do not cover snapshot table bindings")
    return tuple(sorted(bindings, key=lambda item: item.artifact_id))


def _submit_attempt_id_from_operation(operation: OperationRecord) -> str:
    for business_ref in operation.business_refs:
        if business_ref.kind == "submit_attempt":
            return business_ref.value
    raise ValueError("submit operation is missing submit_attempt business ref")


def _read_write_factory(
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


def _pinned_checkpoint_builder(
    *,
    checkpoint_ref: ArtifactRef,
    extra_refs: tuple[ArtifactRef, ...],
    intent: str,
) -> Callable[[OperationRecord, StepRecord, datetime], StepRecord]:
    inner = make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)

    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> StepRecord:
        candidate = inner(operation, step, transaction_now)
        transaction = _active_submit_transaction.get()
        if transaction is None:
            raise SubmitJobError("submit checkpoint transaction is not bound")
        refs = (checkpoint_ref, *extra_refs)
        transaction.set_artifact_protection(
            refs,
            owner_kind="submit-checkpoint",
            owner_id=step.step_id,
            intent=intent,
        )
        return candidate

    return builder


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


def _successor_step_id(operation_id: str, step_name: str) -> str:
    suffix = {
        SUBMIT_STEP_PREPARE: "1",
        SUBMIT_STEP_SUBMIT: "2",
        SUBMIT_STEP_AWAIT: "3",
    }[step_name]
    return f"{operation_id}-step-{suffix}"


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
        "snapshot_table_set_digest",
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
