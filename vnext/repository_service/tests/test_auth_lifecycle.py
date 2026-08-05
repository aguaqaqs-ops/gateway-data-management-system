"""Auth, settings, durable-root and provider lifecycle tests for P2-R2 R2-C2."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import cast

from gateway_repository_service.app import create_app
from gateway_repository_service.control_db import ControlDbNewerVersionError, ControlStore
from gateway_repository_service.layout import DurableLayout, LAYOUT_FORMAT_VERSION
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.process import DoltRunner, process_tree_pids
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate, ProviderUnavailableError
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
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
    min_free_disk_bytes: int | None = None,
) -> RepositoryServiceSettings:
    data_root = tmp_path / "data-root"
    kwargs: dict[str, object] = {
        "profile": profile,
        "data_root": data_root,
        "bearer_token": bearer_token,
        "bearer_token_file": bearer_token_file,
        "dolt_binary": dolt_binary or Path("/usr/local/bin/dolt"),
        "dolt_version": dolt_version,
    }
    if min_free_disk_bytes is not None:
        kwargs["min_free_disk_bytes"] = min_free_disk_bytes
    return RepositoryServiceSettings(**kwargs)  # type: ignore[arg-type]


def _dolt_available() -> bool:
    return Path("/usr/local/bin/dolt").is_file()


@pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
class TestLifecycleIntegration:
    def test_runtime_becomes_ready_with_valid_settings(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        runtime = ServiceRuntime.start(settings)
        try:
            assert runtime.is_ready()
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


class TestStartupFailure:
    def test_missing_production_token_aborts_runtime_start(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, profile="production", bearer_token="env-only")
        with pytest.raises(ServiceStartupError, match="production bearer token file is required"):
            ServiceRuntime.start(settings)

    def test_missing_production_token_aborts_lifespan(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, profile="production", bearer_token="env-only")
        with pytest.raises(ServiceStartupError):
            with TestClient(create_app(settings)):
                pass

    def test_lock_contention_aborts_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create_service(settings.data_root)
        holder = DurableRootLock(layout.service_lock).acquire()
        try:
            with pytest.raises(ServiceStartupError, match="durable root lock is held"):
                ServiceRuntime.start(settings)
        finally:
            holder.release()

    def test_corrupt_control_db_aborts_startup_and_releases_lock(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create_service(settings.data_root)
        settings.control_db_path.write_bytes(b"not-a-database")
        with pytest.raises(ServiceStartupError):
            ServiceRuntime.start(settings)
        with DurableRootLock(layout.service_lock):
            pass

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_provider_failure_aborts_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, dolt_binary=Path("/nonexistent/dolt"))
        with pytest.raises(ServiceStartupError, match="dolt executable is unavailable"):
            ServiceRuntime.start(settings)

    def test_newer_control_db_aborts_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        DurableLayout.create_service(settings.data_root)
        settings.control_db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(settings.control_db_path)
        connection.execute("PRAGMA user_version = 99")
        connection.commit()
        connection.close()
        with pytest.raises(ServiceStartupError, match="newer than supported"):
            ServiceRuntime.start(settings)


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

    def test_settings_str_redacts_bearer_token(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, bearer_token="super-secret-token")
        assert "super-secret-token" not in str(settings)
        assert "super-secret-token" not in f"{settings}"
        assert "<redacted>" in str(settings)


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

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_token_file_change_does_not_hot_rotate(self, tmp_path: Path) -> None:
        token_file = tmp_path / "token"
        token_file.write_text("first-token\n", encoding="utf-8")
        settings = _lifecycle_settings(
            tmp_path,
            bearer_token=None,
            bearer_token_file=token_file,
        )
        with TestClient(create_app(settings)) as client:
            app = cast(FastAPI, client.app)
            auth_state = app.state.auth_state
            assert auth_state.bearer_token == "first-token"
            token_file.write_text("second-token\n", encoding="utf-8")
            assert auth_state.bearer_token == "first-token"
            cached_auth = auth_state

        harness_app = create_test_http_app(settings)
        harness_app.state.auth_state = cached_auth
        harness = create_test_client(harness_app)
        assert (
            harness.get(
                "/_test/auth-required",
                headers={"Authorization": "Bearer first-token"},
            ).status_code
            == 200
        )
        assert (
            harness.get(
                "/_test/auth-required",
                headers={"Authorization": "Bearer second-token"},
            ).status_code
            == 401
        )

    def test_production_openapi_excludes_test_routes(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        client = create_test_client(create_app(settings, enable_lifecycle=False))
        paths = client.get("/openapi.json").json()["paths"]
        assert set(paths.keys()) == {"/healthz", "/readyz"}


class TestRootLockContention:
    def test_subprocess_cannot_acquire_held_lock(self, tmp_path: Path) -> None:
        layout = DurableLayout.create_for_probe(tmp_path / "root")
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
        layout = DurableLayout.create_for_probe(root)
        marker = layout.layout_marker
        payload = json.loads(marker.read_text(encoding="utf-8"))
        payload["layout_format_version"] = LAYOUT_FORMAT_VERSION + 1
        marker.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        with pytest.raises(RuntimeError, match="unsupported layout_format_version"):
            DurableLayout.create_for_probe(root)

    def test_service_layout_does_not_create_probe_namespaces(self, tmp_path: Path) -> None:
        layout = DurableLayout.create_service(tmp_path / "root")
        assert not layout.staging_versioned.exists()
        assert not layout.staging_artifacts.exists()
        assert not layout.artifacts.exists()

    def test_probe_layout_creates_probe_namespaces(self, tmp_path: Path) -> None:
        layout = DurableLayout.create_for_probe(tmp_path / "root")
        assert layout.staging_versioned.is_dir()
        assert layout.staging_artifacts.is_dir()
        assert layout.artifacts.is_dir()

    def test_layout_create_does_not_create_control_db(self, tmp_path: Path) -> None:
        layout = DurableLayout.create_service(tmp_path / "root")
        assert not (layout.service_state / "repository-service.sqlite3").exists()


class TestControlDatabase:
    def test_migration_initializes_user_version_two(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        store = ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)
        try:
            version = store.connection.execute("PRAGMA user_version").fetchone()
            assert version is not None
            assert int(version[0]) == 2
            journal_mode = store.connection.execute("PRAGMA journal_mode").fetchone()
            assert str(journal_mode[0]).upper() == "WAL"
            foreign_keys = store.connection.execute("PRAGMA foreign_keys").fetchone()
            assert int(foreign_keys[0]) == 1
            synchronous = store.connection.execute("PRAGMA synchronous").fetchone()
            assert int(synchronous[0]) == 2
            tables = {
                row[0]
                for row in store.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
                if row[0] != "sqlite_sequence"
            }
            assert tables == {"mutation_idempotency", "synchronous_mutation_effects"}
        finally:
            store.close()

    def test_migration_upgrades_version_one_to_two(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        db_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
        connection.close()

        store = ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)
        try:
            version = store.connection.execute("PRAGMA user_version").fetchone()
            assert int(version[0]) == 2
        finally:
            store.close()

    def test_migration_reopen_is_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        first = ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)
        first.close()
        second = ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)
        second.close()

    def test_migration_rolls_back_on_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        original = ControlStore._apply_migration_step

        def failing_step(connection: sqlite3.Connection, target_version: int) -> None:
            if target_version == 2:
                raise RuntimeError("migration failure")
            original(connection, target_version)

        monkeypatch.setattr(ControlStore, "_apply_migration_step", staticmethod(failing_step))
        with pytest.raises(RuntimeError, match="migration failure"):
            ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)

        connection = sqlite3.connect(db_path)
        version = connection.execute("PRAGMA user_version").fetchone()
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        connection.close()
        assert int(version[0]) == 0
        assert tables == []

        monkeypatch.undo()
        store = ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)
        store.close()

    def test_newer_user_version_fails_closed(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        db_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA user_version = 99")
        connection.commit()
        connection.close()
        with pytest.raises(ControlDbNewerVersionError):
            ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)


class TestProviderLifecycle:
    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_capability_gate_verifies_exact_version(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create_for_probe(settings.data_root)
        gate = OfflineCliCapabilityGate.verify(settings, layout)
        assert gate.verified_version == "2.1.11"

    def test_missing_executable_fails_closed(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, dolt_binary=Path("/nonexistent/dolt"))
        layout = DurableLayout.create_for_probe(settings.data_root)
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            OfflineCliCapabilityGate.verify(settings, layout)

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_version_mismatch_fails_closed(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, dolt_version="0.0.1")
        layout = DurableLayout.create_for_probe(settings.data_root)
        with pytest.raises(ProviderUnavailableError):
            OfflineCliCapabilityGate.verify(settings, layout)

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_provider_check_reaps_child_processes(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create_for_probe(settings.data_root)
        before = set(process_tree_pids(os.getpid()))
        OfflineCliCapabilityGate.verify(settings, layout)
        after = set(process_tree_pids(os.getpid()))
        assert after.issubset(before)


class TestDynamicReadiness:
    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_closed_control_db_makes_runtime_not_ready(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        runtime = ServiceRuntime.start(settings)
        try:
            assert runtime.is_ready()
            runtime.control_store.close()
            assert not runtime.is_ready()
            assert "control database is unavailable" in runtime.not_ready_message()
        finally:
            runtime.shutdown()

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_readyz_returns_503_when_control_db_closed(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            runtime = cast(FastAPI, client.app).state.runtime
            runtime.control_store.close()
            response = client.get("/readyz")
            assert response.status_code == 503
            assert response.json()["code"] == "SERVICE_NOT_READY"
            assert "control database is unavailable" in response.json()["message"]

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_readyz_returns_503_when_free_disk_admission_fails(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            with patch(
                "gateway_repository_service.runtime.has_free_disk_admission",
                return_value=False,
            ):
                response = client.get("/readyz")
            assert response.status_code == 503
            assert "free disk admission failed" in response.json()["message"]

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_readyz_returns_503_when_statvfs_raises(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            with patch(
                "gateway_repository_service.capacity.os.statvfs",
                side_effect=OSError("disk unavailable"),
            ):
                response = client.get("/readyz")
            assert response.status_code == 503
            body = response.json()
            assert body["code"] == "SERVICE_NOT_READY"
            assert body["message"] == "free disk admission failed"
            assert "disk unavailable" not in body["message"]

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_readyz_returns_503_when_write_probe_raises(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            with patch(
                "gateway_repository_service.capacity.Path.mkdir",
                side_effect=OSError("read-only filesystem"),
            ):
                response = client.get("/readyz")
            assert response.status_code == 503
            body = response.json()
            assert body["code"] == "SERVICE_NOT_READY"
            assert body["message"] == "durable root is not writable"
            assert "read-only filesystem" not in body["message"]

    @pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
    def test_readyz_returns_503_when_readiness_check_raises(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            with patch(
                "gateway_repository_service.runtime.is_durable_root_writable",
                side_effect=RuntimeError("unexpected probe failure"),
            ):
                response = client.get("/readyz")
            assert response.status_code == 503
            body = response.json()
            assert body["code"] == "SERVICE_NOT_READY"
            assert body["message"] == "readiness check failed"
            assert "unexpected probe failure" not in body["message"]


@pytest.mark.skipif(not _dolt_available(), reason="dolt executable is unavailable")
def test_dolt_runner_version_check_reaps_children(tmp_path: Path) -> None:
    settings = _lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    before = set(process_tree_pids(os.getpid()))
    DoltRunner(settings, layout.root)
    after = set(process_tree_pids(os.getpid()))
    assert after.issubset(before)
