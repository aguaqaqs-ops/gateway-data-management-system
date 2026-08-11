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


@pytest.mark.asyncio
async def test_resolve_versioned_ref_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/versioned/refs/main")
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
        assert COMMIT_ID in request.url.path
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
