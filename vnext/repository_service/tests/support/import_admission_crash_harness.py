"""Shared helpers for Versioned import admission subprocess crash tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.http.readiness import LifecycleReadiness
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_import.models import IMPORT_ADMISSION_PENDING_STATUS
from gateway_repository_service.versioned_import.store import ImportOperationStore
from support.crash_recovery_worker import CRASH_EXIT_CODE
from support.http_harness import import_headers, import_request_body
from support.import_recovery_harness import restart_runtime, wait_for_import_status
from support.import_worker_harness import MEDIA_TYPE
from support.lifecycle_harness import lifecycle_settings
from support.upload_harness import upload_headers
from test_import_package import build_package_bytes

_WORKER = Path(__file__).with_name("import_admission_crash_worker.py")


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    tests_root = str(_WORKER.parent.parent)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = tests_root if not existing else f"{tests_root}{os.pathsep}{existing}"
    return env


def _worker_command(*args: str) -> list[str]:
    return [sys.executable, str(_WORKER), *args]


def build_import_package_bytes() -> bytes:
    replay_sql = (
        "CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\n"
        "INSERT INTO records (id) VALUES (1);\n"
    )
    manifest = {
        "package_version": 1,
        "canonicalization_manifest_digest": "manifest-digest-1",
        "tables": [
            {
                "name": "records",
                "schema": {
                    "columns": [{"name": "id", "sql_type": "BIGINT", "nullable": False}],
                    "primary_key": ["id"],
                },
                "row_count": 1,
            }
        ],
    }
    return build_package_bytes(manifest=manifest, replay_sql=replay_sql.encode("utf-8"))


def crash_admission_subprocess(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    artifact_id: UUID,
    size_bytes: int,
    raw_sha256: str,
    expected_commit_id: str,
    idempotency_key: str,
    fault_point: str,
    status_out: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = _worker_command(
        "--data-root",
        str(settings.data_root),
        "--dolt-binary",
        str(settings.dolt_binary),
        "--dolt-version",
        settings.dolt_version,
        "--repository-id",
        str(repository_id),
        "--artifact-id",
        str(artifact_id),
        "--size-bytes",
        str(size_bytes),
        "--raw-sha256",
        raw_sha256,
        "--expected-commit-id",
        expected_commit_id,
        "--idempotency-key",
        idempotency_key,
        "--fault-point",
        fault_point,
    )
    if status_out is not None:
        command.extend(["--status-out", str(status_out)])
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=_worker_env(),
    )


def assert_crash_exit(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == CRASH_EXIT_CODE, completed.stderr


def seed_repository_with_import_artifact(
    tmp_path: Path,
) -> tuple[RepositoryServiceSettings, UUID, UUID, str, int, str]:
    settings = lifecycle_settings(tmp_path)
    payload = build_import_package_bytes()
    runtime = ServiceRuntime.start(settings)
    try:
        app = create_app(settings, enable_lifecycle=False)
        app.state.runtime = runtime
        app.state.auth_state = runtime.auth_state
        app.state.readiness = LifecycleReadiness(runtime)
        with TestClient(app) as client:
            create_response = client.post(
                "/v1/repositories",
                headers={
                    "Authorization": "Bearer test-bearer-token",
                    "Idempotency-Key": "admission-crash-create",
                },
            )
            assert create_response.status_code == 201
            body = create_response.json()
            repository_id = UUID(body["repository_id"])
            expected_commit_id = body["initial_commit_id"]

            upload_response = client.post(
                f"/v1/repositories/{repository_id}/artifacts",
                headers=upload_headers(
                    idempotency_key="admission-crash-upload",
                    payload=payload,
                ),
                content=payload,
            )
            assert upload_response.status_code == 201
            artifact_ref = upload_response.json()["artifact_ref"]
            artifact_id = UUID(artifact_ref["artifact_id"])
            size_bytes = int(artifact_ref["size_bytes"])
            raw_sha256 = str(artifact_ref["raw_sha256"])
    finally:
        runtime.shutdown()

    return settings, repository_id, artifact_id, expected_commit_id, size_bytes, raw_sha256


def open_import_store(settings: RepositoryServiceSettings) -> tuple[ControlStore, ImportOperationStore]:
    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    return control_store, store


def submit_import_http(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    artifact_id: UUID,
    size_bytes: int,
    raw_sha256: str,
    expected_commit_id: str,
    idempotency_key: str,
) -> tuple[int, dict[str, object]]:
    runtime = ServiceRuntime.start(settings)
    try:
        app = create_app(settings, enable_lifecycle=False)
        app.state.auth_state = runtime.auth_state
        app.state.runtime = runtime
        client = TestClient(app)
        body = import_request_body(
            repository_id=repository_id,
            artifact_id=artifact_id,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
            expected_commit_id=expected_commit_id,
        )
        response = client.post(
            f"/v1/repositories/{repository_id}/versioned/imports",
            headers=import_headers(idempotency_key=idempotency_key),
            content=json.dumps(body),
        )
        return response.status_code, response.json()
    finally:
        runtime.shutdown()


__all__ = [
    "IMPORT_ADMISSION_PENDING_STATUS",
    "MEDIA_TYPE",
    "assert_crash_exit",
    "crash_admission_subprocess",
    "open_import_store",
    "restart_runtime",
    "seed_repository_with_import_artifact",
    "submit_import_http",
    "wait_for_import_status",
]
