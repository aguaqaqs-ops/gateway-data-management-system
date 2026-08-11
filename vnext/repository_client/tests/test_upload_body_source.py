"""Tests for upload body source contract and coercion."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from gateway_repository_client import (
    NonRewindableUploadSourceError,
    RepositoryClient,
    UploadBodySource,
    coerce_upload_body_source,
)
from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE


def _upload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_nonrewindable_body_without_declared_size_fails_before_request() -> None:
    class _ReadOnlyStream:
        def read(self, size: int = -1) -> bytes:
            return b""

    with pytest.raises(NonRewindableUploadSourceError, match="declared_size"):
        coerce_upload_body_source(_ReadOnlyStream())  # type: ignore[arg-type]


def test_coerce_upload_body_source_passes_through_upload_body_source() -> None:
    payload = b"pass-through"
    source = UploadBodySource(
        declared_size=len(payload),
        rewindable=True,
        _open_chunks=lambda: iter([payload]),
    )

    assert coerce_upload_body_source(source) is source


@pytest.mark.asyncio
async def test_upload_artifact_accepts_public_upload_body_source() -> None:
    payload = b"factory-reopen"
    factory_calls = {"count": 0}
    attempts = {"count": 0}

    def factory() -> list[bytes]:
        factory_calls["count"] += 1
        return [payload]

    source = UploadBodySource(
        declared_size=len(payload),
        rewindable=True,
        _open_chunks=lambda: iter(factory()),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        assert request.read() == payload
        if attempts["count"] == 1:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                headers={"X-Request-ID": "req-1"},
            )
        return httpx.Response(
            201,
            json={
                "artifact_ref": {
                    "artifact_id": "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11",
                    "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                    "size_bytes": len(payload),
                    "raw_sha256": _upload_sha256(payload),
                }
            },
            headers={"X-Request-ID": "req-2"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )

    await client.upload_artifact(
        repository_id="018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11",
        idempotency_key="upload-body-source",
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        raw_sha256=_upload_sha256(payload),
        body=source,
    )

    assert attempts["count"] == 2
    assert factory_calls["count"] == 2
