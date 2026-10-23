"""OpenAPI contract tests for 5A workspace HTTP routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway_backend.http.wiring import PRODUCTION_OPENAPI_PATHS
from tests.support.http_workspace_harness import create_workspace_http_environment

pytestmark = pytest.mark.unit

FROZEN_ARCHIVE_OPENAPI_PATHS = frozenset(
    {
        "/v1/archive-candidates",
        "/v1/archive-plan-preview",
        "/v1/archive-confirmations",
        "/v1/archive-anomaly-resolutions",
        "/v1/archive-audit-events",
        "/v1/archives",
        "/v1/archives/{archive_result_id}",
    }
)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return create_workspace_http_environment(tmp_path).client


def test_openapi_paths_match_frozen_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert PRODUCTION_OPENAPI_PATHS == paths


def test_openapi_archive_paths_match_literal_baseline(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert FROZEN_ARCHIVE_OPENAPI_PATHS <= paths


def test_openapi_documents_the_keyless_fallback_preview_hint(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    response = schema["paths"][
        "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle"
    ]["get"]["responses"]["200"]

    assert "KEYLESS_FALLBACK" in response["description"]
    assert "does not affect risk or submission eligibility" in response["description"]


def test_openapi_operation_diagnostic_details_match_the_bounded_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    diagnostic = schema["OperationDiagnosticResponse"]
    detail = schema["OperationDiagnosticDetailResponse"]

    assert diagnostic["additionalProperties"] is False
    assert set(diagnostic["properties"]) == {"code", "message", "details", "omitted_count"}
    assert set(diagnostic["required"]) == {"code", "message"}
    details_schema = _non_null_union(diagnostic["properties"]["details"])
    assert details_schema["type"] == "array"
    assert details_schema["maxItems"] == 100
    assert details_schema["items"]["$ref"].endswith("/OperationDiagnosticDetailResponse")
    omitted_schema = _non_null_union(diagnostic["properties"]["omitted_count"])
    assert omitted_schema["minimum"] == 0
    assert omitted_schema["maximum"] == 2**53 - 1

    assert detail["additionalProperties"] is False
    assert set(detail["properties"]) == {"code", "side", "table_name", "column_name"}
    assert set(detail["required"]) == {"code", "side", "table_name", "column_name"}
    assert detail["properties"]["code"]["maxLength"] == 128
    assert detail["properties"]["side"]["enum"] == ["INITIAL", "MODIFIED"]
    for field in ("table_name", "column_name"):
        assert _non_null_union(detail["properties"][field])["maxLength"] == 255

    history_diagnostic = schema["HistoryCompareDiagnosticResponse"]
    assert set(history_diagnostic["properties"]) == {
        "code",
        "message",
        "details",
        "omitted_count",
    }
    history_details = _non_null_union(history_diagnostic["properties"]["details"])
    assert history_details["maxItems"] == 100


def _non_null_union(schema: dict[str, object]) -> dict[str, object]:
    alternatives = schema.get("anyOf")
    if not isinstance(alternatives, list):
        return schema
    non_null = next(
        item
        for item in alternatives
        if isinstance(item, dict) and item.get("type") != "null"
    )
    assert isinstance(non_null, dict)
    return non_null


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


def test_openapi_submit_request_rejects_additional_properties(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    accept_request = schema["components"]["schemas"]["AcceptSubmitRequest"]
    assert accept_request.get("additionalProperties") is False
    identity_confirmations = accept_request["properties"]["identity_confirmations"]
    assert identity_confirmations["type"] == "array"
    assert identity_confirmations["maxItems"] == 2
    identity_confirmation_request = schema["components"]["schemas"][
        "SubmitIdentityConfirmationRequest"
    ]
    assert identity_confirmation_request.get("additionalProperties") is False
    assert identity_confirmation_request["properties"]["action"]["enum"] == [
        "ACCEPT_DATASET_REPLACEMENT",
        "ACCEPT_UNVERIFIABLE_DETAILED_RESULT",
    ]
    assert "identity_exception" in schema["components"]["schemas"]["ReviewFactsResponse"]["properties"]
    assert "identity_confirmations" in schema["components"]["schemas"]["ReviewFactsResponse"]["properties"]
    assert "identity_exception" in schema["components"]["schemas"]["HistoryNodeResponse"]["properties"]
    submit_response = schema["components"]["schemas"]["SubmitAcceptedResponse"]
    assert "submit_attempt_id" in submit_response["properties"]
    recovery_request = schema["components"]["schemas"]["OperatorRecoveryRequestBody"]
    assert recovery_request.get("additionalProperties") is False
    apply_review_request = schema["components"]["schemas"]["ApplyReviewRequest"]
    assert apply_review_request.get("additionalProperties") is False
    review_facts_response = schema["components"]["schemas"]["ReviewFactsResponse"]
    assert "events" in review_facts_response["properties"]
    start_archive_request = schema["components"]["schemas"]["StartArchiveRequest"]
    assert start_archive_request.get("additionalProperties") is False
    archive_started_response = schema["components"]["schemas"]["ArchiveStartedResponse"]
    assert "archive_result_id" in archive_started_response["properties"]
