"""Application-owned checkpoint envelopes and READY closure publication contracts."""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.errors import CanonicalEncodingError
from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.application.job_definitions import JobDefinition
from gateway_backend.application.payloads import CHECKPOINT_DOCUMENT_TYPE, CheckpointDecodeError
from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.store import (
    ArtifactStorePort,
    ManifestVerificationError,
    put_with_built_ref,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.operations.contracts import (
    JobStepKey,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    validate_json_structure,
)

STEP_CHECKPOINT_CONTRACT_VERSION = "backend-vnext/operation-step-checkpoint/v1"
READY_CLOSURE_DOCUMENT_TYPE = "ready-closure"
READY_CLOSURE_CONTRACT_VERSION = "backend-vnext/operation-ready-closure/v1"
_JCS_MEDIA_TYPE = "application/jcs"

_DIAGNOSTIC_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$")
_MAX_DECODER_MESSAGE_BYTES = 4 * 1024
_MAX_REFS_PER_DOCUMENT = 64

_CHECKPOINT_DOCUMENT_KEYS = frozenset(
    {
        "checkpoint_contract_version",
        "checkpoint_generation",
        "document_type",
        "job_contract_version",
        "job_kind",
        "job_state",
        "operation_id",
        "prior_output_refs",
        "step_name",
    }
)
_READY_CLOSURE_DOCUMENT_KEYS = frozenset(
    {
        "closure_contract_version",
        "document_type",
        "job_contract_version",
        "outputs",
    }
)
_OUTPUT_ENTRY_KEYS = frozenset({"artifact_ref", "raw_sha256", "size_bytes"})


class CheckpointPublicationError(ValueError):
    """Bounded checkpoint/closure publication failure without a generic recovery taxonomy."""

    def __init__(self, message: str, *, code: str = "CHECKPOINT_PUBLICATION_FAILED") -> None:
        _validate_bounded_diagnostic_code(code)
        _validate_bounded_diagnostic_message(message)
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class StepCheckpointEnvelope:
    """Versioned JCS checkpoint envelope without a Python object graph."""

    job_kind: str
    step_name: str
    operation_id: str
    job_contract_version: str
    checkpoint_generation: int
    prior_output_refs: tuple[ArtifactRef, ...]
    job_state: Mapping[str, object]

    def __post_init__(self) -> None:
        if type(self.job_kind) is not str or self.job_kind == "":
            raise ValueError("job_kind must be a non-empty string")
        if type(self.step_name) is not str or self.step_name == "":
            raise ValueError("step_name must be a non-empty string")
        if type(self.operation_id) is not str or self.operation_id == "":
            raise ValueError("operation_id must be a non-empty string")
        if type(self.job_contract_version) is not str or self.job_contract_version == "":
            raise ValueError("job_contract_version must be a non-empty string")
        if (
            type(self.checkpoint_generation) is not int
            or isinstance(self.checkpoint_generation, bool)
            or self.checkpoint_generation < 0
        ):
            raise ValueError("checkpoint_generation must be a non-negative int")
        if type(self.prior_output_refs) is not tuple:
            raise ValueError("prior_output_refs must be a tuple")
        if len(self.prior_output_refs) > _MAX_REFS_PER_DOCUMENT:
            raise ValueError("prior_output_refs exceeds bounded document size")
        for item in self.prior_output_refs:
            if type(item) is not ArtifactRef:
                raise ValueError("prior_output_refs must contain ArtifactRef")
        _reject_duplicate_artifact_ids(self.prior_output_refs)
        if not isinstance(self.job_state, Mapping):
            raise ValueError("job_state must be a mapping")
        job_state_dict = dict(self.job_state)
        validate_json_structure(job_state_dict)

    def to_document(self) -> dict[str, object]:
        return {
            "checkpoint_contract_version": STEP_CHECKPOINT_CONTRACT_VERSION,
            "checkpoint_generation": self.checkpoint_generation,
            "document_type": CHECKPOINT_DOCUMENT_TYPE,
            "job_contract_version": self.job_contract_version,
            "job_kind": self.job_kind,
            "job_state": dict(self.job_state),
            "operation_id": self.operation_id,
            "prior_output_refs": [artifact_ref_to_dict(item) for item in self.prior_output_refs],
            "step_name": self.step_name,
        }

    def to_canonical_bytes(self) -> bytes:
        return canonicalize_json_value(self.to_document())

    @classmethod
    def from_document(cls, document: object) -> StepCheckpointEnvelope:
        payload = _require_closed_document(document, _CHECKPOINT_DOCUMENT_KEYS, "checkpoint document")
        if _require_string(payload, "document_type") != CHECKPOINT_DOCUMENT_TYPE:
            raise CheckpointDecodeError(
                "document_type is not a checkpoint axis",
                code="CHECKPOINT_DOCUMENT_KIND_MISMATCH",
            )
        if _require_string(payload, "checkpoint_contract_version") != STEP_CHECKPOINT_CONTRACT_VERSION:
            raise CheckpointDecodeError(
                "unsupported checkpoint contract version",
                code="CHECKPOINT_CONTRACT_VERSION_UNSUPPORTED",
            )
        prior_output_refs = _parse_artifact_ref_list(
            payload["prior_output_refs"],
            label="prior_output_refs",
        )
        job_state_raw = payload["job_state"]
        if type(job_state_raw) is not dict:
            raise CheckpointDecodeError("job_state must be a JSON object", code="CHECKPOINT_SHAPE_INVALID")
        job_state = cast(dict[str, object], job_state_raw)
        try:
            validate_json_structure(job_state)
        except ValueError as exc:
            raise CheckpointDecodeError(str(exc), code="CHECKPOINT_SHAPE_INVALID") from exc
        return cls(
            job_kind=_require_string(payload, "job_kind"),
            step_name=_require_string(payload, "step_name"),
            operation_id=_require_string(payload, "operation_id"),
            job_contract_version=_require_string(payload, "job_contract_version"),
            checkpoint_generation=_require_non_negative_int(payload, "checkpoint_generation"),
            prior_output_refs=prior_output_refs,
            job_state=job_state,
        )

    @classmethod
    def from_canonical_bytes(cls, raw_bytes: bytes) -> StepCheckpointEnvelope:
        payload = _parse_canonical_document_bytes(
            raw_bytes,
            shape_invalid_code="CHECKPOINT_SHAPE_INVALID",
            non_canonical_message="checkpoint bytes must be canonical JSON",
        )
        return cls.from_document(payload)


@dataclass(frozen=True, slots=True)
class ReadyClosureEntry:
    """One exact output ref recorded in a READY closure document."""

    artifact_ref: ArtifactRef

    def __post_init__(self) -> None:
        if type(self.artifact_ref) is not ArtifactRef:
            raise ValueError("artifact_ref must be ArtifactRef")

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_ref": artifact_ref_to_dict(self.artifact_ref),
            "raw_sha256": self.artifact_ref.raw_sha256.value,
            "size_bytes": self.artifact_ref.size_bytes,
        }

    @classmethod
    def from_document(cls, payload: object) -> ReadyClosureEntry:
        if type(payload) is not dict:
            raise CheckpointDecodeError("closure output entry must be an object", code="CLOSURE_SHAPE_INVALID")
        entry = cast(dict[str, object], payload)
        extra = set(entry) - _OUTPUT_ENTRY_KEYS
        if extra or set(entry) != _OUTPUT_ENTRY_KEYS:
            raise CheckpointDecodeError("closure output entry has unexpected keys", code="CLOSURE_SHAPE_INVALID")
        artifact_ref = artifact_ref_from_dict(_object(entry, "artifact_ref"))
        size_bytes = _require_non_negative_int(entry, "size_bytes")
        raw_sha256 = DigestRef(_require_string(entry, "raw_sha256"))
        if size_bytes != artifact_ref.size_bytes:
            raise CheckpointDecodeError(
                "closure output size_bytes does not match artifact_ref",
                code="CLOSURE_REF_INTEGRITY_MISMATCH",
            )
        if raw_sha256 != artifact_ref.raw_sha256:
            raise CheckpointDecodeError(
                "closure output raw_sha256 does not match artifact_ref",
                code="CLOSURE_REF_INTEGRITY_MISMATCH",
            )
        return cls(artifact_ref=artifact_ref)


