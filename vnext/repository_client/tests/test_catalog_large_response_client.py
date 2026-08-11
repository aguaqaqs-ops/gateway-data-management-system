"""Large catalog response acceptance tests."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest

from gateway_repository_client import RepositoryClient
from gateway_repository_contracts import (
    MAX_CATALOG_JSON_BYTES,
    MAX_WIRE_ERROR_JSON_BYTES,
    GetVersionedCatalogResponse,
)

REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
COMMIT_ID = "commit-c1"


def _large_catalog_payload(*, table_count: int = 600) -> dict[str, object]:
    tables = [
        {
            "name": f"t{index}",
            "columns": [{"name": "id", "sql_type": "BIGINT", "nullable": False}],
            "primary_key": ["id"],
            "row_count": 0,
        }
        for index in range(table_count)
    ]
    return {"catalog": {"commit_id": COMMIT_ID, "tables": tables}}


@pytest.mark.asyncio
async def test_large_valid_catalog_exceeds_error_limit_but_is_accepted() -> None:
    payload = _large_catalog_payload()
    wire_size = len(json.dumps(payload).encode("utf-8"))
    assert wire_size > MAX_WIRE_ERROR_JSON_BYTES
    assert wire_size < MAX_CATALOG_JSON_BYTES
    GetVersionedCatalogResponse.model_validate(payload)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=payload,
            headers={"X-Request-ID": "req-large"},
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
    assert response == GetVersionedCatalogResponse.model_validate(payload)
