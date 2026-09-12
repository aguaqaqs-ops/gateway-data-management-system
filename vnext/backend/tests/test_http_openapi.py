"""OpenAPI contract tests for 5A workspace HTTP routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway_backend.http.wiring import PRODUCTION_OPENAPI_PATHS
from tests.support.http_workspace_harness import create_workspace_http_environment

pytestmark = pytest.mark.unit


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return create_workspace_http_environment(tmp_path).client


def test_openapi_paths_match_frozen_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert PRODUCTION_OPENAPI_PATHS <= paths


def test_openapi_schemas_reject_additional_properties(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    workspace_response = schema["components"]["schemas"]["WorkspaceResponse"]
    assert workspace_response["properties"]["workspace_id"]["type"] == "string"
    preview_request = schema["components"]["schemas"]["StartPreviewRequest"]
    assert "expected_workspace_version" in preview_request["properties"]
    options_schema = preview_request["properties"]["options"]
    if "$ref" in options_schema:
        ref_name = str(options_schema["$ref"]).rsplit("/", 1)[-1]
        options_schema = schema["components"]["schemas"][ref_name]
    assert options_schema.get("type", "object") == "object"
    assert options_schema.get("additionalProperties") is False
    extra_field = client.post(
        "/v1/workspaces",
        headers={"Authorization": "Bearer test-session-token"},
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
            "extra": True,
        },
    )
    assert extra_field.status_code == 422
