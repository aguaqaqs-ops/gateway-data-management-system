"""Shared helpers for Versioned import recovery and restart tests."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

from gateway_repository_contracts import OperationStatus
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.settings import RepositoryServiceSettings
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


def assert_crash_exit(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == CRASH_EXIT_CODE, completed.stderr