@dataclass(frozen=True, slots=True)
class ReadyClosureDocument:
    """Minimal READY closure document with stable artifact ordering."""

    job_contract_version: str
    outputs: tuple[ReadyClosureEntry, ...]

    def __post_init__(self) -> None:
        if type(self.job_contract_version) is not str or self.job_contract_version == "":
            raise ValueError("job_contract_version must be a non-empty string")
        if type(self.outputs) is not tuple:
            raise ValueError("outputs must be a tuple")
        if len(self.outputs) > _MAX_REFS_PER_DOCUMENT:
            raise ValueError("outputs exceeds bounded document size")
        for item in self.outputs:
            if type(item) is not ReadyClosureEntry:
                raise ValueError("outputs must contain ReadyClosureEntry")

    def to_document(self) -> dict[str, object]:
        return {
            "closure_contract_version": READY_CLOSURE_CONTRACT_VERSION,
            "document_type": READY_CLOSURE_DOCUMENT_TYPE,
            "job_contract_version": self.job_contract_version,
            "outputs": [entry.to_document() for entry in self.outputs],
        }

    def to_canonical_bytes(self) -> bytes:
        return canonicalize_json_value(self.to_document())

    @classmethod
    def build(
        cls,
        output_refs: tuple[ArtifactRef, ...],
        job_contract_version: str,
    ) -> ReadyClosureDocument:
        if type(output_refs) is not tuple:
            raise ValueError("output_refs must be a tuple")
        if len(output_refs) > _MAX_REFS_PER_DOCUMENT:
            raise ValueError("output_refs exceeds bounded document size")
        for item in output_refs:
            if type(item) is not ArtifactRef:
                raise ValueError("output_refs must contain ArtifactRef")
        _reject_duplicate_artifact_ids(output_refs)
        sorted_refs = tuple(sorted(output_refs, key=lambda ref: ref.artifact_id))
        document = cls(
            job_contract_version=job_contract_version,
            outputs=tuple(ReadyClosureEntry(artifact_ref=ref) for ref in sorted_refs),
        )
        _assert_sorted_unique_outputs(document.outputs)
        return document

    @classmethod
    def from_document(cls, document: object) -> ReadyClosureDocument:
        payload = _require_closed_document(document, _READY_CLOSURE_DOCUMENT_KEYS, "ready closure document")
        if _require_string(payload, "document_type") != READY_CLOSURE_DOCUMENT_TYPE:
            raise CheckpointDecodeError(
                "document_type is not a ready closure axis",
                code="CLOSURE_DOCUMENT_KIND_MISMATCH",
            )
        if _require_string(payload, "closure_contract_version") != READY_CLOSURE_CONTRACT_VERSION:
            raise CheckpointDecodeError(
                "unsupported ready closure contract version",
                code="CLOSURE_CONTRACT_VERSION_UNSUPPORTED",
            )
        raw_outputs = payload["outputs"]
        if type(raw_outputs) is not list:
            raise CheckpointDecodeError("closure outputs must be a list", code="CLOSURE_SHAPE_INVALID")
        outputs = tuple(ReadyClosureEntry.from_document(item) for item in raw_outputs)
        document_value = cls(
            job_contract_version=_require_string(payload, "job_contract_version"),
            outputs=outputs,
        )
        try:
            _assert_sorted_unique_outputs(document_value.outputs)
        except ValueError as exc:
            raise CheckpointDecodeError(str(exc), code="CLOSURE_SHAPE_INVALID") from exc
        return document_value

    @classmethod
    def from_canonical_bytes(cls, raw_bytes: bytes) -> ReadyClosureDocument:
        payload = _parse_canonical_document_bytes(
            raw_bytes,
            shape_invalid_code="CLOSURE_SHAPE_INVALID",
            non_canonical_message="ready closure bytes must be canonical JSON",
        )
        return cls.from_document(payload)

    def artifact_refs(self) -> tuple[ArtifactRef, ...]:
        return tuple(entry.artifact_ref for entry in self.outputs)


