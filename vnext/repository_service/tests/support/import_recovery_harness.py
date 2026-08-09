"""Shared helpers for Versioned import recovery and restart tests."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

from gateway_repository_contracts import OperationStatus, RepositoryArtifactRef, UnknownTypePolicy, VerificationPolicy
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import IdempotencyKeyHash
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import ImportOperationStore, ImportRequestBinding, versioned_import_fingerprint_v1
from support.import_worker_harness import MEDIA_TYPE, published_repository_path
from test_import_package import build_package_bytes, write_artifact
from support.crash_recovery_worker import CRASH_EXIT_CODE
from support.lifecycle_harness import lifecycle_settings

_WORKER = Path(__file__).with_name("import_crash_recovery_worker.py")


def start_runtime(tmp_path: Path, **settings_kwargs: object) -> tuple[RepositoryServiceSettings, ServiceRuntime]:
    settings = lifecycle_settings(tmp_path, **settings_kwargs)  # type: ignore[arg-type]
    return settings, ServiceRuntime.start(settings)


def restart_runtime(settings: RepositoryServiceSettings) -> ServiceRuntime:
    return ServiceRuntime.start(settings)


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    tests_root = str(_WORKER.parent.parent)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = tests_root if not existing else f"{tests_root}{os.pathsep}{existing}"
    return env


def _worker_command(*args: str) -> list[str]:
    return [sys.executable, str(_WORKER), *args]


def crash_import_subprocess(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    operation_id: UUID,
    fault_point: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _worker_command(
            "--data-root",
            str(settings.data_root),
            "--dolt-binary",
            str(settings.dolt_binary),
            "--dolt-version",
            settings.dolt_version,
            "--repository-id",
            str(repository_id),
            "--operation-id",
            str(operation_id),
            "--fault-point",
            fault_point,
        ),
        check=False,
        capture_output=True,
        text=True,
        env=_worker_env(),
        timeout=150,
    )


def wait_for_import_status(
    runtime: ServiceRuntime,
    repository_id: UUID,
    operation_id: UUID,
    expected: OperationStatus,
    *,
    timeout: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        operation = runtime.import_store.get_operation(repository_id, operation_id)
        if operation is not None and operation.status == expected:
            return
        time.sleep(0.05)
    operation = runtime.import_store.get_operation(repository_id, operation_id)
    raise AssertionError(
        f"operation {operation_id} did not reach {expected.value}, last={operation}"
    )


_RECOVERY_WORKER = Path(__file__).with_name("import_recovery_crash_worker.py")


def crash_recovery_reconcile_subprocess(
    settings: RepositoryServiceSettings,
    *,
    repository_id: UUID,
    fault_point: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(_RECOVERY_WORKER),
            "--data-root",
            str(settings.data_root),
            "--dolt-binary",
            str(settings.dolt_binary),
            "--dolt-version",
            settings.dolt_version,
            "--repository-id",
            str(repository_id),
            "--fault-point",
            fault_point,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_worker_env(),
    )


def assert_crash_exit(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == CRASH_EXIT_CODE, completed.stderr


def seed_queued_dolt_import(
    tmp_path: Path,
    *,
    repository_id: UUID | None = None,
    artifact_id: UUID | None = None,
    operation_id: UUID | None = None,
    key: str = "dolt-crash",
) -> tuple[RepositoryServiceSettings, UUID, UUID, UUID, str]:
    settings = lifecycle_settings(tmp_path)
    resolved_repository_id = repository_id or uuid4()
    resolved_artifact_id = artifact_id or uuid4()
    resolved_operation_id = operation_id or uuid4()
    layout = DurableLayout.create_for_probe(settings.data_root)
    repository = published_repository_path(layout, resolved_repository_id)
    repository.mkdir(parents=True, exist_ok=True)
    runner = DoltRunner(settings, layout.root)
    cli = OfflineCliProvider(settings, layout, repository, runner)
    cli.initialize_repository()
    expected_commit = cli.head()

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
    payload = build_package_bytes(manifest=manifest, replay_sql=replay_sql.encode("utf-8"))
    ready_path = artifact_ready_path(layout, resolved_repository_id, resolved_artifact_id)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    size_bytes, raw_sha256 = write_artifact(ready_path, payload)

    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    now = "2026-08-06T00:00:00+00:00"
    with store._lock:
        store.mutation_store._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id, repository_scope, media_type, size_bytes, raw_sha256, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(resolved_artifact_id),
                resolved_repository_id.hex,
                MEDIA_TYPE,
                size_bytes,
                raw_sha256,
                now,
                now,
            ),
        )
        store.mutation_store._connection.commit()

    binding = ImportRequestBinding(
        repository_id=resolved_repository_id,
        artifact_ref=RepositoryArtifactRef(
            artifact_id=resolved_artifact_id,
            media_type=MEDIA_TYPE,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        ),
        target_ref="main",
        expected_commit_id=expected_commit,
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    key_hash = IdempotencyKeyHash.from_raw_key(key)
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        operation_id=resolved_operation_id,
    )
    control_store.close()
    return settings, resolved_repository_id, resolved_artifact_id, resolved_operation_id, expected_commit
