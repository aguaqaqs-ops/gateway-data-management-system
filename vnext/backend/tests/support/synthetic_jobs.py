"""Application-owned synthetic jobs for R4 recovery and publication evidence."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
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
from tests.support.external_effect_stub import (
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
from gateway_backend.application.recovery import (
    DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    DIAGNOSTIC_RECONCILE_TIMEOUT,
    ExternalEffectRequestIdentity,
    RecoveryOutcome,
    RecoveryOutcomeDisposition,
    RecoveryPort,
    compute_request_fingerprint,
    validate_external_effect_identity,
)
from gateway_backend.application.recovery import RecoveryCapability
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
from gateway_backend.operations.recovery import (
    reconcile_budget_exhausted,
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
_JOB_STATE_REQUEST_FINGERPRINT = "request_fingerprint"
_JOB_STATE_REQUEST_SENT = "request_sent"
_JOB_STATE_RECONCILE_STARTED_AT = "reconcile_started_at"


def _parse_reconcile_started_at(job_state: Mapping[str, object]) -> datetime:
    value = job_state.get(_JOB_STATE_RECONCILE_STARTED_AT)
    if type(value) is not str or not value:
        raise ValueError("reconcile_started_at must be a non-empty string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reconcile_started_at is malformed") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
        or parsed.utcoffset().total_seconds() != 0
    ):
        raise ValueError("reconcile_started_at must be timezone-aware UTC")
    return parsed


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
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
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


def build_pure_compute_recovery_port(artifact_store: ArtifactStorePort) -> RecoveryPort:
    """Build a RecoveryPort that resumes terminal publication from a durable checkpoint."""

    if not hasattr(artifact_store, "put") or not hasattr(artifact_store, "locate"):
        raise ValueError("artifact_store must implement ArtifactStorePort")

    definition = pure_compute_job_definition()

    class _PureComputeRecoveryPort:
        def recover(
            self,
            operation: OperationRecord,
            step: StepRecord,
            control: ExecutionControl,
            lease_session: LeaseSession,
        ) -> RecoveryOutcome:
            return _recover_pure_compute(operation, step, control, lease_session)

    def _recover_pure_compute(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> RecoveryOutcome:
        if (
            operation.status is OperationStatus.SUCCEEDED
            and step.status is StepStatus.SUCCEEDED
            and operation.ready_closure_ref is not None
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

        if step.checkpoint_ref is None:
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason="pure compute recovery requires a durable checkpoint",
            )

        try:
            payload = _load_pure_compute_payload(operation, artifact_store)
            envelope = load_checkpoint_envelope(artifact_store, step.checkpoint_ref)
        except (CheckpointDecodeError, PayloadDecodeError) as exc:
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason=str(exc),
            )

        if not definition_matches_checkpoint(definition, envelope):
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason="checkpoint envelope does not match the pure-compute JobDefinition",
            )

        try:
            output_ref = _output_ref_from_job_state(
                artifact_store,
                envelope.job_state,
                expected_seed=payload.seed,
            )
        except CheckpointDecodeError as exc:
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason=str(exc),
            )

        closure_ref = prepare_ready_closure(
            artifact_store,
            (output_ref,),
            operation.job_contract_version,
        )
        lease_session.publish_operation(
            make_terminal_ready_closure_builder(closure_ref=closure_ref)
        )
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.PUBLISHED,
            diagnostic_code=None,
            reason=None,
        )

    return _PureComputeRecoveryPort()


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
        recovery_capability=RecoveryCapability.EXTERNAL_EFFECT,
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


class PollingExternalEffectStub(ExternalEffectStub):
    """Submit wrapper that polls only the original operation identity during reconcile."""

    def __init__(
        self,
        inner: ExternalEffectStub,
        *,
        default_poll_result: StubOutcome | None = StubOutcome.CONFIRMED,
    ) -> None:
        self._inner = inner
        self._default_poll_result = default_poll_result
        self._poll_sequences: dict[str, list[StubOutcome | None]] = {}
        self._poll_indexes: dict[str, int] = {}

    def configure_poll(
        self,
        operation_identity: str,
        results: list[StubOutcome | None],
    ) -> None:
        self._poll_sequences[operation_identity] = list(results)
        self._poll_indexes[operation_identity] = 0

    def submit(
        self,
        idempotency_key: str,
        request_ref: ArtifactRef,
    ) -> str:
        return self._inner.submit(idempotency_key, request_ref)

    def poll(self, operation_identity: str) -> StubOutcome | None:
        sequence = self._poll_sequences.get(operation_identity)
        if sequence is None:
            return self._default_poll_result
        index = self._poll_indexes.get(operation_identity, 0)
        if index >= len(sequence):
            last = sequence[-1] if sequence else self._default_poll_result
            return last
        result = sequence[index]
        self._poll_indexes[operation_identity] = index + 1
        return result


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
            expected_identity = compute_operation_identity(
                payload.idempotency_key,
                request_bytes,
            )
            if operation_identity != expected_identity:
                lease_session.publish_operation(
                    _make_manual_recovery_terminal_builder(
                        None,
                        diagnostic=OperationDiagnostic(
                            code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH.upper(),
                            message="submitted operation identity does not match payload semantics",
                        ),
                    )
                )
                return ExecutorAcknowledgment.PUBLISHED
            reconcile_started_at = _iso_utc_timestamp(datetime.now(UTC))
            request_fingerprint = compute_request_fingerprint(request_bytes)
            envelope = envelope_for_step(
                key=key,
                operation=operation,
                step=step,
                checkpoint_generation=_checkpoint_generation(step),
                job_state=_job_state_for_request(
                    idempotency_key=payload.idempotency_key,
                    request_artifact_id=request_ref.artifact_id,
                    operation_identity=operation_identity,
                    request_fingerprint=request_fingerprint,
                    reconcile_started_at=reconcile_started_at,
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
            if last_checkpoint_generation is None:
                last_checkpoint_generation = lease_session.publish_checkpoint(
                    make_checkpoint_step_builder(checkpoint_ref=request_state.checkpoint_ref)
                )
            return lease_session.acknowledge_safe_handoff(last_checkpoint_generation)

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


def build_external_effect_stub_recovery_port(
    artifact_store: ArtifactStorePort,
    *,
    external_stub: ExternalEffectStub | None = None,
    now_factory: Callable[[], datetime] | None = None,
) -> RecoveryPort:
    """Build a RecoveryPort that reuses the original external-effect identity."""

    if not hasattr(artifact_store, "put") or not hasattr(artifact_store, "locate"):
        raise ValueError("artifact_store must implement ArtifactStorePort")

    definition = external_effect_stub_job_definition()
    clock = now_factory or (lambda: datetime.now(UTC))

    class _ExternalEffectStubRecoveryPort:
        def recover(
            self,
            operation: OperationRecord,
            step: StepRecord,
            control: ExecutionControl,
            lease_session: LeaseSession,
        ) -> RecoveryOutcome:
            return _recover_impl(operation, step, control, lease_session)

    def _recover_impl(
        operation: OperationRecord,
        step: StepRecord,
        control: ExecutionControl,
        lease_session: LeaseSession,
    ) -> RecoveryOutcome:
        lease_session.refresh_control()
        if step.checkpoint_ref is None and control.cancel_requested:
            lease_session.publish_operation(_make_cancelled_terminal_builder())
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.CANCELLED,
                diagnostic_code=None,
                reason=None,
            )

        payload = _load_external_effect_stub_payload(operation, artifact_store)
        request_bytes = build_request_bytes(payload.idempotency_key, payload.request_body)
        expected_identity = compute_operation_identity(payload.idempotency_key, request_bytes)
        polling_stub = _as_polling_stub(external_stub, request_bytes=request_bytes)
        if polling_stub is None:
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason="external effect stub is not poll-capable",
            )
        now = clock()

        if step.checkpoint_ref is None:
            return _recover_external_effect_pre_request(
                artifact_store=artifact_store,
                definition=definition,
                operation=operation,
                step=step,
                payload=payload,
                request_bytes=request_bytes,
                expected_identity=expected_identity,
                polling_stub=polling_stub,
                lease_session=lease_session,
                reconcile_started_at=now,
            )

        try:
            envelope = load_checkpoint_envelope(artifact_store, step.checkpoint_ref)
        except (CheckpointDecodeError, ManifestVerificationError) as exc:
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason=str(exc),
            )
        if not definition_matches_checkpoint(definition, envelope):
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
                reason="checkpoint envelope does not match the external-effect stub JobDefinition",
            )

        identity_result = validate_external_effect_identity(
            idempotency_key=payload.idempotency_key,
            request_bytes=request_bytes,
            job_state=envelope.job_state,
            expected_operation_identity=expected_identity,
        )
        if isinstance(identity_result, RecoveryOutcome):
            return identity_result

        try:
            started_at = _parse_reconcile_started_at(envelope.job_state)
            elapsed_seconds = (now - started_at).total_seconds()
            budget_exhausted = reconcile_budget_exhausted(elapsed_seconds)
        except (TypeError, ValueError) as exc:
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
                reason=f"invalid reconcile checkpoint timestamp: {exc}",
            )
        if budget_exhausted:
            return RecoveryOutcome(
                disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
                diagnostic_code=DIAGNOSTIC_RECONCILE_TIMEOUT,
                reason="external effect reconcile session budget exhausted",
            )

        return _recover_external_effect_post_request(
            artifact_store=artifact_store,
            operation=operation,
            payload=payload,
            identity=identity_result,
            polling_stub=polling_stub,
            lease_session=lease_session,
        )

    return _ExternalEffectStubRecoveryPort()


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
    request_fingerprint: str,
    reconcile_started_at: str,
) -> dict[str, object]:
    return {
        _JOB_STATE_IDEMPOTENCY_KEY: idempotency_key,
        _JOB_STATE_REQUEST_ARTIFACT_ID: request_artifact_id,
        _JOB_STATE_OPERATION_IDENTITY: operation_identity,
        _JOB_STATE_REQUEST_FINGERPRINT: request_fingerprint,
        _JOB_STATE_REQUEST_SENT: True,
        _JOB_STATE_RECONCILE_STARTED_AT: reconcile_started_at,
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
    request_bytes = build_request_bytes(expected_payload.idempotency_key, expected_payload.request_body)
    expected_identity = compute_operation_identity(
        expected_payload.idempotency_key,
        request_bytes,
    )
    identity_result = validate_external_effect_identity(
        idempotency_key=expected_payload.idempotency_key,
        request_bytes=request_bytes,
        job_state=job_state,
        expected_operation_identity=expected_identity,
    )
    if isinstance(identity_result, RecoveryOutcome):
        raise CheckpointDecodeError(
            identity_result.reason or "checkpoint identity mismatch",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    request_artifact_id_value = job_state.get(_JOB_STATE_REQUEST_ARTIFACT_ID)
    if type(request_artifact_id_value) is not str or not request_artifact_id_value:
        raise CheckpointDecodeError(
            "checkpoint job_state request_artifact_id is invalid",
            code="CHECKPOINT_JOB_STATE_MISMATCH",
        )
    expected_request_id = request_artifact_id(request_bytes)
    if request_artifact_id_value != expected_request_id:
        raise CheckpointDecodeError(
            "checkpoint job_state request_artifact_id does not match payload semantics",
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
        idempotency_key=identity_result.idempotency_key,
        request_artifact_id=request_artifact_id_value,
        operation_identity=identity_result.repository_operation_id,
        checkpoint_ref=checkpoint_ref,
    )


def _iso_utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_polling_stub(
    external_stub: ExternalEffectStub | None,
    *,
    request_bytes: bytes,
) -> PollingExternalEffectStub | None:
    if isinstance(external_stub, PollingExternalEffectStub):
        return external_stub
    if external_stub is None:
        inner = DeterministicExternalEffectStub(request_bytes=request_bytes)
        return PollingExternalEffectStub(inner)
    poll_method = getattr(external_stub, "poll", None)
    if not callable(poll_method):
        return None
    delegated_poll = cast(Callable[[str], StubOutcome | None], poll_method)

    class _PollingAdapter(PollingExternalEffectStub):
        def __init__(self, inner: ExternalEffectStub) -> None:
            # The adapter delegates polling explicitly; no confirmed fallback.
            super().__init__(inner, default_poll_result=None)

        def poll(self, operation_identity: str) -> StubOutcome | None:
            result = delegated_poll(operation_identity)
            if result is not None and type(result) is not StubOutcome:
                raise ValueError("external effect poll returned an unsupported outcome")
            return result

    return _PollingAdapter(external_stub)


def _recovery_outcome_for_poll_result(poll_result: StubOutcome | None) -> RecoveryOutcome | None:
    if poll_result is None or poll_result is StubOutcome.ACCEPTED:
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.RECONCILE_PENDING,
            diagnostic_code=None,
            reason=None,
        )
    if poll_result is StubOutcome.UNKNOWN:
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason="external effect outcome remains unknown after reconcile poll",
        )
    if poll_result is StubOutcome.CONFIRMED:
        return None
    return RecoveryOutcome(
        disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
        diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
        reason="external effect poll returned an unsupported outcome",
    )


def _publish_confirmed_external_effect_recovery(
    artifact_store: ArtifactStorePort,
    lease_session: LeaseSession,
    operation: OperationRecord,
    *,
    operation_identity: str,
    idempotency_key: str,
) -> RecoveryOutcome:
    response_bytes = build_response_bytes(
        operation_identity,
        idempotency_key,
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
            repository_operation_id=operation_identity,
        )
    )
    return RecoveryOutcome(
        disposition=RecoveryOutcomeDisposition.PUBLISHED,
        diagnostic_code=None,
        reason=None,
    )


def _recover_external_effect_pre_request(
    *,
    artifact_store: ArtifactStorePort,
    definition: JobDefinition,
    operation: OperationRecord,
    step: StepRecord,
    payload: ExternalEffectStubPayload,
    request_bytes: bytes,
    expected_identity: str,
    polling_stub: PollingExternalEffectStub,
    lease_session: LeaseSession,
    reconcile_started_at: datetime,
) -> RecoveryOutcome:
    request_ref = put_with_built_ref(
        artifact_store,
        request_bytes,
        artifact_id=request_artifact_id(request_bytes),
        media_type=_JCS_MEDIA_TYPE,
    )
    operation_identity = polling_stub.submit(payload.idempotency_key, request_ref)
    if operation_identity != expected_identity:
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
            reason="submitted operation identity does not match payload semantics",
        )
    envelope = envelope_for_step(
        key=external_effect_stub_job_key(),
        operation=operation,
        step=step,
        checkpoint_generation=_checkpoint_generation(step),
        job_state=_job_state_for_request(
            idempotency_key=payload.idempotency_key,
            request_artifact_id=request_ref.artifact_id,
            operation_identity=operation_identity,
            request_fingerprint=compute_request_fingerprint(request_bytes),
            reconcile_started_at=_iso_utc_timestamp(reconcile_started_at),
        ),
    )
    checkpoint_ref = prepare_step_checkpoint(artifact_store, envelope)
    if not definition_matches_checkpoint(definition, envelope):
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_EFFECT_IDENTITY_MISMATCH,
            reason="checkpoint envelope does not match the external-effect stub JobDefinition",
        )
    lease_session.publish_checkpoint(make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref))
    try:
        poll_result = polling_stub.poll(operation_identity)
    except (AttributeError, TypeError, ValueError) as exc:
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason=f"external effect stub is not poll-capable: {exc}",
        )
    pending_or_manual = _recovery_outcome_for_poll_result(poll_result)
    if pending_or_manual is not None:
        return pending_or_manual
    return _publish_confirmed_external_effect_recovery(
        artifact_store,
        lease_session,
        operation,
        operation_identity=operation_identity,
        idempotency_key=payload.idempotency_key,
    )


def _recover_external_effect_post_request(
    *,
    artifact_store: ArtifactStorePort,
    operation: OperationRecord,
    payload: ExternalEffectStubPayload,
    identity: ExternalEffectRequestIdentity,
    polling_stub: PollingExternalEffectStub,
    lease_session: LeaseSession,
) -> RecoveryOutcome:
    try:
        poll_result = polling_stub.poll(identity.repository_operation_id)
    except (AttributeError, TypeError, ValueError) as exc:
        return RecoveryOutcome(
            disposition=RecoveryOutcomeDisposition.MANUAL_RECOVERY,
            diagnostic_code=DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
            reason=f"external effect stub is not poll-capable: {exc}",
        )
    pending_or_manual = _recovery_outcome_for_poll_result(poll_result)
    if pending_or_manual is not None:
        return pending_or_manual
    return _publish_confirmed_external_effect_recovery(
        artifact_store,
        lease_session,
        operation,
        operation_identity=identity.repository_operation_id,
        idempotency_key=payload.idempotency_key,
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
    repository_operation_id: str | None,
    *,
    diagnostic: OperationDiagnostic = _UNKNOWN_OUTCOME_DIAGNOSTIC,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    if repository_operation_id is not None and (
        type(repository_operation_id) is not str or not repository_operation_id
    ):
        raise ValueError("repository_operation_id must be a non-empty string or None")

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
    output_ref = ArtifactRef(
        artifact_id=output_artifact_id,
        media_type=_JCS_MEDIA_TYPE,
        size_bytes=len(output_bytes),
        raw_sha256=raw_blob_digest(output_bytes),
    )
    try:
        store.locate(output_ref)
    except ManifestVerificationError as exc:
        raise CheckpointDecodeError(
            "checkpoint output artifact is missing or unreadable",
            code="CHECKPOINT_REF_UNREADABLE",
        ) from exc
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
    "PollingExternalEffectStub",
    "PureComputePayload",
    "build_external_effect_stub_handler",
    "build_external_effect_stub_recovery_port",
    "build_pure_compute_handler",
    "build_pure_compute_recovery_port",
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
