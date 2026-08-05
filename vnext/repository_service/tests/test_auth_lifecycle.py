"""Auth, settings, durable-root and provider lifecycle tests for P2-R2 R2-C2."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from gateway_repository_service.control_db import ControlDbNewerVersionError, ControlStore
from gateway_repository_service.layout import DurableLayout, LAYOUT_FORMAT_VERSION
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.process import DoltRunner, process_tree_pids
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate, ProviderUnavailableError
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings, SettingsError
from support.http_harness import create_test_client, create_test_http_app


def _lifecycle_settings(
    tmp_path: Path,
    *,
    profile: str = "test",
    bearer_token: str | None = "test-bearer-token",
    bearer_token_file: Path | None = None,
    dolt_binary: Path | None = None,
    dolt_version: str = "2.1.11",
) -> RepositoryServiceSettings:
    data_root = tmp_path / "data-root"
    return RepositoryServiceSettings(
        profile=profile,  # type: ignore[arg-type]
        data_root=data_root,
        bearer_token=bearer_token,
        bearer_token_file=bearer_token_file,
        dolt_binary=dolt_binary or Path("/usr/local/bin/dolt"),
        dolt_version=dolt_version,
    )


def _dolt_available() -> bool:
    return Path("/usr/local/bin/dolt").is_file()


@pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
class TestLifecycleIntegration:
    def test_runtime_becomes_ready_with_valid_settings(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        runtime = ServiceRuntime.start(settings)
        try:
            assert runtime.is_ready()
            assert runtime.state.disk_admission is not None
            assert (settings.control_db_path).is_file()
        finally:
            runtime.shutdown()

    def test_readyz_returns_200_when_lifecycle_ready(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            response = client.get("/readyz")
            assert response.status_code == 200
            assert response.json() == {"status": "ready"}

    def test_shutdown_releases_root_lock(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        runtime = ServiceRuntime.start(settings)
        lock_path = runtime.layout.service_lock
        runtime.shutdown()
        with DurableRootLock(lock_path):
            pass


class TestSettingsProfile:
    def test_test_profile_accepts_env_token(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, bearer_token="env-token")
        assert settings.resolve_bearer_token() == "env-token"

    def test_test_profile_accepts_token_file(self, tmp_path: Path) -> None:
        token_file = tmp_path / "token"
        token_file.write_text("file-token\n", encoding="utf-8")
        settings = _lifecycle_settings(
            tmp_path,
            bearer_token=None,
            bearer_token_file=token_file,
        )
        assert settings.resolve_bearer_token() == "file-token"

    def test_production_requires_token_file(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, profile="production", bearer_token="env-only")
        with pytest.raises(SettingsError, match="production bearer token file is required"):
            settings.resolve_bearer_token()

    def test_production_rejects_empty_token_file(self, tmp_path: Path) -> None:
        token_file = tmp_path / "token"
        token_file.write_text("   \n", encoding="utf-8")
        settings = _lifecycle_settings(
            tmp_path,
            profile="production",
            bearer_token="env-only",
            bearer_token_file=token_file,
        )
        with pytest.raises(SettingsError, match="missing or empty"):
            settings.resolve_bearer_token()

    def test_production_ignores_env_token(self, tmp_path: Path) -> None:
        token_file = tmp_path / "token"
        token_file.write_text("file-only-token\n", encoding="utf-8")
        settings = _lifecycle_settings(
            tmp_path,
            profile="production",
            bearer_token="env-token",
            bearer_token_file=token_file,
        )
        assert settings.resolve_bearer_token() == "file-only-token"

    def test_settings_repr_redacts_bearer_token(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, bearer_token="super-secret-token")
        rendered = repr(settings)
        assert "super-secret-token" not in rendered
        assert "<redacted>" in rendered


class TestBearerHarness:
    def test_missing_token_returns_401(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        client = create_test_client(create_test_http_app(settings))
        response = client.get("/_test/auth-required")
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"

    def test_invalid_token_returns_401(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, bearer_token="expected-token")
        client = create_test_client(create_test_http_app(settings))
        response = client.get(
            "/_test/auth-required",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"

    def test_valid_token_returns_200(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, bearer_token="expected-token")
        client = create_test_client(create_test_http_app(settings))
        response = client.get(
            "/_test/auth-required",
            headers={"Authorization": "Bearer expected-token"},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "authorized"}

    def test_error_response_does_not_leak_token(self, tmp_path: Path) -> None:
        secret = "super-secret-bearer-token"
        settings = _lifecycle_settings(tmp_path, bearer_token=secret)
        client = create_test_client(create_test_http_app(settings))
        response = client.get(
            "/_test/auth-required",
            headers={"Authorization": f"Bearer {secret}-wrong"},
        )
        body = response.text
        assert secret not in body

    def test_production_openapi_excludes_test_routes(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        client = create_test_client(create_app(settings, enable_lifecycle=False))
        paths = client.get("/openapi.json").json()["paths"]
        assert set(paths.keys()) == {"/healthz", "/readyz"}


class TestRootLockContention:
    def test_second_lock_holder_fails_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create(settings.data_root)
        holder = DurableRootLock(layout.service_lock).acquire()
        try:
            runtime = ServiceRuntime.start(settings)
            assert not runtime.is_ready()
            assert "durable root lock is held" in runtime.not_ready_message()
            runtime.shutdown()
        finally:
            holder.release()

    def test_subprocess_cannot_acquire_held_lock(self, tmp_path: Path) -> None:
        layout = DurableLayout.create(tmp_path / "root")
        holder = DurableRootLock(layout.service_lock).acquire()
        script = """
