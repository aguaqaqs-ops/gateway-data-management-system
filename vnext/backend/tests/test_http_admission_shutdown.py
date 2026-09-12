"""HTTP creation admission closes before drain while reads remain available."""

from __future__ import annotations

from pathlib import Path

import pytest
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
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/readyz").status_code == 200
        gate = app.state.admission_gate
        assert gate.allows_new_work() is True
        gate.close()
        assert gate.allows_new_work() is False
        assert client.get("/readyz").status_code == 200
        assert client.get("/healthz").status_code == 200
        assert TEST_REPOSITORY_TOKEN not in client.get("/readyz").text
    assert app.state.admission_gate.allows_new_work() is False
