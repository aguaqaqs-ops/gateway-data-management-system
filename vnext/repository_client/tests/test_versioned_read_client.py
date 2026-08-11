"""Resolve and catalog versioned read client tests."""

from __future__ import annotations

import httpx
import pytest

from gateway_repository_client import RepositoryClient
from gateway_repository_contracts import (
    GetVersionedCatalogResponse,
    ResolveVersionedRefResponse,
)

REPO_ID = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"
COMMIT_ID = "commit-c1"


def _catalog_raw_path(*, commit_id: str) -> str:
    from urllib.parse import quote

    encoded = quote(commit_id, safe="")
    return f"/v1/repositories/{REPO_ID}/versioned/commits/{encoded}/catalog"


def _rows_raw_path(*, commit_id: str) -> str:
    from urllib.parse import quote

    encoded = quote(commit_id, safe="")
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
        assert request.url.raw_path.decode() == _catalog_raw_path(commit_id=COMMIT_ID)
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
        assert request.url.raw_path.decode() == _catalog_raw_path(commit_id=commit_id)
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
        assert request.url.raw_path.decode() == _catalog_raw_path(commit_id=commit_id)
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
        assert request.url.raw_path.decode().startswith(_rows_raw_path(commit_id=commit_id))
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
