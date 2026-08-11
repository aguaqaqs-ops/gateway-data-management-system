"""wait_operation monotonic deadline and capped backoff."""

from __future__ import annotations

import httpx
import pytest

from gateway_repository_client import (
    RepositoryClient,
    RepositoryClientTimeoutError,
)
from gateway_repository_contracts import OperationStatus

REPO_ID = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"
OP_ID = "018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c22"


def _operation(*, status: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "operation_id": OP_ID,
        "status": status,
        "result": None,
        "error": None,
    }
    if status == "SUCCEEDED":
        payload["result"] = {
            "commit_id": "commit-c1",
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
async def test_wait_operation_returns_terminal_on_first_query_without_sleep() -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            200,
            json={"operation": _operation(status="FAILED")},
            headers={"X-Request-ID": "req-1"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
    )

    operation = await client.wait_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert attempts["count"] == 1
    assert sleeps == []
    assert operation.status == OperationStatus.FAILED
    assert operation.error is not None
    assert operation.error.code == "IMPORT_REJECTED"


@pytest.mark.asyncio
async def test_wait_operation_uses_monotonic_deadline_and_capped_backoff() -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []
    clock_values = iter([0.0, 0.0, 0.1, 0.1, 0.2, 0.2, 5.0])

    def clock() -> float:
        return next(clock_values)

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(
                200,
                json={"operation": _operation(status="RUNNING")},
                headers={"X-Request-ID": f"req-{attempts['count']}"},
            )
        return httpx.Response(
            200,
            json={"operation": _operation(status="SUCCEEDED")},
            headers={"X-Request-ID": "req-final"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
        clock=clock,
        poll_deadline_seconds=10.0,
    )

    operation = await client.wait_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert attempts["count"] == 3
    assert operation.status == OperationStatus.SUCCEEDED
    assert sleeps
    assert all(delay <= 1.0 for delay in sleeps)
    assert sleeps[0] == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_wait_operation_raises_typed_timeout() -> None:
    attempts = {"count": 0}
    clock_values = iter([0.0, 0.0, 1.0])

    def clock() -> float:
        return next(clock_values)

    async def sleeper(_seconds: float) -> None:
        return None

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(
            200,
            json={"operation": _operation(status="QUEUED")},
            headers={"X-Request-ID": f"req-{attempts['count']}"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
        sleeper=sleeper,
        clock=clock,
        poll_deadline_seconds=0.5,
    )

    with pytest.raises(RepositoryClientTimeoutError):
        await client.wait_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert attempts["count"] == 1
