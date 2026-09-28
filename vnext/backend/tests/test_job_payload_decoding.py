"""Strict payload loading and versioned typed decoder boundary tests."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.checkpoints import (
    StepCheckpointEnvelope,
    load_checkpoint_envelope,
    put_checkpoint_envelope,
)
from gateway_backend.application.job_definitions import (
    JobDefinition,
    JobDefinitionRegistry,
    NormalPublicationCapability,
)
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.payloads import (
    CHECKPOINT_DOCUMENT_TYPE,
    CheckpointDecodeError,
    JOB_PAYLOAD_DOCUMENT_TYPE,
    PayloadDecodeError,
    PayloadDecoderRegistry,
    build_payload_decoder_registry,
    decode_job_payload,
    load_job_payload_bytes,
)
from gateway_backend.artifacts import (
    ArtifactRef,
    InMemoryArtifactStore,
    put_with_built_ref,
)
from gateway_backend.operations import OPERATION_RUNTIME_CONTRACT_VERSION, OperationRecord, OperationStatus
from gateway_backend.operations.contracts import JobStepKey
from tests.support.artifact_staging import (
    object_and_sidecar_paths,
    open_local_store,
    put_bytes,
    reopen_local_store,
    staging_root,
)

pytestmark = pytest.mark.unit

JOB_KIND = "import.package"
STEP_NAME = "validate"
VERSION_V1 = "backend-vnext/synthetic/pure-compute/v1"
DECODER_V1 = "backend-vnext/synthetic/pure-compute/decoder/v1"
HANDLER_V1 = "backend-vnext/synthetic/pure-compute/handler/v1"
TIMESTAMP = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)


@dataclasses.dataclass(frozen=True, slots=True)
class PureComputePayload:
    seed: str


def _sample_key() -> JobStepKey:
    return JobStepKey(job_kind=JOB_KIND, step_name=STEP_NAME)


def _sample_definition() -> JobDefinition:
    return JobDefinition(
        key=_sample_key(),
        supported_payload_versions=frozenset({VERSION_V1}),
        decoder_identity=DECODER_V1,
        handler_identity=HANDLER_V1,
        publication_capability=NormalPublicationCapability.TERMINAL,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )


def _operation_record(**changes: object) -> OperationRecord:
    defaults: dict[str, object] = {
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "operation_id": "op-0001",
        "job_kind": JOB_KIND,
        "job_contract_version": VERSION_V1,
        "job_payload": canonicalize_json_value({"seed": "alpha"}),
        "job_payload_ref": None,
        "business_refs": (),
        "artifact_refs": (),
        "repository_operation_id": None,
        "checkpoint_ref": None,
        "ready_closure_ref": None,
        "status": OperationStatus.QUEUED,
        "diagnostic": None,
        "cancel_requested": False,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
        "completed_at": None,
        "optimistic_version": 0,
    }
    defaults.update(changes)
    return OperationRecord(**defaults)  # type: ignore[arg-type]


def _decode_pure_compute(payload_object: dict[str, object]) -> PureComputePayload:
    seed = payload_object.get("seed")
    if type(seed) is not str or not seed:
        raise ValueError("seed must be a non-empty string")
    return PureComputePayload(seed=seed)


def _decoder_registry(definition: JobDefinition) -> PayloadDecoderRegistry:
    registry = JobDefinitionRegistry.build((definition,))
    return build_payload_decoder_registry(
        registry,
        {definition.decoder_identity: _decode_pure_compute},
    )


def _nested_json_object(depth: int) -> dict[str, object]:
    if depth <= 1:
        return {"leaf": 1}
    return {"nested": _nested_json_object(depth - 1)}


MALFORMED_INLINE_PAYLOAD_SHAPES: tuple[tuple[dict[str, object] | bytes, str], ...] = (
    ({"value": 2**53}, "I-JSON safe range"),
    (_nested_json_object(33), "maximum JSON depth"),
    ({"items": [{} for _ in range(4096)]}, "maximum JSON aggregate size"),
    ({"k" * 129: 1}, "maximum size"),
    ({"s": "x" * (16 * 1024 + 1)}, "maximum size"),
    (
        {f"key-{index}": "y" * 1000 for index in range(70)},
        "maximum inline payload size",
    ),
)


IDENTITY_MISMATCH_CASES: tuple[tuple[dict[str, object], str], ...] = (
    ({"job_kind": "other.kind"}, "job_kind does not match"),
    ({"job_contract_version": "backend-vnext/synthetic/pure-compute/v2"}, "not supported"),
)


class _LocateTrackingStore(InMemoryArtifactStore):
    def __init__(self) -> None:
        super().__init__()
        self.locate_calls = 0

    def locate(self, ref: ArtifactRef) -> bytes:
        self.locate_calls += 1
        return super().locate(ref)


def _operation_with_payload_bytes(job_payload: bytes, job_payload_ref: ArtifactRef | None = None) -> OperationRecord:
    operation = _operation_record(job_payload=canonicalize_json_value({"seed": "alpha"}))
    object.__setattr__(operation, "job_payload", job_payload)
    object.__setattr__(operation, "job_payload_ref", job_payload_ref)
    return operation


def test_document_type_axis_constants_are_distinct() -> None:
    assert JOB_PAYLOAD_DOCUMENT_TYPE == "job-payload"
    assert CHECKPOINT_DOCUMENT_TYPE == "step-checkpoint"
    assert JOB_PAYLOAD_DOCUMENT_TYPE != CHECKPOINT_DOCUMENT_TYPE


def test_checkpoint_decode_error_is_independent_axis() -> None:
    error = CheckpointDecodeError("checkpoint unreadable", code="CHECKPOINT_REF_UNREADABLE")
    assert isinstance(error, ValueError)
    assert error.code == "CHECKPOINT_REF_UNREADABLE"


def test_checkpoint_envelope_round_trip_through_artifact_store() -> None:
    store = InMemoryArtifactStore()
    envelope = StepCheckpointEnvelope(
        job_kind=JOB_KIND,
        step_name=STEP_NAME,
        operation_id="op-0001",
        job_contract_version=VERSION_V1,
        checkpoint_generation=1,
        prior_output_refs=(),
        job_state={"seed": "alpha"},
    )
    checkpoint_ref = put_checkpoint_envelope(store, envelope, artifact_id="checkpoint-round-trip")
    restored = load_checkpoint_envelope(store, checkpoint_ref)
    assert restored == envelope
    assert restored.to_canonical_bytes() == envelope.to_canonical_bytes()


def test_decode_job_payload_returns_frozen_typed_value() -> None:
    definition = _sample_definition()
    operation = _operation_record()
    store = InMemoryArtifactStore()
    decoded = decode_job_payload(
        definition,
        operation,
        store,
        _decoder_registry(definition),
    )
    assert decoded == PureComputePayload(seed="alpha")


def test_decode_rejects_non_job_definition_even_with_matching_qualname() -> None:
    definition = _sample_definition()
    fake_definition = SimpleNamespace(
        key=definition.key,
        supported_payload_versions=definition.supported_payload_versions,
        decoder_identity=definition.decoder_identity,
    )
    operation = _operation_record()
    with pytest.raises(PayloadDecodeError, match="definition must be JobDefinition") as exc_info:
        decode_job_payload(
            fake_definition,  # type: ignore[arg-type]
            operation,
            InMemoryArtifactStore(),
            _decoder_registry(definition),
        )
    assert exc_info.value.code == "PAYLOAD_DEFINITION_INVALID"


def test_inline_payload_decode_does_not_call_store_locate() -> None:
    definition = _sample_definition()
    operation = _operation_record()
    store = _LocateTrackingStore()
    decode_job_payload(
        definition,
        operation,
        store,
        _decoder_registry(definition),
    )
    assert store.locate_calls == 0


def test_payload_ref_decode_reads_exact_ref_from_store() -> None:
    definition = _sample_definition()
    store = InMemoryArtifactStore()
    raw = canonicalize_json_value({"seed": "ref-seed"})
    ref = put_with_built_ref(
        store,
        raw,
        artifact_id="payload-ref-1",
        media_type="application/json",
    )
    operation = _operation_record(job_payload=None, job_payload_ref=ref)
    decoded = decode_job_payload(
        definition,
        operation,
        store,
        _decoder_registry(definition),
    )
    assert decoded == PureComputePayload(seed="ref-seed")


@pytest.mark.parametrize(("changes", "match"), IDENTITY_MISMATCH_CASES)
def test_decode_rejects_identity_axis_mismatch(changes: dict[str, object], match: str) -> None:
    definition = _sample_definition()
    operation = _operation_record(**changes)
    with pytest.raises(PayloadDecodeError, match=match) as exc_info:
        decode_job_payload(
            definition,
            operation,
            InMemoryArtifactStore(),
            _decoder_registry(definition),
        )
    assert exc_info.value.code.startswith("PAYLOAD_")


@pytest.mark.parametrize(("payload", "match"), MALFORMED_INLINE_PAYLOAD_SHAPES)
def test_decode_rejects_malformed_inline_payload_shapes(
    payload: dict[str, object] | bytes,
    match: str,
) -> None:
    definition = _sample_definition()
    if type(payload) is bytes:
        job_payload = payload
    else:
        try:
            job_payload = canonicalize_json_value(payload)
        except Exception:
            job_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    operation = _operation_with_payload_bytes(job_payload)
    with pytest.raises(PayloadDecodeError, match=match) as exc_info:
        decode_job_payload(
            definition,
            operation,
            InMemoryArtifactStore(),
            _decoder_registry(definition),
        )
    assert exc_info.value.code == "PAYLOAD_SHAPE_INVALID"


def test_decode_rejects_mutually_exclusive_payload_binding() -> None:
    definition = _sample_definition()
    store = InMemoryArtifactStore()
    ref = put_with_built_ref(
        store,
        canonicalize_json_value({"seed": "x"}),
        artifact_id="payload-ref-dup",
        media_type="application/json",
    )
    operation = _operation_with_payload_bytes(
        canonicalize_json_value({"seed": "inline"}),
        job_payload_ref=ref,
    )
    with pytest.raises(PayloadDecodeError, match="mutually exclusive"):
        decode_job_payload(
            definition,
            operation,
            store,
            _decoder_registry(definition),
        )


def test_load_job_payload_bytes_rejects_non_canonical_inline_bytes() -> None:
    operation = _operation_with_payload_bytes(b'{"b":1,"a":2}')
    with pytest.raises(PayloadDecodeError, match="canonical JSON bytes"):
        load_job_payload_bytes(operation, InMemoryArtifactStore())


def _put_then_corrupt_bytes(store: InMemoryArtifactStore, raw: bytes, artifact_id: str) -> ArtifactRef:
    ref = put_with_built_ref(
        store,
        raw,
        artifact_id=artifact_id,
        media_type="application/json",
    )
    stored_ref, _ = store._artifacts[ref.artifact_id]
    corrupted = raw[:-1] + (b"x" if raw[-1:] != b"x" else b"y")
    store._artifacts[ref.artifact_id] = (stored_ref, corrupted)
    return stored_ref


REF_FAULT_CASES: tuple[tuple[str, Callable[[InMemoryArtifactStore, bytes], ArtifactRef], str], ...] = (
    (
        "missing",
        lambda store, raw: ArtifactRef(
            artifact_id="payload-ref-missing",
            media_type="application/json",
            size_bytes=len(raw),
            raw_sha256=raw_blob_digest(raw),
        ),
        "unknown artifact_id",
    ),
    (
        "corrupt-digest",
        lambda store, raw: _put_then_corrupt_bytes(store, raw, "payload-ref-corrupt-digest"),
        "raw_sha256 mismatch",
    ),
    (
        "identity-mismatch",
        lambda store, raw: put_with_built_ref(
            store,
            raw,
            artifact_id="payload-ref-identity-mismatch",
            media_type="application/json",
        ),
        "stored artifact identity mismatch",
    ),
)


@pytest.mark.parametrize(("case_name", "build_ref", "match"), REF_FAULT_CASES)
def test_decode_rejects_unreadable_payload_ref(
    case_name: str,
    build_ref: Callable[[InMemoryArtifactStore, bytes], ArtifactRef],
    match: str,
) -> None:
    del case_name
    definition = _sample_definition()
    store = InMemoryArtifactStore()
    raw = canonicalize_json_value({"seed": "stored"})
    ref = build_ref(store, raw)
    locate_ref = ref
    if match == "stored artifact identity mismatch":
        locate_ref = ArtifactRef(
            artifact_id=ref.artifact_id,
            media_type=ref.media_type,
            size_bytes=ref.size_bytes,
            raw_sha256=DigestRef("sha256:" + "b" * 64),
        )
    operation = _operation_record(job_payload=None, job_payload_ref=locate_ref)
    with pytest.raises(PayloadDecodeError, match=match) as exc_info:
        decode_job_payload(
            definition,
            operation,
            store,
            _decoder_registry(definition),
        )
    assert exc_info.value.code == "PAYLOAD_REF_UNREADABLE"


def test_build_payload_decoder_registry_rejects_surplus_decoder_keys() -> None:
    definition = _sample_definition()
    registry = JobDefinitionRegistry.build((definition,))
    with pytest.raises(ValueError, match="exactly one callable per decoder_identity"):
        build_payload_decoder_registry(
            registry,
            {
                definition.decoder_identity: _decode_pure_compute,
                "backend-vnext/extra/decoder/v1": _decode_pure_compute,
            },
        )


def test_build_payload_decoder_registry_rejects_missing_decoder_keys() -> None:
    definition = _sample_definition()
    registry = JobDefinitionRegistry.build((definition,))
    with pytest.raises(ValueError, match="exactly one callable per decoder_identity"):
        build_payload_decoder_registry(registry, {})


def test_job_definition_registry_rejects_duplicate_decoder_identity() -> None:
    first = _sample_definition()
    second = JobDefinition(
        key=JobStepKey(job_kind=JOB_KIND, step_name="publish"),
        supported_payload_versions=frozenset({VERSION_V1}),
        decoder_identity=DECODER_V1,
        handler_identity="backend-vnext/synthetic/stub/handler/v1",
        publication_capability=NormalPublicationCapability.TERMINAL,
        recovery_capability=RecoveryCapability.PURE_RECOMPUTE,
    )
    with pytest.raises(ValueError, match="duplicate decoder_identity"):
        JobDefinitionRegistry.build((first, second))


def test_payload_decoder_registry_rejects_post_build_mutation() -> None:
    definition = _sample_definition()
    registry = _decoder_registry(definition)
    with pytest.raises(TypeError):
        registry._decoders["backend-vnext/extra/decoder/v1"] = _decode_pure_compute  # type: ignore[index]
    assert registry.decode(DECODER_V1, {"seed": "alpha"}) == PureComputePayload(seed="alpha")


@pytest.mark.integration
def test_local_store_payload_ref_reopen_round_trip(tmp_path: Path) -> None:
    definition = _sample_definition()
    root = staging_root(tmp_path)
    store = open_local_store(root)
    raw = canonicalize_json_value({"seed": "reopen-seed"})
    ref = put_bytes(store, raw, artifact_id="payload-reopen", media_type="application/json")
    operation = _operation_record(job_payload=None, job_payload_ref=ref)
    decoded = decode_job_payload(
        definition,
        operation,
        store,
        _decoder_registry(definition),
    )
    assert decoded == PureComputePayload(seed="reopen-seed")
    reopened = reopen_local_store(root)
    decoded_again = decode_job_payload(
        definition,
        operation,
        reopened,
        _decoder_registry(definition),
    )
    assert decoded_again == PureComputePayload(seed="reopen-seed")


@pytest.mark.integration
@pytest.mark.parametrize("variant", ["truncated", "tampered"])
def test_local_store_corrupt_payload_ref_fails_closed(tmp_path: Path, variant: str) -> None:
    definition = _sample_definition()
    root = staging_root(tmp_path)
    store = open_local_store(root)
    raw = canonicalize_json_value({"seed": "corrupt"})
    ref = put_bytes(store, raw, artifact_id=f"payload-{variant}", media_type="application/json")
    object_path, _ = object_and_sidecar_paths(root, ref.artifact_id)
    payload_bytes = object_path.read_bytes()
    if variant == "truncated":
        object_path.write_bytes(payload_bytes[:-4])
    else:
        object_path.write_bytes(payload_bytes[:-1] + b"x")
    operation = _operation_record(job_payload=None, job_payload_ref=ref)
    with pytest.raises(PayloadDecodeError, match="mismatch|failed"):
        decode_job_payload(
            definition,
            operation,
            store,
            _decoder_registry(definition),
        )


@pytest.mark.integration
def test_local_store_missing_payload_ref_fails_closed(tmp_path: Path) -> None:
    definition = _sample_definition()
    root = staging_root(tmp_path)
    store = open_local_store(root)
    raw = canonicalize_json_value({"seed": "ghost"})
    ref = put_with_built_ref(
        store,
        raw,
        artifact_id="payload-missing",
        media_type="application/json",
    )
    operation = _operation_record(job_payload=None, job_payload_ref=ref)
    object_path, sidecar_path = object_and_sidecar_paths(root, ref.artifact_id)
    object_path.unlink()
    sidecar_path.unlink()
    with pytest.raises(PayloadDecodeError, match="unknown artifact_id|artifact bytes are missing|failed"):
        decode_job_payload(
            definition,
            operation,
            store,
            _decoder_registry(definition),
        )
