"""GET bounded-retry behavior for versioned read/operation endpoints."""

from __future__ import annotations

import httpx
import pytest

from gateway_repository_client import RepositoryClient, RepositoryClientError, RepositoryProtocolError


from uuid import UUID

REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
OP_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c22")
COMMIT_ID = "commit-c1"


def _operation_payload(*, status: str = "SUCCEEDED") -> dict[str, object]:
    payload: dict[str, object] = {
        "operation_id": str(OP_ID),
        "status": status,
        "result": None,
        "error": None,
    }
    if status == "SUCCEEDED":
        payload["result"] = {
            "commit_id": COMMIT_ID,
            "target_ref": "main",
            "artifact_id": "018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c33",
            "canonicalization_manifest_digest": "digest",
            "expected_commit_id": "commit-c0",
            "completed_verification_policy": "STRUCTURAL",
            "unknown_type_policy": "REJECT",
        }
    elif status == "FAILED":
        payload["error"] = {
            "code": "IMPORT_REJECTED",
            "message": "rejected",
            "request_id": None,
        }
    return payload


@pytest.mark.asyncio
async def test_get_operation_retries_network_and_503_at_most_three_times() -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                headers={"X-Request-ID": f"req-{attempts['count']}"},
            )
        return httpx.Response(
            200,
            json={"operation": _operation_payload()},
            headers={"X-Request-ID": "req-ok"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )

    response = await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert attempts["count"] == 3
    assert len(sleeps) == 2
    assert response.operation.status.value == "SUCCEEDED"


@pytest.mark.asyncio
async def test_get_operation_retries_transport_error() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(
            200,
            json={"operation": _operation_payload()},
            headers={"X-Request-ID": "req-ok"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )

    response = await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)
    assert attempts["count"] == 2
    assert response.operation.operation_id is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [404, 422])
async def test_get_does_not_retry_non_retryable_status(status_code: int) -> None:
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        code = "COMMIT_NOT_FOUND" if status_code == 404 else "REQUEST_VALIDATION_FAILED"
        return httpx.Response(
            status_code,
            json={"code": code, "message": "nope", "request_id": "req-err"},
            headers={"X-Request-ID": "req-err"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RepositoryClientError) as exc_info:
        await client.get_versioned_catalog(repository_id=REPO_ID, commit_id=COMMIT_ID)

    assert attempts["count"] == 1
    assert exc_info.value.status_code == status_code


@pytest.mark.asyncio
async def test_get_retry_exhausts_at_three_requests() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            503,
            json={"code": "SERVICE_NOT_READY", "message": "not ready"},
            headers={"X-Request-ID": f"req-{attempts['count']}"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )

    with pytest.raises(RepositoryProtocolError, match="missing error body request_id"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_get_retries_502() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                502,
                json={"code": "SERVICE_NOT_READY", "message": "bad gateway"},
                headers={"X-Request-ID": "req-1"},
            )
        return httpx.Response(
            200,
            json={"operation": _operation_payload()},
            headers={"X-Request-ID": "req-ok"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )

    response = await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)
    assert attempts["count"] == 2
    assert response.operation.status.value == "SUCCEEDED"


@pytest.mark.asyncio
async def test_get_retries_503_with_missing_request_id_header() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
            )
        return httpx.Response(
            200,
            json={"operation": _operation_payload()},
            headers={"X-Request-ID": "req-ok"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )

    response = await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)
    assert attempts["count"] == 2
    assert response.operation.status.value == "SUCCEEDED"


@pytest.mark.asyncio
async def test_get_retries_503_with_missing_error_body_request_id() -> None:
    attempts = {"count": 0}

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                503,
                json={"code": "SERVICE_NOT_READY", "message": "not ready"},
                headers={"X-Request-ID": "req-1"},
            )
        return httpx.Response(
            200,
            json={"operation": _operation_payload()},
            headers={"X-Request-ID": "req-ok"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )

    response = await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)
    assert attempts["count"] == 2
    assert response.operation.status.value == "SUCCEEDED"
