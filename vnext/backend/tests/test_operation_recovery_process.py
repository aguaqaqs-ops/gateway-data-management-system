"""Process-level R5 fault-matrix evidence (P4-R5-S3c process boundary).

| Fault boundary | Authoritative owner |
|---|---|
| lease expiry (process) | ``test_process_startup_takeover_moves_expired_running_to_retry_wait`` |

Integration-layer lease/takeover proofs live in ``test_operation_takeover``; consumer E2E in S3a.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.operations import StepStatus

pytestmark = [pytest.mark.integration, pytest.mark.serial]

BACKEND_ROOT = Path(__file__).parents[1]


def _subprocess_environment(db_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    source_path = str(BACKEND_ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_path, environment.get("PYTHONPATH")) if part
    )
    return environment


def _deterministic_jitter(lower: float, _upper: float) -> float:
    return lower


def test_process_startup_takeover_moves_expired_running_to_retry_wait(tmp_path: Path) -> None:
    """P4-R5-S3c process owner: expired RUNNING lease -> RETRY_WAIT via startup recovery."""
    db_path = tmp_path / "process-takeover" / "control.sqlite3"
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
    TransitionDisposition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.contracts import JobStepKey
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.recovery import RecoveryCapabilityValue, build_startup_recovery
from gateway_backend.operations.worker import ClaimedExecutor, ExecutionControl, ExecutorAcknowledgment, StartupDisposition
from gateway_backend.operations.worker_startup import WorkerStartup

db_path = Path(sys.argv[1])
from datetime import UTC, datetime, timedelta
clock = {"value": datetime(2026, 8, 24, 12, 0, tzinfo=UTC)}

def now():
    return clock["value"]

initialize_control_db(db_path)
operation = operation_record_from_document({
    "artifact_refs": [], "business_refs": [], "cancel_requested": False,
    "checkpoint_ref": None, "completed_at": None,
    "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
    "created_at": "2024-01-02T03:04:05Z", "diagnostic": None,
    "document_type": "operation", "job_contract_version": "backend-vnext/synthetic/pure-compute/v1",
    "job_kind": "synthetic.pure-compute", "job_payload": {"seed": "alpha"},
    "job_payload_ref": None, "operation_id": "operation-process-takeover",
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
    "status": StepStatus.PENDING.value, "step_id": "step-process-takeover",
    "step_name": "compute", "updated_at": "2024-01-02T03:04:05Z", "worker_id": None,
})
with ControlDbUnitOfWork(db_path, now=now) as unit_of_work:
    unit_of_work.operations.insert_operation_with_initial_step(operation, step)
    claimed = OperationLifecycleActions(
        unit_of_work.operations,
        transaction_now=unit_of_work.operations.transaction_now,
    ).claim_one("worker-process-old", "lease-process-old")
assert claimed is not None
_, claimed_step = claimed
started_at = claimed_step.started_at
clock["value"] = claimed_step.lease_expires_at + timedelta(seconds=1)

def noop_executor(*_args):
    return ExecutorAcknowledgment.PUBLISHED

class Registry:
    def resolve(self, key):
        if key == JobStepKey("synthetic.pure-compute", "compute"):
            return noop_executor
        return None

def read_uow():
    return ControlDbUnitOfWork(db_path, read_only=True, now=now)

def write_uow():
    return ControlDbUnitOfWork(db_path, now=now)

startup = WorkerStartup(
    read_uow_factory=read_uow,
    write_uow_factory=write_uow,
    registry=Registry(),
    recovery_hook=lambda *_args: StartupDisposition.READY,
    startup_recovery=build_startup_recovery(
        write_uow_factory=write_uow,
        capability_lookup=lambda *_args: RecoveryCapabilityValue.PURE_RECOMPUTE,
        jitter=lambda lower, _upper: lower,
        now_factory=now,
    ),
    observer=lambda _event: None,
    worker_id_factory=lambda: "worker-process-new",
    lease_token_factory=lambda: "lease-process-new",
)
assert startup.startup() is StartupDisposition.RETRYABLE_BLOCK
with ControlDbUnitOfWork(db_path, read_only=True, now=now) as unit_of_work:
    persisted = unit_of_work.operations.get_step("step-process-takeover")
assert persisted.status is StepStatus.RETRY_WAIT
assert persisted.started_at == started_at
assert persisted.worker_id is None
assert persisted.lease_token is None
print("TAKEOVER_OK", flush=True)
'''
    process = subprocess.run(
        [sys.executable, "-c", child_code, str(db_path)],
        cwd=BACKEND_ROOT,
        env=_subprocess_environment(db_path),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert "TAKEOVER_OK" in process.stdout
    assert "lease-process-old" not in process.stdout
    assert str(db_path) not in process.stdout

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted = unit_of_work.operations.get_step("step-process-takeover")
    assert persisted.status is StepStatus.RETRY_WAIT
    assert persisted.started_at is not None
