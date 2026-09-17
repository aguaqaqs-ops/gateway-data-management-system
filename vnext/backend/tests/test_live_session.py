"""Live session file reload, expiry and revocation tests."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gateway_backend.app import create_app
from gateway_backend.settings import BackendSettings
from tests.support.runtime_settings import (
    TEST_DEVICE_KEY,
    TEST_PROJECT_ID,
    TEST_SESSION_TOKEN,
    default_session_document,
    make_backend_settings,
    prepare_backend_runtime_paths,
    write_session_file,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _skip_repository_ready_probe() -> None:
    with patch("gateway_backend.http.runtime.assert_repository_service_ready"):
        yield


WORKSPACE_BODY = {
    "gateway_device_external_key": TEST_DEVICE_KEY,
    "business_project_id": TEST_PROJECT_ID,
}
AUTH = {"Authorization": f"Bearer {TEST_SESSION_TOKEN}"}
ROTATED_TOKEN = "xxxx-session-token"


def _settings(tmp_path: Path) -> BackendSettings:
    prepare_backend_runtime_paths(tmp_path)
    return make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )


def test_deleting_session_file_revokes_authenticated_access(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post("/v1/workspaces", headers=AUTH, json=WORKSPACE_BODY)
        assert created.status_code in {200, 201}
        settings.session_file.unlink()
        revoked = client.post("/v1/workspaces", headers=AUTH, json=WORKSPACE_BODY)
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_rewriting_session_file_without_token_revokes_access(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post("/v1/workspaces", headers=AUTH, json=WORKSPACE_BODY)
        assert created.status_code in {200, 201}
        document = default_session_document()
        sessions = document["sessions"]
        assert isinstance(sessions, list)
        first = sessions[0]
        assert isinstance(first, dict)
        first["token"] = "rotated-token"
        write_session_file(settings.session_file, document)
        revoked = client.post("/v1/workspaces", headers=AUTH, json=WORKSPACE_BODY)
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_same_size_token_replacement_revokes_old_identity_when_mtime_preserved(
    tmp_path: Path,
) -> None:
    assert len(ROTATED_TOKEN) == len(TEST_SESSION_TOKEN)
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post("/v1/workspaces", headers=AUTH, json=WORKSPACE_BODY)
        assert created.status_code in {200, 201}
        original_stat = settings.session_file.stat()
        document = default_session_document()
        sessions = document["sessions"]
        assert isinstance(sessions, list)
        first = sessions[0]
        assert isinstance(first, dict)
        first["token"] = ROTATED_TOKEN
        write_session_file(settings.session_file, document)
        os.utime(
            settings.session_file,
            ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
        )
        replaced = settings.session_file.stat()
        assert replaced.st_size == original_stat.st_size
        assert replaced.st_mtime_ns == original_stat.st_mtime_ns
        revoked = client.post("/v1/workspaces", headers=AUTH, json=WORKSPACE_BODY)
        accepted = client.post(
            "/v1/workspaces",
            headers={"Authorization": f"Bearer {ROTATED_TOKEN}"},
            json=WORKSPACE_BODY,
        )
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert accepted.status_code in {200, 201}


def test_expired_session_is_rejected_on_resolve(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post("/v1/workspaces", headers=AUTH, json=WORKSPACE_BODY)
        assert created.status_code in {200, 201}
        document = default_session_document()
        sessions = document["sessions"]
        assert isinstance(sessions, list)
        first = sessions[0]
        assert isinstance(first, dict)
        first["expires_at"] = "2020-01-01T00:00:00Z"
        write_session_file(settings.session_file, document)
        expired = client.post("/v1/workspaces", headers=AUTH, json=WORKSPACE_BODY)
    assert expired.status_code == 401
    assert expired.json()["code"] == "AUTHENTICATION_REQUIRED"
