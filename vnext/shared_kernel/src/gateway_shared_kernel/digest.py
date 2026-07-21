"""Semantic and raw-blob digest helpers."""

from __future__ import annotations

import hashlib

from gateway_shared_kernel.errors import CanonicalEncodingError, CanonicalErrorCode
from gateway_shared_kernel.types import DigestKind, DigestRef, SemanticDigest

_DOMAIN_PREFIX = b"gateway-vnext:"
_DOMAIN_SUFFIX = b":v1\0"


def _domain_prefix(kind: DigestKind) -> bytes:
    """Return ASCII semantic domain bytes for a registered digest kind."""
    return _DOMAIN_PREFIX + kind.value.encode("ascii") + _DOMAIN_SUFFIX


def semantic_digest(kind: DigestKind, payload: bytes) -> SemanticDigest:
    """Domain-separated SHA-256 over ``gateway-vnext:<kind>:v1\\0 || payload``."""
    if type(kind) is not DigestKind:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "digest kind must be DigestKind",
        )
    if type(payload) is not bytes:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "canonical payload must be bytes",
        )
    preimage = _domain_prefix(kind) + payload
    raw = hashlib.sha256(preimage).digest()
    return SemanticDigest.from_raw(kind, raw)


def raw_blob_digest(raw: bytes) -> DigestRef:
    """Direct SHA-256 of raw bytes with no semantic domain prefix."""
    if type(raw) is not bytes:
        raise CanonicalEncodingError(
            CanonicalErrorCode.CANONICAL_TYPE_MISMATCH,
            "raw blob must be bytes",
        )
    digest = hashlib.sha256(raw).digest()
    return DigestRef.from_raw_digest(digest)
