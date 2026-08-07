"""Visibility tests for UploadArtifact."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast

from gateway_repository_service.app import create_app
from gateway_repository_service.upload_artifact.visibility import (
    artifact_ready_path,
    has_published_artifact_file,
    is_artifact_visible,
)
from support.lifecycle_harness import lifecycle_settings
from support.upload_harness import create_repository, upload_headers


@pytest.mark.integration
def test_artifact_visible_only_with_db_and_ready_file(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"visibility-payload"
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-visibility")
        response = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="visibility-upload", payload=payload),
            content=payload,
        )
        assert response.status_code == 201
        artifact_id = UUID(response.json()["artifact_ref"]["artifact_id"])
        raw_sha256 = response.json()["artifact_ref"]["raw_sha256"]
        size_bytes = response.json()["artifact_ref"]["size_bytes"]

        runtime = cast(FastAPI, client.app).state.runtime
        assert is_artifact_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            artifact_id,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        )

        ready_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        ready_path.unlink()
        assert not is_artifact_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            artifact_id,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        )


@pytest.mark.integration
def test_ready_file_without_db_is_not_visible(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"db-only"
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="create-db-only")
        response = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="db-only-upload", payload=payload),
            content=payload,
        )
        artifact_id = UUID(response.json()["artifact_ref"]["artifact_id"])
        raw_sha256 = response.json()["artifact_ref"]["raw_sha256"]
        size_bytes = response.json()["artifact_ref"]["size_bytes"]
        runtime = cast(FastAPI, client.app).state.runtime

        runtime.mutation_store._connection.execute(
            "DELETE FROM synchronous_mutation_effects WHERE resource_id = ?",
            (str(artifact_id),),
        )
        runtime.mutation_store._connection.commit()

        assert has_published_artifact_file(
            runtime.layout,
            repository_id,
            artifact_id,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        )
        assert not is_artifact_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            artifact_id,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        )
