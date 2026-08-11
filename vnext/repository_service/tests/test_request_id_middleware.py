"""HTTP middleware structured completion diagnostics."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from gateway_repository_service.http.middleware import RequestIdMiddleware


def test_request_id_middleware_logs_completion_fields(caplog: pytest.LogCaptureFixture) -> None:
    async def homepage(_request: Any) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", homepage)])
    app.add_middleware(RequestIdMiddleware)
    with caplog.at_level(logging.INFO, logger="gateway_repository_service.diagnostics"):
        client = TestClient(app)
        response = client.get("/")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    records = [record for record in caplog.records if hasattr(record, "gateway_fields")]
    assert records
    fields = getattr(records[-1], "gateway_fields")
    assert fields["event"] == "http_request_completed"
    assert fields["request_id"] == response.headers["x-request-id"]
    assert fields["code"] == "200"
    assert fields["size_bytes"] == 2
    assert "duration_ms" in fields
    assert "Authorization" not in str(fields)
    assert "idempotency" not in str(fields).lower()
