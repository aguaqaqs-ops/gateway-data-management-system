"""Artifact envelope models and location-independent identity rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from gateway_shared_kernel import DigestRef

IJSON_MAX_SAFE_INTEGER = (2**53) - 1
LOGICAL_REF_PREFIX = "gateway-vnext.artifacts/v1/ref/"
_LOGICAL_SEGMENT_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LOGICAL_REF_PATTERN = re.compile(
    r"^gateway-vnext\.artifacts/v1/ref/"
    r"[a-z0-9]+(?:-[a-z0-9]+)*/"
    r"[a-z0-9]+(?:-[a-z0-9]+)*$"
)
_FORBIDDEN_IDENTITY_KEYS = frozenset(
    {
        "path",
        "host_path",
        "filesystem_path",
        "artifact_root",
        "file_path",
        "absolute_path",
        "provider_path",
        "temporary_root",
    }
)
_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
_TRAVERSAL_SEGMENT_PATTERN = re.compile(r"(^|[\\/])\.\.?($|[\\/])")


class RetentionClass(StrEnum):
    OPERATION = "operation"
    STAGED_DURABLE = "staged-durable"
    RECOMPUTABLE_CACHE = "recomputable-cache"


class ArtifactResolver(StrEnum):
    """Closed location-independent resolver protocol."""

    ARTIFACT_STORE = "artifact-store"


@dataclass(frozen=True, slots=True)
class ContentContract:
    contract_id: str
    semantic_version: str

    def __post_init__(self) -> None:
        if not self.contract_id:
            raise ValueError("contract_id must be non-empty")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.semantic_version):
            raise ValueError("semantic_version must be semver")


@dataclass(frozen=True, slots=True)
class ContractBinding:
    contract_id: str
    semantic_version: str

    def __post_init__(self) -> None:
        if not self.contract_id:
            raise ValueError("contract_id must be non-empty")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", self.semantic_version):
            raise ValueError("semantic_version must be semver")


@dataclass(frozen=True, slots=True)
class AccessMetadata:
    """Generic resolver metadata; provider/root/path never enters the wire."""

    resolver: ArtifactResolver = ArtifactResolver.ARTIFACT_STORE

    def __post_init__(self) -> None:
        if type(self.resolver) is not ArtifactResolver:
            raise ValueError("access_metadata.resolver must be ArtifactResolver")


@runtime_checkable
class ArtifactContentManifest(Protocol):
    """Identity projection required from a capability-owned content DTO."""

    @property
    def content_schema_id(self) -> str: ...

    @property
    def media_type(self) -> str: ...

    @property
    def contract_binding(self) -> ContractBinding: ...

    @property
    def semantic_content_digest(self) -> DigestRef: ...

    @property
    def identity_key(self) -> tuple[object, ...]: ...

    def to_wire_dict(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True, eq=False)
class ArtifactRef:
    artifact_ref_schema_version: int
    logical_ref: str
    media_type: str
    size_bytes: int
    raw_sha256: DigestRef
    content_digest: DigestRef
    content_contract: ContentContract
    content_schema_id: str
    retention_class: RetentionClass
    access_metadata: AccessMetadata

    def __post_init__(self) -> None:
        if type(self.artifact_ref_schema_version) is not int:
            raise ValueError("artifact_ref_schema_version must be an integer")
        if self.artifact_ref_schema_version != 1:
            raise ValueError("artifact_ref_schema_version must be 1")
        validate_logical_ref(self.logical_ref)
        _validate_size_bytes(self.size_bytes)
        if type(self.raw_sha256) is not DigestRef:
            raise ValueError("raw_sha256 must be DigestRef")
        if type(self.content_digest) is not DigestRef:
            raise ValueError("content_digest must be DigestRef")
        if type(self.content_contract) is not ContentContract:
            raise ValueError("content_contract must be ContentContract")
        if type(self.content_schema_id) is not str or not self.content_schema_id:
            raise ValueError("content_schema_id must be a non-empty string")
        _validate_envelope_contract(
            media_type=self.media_type,
            content_contract=self.content_contract,
            content_schema_id=self.content_schema_id,
        )
        if type(self.retention_class) is not RetentionClass:
            raise ValueError("retention_class must be RetentionClass")
        if type(self.access_metadata) is not AccessMetadata:
            raise ValueError("access_metadata must be AccessMetadata")

    @property
    def logical_identity(self) -> str:
        """Stable caller-assigned identity, independent of raw/semantic digests."""

        return self.logical_ref

    @property
    def integrity_identity(self) -> tuple[int, str]:
        return (self.size_bytes, self.raw_sha256.value)

    @property
    def semantic_identity(self) -> tuple[str, str, str, str]:
        return (
            self.content_contract.contract_id,
            self.content_contract.semantic_version,
            self.content_schema_id,
            self.content_digest.value,
        )

    @property
    def cache_key(self) -> tuple[object, ...]:
        """Exact stable ref key; physical provider/root is intentionally absent."""

        return (
            self.logical_identity,
            *self.integrity_identity,
            *self.semantic_identity,
            self.media_type,
            self.retention_class.value,
            self.access_metadata.resolver.value,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ArtifactRef):
            return NotImplemented
        return self.cache_key == other.cache_key


@dataclass(frozen=True, slots=True, eq=False)
class ArtifactManifest:
    """Generic envelope composed with a capability-owned content manifest."""

    manifest_schema_version: int
    logical_ref: str
    media_type: str
    size_bytes: int
    raw_sha256: DigestRef
    content_digest: DigestRef
    content_contract: ContentContract
    content_schema_id: str
    retention_class: RetentionClass
    access_metadata: AccessMetadata
    content: ArtifactContentManifest

    def __post_init__(self) -> None:
        if type(self.manifest_schema_version) is not int:
            raise ValueError("manifest_schema_version must be an integer")
        if self.manifest_schema_version != 1:
            raise ValueError("manifest_schema_version must be 1")
        envelope = self.to_envelope()
        if not isinstance(self.content, ArtifactContentManifest):
            raise ValueError("content must implement the ArtifactContentManifest protocol")
        if self.content.content_schema_id != envelope.content_schema_id:
            raise ValueError("content_schema_id must match content manifest")
        if self.content.media_type != envelope.media_type:
            raise ValueError("media_type must match content manifest")
        if self.content.contract_binding.contract_id != self.content_contract.contract_id:
            raise ValueError("content contract_id must match content manifest")
        if self.content.contract_binding.semantic_version != self.content_contract.semantic_version:
            raise ValueError("content semantic_version must match content manifest")
        if self.content.semantic_content_digest.value != self.content_digest.value:
            raise ValueError("content_digest must match content manifest")

    @property
    def cache_key(self) -> tuple[object, ...]:
        return (*self.to_envelope().cache_key, self.content.identity_key)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ArtifactManifest):
            return NotImplemented
        return self.cache_key == other.cache_key

    def to_envelope(self) -> ArtifactRef:
        return ArtifactRef(
            artifact_ref_schema_version=1,
            logical_ref=self.logical_ref,
            media_type=self.media_type,
            size_bytes=self.size_bytes,
            raw_sha256=self.raw_sha256,
            content_digest=self.content_digest,
            content_contract=self.content_contract,
            content_schema_id=self.content_schema_id,
            retention_class=self.retention_class,
            access_metadata=self.access_metadata,
        )


def validate_logical_ref(logical_ref: str) -> None:
    if type(logical_ref) is not str:
        raise ValueError("logical_ref must be a string")
    if not _LOGICAL_REF_PATTERN.fullmatch(logical_ref):
        raise ValueError(
            "logical_ref must match gateway-vnext.artifacts/v1/ref/<namespace>/<artifact-id>"
        )
    namespace, artifact_id = logical_ref.removeprefix(LOGICAL_REF_PREFIX).split("/")
    if len(namespace) > 63 or len(artifact_id) > 128:
        raise ValueError("logical_ref namespace/id exceeds the v1 length limit")
    if not _LOGICAL_SEGMENT_PATTERN.fullmatch(namespace):
        raise ValueError("logical_ref namespace is invalid")
    if not _LOGICAL_SEGMENT_PATTERN.fullmatch(artifact_id):
        raise ValueError("logical_ref artifact-id is invalid")


def assert_no_host_path_identity(payload: object, *, label: str = "artifact identity") -> None:
    """Reject path-shaped keys and values as defense in depth."""

    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _FORBIDDEN_IDENTITY_KEYS:
                raise ValueError(f"{label} must not contain forbidden key {key!r}")
            assert_no_host_path_identity(value, label=f"{label}.{key}")
        return
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            assert_no_host_path_identity(item, label=f"{label}[{index}]")
        return
    if not isinstance(payload, str):
        return
    lowered = payload.casefold()
    if (
        "\x00" in payload
        or "\\" in payload
        or "%" in payload
        or payload.startswith("/")
        or payload.startswith("//")
        or lowered.startswith("file:")
        or _WINDOWS_DRIVE_PATTERN.match(payload)
        or _TRAVERSAL_SEGMENT_PATTERN.search(payload)
    ):
        raise ValueError(f"{label} must not contain host path value")


def _validate_size_bytes(value: int) -> None:
    if type(value) is not int or value < 0 or value > IJSON_MAX_SAFE_INTEGER:
        raise ValueError("size_bytes must be a non-negative I-JSON safe integer")


def _validate_envelope_contract(
    *,
    media_type: str,
    content_contract: ContentContract,
    content_schema_id: str,
) -> None:
    from gateway_backend.artifacts.contracts import lookup_content_contract

    spec = lookup_content_contract(content_contract.contract_id)
    if content_contract.semantic_version != spec.semantic_version:
        raise ValueError("content_contract semantic_version mismatch")
    if content_schema_id != spec.content_schema_id:
        raise ValueError("content_schema_id mismatch")
    if media_type != spec.media_type:
        raise ValueError("media_type mismatch")
