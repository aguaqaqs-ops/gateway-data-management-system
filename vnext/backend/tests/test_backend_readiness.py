"""Backend /readyz, SQLite integrity, artifact root, and registry gates."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from gateway_backend.app import create_app
from gateway_backend.application.job_definitions import JobDefinitionRegistry
from gateway_backend.application.preview_registry import (
    assert_preview_registry_ready,
    build_preview_job_registry,
)
from gateway_backend.infrastructure.control_db import (
    ControlDbIntegrityError,
    connect_control_db,
    initialize_and_verify_control_db,
)
from gateway_backend.infrastructure.control_db.database import assert_control_db_integrity
from gateway_backend.http.auth import StaticInternalBearerPort
from gateway_backend.http.dependencies import ReadOnlySubmissionStore
from gateway_backend.http.runtime import (
    HttpBaselineCanonicalDigestPort,
    HttpRepositoryMainResolvePort,
    assert_repository_service_ready,
    prepare_backend_runtime,
)
from gateway_backend.infrastructure.artifact_store import validate_artifact_root
from gateway_backend.infrastructure.repository_read import load_repository_bearer_token
from tests.support.runtime_settings import (
    TEST_REPOSITORY_TOKEN,
    make_backend_settings,
    prepare_backend_runtime_paths,
)

pytestmark = pytest.mark.unit


def test_preview_registry_rejects_empty_and_accepts_frozen_three_steps() -> None:
    with pytest.raises(Exception, match="no JobDefinition|incomplete"):
        assert_preview_registry_ready(JobDefinitionRegistry.build(()))
    assert_preview_registry_ready(build_preview_job_registry())


def test_assert_repository_service_ready_fails_closed_when_not_ok() -> None:
    with pytest.raises(ValueError, match="not ready"):
        assert_repository_service_ready("http://127.0.0.1:9", "token", timeout_seconds=0.01)


def test_prepare_backend_runtime_fails_closed_without_artifact_root(tmp_path: Path) -> None:
    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "missing-artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    with pytest.raises(ValueError, match="artifact root"):
        prepare_backend_runtime(settings, skip_repository_ready_probe=True)


def test_prepare_backend_runtime_fails_closed_without_token_file(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "missing-token",
    )
    with pytest.raises(ValueError, match="unreadable"):
        prepare_backend_runtime(settings, skip_repository_ready_probe=True)


def test_token_loader_does_not_embed_secret_in_errors(tmp_path: Path) -> None:
    token_file = tmp_path / "repository-bearer-token"
    token_file.write_text(TEST_REPOSITORY_TOKEN + "\n", encoding="utf-8")
    loaded = load_repository_bearer_token(token_file)
    assert loaded == TEST_REPOSITORY_TOKEN
    missing = tmp_path / "absent"
    with pytest.raises(ValueError, match="unreadable") as exc_info:
        load_repository_bearer_token(missing)
    assert TEST_REPOSITORY_TOKEN not in str(exc_info.value)
    assert str(missing) not in str(exc_info.value)


def test_sqlite_integrity_check_passes_after_initialize(tmp_path: Path) -> None:
    db_path = tmp_path / "control.sqlite3"
    initialize_and_verify_control_db(db_path)
    connection = connect_control_db(db_path)
    try:
        assert_control_db_integrity(connection)
    finally:
        connection.close()
    connection = connect_control_db(db_path)
    try:
        assert_control_db_integrity(connection)
    finally:
        connection.close()


def test_sqlite_integrity_check_fails_closed_on_corrupt_file(tmp_path: Path) -> None:
    db_path = tmp_path / "corrupt.sqlite3"
    db_path.write_bytes(b"not-a-sqlite-database")
    with pytest.raises((ControlDbIntegrityError, Exception)):
        initialize_and_verify_control_db(db_path)


def test_production_readyz_is_ok_after_startup_and_omits_secrets(tmp_path: Path) -> None:
    prepare_backend_runtime_paths(tmp_path)
    settings = make_backend_settings(
        tmp_path,
        control_db_path=tmp_path / "control" / "control.sqlite3",
        artifact_root=tmp_path / "artifacts",
        repository_bearer_token_file=tmp_path / "repository-bearer-token",
    )
    with patch("gateway_backend.http.runtime.assert_repository_service_ready"):
        with TestClient(create_app(settings)) as client:
            ready = client.get("/readyz")
            health = client.get("/healthz")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok"}
    assert health.status_code == 200
    assert TEST_REPOSITORY_TOKEN not in ready.text
    assert str(tmp_path) not in ready.text
    assert str(tmp_path) not in health.text
    runtime = prepare_backend_runtime(settings, skip_repository_ready_probe=True)
    assert type(runtime.workspace_http.session_port).__name__ == "LiveFileSessionPort"
    assert type(runtime.workspace_http.scope_resolution).__name__ == "ProvisionedScopeResolution"
    assert type(runtime.workspace_http.baseline_head_read).__name__ == "ProvisionedBaselineHeadRead"
    assert type(runtime.workspace_http.submission_reader) is ReadOnlySubmissionStore
    assert type(runtime.workspace_http.internal_bearer_port) is StaticInternalBearerPort
    assert type(runtime.workspace_http.baseline_canonical_digest) is HttpBaselineCanonicalDigestPort
    assert type(runtime.workspace_http.main_resolve) is HttpRepositoryMainResolvePort
    assert runtime.workspace_http.job_registry.resolve_runnable is not None


def test_validate_artifact_root_requires_existing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(ValueError, match="existing directory"):
        validate_artifact_root(missing)
    with pytest.raises(ValueError, match="existing directory"):
        validate_artifact_root(Path("relative"))
