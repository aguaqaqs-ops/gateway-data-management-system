"""Artifact raw identity and logical-reference helpers."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.types import LOGICAL_REF_PREFIX, validate_logical_ref


def build_logical_ref(namespace: str, artifact_id: str) -> str:
    """Build a caller-owned logical identity without deriving it from a digest."""

    logical_ref = f"{LOGICAL_REF_PREFIX}{namespace}/{artifact_id}"
    validate_logical_ref(logical_ref)
    return logical_ref


def raw_sha256_from_bytes(raw_bytes: bytes) -> DigestRef:
    return raw_blob_digest(raw_bytes)