import sys
from pathlib import Path
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
try:
    DurableRootLock(Path(sys.argv[1])).acquire()
except RootLockBusy:
    raise SystemExit(2)
raise SystemExit(0)
"""
        try:
            blocked = subprocess.run(
                [sys.executable, "-c", script, str(layout.service_lock)],
                check=False,
            )
            assert blocked.returncode == 2
        finally:
            holder.release()


class TestLayoutValidation:
    def test_newer_layout_format_version_fails_closed(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        layout = DurableLayout.create(root)
        marker = layout.layout_marker
        payload = json.loads(marker.read_text(encoding="utf-8"))
        payload["layout_format_version"] = LAYOUT_FORMAT_VERSION + 1
        marker.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="unsupported layout_format_version"):
            DurableLayout.create(root)

    def test_layout_create_does_not_create_control_db(self, tmp_path: Path) -> None:
        layout = DurableLayout.create(tmp_path / "root")
        assert not (layout.service_state / "repository-service.sqlite3").exists()


class TestControlDatabase:
    def test_migration_initializes_user_version_one(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        store = ControlStore.open(db_path, expected_version=1, busy_timeout_ms=1000)
        try:
            version = store.connection.execute("PRAGMA user_version").fetchone()
            assert version is not None
            assert int(version[0]) == 1
            journal_mode = store.connection.execute("PRAGMA journal_mode").fetchone()
            assert str(journal_mode[0]).upper() == "WAL"
            foreign_keys = store.connection.execute("PRAGMA foreign_keys").fetchone()
            assert int(foreign_keys[0]) == 1
            synchronous = store.connection.execute("PRAGMA synchronous").fetchone()
            assert int(synchronous[0]) == 2
        finally:
            store.close()

    def test_newer_user_version_fails_closed(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        db_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA user_version = 99")
        connection.commit()
        connection.close()
        with pytest.raises(ControlDbNewerVersionError):
            ControlStore.open(db_path, expected_version=1, busy_timeout_ms=1000)

    def test_runtime_not_ready_when_control_db_is_newer(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        db_path = settings.control_db_path
        DurableLayout.create(settings.data_root)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA user_version = 99")
        connection.commit()
        connection.close()
        runtime = ServiceRuntime.start(settings)
        try:
            assert not runtime.is_ready()
            assert "newer than supported" in runtime.not_ready_message()
        finally:
            runtime.shutdown()


class TestProviderLifecycle:
    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_capability_gate_verifies_exact_version(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create(settings.data_root)
        gate = OfflineCliCapabilityGate.verify(settings, layout)
        assert gate.verified_version == "2.1.11"

    def test_missing_executable_fails_closed(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, dolt_binary=Path("/nonexistent/dolt"))
        layout = DurableLayout.create(settings.data_root)
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            OfflineCliCapabilityGate.verify(settings, layout)

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_version_mismatch_fails_closed(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, dolt_version="0.0.1")
        layout = DurableLayout.create(settings.data_root)
        with pytest.raises(ProviderUnavailableError):
            OfflineCliCapabilityGate.verify(settings, layout)

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_provider_check_reaps_child_processes(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create(settings.data_root)
        before = set(process_tree_pids(os.getpid()))
        OfflineCliCapabilityGate.verify(settings, layout)
        after = set(process_tree_pids(os.getpid()))
        assert after.issubset(before)


class TestReadinessFailures:
    def test_missing_bearer_token_prevents_ready(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, bearer_token=None)
        runtime = ServiceRuntime.start(settings)
        try:
            assert not runtime.is_ready()
            assert "bearer token is required" in runtime.not_ready_message()
        finally:
            runtime.shutdown()

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_readyz_returns_503_when_token_missing(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, bearer_token=None)
        with TestClient(create_app(settings)) as client:
            response = client.get("/readyz")
            assert response.status_code == 503
            assert response.json()["code"] == "SERVICE_NOT_READY"


@pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
def test_dolt_runner_version_check_reaps_children(tmp_path: Path) -> None:
    settings = _lifecycle_settings(tmp_path)
    layout = DurableLayout.create(settings.data_root)
    before = set(process_tree_pids(os.getpid()))
    DoltRunner(settings, layout.root)
    after = set(process_tree_pids(os.getpid()))
    assert after.issubset(before)
