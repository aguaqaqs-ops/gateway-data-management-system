"""Application-owned strict payload loading and versioned typed decoder seams."""

from __future__ import annotations

import dataclasses
import json
import re
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeAlias

from gateway_backend.application.job_definition_model import JobDefinition
from gateway_backend.artifacts.store import ArtifactStorePort, ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.operations.contracts import OperationRecord
from gateway_backend.operations.contracts import (
    validate_canonical_job_payload_bytes,
    validate_json_structure,
)

JOB_PAYLOAD_DOCUMENT_TYPE = "job-payload"
CHECKPOINT_DOCUMENT_TYPE = "step-checkpoint"

_DIAGNOSTIC_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_.:-]{0,127}$")
_MAX_DECODER_REGISTRY_ENTRIES = 256
_MAX_DECODER_MESSAGE_BYTES = 4 * 1024

PayloadDecoder: TypeAlias = Callable[[dict[str, object]], object]


class PayloadDecodeError(ValueError):
    """Bounded payload decode failure without a generic recovery taxonomy."""

    def __init__(self, message: str, *, code: str = "PAYLOAD_DECODE_FAILED") -> None:
        _validate_bounded_diagnostic_code(code)
        _validate_bounded_diagnostic_message(message)
        super().__init__(message)
        self.code = code


class CheckpointDecodeError(ValueError):
    """Bounded checkpoint decode failure on an independent version axis."""

    def __init__(self, message: str, *, code: str = "CHECKPOINT_DECODE_FAILED") -> None:
        _validate_bounded_diagnostic_code(code)
        _validate_bounded_diagnostic_message(message)
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PayloadDecoderRegistry:
    """Immutable in-memory registry mapping decoder_identity to typed decoders."""

    _decoders: Mapping[str, PayloadDecoder]

    @classmethod
    def build(cls, decoders: Mapping[str, PayloadDecoder]) -> PayloadDecoderRegistry:
        if not isinstance(decoders, Mapping):
            raise ValueError("decoders must be a mapping")
        if len(decoders) > _MAX_DECODER_REGISTRY_ENTRIES:
            raise ValueError("decoder registry exceeds bounded entry count")
        bound: dict[str, PayloadDecoder] = {}
        for decoder_identity, decoder in decoders.items():
            if type(decoder_identity) is not str:
                raise ValueError("decoder_identity must be a string")
            if not callable(decoder):
                raise ValueError("decoder must be callable")
            if decoder_identity in bound:
                raise ValueError("duplicate decoder_identity in decoder registry build")
            bound[decoder_identity] = decoder
        return PayloadDecoderRegistry(_decoders=types.MappingProxyType(bound))

    def decode(self, decoder_identity: str, payload_object: dict[str, object]) -> object:
        if type(decoder_identity) is not str:
            raise PayloadDecodeError(
                "decoder_identity must be a string",
                code="PAYLOAD_DECODER_IDENTITY_INVALID",
            )
        decoder = self._decoders.get(decoder_identity)
        if decoder is None:
            raise PayloadDecodeError(
                "decoder_identity is not registered",
                code="PAYLOAD_DECODER_NOT_REGISTERED",
            )
        if type(payload_object) is not dict:
            raise PayloadDecodeError(
                "payload object must be a JSON object",
                code="PAYLOAD_SHAPE_INVALID",
            )
        try:
            decoded = decoder(payload_object)
        except PayloadDecodeError:
            raise
        except ValueError as exc:
            raise PayloadDecodeError(str(exc), code="PAYLOAD_TYPED_DECODE_FAILED") from exc
        except TypeError as exc:
            raise PayloadDecodeError(str(exc), code="PAYLOAD_TYPED_DECODE_FAILED") from exc
        _assert_reencodable_decoder_output(decoded)
        return decoded


def load_job_payload_bytes(
    operation: OperationRecord,
    store: ArtifactStorePort,
) -> bytes:
    """Load inline or referenced payload bytes with R1 canonical bounds."""

    if type(operation) is not OperationRecord:
        raise PayloadDecodeError("operation must be OperationRecord", code="PAYLOAD_OPERATION_INVALID")
    inline_present = operation.job_payload is not None
    ref_present = operation.job_payload_ref is not None
    if inline_present == ref_present:
        raise PayloadDecodeError(
            "job_payload and job_payload_ref must be mutually exclusive",
            code="PAYLOAD_BINDING_INVALID",
        )
    if inline_present:
        payload_bytes = operation.job_payload
        if type(payload_bytes) is not bytes:
            raise PayloadDecodeError(
                "job_payload must be canonical JSON bytes",
                code="PAYLOAD_SHAPE_INVALID",
            )
        try:
            validate_canonical_job_payload_bytes(payload_bytes)
        except ValueError as exc:
            raise PayloadDecodeError(str(exc), code="PAYLOAD_SHAPE_INVALID") from exc
        return payload_bytes
    payload_ref = operation.job_payload_ref
    if type(payload_ref) is not ArtifactRef:
        raise PayloadDecodeError(
            "job_payload_ref must be ArtifactRef",
            code="PAYLOAD_REF_INVALID",
        )
    try:
        raw_bytes = store.locate(payload_ref)
    except ManifestVerificationError as exc:
        raise PayloadDecodeError(str(exc), code="PAYLOAD_REF_UNREADABLE") from exc
    try:
        validate_canonical_job_payload_bytes(raw_bytes)
    except ValueError as exc:
        raise PayloadDecodeError(str(exc), code="PAYLOAD_SHAPE_INVALID") from exc
    return raw_bytes


