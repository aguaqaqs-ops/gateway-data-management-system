"""Resolve and catalog versioned read client tests."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from gateway_repository_client import RepositoryClient
from gateway_repository_contracts import (
    GetVersionedCatalogResponse,
    ResolveVersionedRefResponse,
    encode_commit_id_path_segment,
)

REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
COMMIT_ID = "commit-c1"


def _catalog_raw_path(*, commit_id: str) -> str:
    encoded = encode_commit_id_path_segment(commit_id)
    return f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/catalog"


def _rows_raw_path(*, commit_id: str) -> str:
    encoded = encode_commit_id_path_segment(commit_id)
    return f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/rows"


@pytest.mark.asyncio
async def test_resolve_versioned_ref_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == f"/v1/repositories/{REPO_ID}/versioned/refs/main"
        return httpx.Response(
            200,
            json={"ref_name": "main", "commit_id": COMMIT_ID},
            headers={"X-Request-ID": "req-resolve"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    response = await client.resolve_versioned_ref(repository_id=REPO_ID)
    assert response == ResolveVersionedRefResponse(ref_name="main", commit_id=COMMIT_ID)


@pytest.mark.asyncio
async def test_get_versioned_catalog_success() -> None:
    catalog = {
        "commit_id": COMMIT_ID,
        "tables": [
            {
                "name": "items",
                "columns": [{"name": "id", "sql_type": "INT", "nullable": False}],
                "primary_key": ["id"],
                "row_count": 1,
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _catalog_raw_path(commit_id=COMMIT_ID)
        return httpx.Response(
            200,
            json={"catalog": catalog},
            headers={"X-Request-ID": "req-catalog"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    response = await client.get_versioned_catalog(
        repository_id=REPO_ID,
        commit_id=COMMIT_ID,
    )
    assert response == GetVersionedCatalogResponse.model_validate({"catalog": catalog})


@pytest.mark.asyncio
async def test_get_versioned_catalog_encodes_slash_in_commit_id() -> None:
    commit_id = "abc/def"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _catalog_raw_path(commit_id=commit_id)
        return httpx.Response(
            200,
            json={
                "catalog": {
                    "commit_id": commit_id,
                    "tables": [],
                }
            },
            headers={"X-Request-ID": "req-slash"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    await client.get_versioned_catalog(repository_id=REPO_ID, commit_id=commit_id)


@pytest.mark.asyncio
async def test_get_versioned_catalog_encodes_space_in_commit_id() -> None:
    commit_id = "a b"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _catalog_raw_path(commit_id=commit_id)
        return httpx.Response(
            200,
            json={
                "catalog": {
                    "commit_id": commit_id,
                    "tables": [],
                }
            },
            headers={"X-Request-ID": "req-space"},
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    await client.get_versioned_catalog(repository_id=REPO_ID, commit_id=commit_id)


@pytest.mark.asyncio
async def test_stream_versioned_table_rows_encodes_commit_id_in_path() -> None:
    commit_id = "abc/def"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == _rows_raw_path(commit_id=commit_id)
        return httpx.Response(
            200,
            headers={
                "X-Request-ID": "req-stream",
                "Content-Type": "application/vnd.apache.arrow.stream",
            },
            content=b"arrow",
        )

    client = RepositoryClient(
        base_url="http://repository.test",
        bearer_token="token",
        transport=httpx.MockTransport(handler),
    )
    stream = client.stream_versioned_table_rows(
        repository_id=REPO_ID,
        commit_id=commit_id,
        table_name="items",
    )
    async with stream:
        chunks = [chunk async for chunk in stream.aiter_bytes()]
    assert chunks == [b"arrow"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ("ref", "catalog"))
@pytest.mark.parametrize("outcome", ("success", "admission_timeout", "caller_deadline", "cancel", "ordinary_fault"))
async def test_read_busy_has_one_bounded_admission_window(kind: str, outcome: str) -> None:
    from gateway_repository_client.errors import RepositoryClientError, RepositoryClientTimeoutError
    now = [0.0]
    responses: list[httpx.Response] = []
    delays: list[float] = []
    cancelled = [False]
    def handler(request: httpx.Request) -> httpx.Response:
        count = len(responses)
        if outcome == 'ordinary_fault' or outcome == 'success' and count < 2:
            response = httpx.Response(503, json={"code": "SERVICE_NOT_READY", "message": "not ready", "request_id": "busy"}, headers={"X-Request-ID": "busy"})
        elif outcome == 'success' and count >= 127:
            body = {"ref_name": "main", "commit_id": COMMIT_ID} if kind == 'ref' else {"catalog": {"commit_id": COMMIT_ID, "tables": []}}
            response = httpx.Response(200, json=body, headers={"X-Request-ID": "ok"})
        else:
            response = httpx.Response(503, json={"code": "REPOSITORY_BUSY", "message": "repository is busy", "request_id": "busy"}, headers={"X-Request-ID": "busy"})
        responses.append(response)
        return response
    async def sleeper(delay: float) -> None:
        assert responses[-1].is_closed
        delays.append(delay)
        now[0] += delay
        if outcome == 'cancel':
            cancelled[0] = True
    client = RepositoryClient(base_url="http://repository.test", bearer_token="token",
        transport=httpx.MockTransport(handler), sleeper=sleeper, clock=lambda: now[0])
    async def read() -> object:
        deadline = 2.5 if outcome == 'caller_deadline' else None
        if kind == 'ref':
            return await client.resolve_versioned_ref(repository_id=REPO_ID, cancel_requested=lambda: cancelled[0], deadline_at=deadline)
        return await client.get_versioned_catalog(repository_id=REPO_ID, commit_id=COMMIT_ID, cancel_requested=lambda: cancelled[0], deadline_at=deadline)
    if outcome == 'success':
        await read()
        assert now[0] == pytest.approx(125.15) and len(responses) == 128
    else:
        expected = InterruptedError if outcome == 'cancel' else RepositoryClientError if outcome == 'ordinary_fault' else RepositoryClientTimeoutError
        with pytest.raises(expected):
            await read()
        assert now[0] == pytest.approx({'admission_timeout': 300.0, 'caller_deadline': 2.5, 'cancel': 1.0, 'ordinary_fault': 0.15}[outcome])
        if outcome == 'ordinary_fault':
            assert len(responses) == 3 and delays == [0.05, 0.1]
    assert all(response.is_closed for response in responses)
