"""GET bounded-retry behavior for versioned read/operation endpoints."""

from __future__ import annotations

import json
import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest

from gateway_repository_client import RepositoryClient, RepositoryClientError, RepositoryProtocolError
from gateway_repository_client.errors import RepositoryClientTimeoutError

REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
OP_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c22")
COMMIT_ID = "commit-c1"

CONTROL_STOPS = (
    pytest.param("cancel", InterruptedError, id="cancel"),
    pytest.param("deadline", RepositoryClientTimeoutError, id="deadline"),
)


@pytest.mark.parametrize(("stop", "expected"), CONTROL_STOPS)
async def test_catalog_control_stops_after_closed_attempt_before_next_retry(
    stop: str, expected: type[Exception],
) -> None:
    now = [0.0]
    cancelled = [False]
    responses: list[httpx.Response] = []
    sleeps: list[float] = []
    def handler(_request: httpx.Request) -> httpx.Response:
        response = httpx.Response(503, json={"code": "SERVICE_NOT_READY", "message": "not ready"},
            headers={"X-Request-ID": "controlled-attempt"})
        responses.append(response)
        return response
    async def sleeper(delay: float) -> None:
        assert responses[-1].is_closed
        sleeps.append(delay)
        cancelled[0] = stop == "cancel"
        now[0] = 1.0 if stop == "deadline" else now[0]
    client = RepositoryClient(base_url="http://repository.test", bearer_token="token",
        transport=httpx.MockTransport(handler), sleeper=sleeper, clock=lambda: now[0])
    with pytest.raises(expected):
        await client.get_versioned_catalog(repository_id=REPO_ID, commit_id=COMMIT_ID,
            cancel_requested=lambda: cancelled[0], deadline_at=0.5)
    assert len(responses) == 1 and all(response.is_closed for response in responses)
    assert sleeps == [0.05]


@pytest.mark.serial
async def test_catalog_cancellation_interrupts_a_pending_http_attempt() -> None:
    started = asyncio.Event()
    cancelled = [False]
    abandoned = asyncio.Event()
    async def handler(_request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            abandoned.set()
        raise AssertionError("pending request unexpectedly completed")
    client = RepositoryClient(base_url="http://repository.test", bearer_token="token",
        transport=httpx.MockTransport(handler))
    pending = asyncio.create_task(client.get_versioned_catalog(repository_id=REPO_ID, commit_id=COMMIT_ID,
        cancel_requested=lambda: cancelled[0]))
    try:
        await asyncio.wait_for(started.wait(), timeout=2.0)
        cancelled[0] = True
        with pytest.raises(InterruptedError):
            await asyncio.wait_for(pending, timeout=2.0)
        assert abandoned.is_set()
    finally:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


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


@pytest.mark.asyncio
async def test_mid_body_read_error_closes_stream_on_each_retry_attempt() -> None:
    attempts = {"count": 0}
    stream_closes = {"count": 0}
    partial_body = json.dumps({"operation": _operation_payload(status="RUNNING")})[:24].encode()

    class MidBodyReadErrorStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield partial_body
            raise httpx.ReadError("mid-body network failure")
            yield b""  # pragma: no cover

        async def aclose(self) -> None:
            stream_closes["count"] += 1

    class ReadErrorTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(
                200,
                request=request,
                headers={
                    "X-Request-ID": f"req-{attempts['count']}",
                    "Content-Type": "application/json",
                },
                stream=MidBodyReadErrorStream(),
            )

    async def sleeper(_seconds: float) -> None:
        return None

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=ReadErrorTransport(),
        sleeper=sleeper,
    )

    with pytest.raises(httpx.ReadError, match="mid-body network failure"):
        await client.get_operation(repository_id=REPO_ID, operation_id=OP_ID)

    assert attempts["count"] == 3
    assert stream_closes["count"] == 3
