"""Backend artifact ID and raw integrity helpers."""
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.location import build_artifact_id

__all__ = ["build_artifact_id", "raw_sha256_from_bytes"]


def raw_sha256_from_bytes(raw_bytes: bytes) -> DigestRef:
    return raw_blob_digest(raw_bytes)
