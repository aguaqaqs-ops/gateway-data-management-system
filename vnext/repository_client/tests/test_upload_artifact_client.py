"""Tests for the typed async upload client."""

from __future__ import annotations

import hashlib
import io

import httpx
import pytest

from gateway_repository_client import NonRewindableUploadSourceError, RepositoryClient
from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE, UploadArtifactResponse


def _upload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.asyncio
async def test_upload_artifact_retries_rewindable_source_on_503() -> None:
    attempts = {"count": 0}
    repository_id = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"
    artifact_id = "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11"
    payload = b"client-upload"

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                headers={"X-Request-ID": "req-1"},
            )
        assert request.headers["Idempotency-Key"] == "client-upload-key"
        assert request.read() == payload
        return httpx.Response(
            201,
            json={
                "artifact_ref": {
                    "artifact_id": artifact_id,
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

    response = await client.upload_artifact(
        repository_id=repository_id,
        idempotency_key="client-upload-key",
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        raw_sha256=_upload_sha256(payload),
        body=payload,
    )

    assert attempts["count"] == 2
    assert response == UploadArtifactResponse.model_validate(
        {
            "artifact_ref": {
                "artifact_id": artifact_id,
                "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                "size_bytes": len(payload),
                "raw_sha256": _upload_sha256(payload),
            }
        }
    )


@pytest.mark.asyncio
async def test_upload_artifact_rejects_nonrewindable_source_on_retryable_failure() -> None:
    payload = b"non-rewindable"

    class _OneShotStream:
        def __init__(self, data: bytes) -> None:
            self._data = data
            self._done = False

        def read(self, size: int = -1) -> bytes:
            if self._done:
                return b""
            self._done = True
            return self._data

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"code": "SERVICE_NOT_READY", "message": "not ready"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(NonRewindableUploadSourceError):
        await client.upload_artifact(
            repository_id="018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11",
            idempotency_key="non-rewindable",
            media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
            raw_sha256=_upload_sha256(payload),
            body=_OneShotStream(payload),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_upload_artifact_rewinds_file_like_source_between_retries() -> None:
    attempts = {"count": 0}
    payload = b"rewind-me"

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        assert request.read() == payload
        if attempts["count"] == 1:
            return httpx.Response(503, json={"code": "SERVICE_NOT_READY", "message": "not ready"})
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
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )

    await client.upload_artifact(
        repository_id="018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11",
        idempotency_key="rewindable",
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        raw_sha256=_upload_sha256(payload),
        body=io.BytesIO(payload),
    )
    assert attempts["count"] == 2