def decode_job_payload(
    definition: JobDefinition,
    operation: OperationRecord,
    store: ArtifactStorePort,
    decoder_registry: PayloadDecoderRegistry,
) -> object:
    """Decode one operation payload through identity axes and a registered typed decoder."""

    _assert_document_kind_axis(JOB_PAYLOAD_DOCUMENT_TYPE)
    if type(definition) is not JobDefinition:
        raise PayloadDecodeError("definition must be JobDefinition", code="PAYLOAD_DEFINITION_INVALID")
    if type(decoder_registry) is not PayloadDecoderRegistry:
        raise PayloadDecodeError(
            "decoder_registry must be PayloadDecoderRegistry",
            code="PAYLOAD_DECODER_REGISTRY_INVALID",
        )
    _validate_payload_identity_axes(definition, operation)
    payload_bytes = load_job_payload_bytes(operation, store)
    payload_object = _parse_bounded_payload_object(payload_bytes)
    return decoder_registry.decode(definition.decoder_identity, payload_object)


def _validate_payload_identity_axes(definition: JobDefinition, operation: OperationRecord) -> None:
    if operation.job_kind != definition.key.job_kind:
        raise PayloadDecodeError(
            "operation job_kind does not match JobDefinition key",
            code="PAYLOAD_JOB_KIND_MISMATCH",
        )
    if operation.job_contract_version not in definition.supported_payload_versions:
        raise PayloadDecodeError(
            "job_contract_version is not supported by the JobDefinition",
            code="PAYLOAD_CONTRACT_VERSION_UNSUPPORTED",
        )


def _parse_bounded_payload_object(payload_bytes: bytes) -> dict[str, object]:
    try:
        payload = json.loads(payload_bytes)
    except (TypeError, UnicodeDecodeError, ValueError) as exc:
        raise PayloadDecodeError(
            "job_payload must be canonical JSON bytes",
            code="PAYLOAD_SHAPE_INVALID",
        ) from exc
    if type(payload) is not dict:
        raise PayloadDecodeError(
            "job_payload must be a JSON object",
            code="PAYLOAD_SHAPE_INVALID",
        )
    try:
        validate_json_structure(payload)
    except ValueError as exc:
        raise PayloadDecodeError(str(exc), code="PAYLOAD_SHAPE_INVALID") from exc
    return payload


def _assert_document_kind_axis(document_kind: str) -> None:
    if document_kind != JOB_PAYLOAD_DOCUMENT_TYPE:
        raise PayloadDecodeError(
            "document kind is not a job payload axis",
            code="PAYLOAD_DOCUMENT_KIND_MISMATCH",
        )


def _assert_reencodable_decoder_output(value: object) -> None:
    if type(value) is ArtifactRef:
        return
    if type(value) is dict:
        try:
            validate_json_structure(value)
        except ValueError as exc:
            raise PayloadDecodeError(str(exc), code="PAYLOAD_TYPED_OUTPUT_INVALID") from exc
        return
    if _is_frozen_dataclass_instance(value):
        return
    raise PayloadDecodeError(
        "typed decoder output must be re-encodable bounded document or ArtifactRef",
        code="PAYLOAD_TYPED_OUTPUT_INVALID",
    )


def _is_frozen_dataclass_instance(value: object) -> bool:
    if not dataclasses.is_dataclass(value) or isinstance(value, type):
        return False
    params = getattr(type(value), "__dataclass_params__", None)
    return params is not None and bool(params.frozen)


def _validate_bounded_diagnostic_code(value: str) -> None:
    if not _DIAGNOSTIC_CODE_RE.fullmatch(value):
        raise ValueError("diagnostic code must match bounded owner pattern")


def _validate_bounded_diagnostic_message(value: str) -> None:
    encoded = value.encode("utf-8")
    if not 1 <= len(encoded) <= _MAX_DECODER_MESSAGE_BYTES:
        raise ValueError("diagnostic message exceeds bounded owner size")


__all__ = [
    "CHECKPOINT_DOCUMENT_TYPE",
    "CheckpointDecodeError",
    "JOB_PAYLOAD_DOCUMENT_TYPE",
    "PayloadDecodeError",
    "PayloadDecoder",
    "PayloadDecoderRegistry",
    "decode_job_payload",
    "load_job_payload_bytes",
]
