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

from support.lifecycle_harness import prepare_test_roots
from gateway_repository_service.storage_roots import RepositoryRoots
from gateway_repository_service.app import create_app
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlDbError, ControlDbNewerVersionError, ControlStore
from gateway_repository_service.layout import DurableLayout, LAYOUT_FORMAT_VERSION
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.process import DoltRunner, process_tree_pids
from gateway_repository_service.provider_lifecycle import OfflineCliCapabilityGate, ProviderUnavailableError
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from gateway_repository_service.settings import SettingsError, RepositoryServiceSettings
from support.http_harness import PRODUCTION_OPENAPI_PATHS, create_test_client, create_test_http_app


from support.lifecycle_harness import lifecycle_settings as _lifecycle_settings


def _production_auth_settings(tmp_path: Path) -> RepositoryServiceSettings:
    from support.storage_layout import write_storage_layout
    roots = prepare_test_roots(RepositoryRoots.under(tmp_path / "production-roots"))
    storage = write_storage_layout(roots)
    resources = tmp_path / "production-resources.json"
    document = json.loads((Path(__file__).parents[2] / "fixtures/runtime-config/v1/resource-profile.json").read_bytes())
    document.update(environment_id="test", group_id="test")
    resources.write_text(json.dumps(document))
    return RepositoryServiceSettings(profile="production", bearer_token="env-only",
        storage_layout_file=storage, resource_profile_file=resources)