def definition_matches_checkpoint(definition: JobDefinition, envelope: StepCheckpointEnvelope) -> bool:
    """Return whether one checkpoint envelope matches a JobDefinition identity axis."""

    if type(definition) is not JobDefinition:
        raise ValueError("definition must be JobDefinition")
    if type(envelope) is not StepCheckpointEnvelope:
        raise ValueError("envelope must be StepCheckpointEnvelope")
    return (
        definition.key.job_kind == envelope.job_kind
        and definition.key.step_name == envelope.step_name
        and envelope.job_contract_version in definition.supported_payload_versions
    )


def verify_artifact_refs(store: ArtifactStorePort, refs: tuple[ArtifactRef, ...]) -> None:
    """Locate every exact ref and verify size/raw digest through the artifact port."""

    if type(refs) is not tuple:
        raise CheckpointPublicationError("refs must be a tuple", code="CHECKPOINT_REFS_INVALID")
    for ref in refs:
        if type(ref) is not ArtifactRef:
            raise CheckpointPublicationError(
                "refs must contain ArtifactRef",
                code="CHECKPOINT_REFS_INVALID",
            )
        try:
            store.locate(ref)
        except ManifestVerificationError as exc:
            raise CheckpointPublicationError(str(exc), code="CHECKPOINT_REF_UNREADABLE") from exc


