"""Checkpoint envelope and READY closure contract tests."""

from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import dataclasses
import json
from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.checkpoints import (
    CheckpointPublicationError,
    ReadyClosureDocument,
    ReadyClosureEntry,
    STEP_CHECKPOINT_CONTRACT_VERSION,
    StepCheckpointEnvelope,
    definition_matches_checkpoint,
    envelope_for_step,
    load_checkpoint_envelope,
    load_checkpoint_state_artifact,
    load_ready_closure,
    make_checkpoint_step_builder,
    make_terminal_ready_closure_builder,
    prepare_ready_closure,
    prepare_step_checkpoint,
    put_checkpoint_state_artifact,
    put_ready_closure,
    verify_artifact_refs,
)
from gateway_backend.application.job_definitions import (
    JobDefinition,
    JobDefinitionRegistry,
    NormalPublicationCapability,
)
from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.application.payloads import CHECKPOINT_DOCUMENT_TYPE, CheckpointDecodeError
from gateway_backend.artifacts import (
    ArtifactRef,
    InMemoryArtifactStore,
    ManifestVerificationError,
    put_with_built_ref,
)
from gateway_backend.artifacts.serialize import artifact_ref_to_dict
from gateway_backend.operations import OPERATION_RUNTIME_CONTRACT_VERSION, OperationRecord, OperationStatus
from gateway_backend.operations.contracts import JobStepKey, StepRecord, StepStatus
from gateway_backend.operations.state import TransitionDisposition, validate_operation_transition, validate_step_transition
from gateway_backend.operations.store import StaleWrite
from tests.support.artifact_staging import (
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
TS1 = datetime(2024, 1, 2, 3, 4, 6, tzinfo=UTC)
TXN_NOW = datetime(2024, 1, 2, 3, 4, 5, 500000, tzinfo=UTC)


def _artifact_ref(artifact_id: str, *, raw: bytes = b"out") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        media_type="application/octet-stream",
        size_bytes=len(raw),
        raw_sha256=raw_blob_digest(raw),
    )


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
        "status": OperationStatus.RUNNING,
        "diagnostic": None,
        "cancel_requested": False,
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
        "completed_at": None,
        "optimistic_version": 1,
    }
    defaults.update(changes)
    return OperationRecord(**defaults)  # type: ignore[arg-type]


def _step_record(**changes: object) -> StepRecord:
    defaults: dict[str, object] = {
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "step_id": "step-0001",
        "operation_id": "op-0001",
        "step_name": STEP_NAME,
        "status": StepStatus.RUNNING,
        "attempt_count": 1,
        "diagnostic": None,
        "cancel_requested": False,
        "retry_not_before": None,
        "worker_id": "worker-1",
        "lease_token": "lease-1",
        "lease_expires_at": TS1,
        "checkpoint_ref": None,
        "prior_output_refs": (),
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
        "started_at": TIMESTAMP,
        "completed_at": None,
        "optimistic_version": 1,
    }
    defaults.update(changes)
    return StepRecord(**defaults)  # type: ignore[arg-type]


def _sample_envelope(**changes: object) -> StepCheckpointEnvelope:
    defaults: dict[str, object] = {
        "job_kind": JOB_KIND,
        "step_name": STEP_NAME,
        "operation_id": "op-0001",
        "job_contract_version": VERSION_V1,
        "checkpoint_generation": 1,
        "prior_output_refs": (),
        "job_state": {"cursor": "alpha"},
    }
    defaults.update(changes)
    return StepCheckpointEnvelope(**defaults)  # type: ignore[arg-type]


