"""Bounded derived cache references; capabilities own their payload semantics."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import ContextManager, Protocol

import pyarrow as pa
from gateway_shared_kernel import CanonicalEncodingError, DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts.serialize import artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.store import ArtifactBufferStorePort, ArtifactStreamingStorePort
from gateway_backend.artifacts.types import ArtifactRef, assert_no_host_path_identity

COMPUTATION_CACHE_TTL_SECONDS = 86_400
MAX_CACHE_MANIFEST_BYTES = 1024 * 1024
MAX_CACHE_MEMBER_REFS_BYTES = 64 * 1024
CACHE_ACTIVE_INTENT = "active-computation-cache"
CacheReserve = Callable[[int], ContextManager[object]]


class ComputationCacheArtifactStore(ArtifactBufferStorePort, ArtifactStreamingStorePort, Protocol):
    """The existing buffer/stream/root-borrow capabilities used by the adapter."""


class ComputationCacheKind(StrEnum):
    COMPARISON = "comparison"
    RISK = "risk"


class InvalidComputationCachePayload(ValueError):
    """A bounded derived document is malformed; authority and DB faults are separate."""


def _identity(value: str, label: str) -> None:
    if type(value) is not str or not 1 <= len(value.encode("utf-8")) <= 255:
        raise ValueError(f"{label} must be a bounded nonempty identity")
    assert_no_host_path_identity(value, label=label)


@dataclass(frozen=True, slots=True)
class ComputationCacheKey:
    repository_id: str
    kind: ComputationCacheKind
    task_digest: DigestRef

    def __post_init__(self) -> None:
        _identity(self.repository_id, "repository_id")
        if type(self.kind) is not ComputationCacheKind or type(self.task_digest) is not DigestRef:
            raise ValueError("cache kind and task_digest must use their owning types")


@dataclass(frozen=True, slots=True)
class CacheOperationOwner:
    owner_kind: str
    operation_id: str

    def __post_init__(self) -> None:
        if self.owner_kind not in {"preview-operation", "history-compare-operation"}:
            raise ValueError("cache readers require the existing operation owner")
        _identity(self.operation_id, "operation_id")


@dataclass(frozen=True, slots=True)
class ComputationCacheEntry:
    key: ComputationCacheKey
    format: str
    manifest_ref: ArtifactRef
    member_refs: tuple[ArtifactRef, ...]

    def __post_init__(self) -> None:
        if type(self.key) is not ComputationCacheKey:
            raise ValueError("cache entry requires its exact scoped key")
        _identity(self.format, "cache format")
        if (type(self.manifest_ref) is not ArtifactRef
                or self.manifest_ref.media_type != "application/json"
                or self.manifest_ref.size_bytes > MAX_CACHE_MANIFEST_BYTES):
            raise ValueError("cache manifest must be bounded JSON")
        limit = 7 if self.key.kind is ComputationCacheKind.COMPARISON else 1
        if (type(self.member_refs) is not tuple or len(self.member_refs) > limit
                or any(type(ref) is not ArtifactRef for ref in self.member_refs)):
            raise ValueError("cache member reference closure exceeds its kind bound")
        refs = self.refs
        if len({ref.artifact_id for ref in refs}) != len(refs):
            raise ValueError("cache manifest/member ids must be distinct")

    @property
    def refs(self) -> tuple[ArtifactRef, ...]:
        return (self.manifest_ref, *self.member_refs)


def encode_cache_manifest(
    key: ComputationCacheKey, *, format: str, member_refs: tuple[ArtifactRef, ...],
    payload: dict[str, object],
) -> bytes:
    """Encode the shared reference envelope; payload remains capability-owned."""
    raw = canonicalize_json_value({
        "format": format,
        "kind": key.kind.value,
        "repository_id": key.repository_id,
        "task_digest": key.task_digest.value,
        "member_refs": [artifact_ref_to_dict(ref) for ref in member_refs],
        "payload": payload,
    })
    if len(raw) > MAX_CACHE_MANIFEST_BYTES:
        raise ValueError("cache manifest exceeds optional retention bound")
    return raw


def decode_cache_manifest(raw: bytes, entry: ComputationCacheEntry) -> dict[str, object]:
    try:
        return _decode_cache_manifest(raw, entry)
    except (ValueError, TypeError, RecursionError, CanonicalEncodingError):
        raise InvalidComputationCachePayload("invalid computation cache manifest") from None


def _decode_cache_manifest(raw: bytes, entry: ComputationCacheEntry) -> dict[str, object]:
    """Verify the exact registered reference closure before exposing the payload."""
    if len(raw) > MAX_CACHE_MANIFEST_BYTES:
        raise ValueError("cache manifest exceeds optional retention bound")
    value = json.loads(raw)
    if (not isinstance(value, dict)
            or set(value) != {"format", "kind", "repository_id", "task_digest", "member_refs", "payload"}
            or value["format"] != entry.format
            or value["kind"] != entry.key.kind.value
            or value["repository_id"] != entry.key.repository_id
            or value["task_digest"] != entry.key.task_digest.value
            or not isinstance(value["member_refs"], list)
            or not isinstance(value["payload"], dict)
            or canonicalize_json_value(value) != raw):
        raise ValueError("cache manifest scope/format/envelope mismatch")
    members = value["member_refs"]
    if any(not isinstance(ref, dict) for ref in members):
        raise ValueError("cache manifest member is invalid")
    if tuple(artifact_ref_from_dict(ref) for ref in members) != entry.member_refs:
        raise ValueError("cache manifest members differ from the registered closure")
    payload: dict[str, object] = value["payload"]
    return payload


class ComputationCacheLease(Protocol):
    @property
    def entry(self) -> ComputationCacheEntry: ...

    @property
    def payload(self) -> dict[str, object]: ...

    def open_buffer(self, ref: ArtifactRef) -> ContextManager[pa.Buffer]:
        """Borrow one registered member; the consumer prepays its mapped/decoded bytes."""

    def mark_used(self) -> bool:
        """After pair success, touch only this still-current entry and record its producer use."""

    def discard(self) -> bool:
        """Discard this exact manifest version after capability validation fails."""

    def close(self) -> None:
        """Close this read borrow; operation-owned pins survive overlapping leases."""


class ComputationCachePort(Protocol):
    def lookup_and_pin(
        self, key: ComputationCacheKey, *, owner: CacheOperationOwner,
        checkpoint: Callable[[], None], reserve: CacheReserve,
    ) -> ComputationCacheLease | None:
        """Root read borrow -> short DB pin -> bounded complete file/envelope validation."""

    def store(
        self, entry: ComputationCacheEntry,
        blobs: tuple[tuple[ArtifactRef, bytes], ...], *, owner: CacheOperationOwner,
        checkpoint: Callable[[], None], reserve: CacheReserve,
    ) -> bool:
        """After pair success: protect before writing, then atomically index the complete value."""

    def discard_if_same(self, entry: ComputationCacheEntry) -> bool: ...

    def release_operation_pins(self, owner: CacheOperationOwner) -> int:
        """After all operation consumers/leases close, release only cache intents."""