@pytest.mark.integration
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
        settings = _production_auth_settings(tmp_path)
        with patch("gateway_repository_service.runtime.RuntimePreflight") as guard:
            with pytest.raises(ServiceStartupError, match="production bearer token file is required"):
                ServiceRuntime.start(settings)
        guard.assert_called_once_with(settings.deployment_config, "repository_service", startup_capacity=False)
        assert not settings.control_db_path.exists()

    def test_missing_production_token_aborts_lifespan(self, tmp_path: Path) -> None:
        settings = _production_auth_settings(tmp_path)
        with patch("gateway_repository_service.runtime.RuntimePreflight"):
            with pytest.raises(ServiceStartupError, match="production bearer token file is required"):
                with TestClient(create_app(settings)):
                    pass
        assert not settings.control_db_path.exists()

    def test_lock_contention_aborts_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create_service(settings.storage_roots)
        holder = DurableRootLock(layout.service_lock).acquire()
        try:
            with pytest.raises(ServiceStartupError, match="durable root lock is held"):
                ServiceRuntime.start(settings)
        finally:
            holder.release()

    def test_corrupt_control_db_aborts_startup_and_releases_lock(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create_service(settings.storage_roots)
        settings.control_db_path.write_bytes(b"not-a-database")
        with pytest.raises(ServiceStartupError):
            ServiceRuntime.start(settings)
        with DurableRootLock(layout.service_lock):
            pass

    @pytest.mark.integration
    def test_provider_failure_aborts_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, dolt_binary=Path("/nonexistent/dolt"))
        with pytest.raises(ServiceStartupError, match="dolt executable is unavailable"):
            ServiceRuntime.start(settings)

    def test_newer_control_db_aborts_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        DurableLayout.create_service(settings.storage_roots)
        settings.control_db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(settings.control_db_path)
        connection.execute("PRAGMA user_version = 99")
        connection.commit()
        connection.close()
        with pytest.raises(ServiceStartupError, match="newer than supported"):
            ServiceRuntime.start(settings)

    def test_older_control_db_aborts_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        DurableLayout.create_service(settings.storage_roots)
        settings.control_db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(settings.control_db_path)
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
        connection.close()
        with pytest.raises(ServiceStartupError, match="older than supported"):
            ServiceRuntime.start(settings)

    def test_schema_drift_control_db_aborts_startup(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        DurableLayout.create_service(settings.storage_roots)
        ControlStore.open(
            settings.control_db_path,
            expected_version=CONTROL_DB_USER_VERSION,
            busy_timeout_ms=1000,
        ).close()
        connection = sqlite3.connect(settings.control_db_path)
        connection.execute("ALTER TABLE artifact_lifecycle ADD COLUMN bytes_delete_intent_at TEXT NULL")
        connection.commit()
        connection.close()
        with pytest.raises(ServiceStartupError, match="does not match baseline"):
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

    @pytest.mark.integration
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
        assert set(paths.keys()) == PRODUCTION_OPENAPI_PATHS


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
        with pytest.raises(RuntimeError, match="invalid or unsupported"):
            DurableLayout.create_for_probe(root)

    def test_service_layout_creates_mutation_staging_not_probe_artifacts(self, tmp_path: Path) -> None:
        layout = DurableLayout.create_service(prepare_test_roots(RepositoryRoots.under(tmp_path / "root")))
        assert layout.staging_versioned.is_dir()
        assert layout.staging_artifacts.is_dir()
        assert layout.artifacts.is_dir()
        assert not layout.probe_namespaces

    def test_probe_layout_creates_probe_namespaces(self, tmp_path: Path) -> None:
        layout = DurableLayout.create_for_probe(tmp_path / "root")
        assert layout.staging_versioned.is_dir()
        assert layout.staging_artifacts.is_dir()
        assert layout.artifacts.is_dir()

    def test_layout_create_does_not_create_control_db(self, tmp_path: Path) -> None:
        layout = DurableLayout.create_service(prepare_test_roots(RepositoryRoots.under(tmp_path / "root")))
        assert not (layout.service_state / "repository-service.sqlite3").exists()


_CONTROL_DB_VERSION_MISMATCH_CASES: tuple[tuple[int, bool, type[ControlDbError], str], ...] = (
    (0, True, ControlDbError, "older than supported"),
    (1, False, ControlDbError, "older than supported"),
    (15, False, ControlDbError, "older than supported"),
    (17, False, ControlDbNewerVersionError, "user_version 17 is newer than supported 16"),
    (99, False, ControlDbNewerVersionError, "newer than supported"),
)

_CONTROL_DB_SCHEMA_DRIFT_CASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "extra_table_artifact_residual",
        ("CREATE TABLE artifact_residual (residual_id INTEGER PRIMARY KEY)",),
    ),
    (
        "missing_table_audit",
        ("DROP TABLE repository_import_recovery_audit",),
    ),
    (
        "extra_column_delete_intent",
        ("ALTER TABLE artifact_lifecycle ADD COLUMN bytes_delete_intent_at TEXT NULL",),
    ),
    (
        "extra_column_delete_receipt",
        ("ALTER TABLE artifact_lifecycle ADD COLUMN bytes_deleted_receipt_dev INTEGER NULL",),
    ),
    (
        "altered_column_type",
        (
            "DROP TABLE repository_import_recovery_audit",
            """
            CREATE TABLE repository_import_recovery_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id BLOB NOT NULL
            )
            """,
        ),
    ),
    (
        "missing_constraint",
        (
            "DROP TABLE repository_import_recovery_audit",
            """
            CREATE TABLE repository_import_recovery_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id TEXT NOT NULL,
                action TEXT NOT NULL,
                prior_status TEXT NOT NULL,
                prior_code TEXT NULL,
                final_status TEXT NOT NULL,
                final_code TEXT NULL,
                evidence_summary_json TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """,
        ),
    ),
    (
        "missing_index",
        ("DROP INDEX repository_import_operations_manual_barrier_idx",),
    ),
    (
        "modified_index",
        (
            "DROP INDEX repository_import_operations_manual_barrier_idx",
            """
            CREATE INDEX repository_import_operations_manual_barrier_idx
            ON repository_import_operations (repository_scope)
            """,
        ),
    ),
    (
        "extra_index",
        ("CREATE INDEX extra_artifact_media_idx ON artifact_lifecycle (media_type)",),
    ),
    (
        "missing_trigger",
        ("DROP TRIGGER prevent_insert_succeeded_when_terminal",),
    ),
    (
        "modified_trigger",
        (
            "DROP TRIGGER artifact_lifecycle_forbid_cleanup_seq_update",
            """
            CREATE TRIGGER artifact_lifecycle_forbid_cleanup_seq_update
            BEFORE UPDATE OF cleanup_seq ON artifact_lifecycle
            BEGIN
                SELECT RAISE(ABORT, 'modified trigger body');
            END
            """,
        ),
    ),
    (
        "extra_view",
        ("CREATE VIEW extra_view AS SELECT 1 AS ok",),
    ),
)


