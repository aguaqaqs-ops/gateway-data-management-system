"""Shared helpers for upload artifact tests."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from uuid import UUID

from fastapi.testclient import TestClient

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE


def upload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def upload_headers(
    *,
    token: str = "test-bearer-token",
    idempotency_key: str = "upload-key-1",
    payload: bytes = b"artifact-bytes",
    raw_sha256: str | None = None,
    content_type: str = REPOSITORY_IMPORT_MEDIA_TYPE,
) -> dict[str, str]:
    digest = raw_sha256 or upload_sha256(payload)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "Content-Length": str(len(payload)),
        "Idempotency-Key": idempotency_key,
        "X-Artifact-SHA256": digest,
    }


def chunked_payload(payload: bytes, *, chunk_size: int) -> Iterable[bytes]:
    for offset in range(0, len(payload), chunk_size):
        yield payload[offset : offset + chunk_size]


def create_repository(client: TestClient, *, idempotency_key: str = "create-for-upload") -> UUID:
    response = client.post(
        "/v1/repositories",
        headers={
            "Authorization": "Bearer test-bearer-token",
            "Idempotency-Key": idempotency_key,
        },
    )
    assert response.status_code == 201
    return UUID(response.json()["repository_id"])
