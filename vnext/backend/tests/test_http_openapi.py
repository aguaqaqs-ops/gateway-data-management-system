"""OpenAPI contract tests for 5A workspace HTTP routes."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from gateway_backend.http.schemas.operator_recovery import OperatorRecoveryRequestBody
from gateway_backend.http.wiring import (
    PRODUCTION_INTERNAL_PATHS,
    PRODUCTION_OPENAPI_PATHS,
    PRODUCTION_RUNTIME_PATHS,
)
from gateway_backend.device_identity import device_route_key
from tests.support.http_workspace_harness import create_workspace_http_environment
from tests.support.runtime_settings import TEST_DEVICE_KEY

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

INTERNAL_ONLY_COMPONENT_SCHEMAS = frozenset(
    {
        "DeviceRegistrationResponse",
        "DrainSnapshot",
        "OperatorRecoveryRequestBody",
        "OperatorRecoveryResponse",
        "RegisterDeviceRequest",
    }
)

SHARED_STATISTICS_COMPONENT_SCHEMAS = frozenset(
    {
        "BucketValue",
        "CollectionHealth",
        "CurrentProcess",
        "GroupStatistics",
        "GroupStorageItem",
        "ResourceBucket",
        "ResourceSeries",
        "StatisticsPage_ResourceSeries_",
    }
)

FROZEN_PUBLIC_COMPONENT_SCHEMAS = frozenset(
    {
        "AcceptSubmitOptions",
        "AcceptSubmitRequest",
        "AppendArchiveAnomalyResolutionRequest",
        "AppendArchiveConfirmationRequest",
        "ApplyReviewRequest",
        "ArchiveAffectedCandidateResponse",
        "ArchiveAuditAppendResponse",
        "ArchiveAuditEventResponse",
        "ArchiveAuditEventsResponse",
        "ArchiveAuditReferenceRequest",
        "ArchiveAuditReferenceResponse",
        "ArchiveBaselineTimeDetailsResponse",
        "ArchiveBusinessIssueResponse",
        "ArchiveBusinessSubjectResponse",
        "ArchiveBusinessValidationResponse",
        "ArchiveCandidateResponse",
        "ArchiveCandidatesResponse",
        "ArchiveContentIdentityResponse",
        "ArchiveEmptyIssueDetailsResponse",
        "ArchiveGeneratedTimeResponse",
        "ArchiveIdentitySubjectResponse",
        "ArchivePreviewAnomalyResponse",
        "ArchivePreviewDispositionResponse",
        "ArchivePreviewWorkspaceReleaseResponse",
        "ArchiveResultResponse",
        "ArchiveSelectedRefRequest",
        "ArchiveSiblingSubjectResponse",
        "ArchiveSourceDiagnosticResponse",
        "ArchiveSourceEdgeResponse",
        "ArchiveSourceIssueDetailsResponse",
        "ArchiveSourceReferenceResponse",
        "ArchiveStartedResponse",
        "ArchiveTimeComparisonResponse",
        "ArchiveTimeQualityDetailsResponse",
        "ArchiveTimeRegressionDetailsResponse",
        "BaselineHeadResponse",
        "BucketValue",
        "CacheCounts",
        "CloseSubmissionRequest",
        "CloseSubmissionResponse",
        "CollectionHealth",
        "CreateWorkspaceRequest",
        "CurrentProcess",
        "DeviceContextResponse",
        "ErrorResponse",
        "ExecutionMetrics",
        "ExecutionSummary",
        "GroupStatistics",
        "GroupStorageItem",
        "HTTPValidationError",
        "HistoryCompareAcceptRequest",
        "HistoryCompareAcceptResponse",
        "HistoryCompareDiagnosticResponse",
        "HistoryCompareListItemResponse",
        "HistoryCompareListResponse",
        "HistoryCompareNodeRequest",
        "HistoryComparePairResultResponse",
        "HistoryCompareResultInputResponse",
        "HistoryCompareResultResponse",
        "HistoryHeadResponse",
        "HistoryListResponse",
        "HistoryNodeRefResponse",
        "HistoryNodeResponse",
        "InputShape",
        "OperationAcceptedResponse",
        "OperationDiagnosticDetailResponse",
        "OperationDiagnosticResponse",
        "OperationResponse",
        "PreviewArchivePlanRequest",
        "PreviewArchivePlanResponse",
        "PreviewArtifactRefResponse",
        "PreviewIdentityPairResponse",
        "PreviewResultResponse",
        "ResourceBucket",
        "ResourceSeries",
        "ReviewAppliedResponse",
        "ReviewEventResponse",
        "ReviewFactsResponse",
        "ReviewIdentityConfirmationResponse",
        "SourceArtifactResponse",
        "StageDurations",
        "StartArchiveRequest",
        "StartPreviewOptions",
        "StartPreviewRequest",
        "StatisticsPage_ExecutionSummary_",
        "StatisticsPage_ResourceSeries_",
        "StatisticsPage_StorageRecord_",
        "StatisticsPage_WriteRecord_",
        "StorageRecord",
        "SubmissionClosureSummaryResponse",
        "SubmissionDispositionResponse",
        "SubmissionResponse",
        "SubmissionResultPairResponse",
        "SubmissionResultResponse",
        "SubmitAcceptedResponse",
        "SubmitAttemptResponse",
        "SubmitIdentityConfirmationRequest",
        "TableMetric",
        "UploadRevisionResponse",
        "ValidationError",
        "WorkspaceResponse",
        "WriteRecord",
    }
)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return create_workspace_http_environment(tmp_path).client


def test_openapi_paths_match_frozen_routes(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert len(PRODUCTION_OPENAPI_PATHS) == 35
    assert PRODUCTION_OPENAPI_PATHS == paths
    assert not any(path.startswith("/internal/") for path in paths)


def test_runtime_routes_match_frozen_routes(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    runtime_routes = [
        context.original_route
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
    ]
    runtime_paths = {route.path for route in runtime_routes}
    assert len(PRODUCTION_INTERNAL_PATHS) == 6
    assert len(PRODUCTION_RUNTIME_PATHS) == 41
    assert runtime_paths == PRODUCTION_RUNTIME_PATHS
    for route in runtime_routes:
        if route.path in PRODUCTION_INTERNAL_PATHS:
            assert route.include_in_schema is False
        else:
            assert route.include_in_schema is True


def test_openapi_component_schemas_match_frozen_public_set(client: TestClient) -> None:
    schemas = set(client.get("/openapi.json").json()["components"]["schemas"])
    assert len(FROZEN_PUBLIC_COMPONENT_SCHEMAS) == 102
    assert schemas == FROZEN_PUBLIC_COMPONENT_SCHEMAS
    assert schemas.isdisjoint(INTERNAL_ONLY_COMPONENT_SCHEMAS)
    assert SHARED_STATISTICS_COMPONENT_SCHEMAS <= schemas


def test_openapi_archive_paths_match_literal_baseline(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    assert FROZEN_ARCHIVE_OPENAPI_PATHS <= paths


def test_openapi_archive_candidate_exposes_required_review_version(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    candidate = schemas["ArchiveCandidateResponse"]
    assert candidate["additionalProperties"] is False
    assert set(candidate["properties"]) == {
        "submission_id",
        "expected_candidate_digest",
        "review_version",
    }
    assert set(candidate["required"]) == {
        "submission_id",
        "expected_candidate_digest",
        "review_version",
    }
    assert candidate["properties"]["review_version"]["type"] == "integer"
    assert candidate["properties"]["review_version"]["minimum"] == 0
    assert candidate["properties"]["review_version"]["maximum"] == 2**53 - 1
    selected = schemas["ArchiveSelectedRefRequest"]
    assert set(selected["properties"]) == {"submission_id", "expected_candidate_digest"}


def test_openapi_documents_the_keyless_fallback_preview_hint(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    response = schema["paths"][
        "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle"
    ]["get"]["responses"]["200"]

    assert "KEYLESS_FALLBACK" in response["description"]
    assert "does not affect risk or submission eligibility" in response["description"]


@pytest.mark.parametrize(
    "path",
    (
        "/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}/bundle",
        "/v1/history-compares/{operation_id}/bundle",
    ),
)
def test_bundle_openapi_declares_only_complete_tar(client: TestClient, path: str) -> None:
    responses = client.get("/openapi.json").json()["paths"][path]["get"]["responses"]
    assert set(responses["200"]["content"]) == {"application/x-tar"}
    assert set(responses["200"]["headers"]) == {"Content-Length", "ETag", "Content-Disposition"}
    assert "BUNDLE_INTEGRITY_FAILURE" in responses["503"]["description"]


def test_openapi_operation_diagnostic_details_match_the_bounded_contract(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    diagnostic = schema["OperationDiagnosticResponse"]
    detail = schema["OperationDiagnosticDetailResponse"]

    assert diagnostic["additionalProperties"] is False
    assert set(diagnostic["properties"]) == {"code", "message", "details", "omitted_count"}
    assert set(diagnostic["required"]) == {"code", "message"}
    details_schema = _non_null_union(diagnostic["properties"]["details"])
    assert details_schema["type"] == "array"
    assert details_schema["maxItems"] == 100
    detail_items_schema = details_schema["items"]
    assert isinstance(detail_items_schema, dict)
    assert detail_items_schema["$ref"].endswith("/OperationDiagnosticDetailResponse")
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
        item for item in alternatives if isinstance(item, dict) and item.get("type") != "null"
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
        headers={
            "Authorization": "Bearer test-session-token",
            "X-Gateway-Device-Key": device_route_key(TEST_DEVICE_KEY),
        },
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
    assert (
        "identity_exception" in schema["components"]["schemas"]["ReviewFactsResponse"]["properties"]
    )
    assert (
        "identity_confirmations"
        in schema["components"]["schemas"]["ReviewFactsResponse"]["properties"]
    )
    assert (
        "identity_exception" in schema["components"]["schemas"]["HistoryNodeResponse"]["properties"]
    )
    submit_response = schema["components"]["schemas"]["SubmitAcceptedResponse"]
    assert "submit_attempt_id" in submit_response["properties"]
    assert "OperatorRecoveryRequestBody" not in schema["components"]["schemas"]
    assert OperatorRecoveryRequestBody.model_json_schema().get("additionalProperties") is False
    apply_review_request = schema["components"]["schemas"]["ApplyReviewRequest"]
    assert apply_review_request.get("additionalProperties") is False
    review_facts_response = schema["components"]["schemas"]["ReviewFactsResponse"]
    assert "events" in review_facts_response["properties"]
    start_archive_request = schema["components"]["schemas"]["StartArchiveRequest"]
    assert start_archive_request.get("additionalProperties") is False
    archive_started_response = schema["components"]["schemas"]["ArchiveStartedResponse"]
    assert "archive_result_id" in archive_started_response["properties"]


def test_openapi_create_statuses_response_models_and_workspace_occupancy(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    for path, statuses, model in (
        ("/v1/workspaces", ("201", "200"), "WorkspaceResponse"),
        ("/v1/history-compares", ("202", "200"), "HistoryCompareAcceptResponse"),
    ):
        responses = schema["paths"][path]["post"]["responses"]
        assert {key for key in responses if key.startswith("2")} == set(statuses)
        for status in statuses:
            assert responses[status]["content"]["application/json"]["schema"] == {
                "$ref": f"#/components/schemas/{model}"
            }
    workspace = schema["components"]["schemas"]["WorkspaceResponse"]
    for field in (
        "active_preview_operation_id",
        "active_submit_attempt_id",
        "active_submission_id",
    ):
        assert field in workspace["required"]
        assert workspace["properties"][field]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert "RETURN_FOR_REVISION" not in str(schema)
    assert "RETURNED_FOR_REVISION" not in str(schema)
    assert (
        "ARCHIVE_PENDING_REVIEW"
        in schema["paths"]["/v1/archives"]["post"]["responses"]["409"]["description"]
    )


def test_archive_business_diagnostics_closure_and_reference_limits_are_closed_schemas(
    client: TestClient,
) -> None:
    schema = client.get("/openapi.json").json()
    models = schema["components"]["schemas"]
    assert models["StartArchiveRequest"]["properties"]["confirmation_refs"]["maxItems"] == 1
    assert (
        models["StartArchiveRequest"]["properties"]["anomaly_resolution_refs"]["maxItems"] == 1601
    )
    for name in (
        "ArchiveBusinessValidationResponse",
        "ArchiveSourceDiagnosticResponse",
        "ArchiveTimeComparisonResponse",
        "ArchiveBusinessIssueResponse",
        "ArchiveBusinessSubjectResponse",
        "ArchiveSourceIssueDetailsResponse",
        "CloseSubmissionRequest",
    ):
        assert models[name]["additionalProperties"] is False
    assert "submission_disposition" in models["ReviewFactsResponse"]["properties"]
    assert "submission_disposition" in models["HistoryNodeResponse"]["properties"]
    assert "archive_disposition" not in models["HistoryNodeResponse"]["properties"]
    route = schema["paths"]["/v1/submissions/{submission_id}/closure"]["post"]
    assert {"200", "201", "403", "404", "409", "503"} <= set(route["responses"])


def test_history_compare_openapi_freezes_discovery_and_errors(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    list_route = paths["/v1/history-compares"]["get"]
    query = {item["name"]: item for item in list_route["parameters"] if item["in"] == "query"}
    assert set(query) == {"limit", "after"}
    assert query["limit"]["schema"]["default"] == 50
    assert query["limit"]["schema"]["minimum"] == 1
    assert query["limit"]["schema"]["maximum"] == 100
    assert _non_null_union(query["after"]["schema"])["maxLength"] == 1024
    response_model = schema["components"]["schemas"]["HistoryCompareListResponse"]
    assert response_model["additionalProperties"] is False
    assert set(response_model["properties"]) == {"items", "next_cursor"}
    assert set(response_model["required"]) == {"items", "next_cursor"}
    item = schema["components"]["schemas"]["HistoryCompareListItemResponse"]
    assert item["additionalProperties"] is False
    assert set(item["properties"]) == {
        "operation_id",
        "nodes",
        "status",
        "accepted_at",
        "completed_at",
        "result_expires_at",
    }
    assert set(item["required"]) == set(item["properties"])
    for field in ("completed_at", "result_expires_at"):
        assert {entry.get("type") for entry in item["properties"][field]["anyOf"]} == {
            "string",
            "null",
        }
    post = paths["/v1/history-compares"]["post"]
    key_header = next(item for item in post["parameters"] if item["name"] == "Idempotency-Key")
    assert key_header["required"] is True
    expected = {
        ("post", "/v1/history-compares", "404"): {"RESOURCE_NOT_FOUND", "ARTIFACT_UNAVAILABLE"},
        ("post", "/v1/history-compares", "409"): {
            "IDEMPOTENCY_CONFLICT",
            "HISTORY_COMPARE_REQUEST_EXPIRED",
            "HISTORY_COMPARE_SCOPE_LIMIT",
        },
        ("post", "/v1/history-compares", "429"): {
            "HISTORY_COMPARE_ALIAS_LIMIT",
            "OPERATION_QUEUE_FULL",
        },
        ("post", "/v1/history-compares", "503"): {
            "SERVICE_NOT_READY",
            "HISTORY_INTEGRITY_FAILURE",
            "BUNDLE_INTEGRITY_FAILURE",
        },
        ("get", "/v1/history-compares/{operation_id}", "410"): {"HISTORY_COMPARE_RESULT_EXPIRED"},
        ("get", "/v1/history-compares/{operation_id}/bundle", "410"): {
            "HISTORY_COMPARE_RESULT_EXPIRED"
        },
        ("get", "/v1/history-compares/{operation_id}", "503"): {
            "HISTORY_INTEGRITY_FAILURE",
            "BUNDLE_INTEGRITY_FAILURE",
        },
        ("get", "/v1/history-compares/{operation_id}/bundle", "503"): {
            "HISTORY_INTEGRITY_FAILURE",
            "BUNDLE_INTEGRITY_FAILURE",
        },
    }
    for (method, path, status), codes in expected.items():
        response = paths[path][method]["responses"][status]
        assert all(code in response["description"] for code in codes)
        assert response["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
    for path in (
        "/v1/workspaces/{workspace_id}/preview-operations",
        "/v1/workspaces/{workspace_id}/submit-attempts",
    ):
        assert "OPERATION_QUEUE_FULL" in paths[path]["post"]["responses"]["429"]["description"]