MALFORMED_CLOSURE_SHAPES: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "missing_outputs",
        {
            "closure_contract_version": "backend-vnext/operation-ready-closure/v1",
            "document_type": "ready-closure",
            "job_contract_version": VERSION_V1,
        },
        "unexpected keys",
    ),
    (
        "duplicate_artifact_id",
        {
            "closure_contract_version": "backend-vnext/operation-ready-closure/v1",
            "document_type": "ready-closure",
            "job_contract_version": VERSION_V1,
            "outputs": [
                {
                    "artifact_ref": artifact_ref_to_dict(_artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40")),
                    "raw_sha256": _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40").raw_sha256.value,
                    "size_bytes": _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40").size_bytes,
                },
                {
                    "artifact_ref": artifact_ref_to_dict(_artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40")),
                    "raw_sha256": _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40").raw_sha256.value,
                    "size_bytes": _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40").size_bytes,
                },
            ],
        },
        "strictly sorted",
    ),
    (
        "unsorted_outputs",
        {
            "closure_contract_version": "backend-vnext/operation-ready-closure/v1",
            "document_type": "ready-closure",
            "job_contract_version": VERSION_V1,
            "outputs": [
                {
                    "artifact_ref": artifact_ref_to_dict(_artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40")),
                    "raw_sha256": _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40").raw_sha256.value,
                    "size_bytes": _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40").size_bytes,
                },
                {
                    "artifact_ref": artifact_ref_to_dict(_artifact_ref("a1:durable:7da78573aab236ac2609160080c4e25358da490eac66f16e71800596e865e683")),
                    "raw_sha256": _artifact_ref("a1:durable:7da78573aab236ac2609160080c4e25358da490eac66f16e71800596e865e683").raw_sha256.value,
                    "size_bytes": _artifact_ref("a1:durable:7da78573aab236ac2609160080c4e25358da490eac66f16e71800596e865e683").size_bytes,
                },
            ],
        },
        "strictly sorted",
    ),
)

CHECKPOINT_ENVELOPE_FAULTS: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "unsupported_contract_version",
        {
            "checkpoint_contract_version": "backend-vnext/operation-step-checkpoint/v99",
            "checkpoint_generation": 0,
            "document_type": CHECKPOINT_DOCUMENT_TYPE,
            "job_contract_version": VERSION_V1,
            "job_kind": JOB_KIND,
            "job_state": {},
            "operation_id": "op-0001",
            "prior_output_refs": [],
            "step_name": STEP_NAME,
        },
        "unsupported checkpoint contract version",
    ),
    (
        "wrong_document_type",
        {
            "checkpoint_contract_version": STEP_CHECKPOINT_CONTRACT_VERSION,
            "checkpoint_generation": 0,
            "document_type": "job-payload",
            "job_contract_version": VERSION_V1,
            "job_kind": JOB_KIND,
            "job_state": {},
            "operation_id": "op-0001",
            "prior_output_refs": [],
            "step_name": STEP_NAME,
        },
        "document_type is not a checkpoint axis",
    ),
)


def _duplicate_checkpoint_bytes() -> bytes:
    return (
        b'{"checkpoint_contract_version":"backend-vnext/operation-step-checkpoint/v1",'
        b'"checkpoint_generation":1,'
        b'"document_type":"step-checkpoint",'
        b'"job_contract_version":"backend-vnext/synthetic/pure-compute/v1",'
        b'"job_kind":"synthetic.pure-compute",'
        b'"job_kind":"duplicate",'
        b'"job_state":{},'
        b'"operation_id":"op-0001",'
        b'"prior_output_refs":[],'
        b'"step_name":"compute"}'
    )


