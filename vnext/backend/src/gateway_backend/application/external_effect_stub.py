"""Test-only deterministic external-effect stub for R4 identity and recovery evidence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.types import ArtifactRef

STUB_REQUEST_DOCUMENT_TYPE = "external-effect-stub-request"
STUB_REQUEST_CONTRACT_VERSION = "backend-vnext/synthetic/stub/request/v1"
STUB_RESPONSE_DOCUMENT_TYPE = "external-effect-stub-response"
STUB_RESPONSE_CONTRACT_VERSION = "backend-vnext/synthetic/stub/response/v1"

_MAX_IDEMPOTENCY_KEY_BYTES = 255
_MAX_REQUEST_BODY_BYTES = 256


class StubOutcome(StrEnum):
    """Bounded test outcomes for the external-effect stub synthetic job."""

    ACCEPTED = "accepted"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ExternalEffectStubRequest:
    """Bounded immutable request input for the external-effect stub."""

    idempotency_key: str
    request_body: str


class ExternalEffectStub(ABC):
    """Test-only port that returns deterministic operation identity without real I/O."""

    @abstractmethod
    def submit(
        self,
        idempotency_key: str,
        request_ref: ArtifactRef,
    ) -> str:
        """Return the stable operation identity for one durable request submission."""


class DeterministicExternalEffectStub(ExternalEffectStub):
    """Pure in-process stub that derives identity from the idempotency key and request bytes."""

    def __init__(self, *, request_bytes: bytes) -> None:
        self._request_bytes = request_bytes

    def submit(
        self,
        idempotency_key: str,
        request_ref: ArtifactRef,
    ) -> str:
        del request_ref
        return compute_operation_identity(idempotency_key, self._request_bytes)


class RecordingExternalEffectStub(ExternalEffectStub):
    """Wrapper that records submit invocations for blind-replay contract tests."""

    def __init__(self, inner: ExternalEffectStub) -> None:
        self._inner = inner
        self.submit_count = 0
        self.last_idempotency_key: str | None = None

    def submit(
        self,
        idempotency_key: str,
        request_ref: ArtifactRef,
    ) -> str:
        self.submit_count += 1
        self.last_idempotency_key = idempotency_key
        return self._inner.submit(idempotency_key, request_ref)


def decode_stub_outcome(value: object) -> StubOutcome:
    if type(value) is not str:
        raise ValueError("stub_outcome must be a string")
    try:
        return StubOutcome(value)
    except ValueError as exc:
        raise ValueError("stub_outcome must be accepted, confirmed, or unknown") from exc


def decode_external_effect_stub_request(payload_object: dict[str, object]) -> ExternalEffectStubRequest:
    idempotency_key = payload_object.get("idempotency_key")
    request_body = payload_object.get("request_body")
    stub_outcome = payload_object.get("stub_outcome")
    if type(idempotency_key) is not str or not idempotency_key:
        raise ValueError("idempotency_key must be a non-empty string")
    if len(idempotency_key.encode("utf-8")) > _MAX_IDEMPOTENCY_KEY_BYTES:
        raise ValueError("idempotency_key exceeds bounded payload size")
    if type(request_body) is not str or not request_body:
        raise ValueError("request_body must be a non-empty string")
    if len(request_body.encode("utf-8")) > _MAX_REQUEST_BODY_BYTES:
        raise ValueError("request_body exceeds bounded payload size")
    decode_stub_outcome(stub_outcome)
    return ExternalEffectStubRequest(
        idempotency_key=idempotency_key,
        request_body=request_body,
    )


def build_request_bytes(idempotency_key: str, request_body: str) -> bytes:
    """Return canonical JCS request bytes for one immutable external-effect submission."""

    document = {
        "contract_version": STUB_REQUEST_CONTRACT_VERSION,
        "document_type": STUB_REQUEST_DOCUMENT_TYPE,
        "idempotency_key": idempotency_key,
        "request_body": request_body,
    }
    return canonicalize_json_value(document)


def build_response_bytes(
    operation_identity: str,
    idempotency_key: str,
    *,
    outcome: StubOutcome,
) -> bytes:
    """Return canonical JCS response bytes for one confirmed stub outcome."""

    document = {
        "contract_version": STUB_RESPONSE_CONTRACT_VERSION,
        "document_type": STUB_RESPONSE_DOCUMENT_TYPE,
        "idempotency_key": idempotency_key,
        "operation_identity": operation_identity,
        "outcome": outcome.value,
    }
    return canonicalize_json_value(document)


def compute_operation_identity(idempotency_key: str, request_bytes: bytes) -> str:
    """Derive a stable operation identity from the idempotency key and request digest."""

    request_digest = raw_blob_digest(request_bytes).value
    material = f"{idempotency_key}:{request_digest}".encode("utf-8")
    return f"synthetic-stub-op:{raw_blob_digest(material).value}"


def request_artifact_id(request_bytes: bytes) -> str:
    return f"external-effect-stub-request:{raw_blob_digest(request_bytes).value}"


def response_artifact_id(response_bytes: bytes) -> str:
    return f"external-effect-stub-response:{raw_blob_digest(response_bytes).value}"


__all__ = [
    "DeterministicExternalEffectStub",
    "ExternalEffectStub",
    "ExternalEffectStubRequest",
    "RecordingExternalEffectStub",
    "STUB_REQUEST_CONTRACT_VERSION",
    "STUB_REQUEST_DOCUMENT_TYPE",
    "STUB_RESPONSE_CONTRACT_VERSION",
    "STUB_RESPONSE_DOCUMENT_TYPE",
    "StubOutcome",
    "build_request_bytes",
    "build_response_bytes",
    "compute_operation_identity",
    "decode_external_effect_stub_request",
    "decode_stub_outcome",
    "request_artifact_id",
    "response_artifact_id",
]
