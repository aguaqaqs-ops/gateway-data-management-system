"""Submit worker composition and duplicate-delivery integration tests."""

from __future__ import annotations

from pathlib import Path
from threading import Event, Thread

import pytest

from gateway_backend.application.submit_registry import (
    PREPARE_IMPORT_HANDLER,
    submit_job_definitions,
)
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.application.submission.job_payload import SUBMIT_JOB_KIND, SUBMIT_STEP_PREPARE
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationStatus,
    StepStatus,
    TransitionDisposition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.worker import StartupDisposition, WorkerEvent
from tests.support.submit_job_harness import (
    build_submit_worker_harness,
    dolt_available,
    repository_service_session,
    submit_step_id,
)

pytestmark = pytest.mark.integration


def _submit_operation_document(operation_id: str) -> dict[str, object]:
    return {
        "artifact_refs": [],
        "business_refs": [{"kind": "submit_attempt", "value": "sa-worker-1"}],
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2026-08-24T12:00:00Z",
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": SUBMIT_JOB_CONTRACT_VERSION,
        "job_kind": SUBMIT_JOB_KIND,
        "job_payload": {
            "document_type": "submit_job_payload",
            "contract_version": SUBMIT_JOB_CONTRACT_VERSION,
            "submit_attempt_id": "sa-worker-1",
            "workspace_id": "ws-worker-1",
            "generation": 1,
            "upload_revision_id": "ur-worker-1",
            "preview_result_id": "pr-worker-1",
            "repository_id": "repo-worker-1",
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
            "repository_upload_idempotency_key": "upload-worker-1",
            "repository_import_idempotency_key": "import-worker-1",
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
        "updated_at": "2026-08-24T12:00:00Z",
    }


def _submit_step_document(operation_id: str, step_id: str, step_name: str) -> dict[str, object]:
    return {
        "attempt_count": 0,
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": "2026-08-24T12:00:00Z",
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
        "step_name": step_name,
        "updated_at": "2026-08-24T12:00:00Z",
        "worker_id": None,
    }


def test_submit_worker_composition_registers_submit_handlers(tmp_path: Path) -> None:
    harness = build_submit_worker_harness(tmp_path, repository_base_url="http://127.0.0.1:9")
    assert submit_job_definitions()
    assert PREPARE_IMPORT_HANDLER in harness.handlers
    assert harness.runtime._startup.startup() is StartupDisposition.READY


def test_submit_worker_runtime_claims_submit_operation(tmp_path: Path) -> None:
    harness = build_submit_worker_harness(tmp_path, repository_base_url="http://127.0.0.1:9")
    operation_id = "operation-submit-worker-1"
    step_id = submit_step_id(operation_id, SUBMIT_STEP_PREPARE)
    operation = operation_record_from_document(_submit_operation_document(operation_id))
    step = step_record_from_document(
        _submit_step_document(operation_id, step_id=step_id, step_name=SUBMIT_STEP_PREPARE)
    )
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
    startup = harness.runtime._startup
    assert startup.startup() is StartupDisposition.READY
    work = startup.claim_one()
    assert work is not None
    assert work.operation.operation_id == operation_id
    assert work.step.step_id == step_id
    assert callable(work.executor)
    assert work.step.step_name == SUBMIT_STEP_PREPARE


@pytest.mark.serial
def test_submit_worker_duplicate_claim_is_exclusive(tmp_path: Path) -> None:
    harness = build_submit_worker_harness(tmp_path, repository_base_url="http://127.0.0.1:9")
    operation_id = "operation-submit-worker-duplicate"
    step_id = submit_step_id(operation_id, SUBMIT_STEP_PREPARE)
    operation = operation_record_from_document(_submit_operation_document(operation_id))
    step = step_record_from_document(
        _submit_step_document(operation_id, step_id=step_id, step_name=SUBMIT_STEP_PREPARE)
    )
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )
    startup = harness.runtime._startup
    assert startup.startup() is StartupDisposition.READY
    first = startup.claim_one()
    assert first is not None
    second = startup.claim_one()
    assert second is None
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        claimed_step = unit_of_work.operations.get_step(step_id)
    assert claimed_step.worker_id is not None
    assert claimed_step.lease_token is not None


@pytest.mark.serial
def test_submit_worker_reaches_ready_with_live_repository_service(tmp_path: Path) -> None:
    if not dolt_available():
        pytest.skip("dolt is not available")

    with repository_service_session(tmp_path) as service:
        ready = Event()
        stop = Event()

        def observe(event: WorkerEvent) -> None:
            if event.code.value == "worker_ready":
                ready.set()

        runtime = build_submit_worker_harness(
            tmp_path / "worker-live-runtime",
            repository_base_url=service.base_url,
            observer=observe,
        ).runtime
        runner = Thread(target=runtime.run, args=(stop.is_set, stop.wait), daemon=False)
        runner.start()
        try:
            assert ready.wait(timeout=15)
        finally:
            stop.set()
            runner.join(timeout=15)
        assert not runner.is_alive()