def put_checkpoint_envelope(
    store: ArtifactStorePort,
    envelope: StepCheckpointEnvelope,
    *,
    artifact_id: str | None = None,
) -> ArtifactRef:
    raw_bytes = envelope.to_canonical_bytes()
    resolved_id = artifact_id or _content_artifact_id("step-checkpoint", raw_bytes)
    return put_with_built_ref(
        store,
        raw_bytes,
        artifact_id=resolved_id,
        media_type=_JCS_MEDIA_TYPE,
    )


def load_checkpoint_envelope(store: ArtifactStorePort, ref: ArtifactRef) -> StepCheckpointEnvelope:
    try:
        raw_bytes = store.locate(ref)
    except ManifestVerificationError as exc:
        raise CheckpointDecodeError(str(exc), code="CHECKPOINT_REF_UNREADABLE") from exc
    return StepCheckpointEnvelope.from_canonical_bytes(raw_bytes)


def put_ready_closure(
    store: ArtifactStorePort,
    document: ReadyClosureDocument,
    *,
    artifact_id: str | None = None,
) -> ArtifactRef:
    raw_bytes = document.to_canonical_bytes()
    resolved_id = artifact_id or _content_artifact_id("ready-closure", raw_bytes)
    return put_with_built_ref(
        store,
        raw_bytes,
        artifact_id=resolved_id,
        media_type=_JCS_MEDIA_TYPE,
    )


def load_ready_closure(store: ArtifactStorePort, ref: ArtifactRef) -> ReadyClosureDocument:
    try:
        raw_bytes = store.locate(ref)
    except ManifestVerificationError as exc:
        raise CheckpointDecodeError(str(exc), code="CLOSURE_REF_UNREADABLE") from exc
    document = ReadyClosureDocument.from_canonical_bytes(raw_bytes)
    verify_artifact_refs(store, document.artifact_refs())
    return document


def prepare_step_checkpoint(
    store: ArtifactStorePort,
    envelope: StepCheckpointEnvelope,
    *,
    artifact_id: str | None = None,
) -> ArtifactRef:
    """Persist one checkpoint envelope before a durable CAS publication."""

    verify_artifact_refs(store, envelope.prior_output_refs)
    return put_checkpoint_envelope(store, envelope, artifact_id=artifact_id)


