"""Idempotency tests for UploadArtifact."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from support.lifecycle_harness import lifecycle_settings
from support.upload_harness import create_repository, upload_headers


@pytest.mark.integration
def test_upload_same_key_replays_original_response(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"same-key-payload"
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-same-key")
        headers = upload_headers(idempotency_key="upload-same-key", payload=payload)
        first = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=headers,
            content=payload,
        )
        second = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=headers,
            content=payload,
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()


@pytest.mark.integration
def test_upload_different_content_same_key_conflicts(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-conflict")
        first_payload = b"first-payload"
        second_payload = b"second-payload"
        first = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="conflict-key", payload=first_payload),
            content=first_payload,
        )
        second = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="conflict-key", payload=second_payload),
            content=second_payload,
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.integration
def test_upload_idempotency_scope_is_isolated_by_repository(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"shared-scope-payload"
    with TestClient(create_app(settings)) as client:
        repository_a = create_repository(client, idempotency_key="create-a")
        repository_b = create_repository(client, idempotency_key="create-b")
        headers = upload_headers(idempotency_key="shared-upload-key", payload=payload)
        first = client.post(
            f"/v1/repositories/{repository_a}/artifacts",
            headers=headers,
            content=payload,
        )
        second = client.post(
            f"/v1/repositories/{repository_b}/artifacts",
            headers=headers,
            content=payload,
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["artifact_ref"]["artifact_id"] != second.json()["artifact_ref"]["artifact_id"]