def _duplicate_closure_bytes() -> bytes:
    output = ReadyClosureEntry.from_document(
        {
            "artifact_ref": artifact_ref_to_dict(_artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40")),
            "raw_sha256": _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40").raw_sha256.value,
            "size_bytes": _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40").size_bytes,
        }
    ).to_document()
    return (
        b'{"closure_contract_version":"backend-vnext/operation-ready-closure/v1",'
        b'"document_type":"ready-closure",'
        b'"job_contract_version":"' + VERSION_V1.encode("ascii") + b'",'
        b'"job_contract_version":"duplicate",'
        b'"outputs":[' + json.dumps(output).encode("ascii") + b"]}"
    )


CANONICAL_DOCUMENT_BYTE_FAULTS: tuple[tuple[str, str, bytes, str], ...] = (
    (
        "checkpoint",
        "non-canonical-whitespace",
        b" " + _sample_envelope().to_canonical_bytes(),
        "checkpoint bytes must be canonical JSON",
    ),
    (
        "checkpoint",
        "duplicate-member",
        _duplicate_checkpoint_bytes(),
        "duplicate JSON member name",
    ),
    (
        "closure",
        "non-canonical-whitespace",
        b" " + ReadyClosureDocument.build((_artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40"),), VERSION_V1).to_canonical_bytes(),
        "ready closure bytes must be canonical JSON",
    ),
    (
        "closure",
        "duplicate-member",
        _duplicate_closure_bytes(),
        "duplicate JSON member name",
    ),
)


@pytest.mark.parametrize(("axis", "fault_kind", "raw_bytes", "message"), CANONICAL_DOCUMENT_BYTE_FAULTS)
def test_canonical_document_bytes_reject_non_canonical_and_duplicate_keys(
    axis: str,
    fault_kind: str,
    raw_bytes: bytes,
    message: str,
) -> None:
    del fault_kind
    decoder = (
        StepCheckpointEnvelope.from_canonical_bytes
        if axis == "checkpoint"
        else ReadyClosureDocument.from_canonical_bytes
    )
    with pytest.raises(CheckpointDecodeError, match=message):
        decoder(raw_bytes)


@pytest.mark.unit
def test_checkpoint_envelope_canonical_round_trip() -> None:
    envelope = _sample_envelope(
        prior_output_refs=(_artifact_ref("a1:durable:18f3b90fc468ae141470bc5e953db836f4667a24161126f6e818100ce262e9c6"),),
        job_state={"cursor": "beta", "count": 2},
    )
    raw = envelope.to_canonical_bytes()
    restored = StepCheckpointEnvelope.from_canonical_bytes(raw)
    assert restored == envelope
    assert restored.to_canonical_bytes() == raw


def test_ready_closure_document_sorts_outputs_by_artifact_id() -> None:
    ref_b = _artifact_ref("a1:durable:7da78573aab236ac2609160080c4e25358da490eac66f16e71800596e865e683")
    ref_a = _artifact_ref("a1:durable:a1b30be8cf54caeb21603fbf5ceff7e647626133fccd7e8d631d1491c475eb40")
    document = ReadyClosureDocument.build((ref_a, ref_b), VERSION_V1)
    assert [entry.artifact_ref.artifact_id for entry in document.outputs] == [ref_b.artifact_id, ref_a.artifact_id]
    raw = document.to_canonical_bytes()
    # a1 wire bytes changed with the IDs; the original sorting/raw SHA formula remains.
    expected = (
        b'{"closure_contract_version":"backend-vnext/operation-ready-closure/v1","document_type":"ready-closur'
        b'e","job_contract_version":"backend-vnext/synthetic/pure-compute/v1","outputs":[{"artifact_ref":{"art'
        b'ifact_id":"a1:durable:7da78573aab236ac2609160080c4e25358da490eac66f16e71800596e865e683","media_type"'
        b':"application/octet-stream","raw_sha256":"sha256:762069bc07a6e1b5df123a5ae7bd91c10daa04694fbaa17fba0'
        b'cd6a8dcce8f22","size_bytes":3},"raw_sha256":"sha256:762069bc07a6e1b5df123a5ae7bd91c10daa04694fbaa17f'
        b'ba0cd6a8dcce8f22","size_bytes":3},{"artifact_ref":{"artifact_id":"a1:durable:a1b30be8cf54caeb21603fb'
        b'f5ceff7e647626133fccd7e8d631d1491c475eb40","media_type":"application/octet-stream","raw_sha256":"sha'
        b'256:762069bc07a6e1b5df123a5ae7bd91c10daa04694fbaa17fba0cd6a8dcce8f22","size_bytes":3},"raw_sha256":"'
        b'sha256:762069bc07a6e1b5df123a5ae7bd91c10daa04694fbaa17fba0cd6a8dcce8f22","size_bytes":3}]}'
    )
    assert raw == expected
    assert raw_blob_digest(raw).value == "sha256:3a30adbe13c24e6363028b4474ab78735b97c22bf9b0ce00d2d8201016a26a00"
    restored = ReadyClosureDocument.from_canonical_bytes(raw)
    assert restored == document
    assert restored.to_canonical_bytes() == expected


@pytest.mark.unit
@pytest.mark.parametrize("ref_count", (4_096, 4_097, 32_768))
def test_ready_closure_retains_bounded_large_snapshot_artifact_sets(ref_count: int) -> None:
    refs = tuple(_artifact_ref(build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", f"artifact-{index:05d}")) for index in range(ref_count))
    document = ReadyClosureDocument.build(refs, VERSION_V1)
    assert len(document.outputs) == ref_count
    raw = document.to_canonical_bytes()
    restored = ReadyClosureDocument.from_canonical_bytes(raw)
    assert restored == document
    assert restored.artifact_refs() == tuple(sorted(refs, key=lambda ref: ref.artifact_id))
    assert restored.to_canonical_bytes() == raw


def test_ready_closure_rejects_over_capacity_on_build_construction_and_decode() -> None:
    refs = tuple(_artifact_ref(build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", f"artifact-{index:05d}")) for index in range(32_769))
    with pytest.raises(ValueError, match="output_refs exceeds bounded document size"):
        ReadyClosureDocument.build(refs, VERSION_V1)
    entries = tuple(ReadyClosureEntry(artifact_ref=ref) for ref in refs)
    with pytest.raises(ValueError, match="outputs exceeds bounded document size"):
        ReadyClosureDocument(job_contract_version=VERSION_V1, outputs=entries)
    payload = {
        "closure_contract_version": "backend-vnext/operation-ready-closure/v1",
        "document_type": "ready-closure",
        "job_contract_version": VERSION_V1,
        "outputs": [entry.to_document() for entry in entries],
    }
    with pytest.raises(ValueError, match="outputs exceeds bounded document size"):
        ReadyClosureDocument.from_canonical_bytes(canonicalize_json_value(payload))


@pytest.mark.unit
def test_checkpoint_state_artifact_keeps_materialized_refs_out_of_inline_payload() -> None:
    store = InMemoryArtifactStore()
    state_ref = put_checkpoint_state_artifact(
        store,
        {
            "document_type": "snapshot-sides",
            "contract_version": "snapshot-sides/v1",
            "refs": [f"table-{index:04d}" for index in range(5_000)],
        },
        artifact_id_prefix='preview-materialized-sides',
    )
    pointer = StepCheckpointEnvelope(
        job_kind=JOB_KIND,
        step_name=STEP_NAME,
        operation_id="op-large-state",
        job_contract_version=VERSION_V1,
        checkpoint_generation=0,
        prior_output_refs=(),
        job_state={"materialized_sides_ref": artifact_ref_to_dict(state_ref)},
    )

    restored_pointer = StepCheckpointEnvelope.from_canonical_bytes(pointer.to_canonical_bytes())
    restored_state = load_checkpoint_state_artifact(
        store,
        state_ref,
        document_type="snapshot-sides",
        contract_version="snapshot-sides/v1",
    )
    refs = restored_state["refs"]
    assert len(restored_pointer.job_state) == 1
    assert isinstance(refs, list) and len(refs) == 5_000


def test_definition_matches_checkpoint_identity_axes() -> None:
    definition = _sample_definition()
    envelope = _sample_envelope()
    assert definition_matches_checkpoint(definition, envelope) is True
    mismatch = _sample_envelope(job_contract_version="backend-vnext/unknown/v1")
    assert definition_matches_checkpoint(definition, mismatch) is False


def test_verify_artifact_refs_rejects_digest_mismatch() -> None:
    store = InMemoryArtifactStore()
    raw = b"payload"
    ref = put_with_built_ref(store, raw, artifact_id="a1:durable:e646c278057adf7f1d8acdf56c11b37da4310c7751c0e10c548f4fe2654ac1e6", media_type="application/octet-stream")
    bad_ref = ArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=DigestRef("sha256:" + "b" * 64),
    )
    with pytest.raises(CheckpointPublicationError, match="stored artifact identity mismatch"):
        verify_artifact_refs(store, (bad_ref,))


@pytest.mark.parametrize(("label", "payload", "message"), MALFORMED_CLOSURE_SHAPES)
def test_ready_closure_decode_rejects_malformed_shapes(
    label: str,
    payload: dict[str, object],
    message: str,
) -> None:
    del label
    with pytest.raises(CheckpointDecodeError, match=message):
        ReadyClosureDocument.from_document(payload)


@pytest.mark.parametrize(("label", "payload", "message"), CHECKPOINT_ENVELOPE_FAULTS)
def test_checkpoint_decode_rejects_malformed_envelopes(
    label: str,
    payload: dict[str, object],
    message: str,
) -> None:
    del label
    with pytest.raises(CheckpointDecodeError, match=message):
        StepCheckpointEnvelope.from_document(payload)


def test_ready_closure_ref_set_once_guard_rejects_rewrite() -> None:
    current = _operation_record(
        ready_closure_ref=_artifact_ref("a1:durable:6fbdbe17f9da43c5bb5b2ba31d8363d3206382816df32c90715d745918d2638d"),
        optimistic_version=2,
        updated_at=TS1,
    )
    candidate = _operation_record(
        ready_closure_ref=_artifact_ref("a1:durable:f20e73c130a434943b87250d60e5672614d0d5f2802753bd5a291ccc9f7dea75"),
        optimistic_version=3,
        updated_at=TS1,
    )
    with pytest.raises(ValueError, match="ready_closure_ref can only be set once"):
        validate_operation_transition(current, candidate)


def test_same_ref_put_is_idempotent() -> None:
    store = InMemoryArtifactStore()
    envelope = _sample_envelope()
    first = prepare_step_checkpoint(store, envelope)
    second = prepare_step_checkpoint(store, envelope)
    assert first == second
    assert load_checkpoint_envelope(store, first) == envelope


def test_identity_mismatch_put_fails_closed() -> None:
    store = InMemoryArtifactStore()
    envelope = _sample_envelope()
    ref = prepare_step_checkpoint(store, envelope)
    conflicting = ArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=DigestRef("sha256:" + "c" * 64),
    )
    with pytest.raises(ManifestVerificationError, match="raw_sha256 mismatch"):
        store.put(envelope.to_canonical_bytes(), conflicting)


def test_stale_cas_leaves_unreferenced_artifact_without_cleanup() -> None:
    store = InMemoryArtifactStore()
    output_ref = put_with_built_ref(
        store,
        b"output",
        artifact_id="a1:durable:e646c278057adf7f1d8acdf56c11b37da4310c7751c0e10c548f4fe2654ac1e6",
        media_type="application/octet-stream",
    )
    closure_ref = prepare_ready_closure(store, (output_ref,), VERSION_V1)
    operation = _operation_record()
    step = _step_record()
    builder = make_terminal_ready_closure_builder(closure_ref=closure_ref)
    terminal_step, terminal_operation = builder(operation, step, TS1)
    stale_step = dataclasses.replace(terminal_step, optimistic_version=step.optimistic_version)
    with pytest.raises(ValueError, match="optimistic_version must be current \\+ 1"):
        validate_step_transition(step, stale_step)
    assert store.locate(closure_ref) == load_ready_closure(store, closure_ref).to_canonical_bytes()
    cleanup = getattr(store, "delete", None)
    assert cleanup is None or not callable(cleanup)


def test_publication_builders_do_not_touch_artifact_store() -> None:
    store = MagicMock(spec=InMemoryArtifactStore)
    envelope = _sample_envelope()
    checkpoint_ref = prepare_step_checkpoint(InMemoryArtifactStore(), envelope)
    operation = _operation_record()
    step = _step_record()
    checkpoint_builder = make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)
    checkpoint_builder(operation, step, TXN_NOW)
    prep_store = InMemoryArtifactStore()
    output_ref = put_with_built_ref(
        prep_store,
        b"output",
        artifact_id="a1:durable:e646c278057adf7f1d8acdf56c11b37da4310c7751c0e10c548f4fe2654ac1e6",
        media_type="application/octet-stream",
    )
    closure_ref = prepare_ready_closure(
        prep_store,
        (output_ref,),
        VERSION_V1,
    )
    terminal_builder = make_terminal_ready_closure_builder(closure_ref=closure_ref)
    terminal_builder(operation, step, TS1)
    store.put.assert_not_called()
    store.locate.assert_not_called()


def test_terminal_builder_rejects_second_closure_assignment() -> None:
    closure_ref = _artifact_ref("a1:durable:8fdb534e28e4938fcc2d3449cda45ce30748a3309e98c61c184ce0e75fa99beb")
    builder = make_terminal_ready_closure_builder(closure_ref=closure_ref)
    operation = _operation_record(ready_closure_ref=_artifact_ref("a1:durable:e04b618294f79b05ade2f6804e079fe588f0b025a8e3c20de4cb1ec24bd67207"))
    step = _step_record()
    with pytest.raises(CheckpointPublicationError, match="ready_closure_ref is already set"):
        builder(operation, step, TS1)


def test_envelope_for_step_uses_transaction_fresh_prior_output_refs() -> None:
    prior = (_artifact_ref("a1:durable:18f3b90fc468ae141470bc5e953db836f4667a24161126f6e818100ce262e9c6"),)
    operation = _operation_record()
    step = _step_record(prior_output_refs=prior)
    envelope = envelope_for_step(
        key=_sample_key(),
        operation=operation,
        step=step,
        checkpoint_generation=2,
        job_state={"phase": "compute"},
    )
    assert envelope.prior_output_refs == prior
    assert envelope.checkpoint_generation == 2


def test_checkpoint_builder_increments_step_version_once() -> None:
    store = InMemoryArtifactStore()
    checkpoint_ref = prepare_step_checkpoint(store, _sample_envelope())
    operation = _operation_record()
    step = _step_record()
    builder = make_checkpoint_step_builder(checkpoint_ref=checkpoint_ref)
    candidate = builder(operation, step, TXN_NOW)
    assert candidate.checkpoint_ref == checkpoint_ref
    assert candidate.optimistic_version == step.optimistic_version + 1
    assert validate_step_transition(step, candidate) is TransitionDisposition.APPLY


def test_stale_write_type_available_for_cas_failure_boundary() -> None:
    assert issubclass(StaleWrite, Exception)


@pytest.mark.integration
def test_local_store_missing_closure_fails_closed(tmp_path: object) -> None:
    from pathlib import Path

    root = staging_root(cast(Path, tmp_path))
    store = open_local_store(root)
    missing = _artifact_ref("a1:durable:5d4cfe19eb81712c74efce046a73998d6ac9e61bc3b87ef8256d367abfa2da96")
    with pytest.raises(CheckpointDecodeError, match="artifact ref is not available"):
        load_ready_closure(store, missing)


@pytest.mark.integration
def test_local_store_reopen_readback_round_trip(tmp_path: object) -> None:
    from pathlib import Path

    root = staging_root(cast(Path, tmp_path))
    store = open_local_store(root)
    output_ref = put_bytes(store, b"ready-output", artifact_id="a1:durable:f88eb7a5bf8fdc5fc059653d1b1bb4219a3c6a0282a5ea5927e5e1765368223d")
    document = ReadyClosureDocument.build((output_ref,), VERSION_V1)
    closure_ref = put_ready_closure(store, document)
    checkpoint_ref = prepare_step_checkpoint(
        store,
        _sample_envelope(prior_output_refs=(output_ref,)),
    )
    reopened = reopen_local_store(root)
    assert load_ready_closure(reopened, closure_ref) == document
    assert load_checkpoint_envelope(reopened, checkpoint_ref) == _sample_envelope(
        prior_output_refs=(output_ref,)
    )


def test_registry_definition_matches_checkpoint_via_helper() -> None:
    registry = JobDefinitionRegistry.build((_sample_definition(),))
    definition = registry.get(_sample_key())
    assert definition_matches_checkpoint(definition, _sample_envelope()) is True