def prepare_ready_closure(
    store: ArtifactStorePort,
    output_refs: tuple[ArtifactRef, ...],
    job_contract_version: str,
    *,
    artifact_id: str | None = None,
) -> ArtifactRef:
    """Verify output refs, persist closure bytes, and return the exact closure ref."""

    verify_artifact_refs(store, output_refs)
    document = ReadyClosureDocument.build(output_refs, job_contract_version)
    return put_ready_closure(store, document, artifact_id=artifact_id)


def make_checkpoint_step_builder(
    *,
    checkpoint_ref: ArtifactRef,
) -> Callable[[OperationRecord, StepRecord, datetime], StepRecord]:
    """Return a pure checkpoint publication builder for LeaseSession.publish_checkpoint."""

    if type(checkpoint_ref) is not ArtifactRef:
        raise ValueError("checkpoint_ref must be ArtifactRef")

    def builder(
        _operation: OperationRecord,
        step: StepRecord,
        transaction_now: datetime,
    ) -> StepRecord:
        return dataclasses.replace(
            step,
            checkpoint_ref=checkpoint_ref,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )

    return builder


def make_terminal_ready_closure_builder(
    *,
    closure_ref: ArtifactRef,
    step_status: StepStatus = StepStatus.SUCCEEDED,
    operation_status: OperationStatus = OperationStatus.SUCCEEDED,
) -> Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]]:
    """Return a pure terminal publication builder for LeaseSession.publish_operation."""

    if type(closure_ref) is not ArtifactRef:
        raise ValueError("closure_ref must be ArtifactRef")
    if type(step_status) is not StepStatus:
        raise ValueError("step_status must be StepStatus")
    if type(operation_status) is not OperationStatus:
        raise ValueError("operation_status must be OperationStatus")
    if not step_status.is_final_terminal():
        raise ValueError("step_status must be a final terminal status")
    if not operation_status.is_final_terminal():
        raise ValueError("operation_status must be a final terminal status")

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
            status=step_status,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=step.optimistic_version + 1,
        )
        terminal_operation = dataclasses.replace(
            operation,
            status=operation_status,
            ready_closure_ref=closure_ref,
            completed_at=transaction_now,
            updated_at=transaction_now,
            optimistic_version=operation.optimistic_version + 1,
        )
        return terminal_step, terminal_operation

    return builder


def envelope_for_step(
    *,
    key: JobStepKey,
    operation: OperationRecord,
    step: StepRecord,
    checkpoint_generation: int,
    job_state: Mapping[str, object],
) -> StepCheckpointEnvelope:
    """Build a checkpoint envelope aligned to transaction-fresh records."""

    return StepCheckpointEnvelope(
        job_kind=key.job_kind,
        step_name=key.step_name,
        operation_id=operation.operation_id,
        job_contract_version=operation.job_contract_version,
        checkpoint_generation=checkpoint_generation,
        prior_output_refs=step.prior_output_refs,
        job_state=dict(job_state),
    )


def _content_artifact_id(prefix: str, raw_bytes: bytes) -> str:
    return f"{prefix}:{raw_blob_digest(raw_bytes).value}"


def _parse_canonical_document_bytes(
    raw_bytes: bytes,
    *,
    shape_invalid_code: str,
    non_canonical_message: str,
) -> dict[str, object]:
    try:
        canonical = canonicalize_jcs(raw_bytes)
    except CanonicalEncodingError as exc:
        raise CheckpointDecodeError(str(exc), code=shape_invalid_code) from exc
    if canonical != raw_bytes:
        raise CheckpointDecodeError(non_canonical_message, code=shape_invalid_code)
    try:
        document = json.loads(canonical)
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise CheckpointDecodeError(non_canonical_message, code=shape_invalid_code) from exc
    if type(document) is not dict:
        raise CheckpointDecodeError(non_canonical_message, code=shape_invalid_code)
    return cast(dict[str, object], document)


