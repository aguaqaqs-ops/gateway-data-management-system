"""Integration tests for UploadArtifact with real Dolt."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast

from gateway_repository_service.app import create_app
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION
from gateway_repository_service.upload_artifact.visibility import (
    artifact_ready_path,
    is_artifact_visible,
)
from support.control_db_harness import locked_control_connection
from support.lifecycle_harness import lifecycle_settings
from support.upload_harness import create_repository, upload_headers


@pytest.mark.integration
def test_upload_integration_publishes_ready_file_and_lifecycle(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    payload = b"integration-upload-payload"
    with TestClient(create_app(settings)) as client:
        repository_id = create_repository(client, idempotency_key="integration-create")
        response = client.post(
            f"/v1/repositories/{repository_id}/artifacts",
            headers=upload_headers(idempotency_key="integration-upload", payload=payload),
            content=payload,
        )
        assert response.status_code == 201
        body = response.json()
        artifact_id = UUID(body["artifact_ref"]["artifact_id"])

        runtime = cast(FastAPI, client.app).state.runtime
        ready_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        assert ready_path.is_file()
        assert ready_path.read_bytes() == payload
        assert is_artifact_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            artifact_id,
            size_bytes=len(payload),
            raw_sha256=body["artifact_ref"]["raw_sha256"],
        )

        with locked_control_connection(runtime.control_store) as connection:
            lifecycle = connection.execute(
                """
                SELECT artifact_id, repository_scope, size_bytes, raw_sha256, created_at, updated_at
                FROM artifact_lifecycle
                WHERE artifact_id = ?
                """,
                (str(artifact_id),),
            ).fetchone()
            version = connection.execute("PRAGMA user_version").fetchone()
        assert lifecycle is not None
        assert lifecycle["repository_scope"] == repository_id.hex
        assert int(lifecycle["size_bytes"]) == len(payload)
        assert lifecycle["raw_sha256"] == body["artifact_ref"]["raw_sha256"]
        assert lifecycle["created_at"]
        assert lifecycle["updated_at"]

        assert version is not None
        assert int(version[0]) == CONTROL_DB_USER_VERSION
