"""Backend artifact ID and raw integrity helpers."""

from __future__ import annotations

import re

from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.types import validate_artifact_id

_ARTIFACT_ID_SEGMENT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def build_artifact_id(namespace: str, suffix: str) -> str:
    """Build a bounded opaque ID for local tests and owner-created artifacts."""

    if not _ARTIFACT_ID_SEGMENT.fullmatch(namespace):
        raise ValueError("artifact namespace is invalid")
    if not _ARTIFACT_ID_SEGMENT.fullmatch(suffix):
        raise ValueError("artifact suffix is invalid")
    artifact_id = f"{namespace}-{suffix}"
    validate_artifact_id(artifact_id)
    return artifact_id


def raw_sha256_from_bytes(raw_bytes: bytes) -> DigestRef:
    return raw_blob_digest(raw_bytes)
