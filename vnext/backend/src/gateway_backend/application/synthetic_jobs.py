"""Application-owned synthetic jobs for R4 recovery and publication evidence."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    make_checkpoint_step_builder,
    make_terminal_ready_closure_builder,
    prepare_ready_closure,
    prepare_step_checkpoint,
)
from gateway_backend.application.external_effect_stub import (
    DeterministicExternalEffectStub,
    ExternalEffectStub,
    StubOutcome,
    build_request_bytes,
    build_response_bytes,
    compute_operation_identity,
    decode_external_effect_stub_request,
    decode_stub_outcome,
    request_artifact_id,
    response_artifact_id,
)
from gateway_backend.application.job_definitions import (
    JobDefinition,
    NormalPublicationCapability,
)
from gateway_backend.application.payloads import CheckpointDecodeError, PayloadDecodeError, PayloadDecoder, load_job_payload_bytes
from gateway_backend.artifacts.store import ArtifactStorePort, ManifestVerificationError, put_with_built_ref
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.operations.contracts import (
    JobStepKey,
    OperationDiagnostic,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
)
from gateway_backend.operations.worker import (
    CheckpointGeneration,
    ClaimedExecutor,
    ExecutionControl,
    ExecutorAcknowledgment,
    LeaseSession,
)

PURE_COMPUTE_JOB_KIND = "synthetic.pure-compute"
PURE_COMPUTE_STEP_NAME = "compute"
PURE_COMPUTE_PAYLOAD_VERSION = "backend-vnext/synthetic/pure-compute/v1"
PURE_COMPUTE_DECODER_IDENTITY = "backend-vnext/synthetic/pure-compute/decoder/v1"
PURE_COMPUTE_HANDLER_IDENTITY = "backend-vnext/synthetic/pure-compute/handler/v1"

PURE_COMPUTE_OUTPUT_DOCUMENT_TYPE = "pure-compute-output"
PURE_COMPUTE_OUTPUT_CONTRACT_VERSION = "backend-vnext/synthetic/pure-compute/output/v1"
_JCS_MEDIA_TYPE = "application/jcs"
_MAX_SEED_BYTES = 256

_JOB_STATE_OUTPUT_ARTIFACT_ID = "output_artifact_id"
_JOB_STATE_SEED = "seed"

EXTERNAL_EFFECT_STUB_JOB_KIND = "synthetic.external-effect-stub"
EXTERNAL_EFFECT_STUB_STEP_NAME = "request"
EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION = "backend-vnext/synthetic/stub/v1"
EXTERNAL_EFFECT_STUB_DECODER_IDENTITY = "backend-vnext/synthetic/stub/decoder/v1"
EXTERNAL_EFFECT_STUB_HANDLER_IDENTITY = "backend-vnext/synthetic/stub/handler/v1"

_JOB_STATE_IDEMPOTENCY_KEY = "idempotency_key"
_JOB_STATE_OPERATION_IDENTITY = "operation_identity"
_JOB_STATE_REQUEST_ARTIFACT_ID = "request_artifact_id"
_JOB_STATE_REQUEST_SENT = "request_sent"


@dataclass(frozen=True, slots=True)
class PureComputePayload:
    """Bounded deterministic input for the pure-compute synthetic job."""

    seed: str


def pure_compute_job_key() -> JobStepKey:
    return JobStepKey(job_kind=PURE_COMPUTE_JOB_KIND, step_name=PURE_COMPUTE_STEP_NAME)


def pure_compute_job_definition() -> JobDefinition:
    return JobDefinition(
        key=pure_compute_job_key(),
        supported_payload_versions=frozenset({PURE_COMPUTE_PAYLOAD_VERSION}),
        decoder_identity=PURE_COMPUTE_DECODER_IDENTITY,
        handler_identity=PURE_COMPUTE_HANDLER_IDENTITY,
        publication_capability=NormalPublicationCapability.TERMINAL,
    )


def decode_pure_compute_payload(payload_object: dict[str, object]) -> PureComputePayload:
    seed = payload_object.get("seed")
    if type(seed) is not str or not seed:
        raise ValueError("seed must be a non-empty string")
    seed_bytes = seed.encode("utf-8")
    if len(seed_bytes) > _MAX_SEED_BYTES:
        raise ValueError("seed exceeds bounded payload size")
    return PureComputePayload(seed=seed)


def pure_compute_payload_decoders() -> Mapping[str, PayloadDecoder]:
    return {PURE_COMPUTE_DECODER_IDENTITY: decode_pure_compute_payload}


def compute_pure_compute_output_bytes(seed: str) -> bytes:
    """Return canonical JCS output bytes derived only from the bounded seed."""

    document = {
        "contract_version": PURE_COMPUTE_OUTPUT_CONTRACT_VERSION,
        "document_type": PURE_COMPUTE_OUTPUT_DOCUMENT_TYPE,
        "result_digest": raw_blob_digest(seed.encode("utf-8")).value,
        "seed": seed,
    }
    return canonicalize_json_value(document)


def build_pure_compute_handler(artifact_store: ArtifactStorePort) -> ClaimedExecutor:
    """Build one terminal pure-compute handler bound to an injected artifact store."""

    if not hasattr(artifact_store, "put") or not hasattr(artifact_store, "locate"):
        raise ValueError("artifact_store must implement ArtifactStorePort")

    definition = pure_compute_job_definition()

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

        payload = _load_pure_compute_payload(operation, artifact_store)
        key = pure_compute_job_key()
        output_ref: ArtifactRef

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the pure-compute JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            output_ref = _output_ref_from_job_state(
                artifact_store,
                envelope.job_state,
                expected_seed=payload.seed,
            )
        else:
            output_bytes = compute_pure_compute_output_bytes(payload.seed)
            output_ref = _put_pure_compute_output(artifact_store, output_bytes)
            envelope = envelope_for_step(
                key=key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state=_job_state_for_output(payload.seed, output_ref.artifact_id),
            )
            checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
            lease_session.publish_checkpoint(
                make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)
            )

        lease_session.refresh_control()
        if control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return ExecutorAcknowledgment.PUBLISHED

        closure_ref = prepare_ready_closure(
            artifact_store,
            (output_ref,),
            operation.job_contract_version,
        )
        lease_session.publish_operation(
            make_terminal_ready_closure_builder(closure_ref=closure_ref)
        )
        return ExecutorAcknowledgment.PUBLISHED

    return execute


def pure_compute_composition_bundle(
    artifact_store: ArtifactStorePort,
) -> tuple[tuple[JobDefinition, ...], Mapping[str, ClaimedExecutor], Mapping[str, PayloadDecoder]]:
    """Return definitions, handlers, and decoders for worker-runtime injection."""

    return (
        (pure_compute_job_definition(),),
        {PURE_COMPUTE_HANDLER_IDENTITY: build_pure_compute_handler(artifact_store)},
        dict(pure_compute_payload_decoders()),
    )


@dataclass(frozen=True, slots=True)
class ExternalEffectStubPayload:
    """Bounded deterministic input for the external-effect stub synthetic job."""

    idempotency_key: str
    request_body: str
    stub_outcome: StubOutcome


def external_effect_stub_job_key() -> JobStepKey:
    return JobStepKey(
        job_kind=EXTERNAL_EFFECT_STUB_JOB_KIND,
        step_name=EXTERNAL_EFFECT_STUB_STEP_NAME,
    )


def external_effect_stub_job_definition() -> JobDefinition:
    return JobDefinition(
        key=external_effect_stub_job_key(),
        supported_payload_versions=frozenset({EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION}),
        decoder_identity=EXTERNAL_EFFECT_STUB_DECODER_IDENTITY,
        handler_identity=EXTERNAL_EFFECT_STUB_HANDLER_IDENTITY,
        publication_capability=NormalPublicationCapability.TERMINAL,
    )


def decode_external_effect_stub_payload(payload_object: dict[str, object]) -> ExternalEffectStubPayload:
    request = decode_external_effect_stub_request(payload_object)
    stub_outcome = decode_stub_outcome(payload_object.get("stub_outcome"))
    return ExternalEffectStubPayload(
        idempotency_key=request.idempotency_key,
        request_body=request.request_body,
        stub_outcome=stub_outcome,
    )


def external_effect_stub_payload_decoders() -> Mapping[str, PayloadDecoder]:
    return {EXTERNAL_EFFECT_STUB_DECODER_IDENTITY: decode_external_effect_stub_payload}


def build_external_effect_stub_handler(
    artifact_store: ArtifactStorePort,
    *,
    external_stub: ExternalEffectStub | None = None,
) -> ClaimedExecutor:
    """Build one external-effect stub handler bound to an injected artifact store."""

    if not hasattr(artifact_store, "put") or not hasattr(artifact_store, "locate"):
        raise ValueError("artifact_store must implement ArtifactStorePort")

    definition = external_effect_stub_job_definition()

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

        payload = _load_external_effect_stub_payload(operation, artifact_store)
        key = external_effect_stub_job_key()
        request_state: _ExternalEffectRequestState
        last_checkpoint_generation: CheckpointGeneration | None = None

        if step.checkpoint_ref is not None:
            envelope = load_checkpoint_envelope(artifact_store, step.checkpoint_ref)
            if not definition_matches_checkpoint(definition, envelope):
                raise CheckpointDecodeError(
                    "checkpoint envelope does not match the external-effect stub JobDefinition",
                    code="CHECKPOINT_IDENTITY_MISMATCH",
                )
            request_state = _request_state_from_job_state(
                artifact_store,
                envelope.job_state,
                expected_payload=payload,
                checkpoint_ref=step.checkpoint_ref,
            )
        else:
            request_bytes = build_request_bytes(payload.idempotency_key, payload.request_body)
            request_ref = put_with_built_ref(
                artifact_store,
                request_bytes,
                artifact_id=request_artifact_id(request_bytes),
                media_type=_JCS_MEDIA_TYPE,
            )
            stub = external_stub or DeterministicExternalEffectStub(request_bytes=request_bytes)
            operation_identity = stub.submit(payload.idempotency_key, request_ref)
            envelope = envelope_for_step(
                key=key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state=_job_state_for_request(
                    idempotency_key=payload.idempotency_key,
                    request_artifact_id=request_ref.artifact_id,
                    operation_identity=operation_identity,
                ),
            )
            checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
            last_checkpoint_generation = lease_session.publish_checkpoint(
                make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)
            )
            request_state = _ExternalEffectRequestState(
                idempotency_key=payload.idempotency_key,
                request_artifact_id=request_ref.artifact_id,
                operation_identity=operation_identity,
                checkpoint_ref=checkpoint_ref,
            )

        if payload.stub_outcome is StubOutcome.ACCEPTED:
            if last_checkpoint_generation is None:
                last_checkpoint_generation = lease_session.publish_checkpoint(
                    make_checkpoint_step_builder(checkpoint_ref=request_state.checkpoint_ref)
                )
            return lease_session.acknowledge_safe_handoff(last_checkpoint_generation)

        if payload.stub_outcome is StubOutcome.UNKNOWN:
            lease_session.publish_operation(
                _make_manual_recovery_terminal_builder(request_state.operation_identity)
            )
            return ExecutorAcknowledgment.PUBLISHED

        response_bytes = build_response_bytes(
            request_state.operation_identity,
            request_state.idempotency_key,
            outcome=StubOutcome.CONFIRMED,
        )
        response_ref = put_with_built_ref(
            artifact_store,
            response_bytes,
            artifact_id=response_artifact_id(response_bytes),
            media_type=_JCS_MEDIA_TYPE,
        )
        closure_ref = prepare_ready_closure(
            artifact_store,
            (response_ref,),
            operation.job_contract_version,
        )
        lease_session.publish_operation(
            _make_confirmed_terminal_builder(
                closure_ref=closure_ref,
                repository_operation_id=request_state.operation_identity,
            )
        )
        return ExecutorAcknowledgment.PUBLISHED

    return execute


def external_effect_stub_composition_bundle(
    artifact_store: ArtifactStorePort,
    *,
    external_stub: ExternalEffectStub | None = None,
) -> tuple[tuple[JobDefinition, ...], Mapping[str, ClaimedExecutor], Mapping[str, PayloadDecoder]]:
    """Return definitions, handlers, and decoders for worker-runtime injection."""

    return (
        (external_effect_stub_job_definition(),),
        {
            EXTERNAL_EFFECT_STUB_HANDLER_IDENTITY: build_external_effect_stub_handler(
                artifact_store,
                external_stub=external_stub,
            )
        },
        dict(external_effect_stub_payload_decoders()),
    )


@dataclass(frozen=True, slots=True)
class _ExternalEffectRequestState:
    idempotency_key: str
    request_artifact_id: str
    operation_identity: str
    checkpoint_ref: ArtifactRef


def _load_external_effect_stub_payload(
    operation: OperationRecord,
    store: ArtifactStorePort,
) -> ExternalEffectStubPayload:
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
    return decode_external_effect_stub_payload(cast(dict[str, object], payload_object))


def _job_state_for_request(
    *,
    idempotency_key: str,
    request_artifact_id: str,
    operation_identity: str,
) -> dict[str, object]:
    return {
        _JOB_STATE_IDEMPOTENCY_KEY: idempotency_key,
        _JOB_STATE_REQUEST_ARTIFACT_ID: request_artifact_id,
        _JOB_STATE_OPERATION_IDENTITY: operation_identity,
        _JOB_STATE_REQUEST_SENT: True,
    }


def _request_state_from_job_state(
    store: ArtifactStorePort,
    job_state: Mapping[str, object],
    *,
    expected_payload: ExternalEffectStubPayload,
    checkpoint_ref: ArtifactRef,
) -> _ExternalEffectRequestState:
    if not isinstance(job_state, Mapping):
        raise CheckpointDecodeError("job_state must be a mapping", code="CHECKPOINT_SHAPE_INVALID")
    idempotency_key = job_state.get(_JOB_STATE_IDEMPOTENCY_KEY)
    request_artifact_id_value = job_state.get(_JOB_STATE_REQUEST_ARTIFACT_ID)
    operation_identity = job_state.get(_JOB_STATE_OPERATION_IDENTITY)
    request_sent = job_state.get(_JOB_STATE_REQUEST_SENT)
    if type(idempotency_key) is not str or idempotency_key != expected_payload.idempotency_key:
        raise CheckpointDecodeError(
            "checkpoint job_state idempotency_key does not match payload",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if type(request_artifact_id_value) is not str or not request_artifact_id_value:
        raise CheckpointDecodeError(
            "checkpoint job_state request_artifact_id is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if type(operation_identity) is not str or not operation_identity:
        raise CheckpointDecodeError(
            "checkpoint job_state operation_identity is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if request_sent is not True:
        raise CheckpointDecodeError(
            "checkpoint job_state request_sent must be true",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    request_bytes = build_request_bytes(expected_payload.idempotency_key, expected_payload.request_body)
    expected_request_id = request_artifact_id(request_bytes)
    if request_artifact_id_value != expected_request_id:
        raise CheckpointDecodeError(
            "checkpoint job_state request_artifact_id does not match payload semantics",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    expected_identity = compute_operation_identity(
        expected_payload.idempotency_key,
        request_bytes,
    )
    if operation_identity != expected_identity:
        raise CheckpointDecodeError(
            "checkpoint job_state operation_identity does not match payload semantics",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    request_ref = ArtifactRef(
        artifact_id=request_artifact_id_value,
        media_type=_JCS_MEDIA_TYPE,
        size_bytes=len(request_bytes),
        raw_sha256=raw_blob_digest(request_bytes),
    )
    try:
        store.locate(request_ref)
    except ManifestVerificationError as exc:
        raise CheckpointDecodeError(str(exc), code="CHECKPOINT_REF_UNREADABLE") from exc
    return _ExternalEffectRequestState(
        idempotency_key=idempotency_key,
        request_artifact_id=request_artifact_id_value,
        operation_identity=operation_identity,
        checkpoint_ref=checkpoint_ref,
    )


def _make_confirmed_terminal_builder(
    *,
    closure_ref: ArtifactRef,
    repository_operation_id: str,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    base_builder = make_terminal_ready_closure_builder(closure_ref=closure_ref)

    def builder(
        operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> tuple[StepRecord, OperationRecord]:
        terminal_step, terminal_operation = base_builder(operation, step, transaction_now)
        return terminal_step, dataclasses.replace(
            terminal_operation,
            repository_operation_id=repository_operation_id,
        )

    return builder


_UNKNOWN_OUTCOME_DIAGNOSTIC = OperationDiagnostic(
    code="EXTERNAL_EFFECT_UNKNOWN_OUTCOME",
    message="external effect outcome is unknown and requires R5 reconciliation",
)


def _make_manual_recovery_terminal_builder(
    repository_operation_id: str,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    if type(repository_operation_id) is not str or not repository_operation_id:
        raise ValueError("repository_operation_id must be a non-empty string")

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
            diagnostic=_UNKNOWN_OUTCOME_DIAGNOSTIC,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=OperationStatus.MANUAL_RECOVERY_REQUIRED,
            repository_operation_id=repository_operation_id,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
            diagnostic=_UNKNOWN_OUTCOME_DIAGNOSTIC,
        )
        return terminal_step, terminal_operation

    return builder


def _load_pure_compute_payload(
    operation: OperationRecord,
    store: ArtifactStorePort,
) -> PureComputePayload:
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
    return decode_pure_compute_payload(cast(dict[str, object], payload_object))


def _put_pure_compute_output(store: ArtifactStorePort, output_bytes: bytes) -> ArtifactRef:
    artifact_id = _output_artifact_id(output_bytes)
    return put_with_built_ref(
        store,
        output_bytes,
        artifact_id=artifact_id,
        media_type=_JCS_MEDIA_TYPE,
    )


def _output_artifact_id(output_bytes: bytes) -> str:
    return f"pure-compute-output:{raw_blob_digest(output_bytes).value}"


def _job_state_for_output(seed: str, output_artifact_id: str) -> dict[str, object]:
    return {
        _JOB_STATE_OUTPUT_ARTIFACT_ID: output_artifact_id,
        _JOB_STATE_SEED: seed,
    }


def _checkpoint_generation(step: StepRecord) -> int:
    attempt_count = step.attempt_count
    if type(attempt_count) is not int or isinstance(attempt_count, bool) or attempt_count < 1:
        raise ValueError("attempt_count must be a positive int for checkpoint generation")
    return attempt_count


def _output_ref_from_job_state(
    store: ArtifactStorePort,
    job_state: Mapping[str, object],
    *,
    expected_seed: str,
) -> ArtifactRef:
    if not isinstance(job_state, Mapping):
        raise CheckpointDecodeError("job_state must be a mapping", code="CHECKPOINT_SHAPE_INVALID")
    seed = job_state.get(_JOB_STATE_SEED)
    output_artifact_id = job_state.get(_JOB_STATE_OUTPUT_ARTIFACT_ID)
    if type(seed) is not str or seed != expected_seed:
        raise CheckpointDecodeError(
            "checkpoint job_state seed does not match payload",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    if type(output_artifact_id) is not str or not output_artifact_id:
        raise CheckpointDecodeError(
            "checkpoint job_state output_artifact_id is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    output_bytes = compute_pure_compute_output_bytes(expected_seed)
    expected_id = _output_artifact_id(output_bytes)
    if output_artifact_id != expected_id:
        raise CheckpointDecodeError(
            "checkpoint job_state output_artifact_id does not match payload semantics",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    output_ref = put_with_built_ref(
        store,
        output_bytes,
        artifact_id=output_artifact_id,
        media_type=_JCS_MEDIA_TYPE,
    )
    store.locate(output_ref)
    return output_ref


def _make_cancelled_terminal_builder() -> Callable[
    [OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]
]:
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


__all__ = [
    "EXTERNAL_EFFECT_STUB_DECODER_IDENTITY",
    "EXTERNAL_EFFECT_STUB_HANDLER_IDENTITY",
    "EXTERNAL_EFFECT_STUB_JOB_KIND",
    "EXTERNAL_EFFECT_STUB_PAYLOAD_VERSION",
    "EXTERNAL_EFFECT_STUB_STEP_NAME",
    "ExternalEffectStubPayload",
    "PURE_COMPUTE_DECODER_IDENTITY",
    "PURE_COMPUTE_HANDLER_IDENTITY",
    "PURE_COMPUTE_JOB_KIND",
    "PURE_COMPUTE_OUTPUT_CONTRACT_VERSION",
    "PURE_COMPUTE_OUTPUT_DOCUMENT_TYPE",
    "PURE_COMPUTE_PAYLOAD_VERSION",
    "PURE_COMPUTE_STEP_NAME",
    "PureComputePayload",
    "build_external_effect_stub_handler",
    "build_pure_compute_handler",
    "compute_pure_compute_output_bytes",
    "decode_external_effect_stub_payload",
    "decode_pure_compute_payload",
    "external_effect_stub_composition_bundle",
    "external_effect_stub_job_definition",
    "external_effect_stub_job_key",
    "external_effect_stub_payload_decoders",
    "pure_compute_composition_bundle",
    "pure_compute_job_definition",
    "pure_compute_job_key",
    "pure_compute_payload_decoders",
]
