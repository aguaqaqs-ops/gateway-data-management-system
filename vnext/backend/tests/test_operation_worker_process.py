"""Real module-entrypoint and signal evidence for the operation worker."""

from __future__ import annotations

import os
import selectors
import signal
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationStatus,
    StepStatus,
    TransitionDisposition,
    operation_record_from_document,
    step_record_from_document,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]

BACKEND_ROOT = Path(__file__).parents[1]
MODULE = "gateway_backend.bootstrap.operation_worker"


def _spawn_worker(db_path: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", MODULE],
        cwd=BACKEND_ROOT,
        env=_subprocess_environment(db_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def _subprocess_environment(db_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    source_path = str(BACKEND_ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_path, environment.get("PYTHONPATH")) if part
    )
    environment["GATEWAY_BACKEND_OPERATION_WORKER_CONTROL_DB_PATH"] = str(db_path)
    return environment


def _read_until(process: subprocess.Popen[str], marker: str, timeout: float = 5.0) -> str:
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    lines: list[str] = []
    try:
        while True:
            ready = selector.select(timeout=timeout)
            assert ready, f"worker did not emit {marker!r}; output={''.join(lines)!r}"
            line = process.stdout.readline()
            if not line:
                break
            lines.append(line)
            if marker in line:
                return "".join(lines)
    finally:
        selector.close()
    return "".join(lines)


def _finish(process: subprocess.Popen[str], signal_number: signal.Signals) -> str:
    os.kill(process.pid, signal_number)
    try:
        output, _ = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate(timeout=5)
        pytest.fail(f"worker did not exit after signal; output={output!r}")
    return output


def test_module_worker_bootstraps_empty_db_and_drains_on_sigterm(tmp_path: Path) -> None:
    db_path = tmp_path / "server-owned" / "control.sqlite3"
    process = _spawn_worker(db_path)
    try:
        initial_output = _read_until(process, "code=worker_ready")
        output = initial_output + _finish(process, signal.SIGTERM)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode == 0
    assert "code=drain_started" in output
    assert "code=worker_exited" in output
    assert "RuntimeWarning" not in output
    assert "runpy" not in output
    assert str(db_path) not in output
    assert db_path.is_file()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute(
            "SELECT version FROM control_schema_migrations WHERE component = 'operations'"
        ).fetchone()[0] == 1


@pytest.mark.parametrize("failure_kind", ("corrupt", "higher_schema"))
def test_module_worker_failure_is_nonzero_and_redacted(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    db_path = tmp_path / failure_kind / "control.sqlite3"
    db_path.parent.mkdir(parents=True)
    if failure_kind == "corrupt":
        db_path.write_bytes(b"not-a-sqlite-database")
    else:
        initialize_control_db(db_path)
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "UPDATE control_schema_migrations SET version = 2 WHERE component = 'operations'"
            )
            connection.commit()

    process = _spawn_worker(db_path)
    try:
        output, _ = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode != 0
    assert "operation_worker_failed" in output
    assert str(db_path) not in output
    assert "lease-" not in output


def test_missing_handler_failure_redacts_payload_token_path_and_sql(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "redaction" / "control.sqlite3"
    db_path.parent.mkdir(parents=True)
    initialize_control_db(db_path)
    secret_token = "lease-s6-secret-token"
    secret_sql = "SELECT secret_value FROM private_table"
    operation = operation_record_from_document(
        {
            "artifact_refs": [],
            "business_refs": [],
            "cancel_requested": False,
            "checkpoint_ref": None,
            "completed_at": None,
            "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
            "created_at": "2024-01-02T03:04:05Z",
            "diagnostic": None,
            "document_type": "operation",
            "job_contract_version": "backend-vnext/import-package/v1",
            "job_kind": "import.package",
            "job_payload": {
                "database_path": str(db_path),
                "lease_token": secret_token,
                "sql": secret_sql,
            },
            "job_payload_ref": None,
            "operation_id": "operation-redaction-1",
            "optimistic_version": 0,
            "ready_closure_ref": None,
            "repository_operation_id": None,
            "status": OperationStatus.QUEUED.value,
            "updated_at": "2024-01-02T03:04:05Z",
        }
    )
    step = step_record_from_document(
        {
            "attempt_count": 0,
            "cancel_requested": False,
            "checkpoint_ref": None,
            "completed_at": None,
            "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
            "created_at": "2024-01-02T03:04:05Z",
            "diagnostic": None,
            "document_type": "step",
            "lease_expires_at": None,
            "lease_token": None,
            "operation_id": operation.operation_id,
            "optimistic_version": 0,
            "prior_output_refs": [],
            "retry_not_before": None,
            "started_at": None,
            "status": StepStatus.PENDING.value,
            "step_id": "step-redaction-1",
            "step_name": "validate",
            "updated_at": "2024-01-02T03:04:05Z",
            "worker_id": None,
        }
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )

    process = _spawn_worker(db_path)
    try:
        output, _ = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode != 0
    assert "operation_worker_failed" in output
    assert secret_token not in output
    assert secret_sql not in output
    assert str(db_path) not in output


@pytest.mark.parametrize(
    ("termination_barrier", "expected_step_version"),
    (("before_checkpoint", 1), ("after_checkpoint", 2)),
)
def test_process_termination_respects_checkpoint_commit_barrier(
    tmp_path: Path,
    termination_barrier: str,
    expected_step_version: int,
) -> None:
    db_path = tmp_path / "termination" / "control.sqlite3"
    db_path.parent.mkdir(parents=True)
    child_code = r'''
import dataclasses
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationStatus,
    StepStatus,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.worker import ExecutionControl

db_path = Path(sys.argv[1])
clock_value = datetime.now(UTC) - timedelta(seconds=60)
clock = lambda: clock_value
initialize_control_db(db_path, now=clock)
operation = operation_record_from_document({
    "artifact_refs": [], "business_refs": [], "cancel_requested": False,
    "checkpoint_ref": None, "completed_at": None,
    "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
    "created_at": "2024-01-02T03:04:05Z", "diagnostic": None,
    "document_type": "operation", "job_contract_version": "backend-vnext/import-package/v1",
    "job_kind": "import.package", "job_payload": {"request": {"value": 1}},
    "job_payload_ref": None, "operation_id": "operation-process-1",
    "optimistic_version": 0, "ready_closure_ref": None, "repository_operation_id": None,
    "status": OperationStatus.QUEUED.value, "updated_at": "2024-01-02T03:04:05Z",
})
step = step_record_from_document({
    "attempt_count": 0, "cancel_requested": False, "checkpoint_ref": None,
    "completed_at": None, "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
    "created_at": "2024-01-02T03:04:05Z", "diagnostic": None,
    "document_type": "step", "lease_expires_at": None, "lease_token": None,
    "operation_id": operation.operation_id, "optimistic_version": 0,
    "prior_output_refs": [], "retry_not_before": None, "started_at": None,
    "status": StepStatus.PENDING.value, "step_id": "step-process-1",
    "step_name": "validate", "updated_at": "2024-01-02T03:04:05Z", "worker_id": None,
})
with ControlDbUnitOfWork(db_path, now=clock) as unit_of_work:
    unit_of_work.operations.insert_operation_with_initial_step(operation, step)
    claimed = OperationLifecycleActions(
        unit_of_work.operations,
        transaction_now=unit_of_work.operations.transaction_now,
    ).claim_one("worker-process-1", "lease-process-1")
assert claimed is not None
claimed_operation, claimed_step = claimed

def write_uow_factory():
    return ControlDbUnitOfWork(db_path, now=clock)

session = LeaseSession(
    worker_id="worker-process-1", lease_token="lease-process-1",
    operation_id=claimed_operation.operation_id, step_id=claimed_step.step_id,
    write_uow_factory=write_uow_factory, control=ExecutionControl(), observer=lambda _event: None,
)
session.refresh_control()
print("BEFORE_CHECKPOINT", flush=True)
sys.stdin.buffer.read(1)
session.publish_checkpoint(
    lambda _operation, current_step, now: dataclasses.replace(
        current_step, updated_at=now, optimistic_version=current_step.optimistic_version + 1,
    )
)
print("AFTER_CHECKPOINT", flush=True)
sys.stdin.buffer.read(1)
'''
    process = subprocess.Popen(
        [sys.executable, "-c", child_code, str(db_path)],
        cwd=BACKEND_ROOT,
        env=_subprocess_environment(db_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        _read_until(process, "BEFORE_CHECKPOINT")
        if termination_barrier == "after_checkpoint":
            assert process.stdin is not None
            process.stdin.write("1")
            process.stdin.flush()
            _read_until(process, "AFTER_CHECKPOINT")
        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation("operation-process-1")
        persisted_step = unit_of_work.operations.get_step("step-process-1")
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_step.optimistic_version == expected_step_version
    assert persisted_step.lease_expires_at is not None
    assert persisted_step.lease_expires_at < datetime.now(UTC) - timedelta(seconds=1)
