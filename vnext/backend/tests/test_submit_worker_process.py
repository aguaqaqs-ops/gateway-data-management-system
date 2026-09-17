"""Real module-entrypoint evidence for submit-aware operation worker drain."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND, SUBMIT_STEP_PREPARE
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationStatus,
    StepStatus,
)
from tests.support.runtime_settings import write_mapping_file

pytestmark = [pytest.mark.integration, pytest.mark.serial]

BACKEND_ROOT = Path(__file__).parents[1]
MODULE = "gateway_backend.bootstrap.operation_worker"


def _submit_operation_document(operation_id: str) -> dict[str, object]:
    return {
        "artifact_refs": [],
        "business_refs": [{"kind": "submit_attempt", "value": "sa-process-1"}],
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2024-01-02T03:04:05Z",
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": SUBMIT_JOB_CONTRACT_VERSION,
        "job_kind": SUBMIT_JOB_KIND,
        "job_payload": {
            "document_type": "submit_job_payload",
            "contract_version": SUBMIT_JOB_CONTRACT_VERSION,
            "submit_attempt_id": "sa-process-1",
            "workspace_id": "ws-process-1",
            "generation": 1,
            "upload_revision_id": "ur-process-1",
            "preview_result_id": "pr-process-1",
            "repository_id": "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11",
            "business_baseline_node_id": "node-1",
            "business_baseline_commit_id": "commit-base",
            "baseline_head_version": 3,
            "repository_expected_commit_id": "commit-base",
            "canonical_business_digest": "sha256:canonical",
            "source_artifact_refs": ["source-1"],
            "preview_ready_closure_ref": "closure-1",
            "snapshot_table_set_digest": "sha256:snapshot-set",
            "ruleset_version": "v1",
            "storage_projection_version": "v1",
            "canonicalization_manifest_contract_version": "v1",
            "repository_import_package_version": 1,
            "accept_request_fingerprint": "fp-accept",
            "repository_upload_idempotency_key": "upload-process-1",
            "repository_import_idempotency_key": "import-process-1",
            "repository_policy": {
                "target_ref": "main",
                "verification_policy": "STRUCTURAL",
                "unknown_type_policy": "REJECT",
            },
            "builder_mutation_policy": "REBUILD_ALWAYS",
            "options": {},
        },
        "job_payload_ref": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "ready_closure_ref": None,
        "repository_operation_id": None,
        "status": OperationStatus.QUEUED.value,
        "updated_at": "2024-01-02T03:04:05Z",
    }


def _submit_step_document(operation_id: str, step_id: str) -> dict[str, object]:
    return {
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
        "operation_id": operation_id,
        "optimistic_version": 0,
        "prior_output_refs": [],
        "retry_not_before": None,
        "started_at": None,
        "status": StepStatus.PENDING.value,
        "step_id": step_id,
        "step_name": SUBMIT_STEP_PREPARE,
        "updated_at": "2024-01-02T03:04:05Z",
        "worker_id": None,
    }


def _subprocess_environment(db_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    source_path = str(BACKEND_ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_path, environment.get("PYTHONPATH")) if part
    )
    environment["GATEWAY_BACKEND_OPERATION_WORKER_CONTROL_DB_PATH"] = str(db_path)
    artifact_root = db_path.parent / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    token_file = db_path.parent / "repository-bearer-token"
    token_file.write_text("test-repository-token\n", encoding="utf-8")
    environment["GATEWAY_BACKEND_OPERATION_WORKER_ARTIFACT_ROOT"] = str(artifact_root)
    environment["GATEWAY_BACKEND_OPERATION_WORKER_REPOSITORY_BASE_URL"] = "http://127.0.0.1:9"
    environment["GATEWAY_BACKEND_OPERATION_WORKER_REPOSITORY_BEARER_TOKEN_FILE"] = str(token_file)
    mapping_file = write_mapping_file(db_path.parent / "provisioned-mapping.json")
    environment["GATEWAY_BACKEND_OPERATION_WORKER_PROVISIONED_MAPPING_FILE"] = str(mapping_file)
    return environment


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


def test_module_worker_bootstraps_submit_registry_and_drains_on_sigterm(tmp_path: Path) -> None:
    db_path = tmp_path / "submit-process" / "control.sqlite3"
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
    assert str(db_path) not in output
    assert "test-repository-token" not in output
    assert db_path.is_file()


@pytest.mark.parametrize(
    ("termination_barrier", "expected_step_version"),
    (("before_checkpoint", 1), ("after_checkpoint", 2)),
)
def test_submit_process_termination_respects_checkpoint_commit_barrier(
    tmp_path: Path,
    termination_barrier: str,
    expected_step_version: int,
) -> None:
    db_path = tmp_path / "submit-termination" / "control.sqlite3"
    db_path.parent.mkdir(parents=True)
    child_code = r'''
import dataclasses
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gateway_backend.application.submission.job_payload import SUBMIT_STEP_PREPARE
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
    "document_type": "operation", "job_contract_version": "backend-vnext/submit/v1",
    "job_kind": "backend-vnext/submit", "job_payload": {"submit_attempt_id": "sa-1"},
    "job_payload_ref": None, "operation_id": "operation-submit-checkpoint",
    "optimistic_version": 0, "ready_closure_ref": None, "repository_operation_id": None,
    "status": OperationStatus.QUEUED.value, "updated_at": "2024-01-02T03:04:05Z",
})
step = step_record_from_document({
    "attempt_count": 0, "cancel_requested": False, "checkpoint_ref": None,
    "completed_at": None, "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
    "created_at": "2024-01-02T03:04:05Z", "diagnostic": None,
    "document_type": "step", "lease_expires_at": None, "lease_token": None,
    "operation_id": "operation-submit-checkpoint", "optimistic_version": 0,
    "prior_output_refs": [], "retry_not_before": None, "started_at": None,
    "status": StepStatus.PENDING.value, "step_id": "step-submit-checkpoint",
    "step_name": SUBMIT_STEP_PREPARE, "updated_at": "2024-01-02T03:04:05Z", "worker_id": None,
})
with ControlDbUnitOfWork(db_path, now=clock) as unit_of_work:
    unit_of_work.operations.insert_operation_with_initial_step(operation, step)
    claimed = OperationLifecycleActions(
        unit_of_work.operations,
        transaction_now=unit_of_work.operations.transaction_now,
    ).claim_one("worker-submit-checkpoint", "lease-submit-checkpoint")
assert claimed is not None
claimed_operation, claimed_step = claimed

def write_uow_factory():
    return ControlDbUnitOfWork(db_path, now=clock)

session = LeaseSession(
    worker_id="worker-submit-checkpoint", lease_token="lease-submit-checkpoint",
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
        persisted_operation = unit_of_work.operations.get_operation("operation-submit-checkpoint")
        persisted_step = unit_of_work.operations.get_step("step-submit-checkpoint")
    assert persisted_operation.status is OperationStatus.RUNNING
    assert persisted_step.status is StepStatus.RUNNING
    assert persisted_step.optimistic_version == expected_step_version
