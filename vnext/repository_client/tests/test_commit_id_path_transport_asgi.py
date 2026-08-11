"""ASGI end-to-end CommitId path transport tests."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from gateway_repository_contracts import decode_commit_id_path_segment

_COMMIT_ID_MATRIX = (
    ".",
    "..",
    "/",
    "%",
    "?",
    "#",
    "a b",
    "中文",
)


@pytest.fixture
def echo_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(ValueError)
    async def _validation_error_handler(_request: object, _exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"code": "REQUEST_VALIDATION_FAILED", "message": "request validation failed"},
        )

    @app.get("/v1/repositories/{repository_id}/versioned/commits/{commit_id}/echo")
    def echo_commit_id(commit_id: str) -> dict[str, str]:
        return {"commit_id": decode_commit_id_path_segment(commit_id)}

    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_id", _COMMIT_ID_MATRIX)
async def test_commit_id_path_transport_asgi_roundtrip(
    echo_app: FastAPI,
    commit_id: str,
) -> None:
    from gateway_repository_contracts import encode_commit_id_path_segment

    encoded = encode_commit_id_path_segment(commit_id)
    transport = httpx.ASGITransport(app=echo_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/v1/repositories/00000000-0000-4000-8000-000000000001"
            f"/versioned/commits/{encoded}/echo",
        )
    assert response.status_code == 200
    assert response.json()["commit_id"] == commit_id


@pytest.mark.asyncio
async def test_commit_id_path_transport_rejects_raw_logical_segment(
    echo_app: FastAPI,
) -> None:
    transport = httpx.ASGITransport(app=echo_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/v1/repositories/00000000-0000-4000-8000-000000000001"
            "/versioned/commits/commit-c1/echo",
        )
    assert response.status_code == 422