def _reject_duplicate_artifact_ids(refs: tuple[ArtifactRef, ...]) -> None:
    seen: set[str] = set()
    for ref in refs:
        if ref.artifact_id in seen:
            raise ValueError("artifact refs must not contain duplicate artifact_id")
        seen.add(ref.artifact_id)


def _assert_sorted_unique_outputs(outputs: tuple[ReadyClosureEntry, ...]) -> None:
    previous_id: str | None = None
    for entry in outputs:
        artifact_id = entry.artifact_ref.artifact_id
        if previous_id is not None and artifact_id <= previous_id:
            raise ValueError("closure outputs must be strictly sorted by artifact_id")
        previous_id = artifact_id


def _require_closed_document(
    document: object,
    allowed_keys: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(document) is not dict:
        raise CheckpointDecodeError(f"{label} must be a JSON object", code="CHECKPOINT_SHAPE_INVALID")
    payload = cast(dict[str, object], document)
    extra = set(payload) - allowed_keys
    missing = allowed_keys - set(payload)
    if extra or missing:
        raise CheckpointDecodeError(f"{label} has unexpected keys", code="CHECKPOINT_SHAPE_INVALID")
    return payload


def _parse_artifact_ref_list(value: object, *, label: str) -> tuple[ArtifactRef, ...]:
    if type(value) is not list:
        raise CheckpointDecodeError(f"{label} must be a list", code="CHECKPOINT_SHAPE_INVALID")
    refs: list[ArtifactRef] = []
    for item in value:
        if type(item) is not dict:
            raise CheckpointDecodeError(f"{label} entries must be objects", code="CHECKPOINT_SHAPE_INVALID")
        refs.append(artifact_ref_from_dict(cast(dict[str, object], item)))
    if len(refs) > _MAX_REFS_PER_DOCUMENT:
        raise CheckpointDecodeError(f"{label} exceeds bounded document size", code="CHECKPOINT_SHAPE_INVALID")
    refs_tuple = tuple(refs)
    try:
        _reject_duplicate_artifact_ids(refs_tuple)
    except ValueError as exc:
        raise CheckpointDecodeError(str(exc), code="CHECKPOINT_SHAPE_INVALID") from exc
    return refs_tuple


def _require_string(payload: Mapping[str, object], key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise CheckpointDecodeError(f"{key} must be a string", code="CHECKPOINT_SHAPE_INVALID")
    if value == "":
        raise CheckpointDecodeError(f"{key} must not be empty", code="CHECKPOINT_SHAPE_INVALID")
    return value


def _require_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise CheckpointDecodeError(f"{key} must be a non-negative int", code="CHECKPOINT_SHAPE_INVALID")
    return value


def _object(payload: Mapping[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    if type(value) is not dict:
        raise CheckpointDecodeError(f"{key} must be an object", code="CHECKPOINT_SHAPE_INVALID")
    return cast(dict[str, object], value)


def _validate_bounded_diagnostic_code(value: str) -> None:
    if not _DIAGNOSTIC_CODE_RE.fullmatch(value):
        raise ValueError("diagnostic code must match bounded owner pattern")


def _validate_bounded_diagnostic_message(value: str) -> None:
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= _MAX_DECODER_MESSAGE_BYTES:
        raise ValueError("diagnostic message exceeds bounded owner size")


__all__ = [
    "CheckpointPublicationError",
    "ReadyClosureDocument",
    "ReadyClosureEntry",
    "STEP_CHECKPOINT_CONTRACT_VERSION",
    "READY_CLOSURE_CONTRACT_VERSION",
    "READY_CLOSURE_DOCUMENT_TYPE",
    "StepCheckpointEnvelope",
    "definition_matches_checkpoint",
    "envelope_for_step",
    "load_checkpoint_envelope",
    "load_ready_closure",
    "make_checkpoint_step_builder",
    "make_terminal_ready_closure_builder",
    "prepare_ready_closure",
    "prepare_step_checkpoint",
    "put_checkpoint_envelope",
    "put_ready_closure",
    "verify_artifact_refs",
]
