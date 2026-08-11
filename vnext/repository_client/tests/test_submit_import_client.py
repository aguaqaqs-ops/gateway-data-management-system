"""submit_versioned_import idempotency and retry semantics."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID

import httpx
import pytest

from gateway_repository_client import RepositoryClient
from gateway_repository_contracts import (
    REPOSITORY_IMPORT_MEDIA_TYPE,
    SubmitVersionedImportRequest,
    SubmitVersionedImportResponse,
)

REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
ARTIFACT_ID = "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11"
OP_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")


def _import_request(*, expected_commit_id: str = "commit-c0") -> SubmitVersionedImportRequest:
    return SubmitVersionedImportRequest.model_validate(
        {
            "repository_id": REPO_ID,
            "artifact_ref": {
                "artifact_id": ARTIFACT_ID,
                "media_type": REPOSITORY_IMPORT_MEDIA_TYPE,
                "size_bytes": 12,
                "raw_sha256": "a" * 64,
            },
            "target_ref": "main",
            "expected_commit_id": expected_commit_id,
        }
    )


@pytest.mark.asyncio
async def test_submit_import_retries_same_idempotency_key_and_body() -> None:
    attempts = {"count": 0}
    bodies: list[bytes] = []
    keys: list[str] = []

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        bodies.append(request.read())
        keys.append(request.headers["Idempotency-Key"])
        if attempts["count"] == 1:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                headers={"X-Request-ID": "req-1"},
            )
        return httpx.Response(
            202,
            json={"operation_id": str(OP_ID)},
            headers={"X-Request-ID": "req-2"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )
    request = _import_request()
    response = await client.submit_versioned_import(
        idempotency_key="import-key",
        request=request,
    )

    assert attempts["count"] == 2
    assert keys == ["import-key", "import-key"]
    assert bodies[0] == bodies[1]
    assert json.loads(bodies[0]) == request.model_dump(mode="json")
    assert response == SubmitVersionedImportResponse(operation_id=OP_ID)


@pytest.mark.asyncio
async def test_submit_import_does_not_rewrite_key_or_body_on_caller_mutation() -> None:
    """Client must send exact caller-provided key and body; it does not mint a new key."""

    seen: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.headers["Idempotency-Key"], request.read()))
        return httpx.Response(
            202,
            json={"operation_id": str(OP_ID)},
            headers={"X-Request-ID": f"req-{len(seen)}"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )

    first = _import_request(expected_commit_id="commit-c0")
    second = _import_request(expected_commit_id="commit-c1")
    await client.submit_versioned_import(idempotency_key="same-key", request=first)
    await client.submit_versioned_import(idempotency_key="same-key", request=second)

    assert seen[0][0] == "same-key"
    assert seen[1][0] == "same-key"
    assert seen[0][1] != seen[1][1]
    assert json.loads(seen[0][1])["expected_commit_id"] == "commit-c0"
    assert json.loads(seen[1][1])["expected_commit_id"] == "commit-c1"


@pytest.mark.asyncio
async def test_submit_import_snapshot_freezes_path_and_body_across_retry() -> None:
    attempts = {"count": 0}
    barrier = asyncio.Event()
    captured: list[tuple[str, bytes, str]] = []
    mutated_repo = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c99")

    async def sleeper(_seconds: float) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            request = _import_request()
            request.repository_id = mutated_repo
            barrier.set()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.url.path, request.read(), request.headers["Idempotency-Key"]))
        if len(captured) == 1:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                headers={"X-Request-ID": "req-1"},
            )
        return httpx.Response(
            202,
            json={"operation_id": str(OP_ID)},
            headers={"X-Request-ID": "req-2"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )
    request = _import_request()
    await client.submit_versioned_import(idempotency_key="import-key", request=request)

    assert len(captured) == 2
    first_path, first_body, first_key = captured[0]
    second_path, second_body, second_key = captured[1]
    assert first_path == second_path
    assert first_body == second_body
    assert first_key == second_key
    assert str(mutated_repo) not in first_path
    assert json.loads(first_body)["repository_id"] == str(REPO_ID)