class TestControlDatabase:
    def _seed_terminal_succeeded_contradiction(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO mutation_idempotency (
                mutation_kind,
                repository_scope,
                key_hash,
                request_fingerprint,
                terminal_not_published,
                created_at
            ) VALUES ('create_repository', '', ?, ?, 1, '2026-08-05T00:00:00+00:00')
            """,
            (b"\x01" * 32, b"legacy-fingerprint"),
        )
        idempotency_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        connection.execute(
            """
            INSERT INTO synchronous_mutation_effects (
                idempotency_id,
                resource_id,
                status,
                response_status,
                response_body,
                updated_at
            ) VALUES (?, ?, 'SUCCEEDED', 201, '{}', '2026-08-05T00:00:00+00:00')
            """,
            (idempotency_id, "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"),
        )
        connection.commit()

    def test_baseline_initializes_current_user_version_and_schema(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        store = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
        try:
            version = store.connection.execute("PRAGMA user_version").fetchone()
            assert version is not None
            assert int(version[0]) == CONTROL_DB_USER_VERSION
            journal_mode = store.connection.execute("PRAGMA journal_mode").fetchone()
            assert journal_mode is not None
            assert str(journal_mode[0]).upper() == "WAL"
            foreign_keys = store.connection.execute("PRAGMA foreign_keys").fetchone()
            assert foreign_keys is not None
            assert int(foreign_keys[0]) == 1
            synchronous = store.connection.execute("PRAGMA synchronous").fetchone()
            assert synchronous is not None
            assert int(synchronous[0]) == 2
            tables = {
                row[0]
                for row in store.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
                if row[0] != "sqlite_sequence"
            }
            assert tables == {
                "artifact_lifecycle",
                "mutation_idempotency",
                "repository_import_operations",
                "repository_import_recovery_audit",
                "synchronous_mutation_effects",
            }
            assert "artifact_residual" not in tables
            artifact_columns = {
                row[1]
                for row in store.connection.execute("PRAGMA table_info(artifact_lifecycle)").fetchall()
            }
            assert artifact_columns == {
                "artifact_id",
                "repository_scope",
                "media_type",
                "size_bytes",
                "raw_sha256",
                "created_at",
                "updated_at",
                "consumed_by_operation_id",
                "consumed_at",
                "bytes_deleted_at",
                "cleanup_seq",
            }
            operation_columns = {
                row[1]
                for row in store.connection.execute(
                    "PRAGMA table_info(repository_import_operations)"
                ).fetchall()
            }
            assert "enqueue_sequence" in operation_columns
            assert "manual_recovery_required" in operation_columns
            barrier_index = store.connection.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type = 'index'
                  AND name = 'repository_import_operations_manual_barrier_idx'
                """
            ).fetchone()
            assert barrier_index is not None
            assert "manual_recovery_required = 1" in str(barrier_index[0])
            idempotency_sql = store.connection.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'mutation_idempotency'"
            ).fetchone()
            effects_sql = store.connection.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'synchronous_mutation_effects'"
            ).fetchone()
            assert idempotency_sql is not None and effects_sql is not None
            assert "create_repository" in str(idempotency_sql[0])
            assert "upload_artifact" in str(idempotency_sql[0])
            assert "response_status = 201" in str(effects_sql[0])
            triggers = {
                row[0]
                for row in store.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                ).fetchall()
            }
            assert triggers == {
                "prevent_succeeded_when_terminal",
                "prevent_terminal_when_succeeded",
                "prevent_insert_succeeded_when_terminal",
                "prevent_insert_terminal_when_succeeded",
                "artifact_lifecycle_forbid_cleanup_seq_update",
            }
        finally:
            store.close()

    def test_baseline_reopen_is_idempotent_and_preserves_data(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        first = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
        try:
            first.connection.execute(
                """
                INSERT INTO mutation_idempotency (
                    mutation_kind,
                    repository_scope,
                    key_hash,
                    request_fingerprint,
                    terminal_not_published,
                    created_at
                ) VALUES ('create_repository', '', ?, ?, 0, '2026-08-05T00:00:00+00:00')
                """,
                (b"\x02" * 32, b"fp-reopen"),
            )
            first.connection.commit()
        finally:
            first.close()

        second = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
        try:
            row = second.connection.execute(
                "SELECT COUNT(*) FROM mutation_idempotency WHERE request_fingerprint = ?",
                (b"fp-reopen",),
            ).fetchone()
            assert row is not None and int(row[0]) == 1
        finally:
            second.close()

        ControlStore.preflight_exact_version(db_path, expected_version=CONTROL_DB_USER_VERSION)
        readonly = ControlStore.open_readonly(db_path, expected_version=CONTROL_DB_USER_VERSION)
        try:
            row = readonly.connection.execute(
                "SELECT COUNT(*) FROM mutation_idempotency WHERE request_fingerprint = ?",
                (b"fp-reopen",),
            ).fetchone()
            assert row is not None and int(row[0]) == 1
        finally:
            readonly.close()

    def test_baseline_init_rolls_back_on_statement_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        original_execute_statements = ControlStore._execute_statements

        def failing_baseline_execute(
            connection: sqlite3.Connection, statements: tuple[str, ...]
        ) -> None:
            if statements and "mutation_idempotency" in statements[0]:
                original_execute_statements(connection, (statements[0],))
                raise RuntimeError("baseline ddl failure")
            original_execute_statements(connection, statements)

        monkeypatch.setattr(
            ControlStore,
            "_execute_statements",
            staticmethod(failing_baseline_execute),
        )
        with pytest.raises(RuntimeError, match="baseline ddl failure"):
            ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)

        connection = sqlite3.connect(db_path)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            in_transaction = connection.in_transaction
        finally:
            connection.close()
        assert version is not None and int(version[0]) == 0
        assert tables == set()
        assert in_transaction is False

        monkeypatch.undo()
        store = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
        store.close()

    def test_rejects_mismatched_expected_version(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        with pytest.raises(ControlDbError, match="does not match baseline"):
            ControlStore.open(db_path, expected_version=2, busy_timeout_ms=1000)
        assert not db_path.exists()

    @pytest.mark.parametrize(
        ("user_version", "seed_table", "exc_type", "pattern"),
        _CONTROL_DB_VERSION_MISMATCH_CASES,
        ids=[f"v{case[0]}-table{case[1]}" for case in _CONTROL_DB_VERSION_MISMATCH_CASES],
    )
    def test_non_baseline_user_version_fails_closed_without_modification(
        self,
        tmp_path: Path,
        user_version: int,
        seed_table: bool,
        exc_type: type[ControlDbError],
        pattern: str,
    ) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        db_path.parent.mkdir(parents=True)
        connection = sqlite3.connect(db_path)
        try:
            if seed_table:
                connection.execute("CREATE TABLE leftover (id INTEGER PRIMARY KEY)")
            connection.execute(f"PRAGMA user_version = {user_version}")
            connection.commit()
        finally:
            connection.close()

        before = db_path.read_bytes()
        with pytest.raises(exc_type, match=pattern):
            ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
        assert db_path.read_bytes() == before

        with pytest.raises(ControlDbError, match=f"{pattern}|WAL mode is unavailable"):
            ControlStore.open(
                db_path,
                expected_version=CONTROL_DB_USER_VERSION,
                busy_timeout_ms=1000,
                allow_migration=False,
            )
        with pytest.raises(exc_type, match=pattern):
            ControlStore.preflight_exact_version(db_path, expected_version=CONTROL_DB_USER_VERSION)
        assert db_path.read_bytes() == before

    @pytest.mark.parametrize(
        ("label", "statements"),
        _CONTROL_DB_SCHEMA_DRIFT_CASES,
        ids=[case[0] for case in _CONTROL_DB_SCHEMA_DRIFT_CASES],
    )
    def test_exact_schema_mismatch_with_matching_user_version_fails_closed(
        self,
        tmp_path: Path,
        label: str,
        statements: tuple[str, ...],
    ) -> None:
        del label
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        store = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
        store.checkpoint_wal_truncate()
        store.close()

        connection = sqlite3.connect(db_path)
        try:
            connection.execute("PRAGMA journal_mode = DELETE")
            for statement in statements:
                connection.execute(statement)
            connection.commit()
        finally:
            connection.close()

        before = db_path.read_bytes()
        with pytest.raises(ControlDbError, match="does not match baseline"):
            ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
        assert db_path.read_bytes() == before

        with pytest.raises(ControlDbError, match="does not match baseline|WAL mode is unavailable"):
            ControlStore.open(
                db_path,
                expected_version=CONTROL_DB_USER_VERSION,
                busy_timeout_ms=1000,
                allow_migration=False,
            )
        with pytest.raises(ControlDbError, match="does not match baseline|WAL mode is unavailable"):
            ControlStore.preflight_exact_version(db_path, expected_version=CONTROL_DB_USER_VERSION)
        assert db_path.read_bytes() == before

    def test_in_use_constraints_and_triggers_enforced(self, tmp_path: Path) -> None:
        db_path = tmp_path / "service-state" / "repository-service.sqlite3"
        store = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                self._seed_terminal_succeeded_contradiction(store.connection)
            store.connection.rollback()

            with pytest.raises(sqlite3.IntegrityError):
                store.connection.execute(
                    """
                    INSERT INTO mutation_idempotency (
                        mutation_kind,
                        repository_scope,
                        key_hash,
                        request_fingerprint,
                        terminal_not_published,
                        created_at
                    ) VALUES ('create_repository', 'non-empty', ?, ?, 0, '2026-08-05T00:00:00+00:00')
                    """,
                    (b"\x03" * 32, b"fp-bad-scope"),
                )
            store.connection.rollback()

            store.connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id,
                    repository_scope,
                    media_type,
                    size_bytes,
                    raw_sha256,
                    created_at,
                    updated_at,
                    cleanup_seq
                ) VALUES (
                    '018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c12',
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'application/vnd.gateway.repository-import.v1+tar+zstd',
                    1,
                    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                    '2026-08-05T00:00:00+00:00',
                    '2026-08-05T00:00:00+00:00',
                    1
                )
                """
            )
            store.connection.commit()
            with pytest.raises(sqlite3.IntegrityError, match="cleanup_seq is immutable"):
                store.connection.execute(
                    """
                    UPDATE artifact_lifecycle
                    SET cleanup_seq = 2
                    WHERE artifact_id = '018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c12'
                    """
                )
            store.connection.rollback()
        finally:
            store.close()


class TestProviderLifecycle:
    @pytest.mark.integration
    def test_capability_gate_verifies_exact_version(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create_for_probe(settings.storage_roots)
        gate = OfflineCliCapabilityGate.verify(settings, layout)
        assert gate.verified_version == "2.1.11"

    def test_missing_executable_fails_closed(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, dolt_binary=Path("/nonexistent/dolt"))
        layout = DurableLayout.create_for_probe(settings.storage_roots)
        with pytest.raises(ProviderUnavailableError, match="unavailable"):
            OfflineCliCapabilityGate.verify(settings, layout)

    @pytest.mark.integration
    def test_version_mismatch_fails_closed(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path, dolt_version="0.0.1")
        layout = DurableLayout.create_for_probe(settings.storage_roots)
        with pytest.raises(ProviderUnavailableError):
            OfflineCliCapabilityGate.verify(settings, layout)

    @pytest.mark.integration
    def test_provider_check_reaps_child_processes(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        layout = DurableLayout.create_for_probe(settings.storage_roots)
        before = set(process_tree_pids(os.getpid()))
        OfflineCliCapabilityGate.verify(settings, layout)
        after = set(process_tree_pids(os.getpid()))
        assert after.issubset(before)


class TestDynamicReadiness:
    @pytest.mark.integration
    @pytest.mark.serial
    def test_unavailable_control_db_makes_runtime_not_ready(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        runtime = ServiceRuntime.start(settings)
        try:
            assert runtime.is_ready()
            with patch.object(runtime.control_store, "is_open", return_value=False):
                assert not runtime.is_ready()
                assert "control database is unavailable" in runtime.not_ready_message()
        finally:
            runtime.shutdown()

    @pytest.mark.integration
    def test_readyz_returns_503_when_control_db_unavailable(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            runtime = cast(FastAPI, client.app).state.runtime
            with patch.object(runtime.control_store, "is_open", return_value=False):
                response = client.get("/readyz")
                assert response.status_code == 503
                assert response.json()["code"] == "SERVICE_NOT_READY"
                assert "control database is unavailable" in response.json()["message"]

    @pytest.mark.integration
    def test_readyz_returns_503_when_free_disk_admission_fails(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            with patch(
                "gateway_repository_service.runtime.has_layout_disk_admission",
                return_value=False,
            ):
                response = client.get("/readyz")
            assert response.status_code == 503
            assert "free disk admission failed" in response.json()["message"]

    @pytest.mark.integration
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

    @pytest.mark.integration
    def test_readyz_returns_503_when_write_probe_raises(self, tmp_path: Path) -> None:
        settings = _lifecycle_settings(tmp_path)
        with TestClient(create_app(settings)) as client:
            assert client.get("/readyz").status_code == 200
            with patch(
                "gateway_repository_service.capacity.Path.write_text",
                side_effect=OSError("read-only filesystem"),
            ):
                response = client.get("/readyz")
            assert response.status_code == 503
            body = response.json()
            assert body["code"] == "SERVICE_NOT_READY"
            assert body["message"] == "durable root is not writable"
            assert "read-only filesystem" not in body["message"]

    @pytest.mark.integration
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


@pytest.mark.integration
def test_dolt_runner_version_check_reaps_children(tmp_path: Path) -> None:
    settings = _lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.storage_roots)
    before = set(process_tree_pids(os.getpid()))
    DoltRunner.for_layout(settings, layout)
    after = set(process_tree_pids(os.getpid()))
    assert after.issubset(before)
