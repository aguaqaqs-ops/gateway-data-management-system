"""HTTP creation admission closes before drain while reads remain available."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway_backend.app import create_app
from gateway_backend.http.dependencies import ClosableAdmissionGate
from tests.support.http_workspace_harness import (
    TEST_BEARER,
    create_workspace_http_environment,
)
from tests.support.runtime_settings import (
    TEST_REPOSITORY_TOKEN,
    make_backend_settings,
    prepare_backend_runtime_paths,
)

pytestmark = pytest.mark.unit

AUTH = {"Authorization": f"Bearer {TEST_BEARER}"}


def test_closable_admission_gate_stops_new_work() -> None:
    gate = ClosableAdmissionGate()
    assert gate.allows_new_work() is True
    gate.close()
    assert gate.allows_new_work() is False
    gate.close()
    assert gate.allows_new_work() is False


def test_create_routes_reject_after_admission_close_while_reads_remain(tmp_path: Path) -> None:
    env = create_workspace_http_environment(tmp_path, admission_open=True)
    created = env.client.post(
        "/v1/workspaces",
        headers=AUTH,
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert created.status_code in {200, 201}
    closed = create_workspace_http_environment(tmp_path, admission_open=False)
    rejected = closed.client.post(
        "/v1/workspaces",
        headers=AUTH,
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert rejected.status_code == 429
    assert rejected.json()["code"] == "ADMISSION_LIMIT_REACHED"
    health = closed.client.get("/healthz")
    ready = closed.client.get("/readyz")
    missing_operation = closed.client.get("/v1/operations/op-missing", headers=AUTH)
    assert health.status_code == 200
    assert ready.status_code == 200
    assert missing_operation.status_code in {401, 403, 404}


def test_production_shutdown_closes_admission_gate(tmp_path: Path) -> None:
    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    with patch("gateway_backend.http.runtime.assert_repository_service_ready"):
        with TestClient(create_app(settings)) as client:
            fastapi_app = cast(FastAPI, client.app)
            assert client.get("/readyz").status_code == 200
            gate = fastapi_app.state.admission_gate
            assert gate.allows_new_work() is True
            gate.close()
            assert gate.allows_new_work() is False
            assert client.get("/readyz").status_code == 200
            assert client.get("/healthz").status_code == 200
            assert TEST_REPOSITORY_TOKEN not in client.get("/readyz").text
        assert fastapi_app.state.admission_gate.allows_new_work() is False


def test_production_lifespan_shutdown_marks_not_ready(tmp_path: Path) -> None:
    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    with patch("gateway_backend.http.runtime.assert_repository_service_ready"):
        with TestClient(create_app(settings)) as client:
            fastapi_app = cast(FastAPI, client.app)
            assert client.get("/readyz").status_code == 200
        assert client.get("/readyz").status_code == 503
        assert client.get("/healthz").status_code == 200
        assert fastapi_app.state.ready is False
        assert fastapi_app.state.admission_gate.allows_new_work() is False


def test_submit_create_route_rejects_after_admission_close(tmp_path: Path) -> None:
    from tests.support.http_workspace_harness import BASELINE_HEAD, seed_submit_ready_workspace

    env = create_workspace_http_environment(tmp_path, admission_open=True)
    seed = seed_submit_ready_workspace(env.db_path, env.artifact_store)
    workspace = seed["workspace"]
    upload = seed["upload_revision"]
    preview = seed["preview_result"]
    closed = create_workspace_http_environment(tmp_path, admission_open=False)
    rejected = closed.client.post(
        f"/v1/workspaces/{workspace.workspace_id}/submit-attempts",
        headers=closed.auth_headers(idempotency_key="submit-admission-close"),
        json={
            "expected_workspace_version": workspace.optimistic_version,
            "upload_revision_id": upload.upload_revision_id,
            "preview_result_id": preview.preview_result_id,
            "generation": upload.generation,
            "expected_baseline_node_id": BASELINE_HEAD.business_baseline_node_id,
            "expected_baseline_head_version": BASELINE_HEAD.baseline_head_version,
            "options": {},
        },
    )
    assert rejected.status_code == 429
    assert rejected.json()["code"] == "ADMISSION_LIMIT_REACHED"


def test_closable_admission_gate_rejects_when_in_flight_limit_reached() -> None:
    gate = ClosableAdmissionGate(limit=1)
    assert gate.try_acquire() is True
    assert gate.try_acquire() is False
    gate.release()
    assert gate.try_acquire() is True


def test_create_routes_reject_when_admission_slots_are_full(tmp_path: Path) -> None:
    gate = ClosableAdmissionGate(limit=1)
    assert gate.try_acquire() is True
    env = create_workspace_http_environment(tmp_path, admission_gate=gate)
    rejected = env.client.post(
        "/v1/workspaces",
        headers=AUTH,
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert rejected.status_code == 429
    assert rejected.json()["code"] == "ADMISSION_LIMIT_REACHED"
    assert rejected.json()["message"] == "gateway admission limit reached"
    gate.release()
    created = env.client.post(
        "/v1/workspaces",
        headers=AUTH,
        json={
            "gateway_device_external_key": "device-1",
            "business_project_id": "project-1",
        },
    )
    assert created.status_code in {200, 201}
