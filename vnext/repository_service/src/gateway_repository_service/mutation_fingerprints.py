"""Deterministic internal request fingerprints for synchronous mutations."""

from __future__ import annotations

import struct

CREATE_REPOSITORY_FINGERPRINT_V1 = b"create_repository/v1\x00"
UPLOAD_ARTIFACT_FINGERPRINT_PREFIX_V1 = b"upload_artifact/v1\x00"


def create_repository_fingerprint_v1() -> bytes:
    return CREATE_REPOSITORY_FINGERPRINT_V1


def upload_artifact_fingerprint_v1(
    *,
    media_type: str,
    declared_size: int,
    raw_sha256_hex: str,
) -> bytes:
    if declared_size < 0:
        raise ValueError("declared_size must be non-negative")
    if len(raw_sha256_hex) != 64:
        raise ValueError("raw_sha256_hex must be 64 lowercase hex characters")
    raw_sha256 = bytes.fromhex(raw_sha256_hex)
    return (
        UPLOAD_ARTIFACT_FINGERPRINT_PREFIX_V1
        + media_type.encode("utf-8")
        + b"\x00"
        + struct.pack(">Q", declared_size)
        + raw_sha256
    )
