"""Submit worker composition and duplicate-delivery integration tests."""

from __future__ import annotations

from pathlib import Path
from threading import Event, Thread

import pytest

from gateway_backend.application.recovery import RecoveryOutcomeDisposition
from gateway_backend.application.submit_jobs import build_submit_recovery_port
from gateway_backend.application.submit_registry import (
    PREPARE_IMPORT_HANDLER,
    SUBMIT_IMPORT_HANDLER,
    submit_job_definitions,
)
from gateway_backend.capabilities.storage_projection.contracts import REPOSITORY_IMPORT_MEDIA_TYPE
from gateway_backend.domain.submission.models import SubmitAttemptState
from gateway_backend.application.submission.contracts import SUBMIT_JOB_CONTRACT_VERSION
from gateway_backend.application.submission.job_payload import (
    SUBMIT_JOB_KIND,
    SUBMIT_STEP_PREPARE,
    SUBMIT_STEP_SUBMIT,
)
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.worker import ExecutionControl, ExecutorAcknowledgment
from gateway_backend.bootstrap.operation_worker import build_worker_write_uow_factory
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationStatus,
    StepStatus,
    TransitionDisposition,
    WritePrecondition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.worker import StartupDisposition, WorkerEvent
from tests.support.submit_job_harness import (
    RecordingTransport,
    build_submit_worker_harness,
    repository_service_session,
    submit_step_id,
)
from tests.test_submit_job_prepare import _accept_prepared_operation, _run_prepare_handler

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
def test_submit_worker_reaches_ready_with_live_repository_service(
    tmp_path: Path,
    requires_dolt: None,
) -> None:
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


REPOSITORY_UUID = "018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11"


def test_submit_worker_executes_submit_import_publishes_checkpoint(tmp_path: Path) -> None:
    transport = RecordingTransport()
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=transport,
    )
    operation_id = _accept_prepared_operation(
        harness.db_path,
        harness.artifact_store,
        repository_id=REPOSITORY_UUID,
    )
    _run_prepare_handler(harness.db_path, harness.artifact_store, operation_id)

    startup = harness.runtime._startup
    assert startup.startup() is StartupDisposition.READY
    work = startup.claim_one()
    assert work is not None
    assert work.step.step_name == SUBMIT_STEP_SUBMIT
    assert work.step.worker_id is not None
    assert work.step.lease_token is not None
    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(harness.db_path)

    control = ExecutionControl()
    session = LeaseSession(
        worker_id=work.step.worker_id,
        lease_token=work.step.lease_token,
        operation_id=work.operation.operation_id,
        step_id=work.step.step_id,
        write_uow_factory=build_worker_write_uow_factory(control_transaction_factory),
        control=control,
        observer=lambda _event: None,
    )
    acknowledgment = work.executor(work.operation, work.step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
    assert len(transport.requests) >= 2

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        submit_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_SUBMIT)
        )
        steps, _cursor = unit_of_work.operations.list_steps(operation_id)
        await_step = next(step for step in steps if step.step_name == "await_import_result")
    assert submit_step.checkpoint_ref is not None
    assert await_step.status is StepStatus.PENDING


@pytest.mark.serial
def test_submit_import_w2_crash_rebuilds_checkpoint_via_claim(tmp_path: Path) -> None:
    from dataclasses import replace
    from datetime import timedelta

    from gateway_backend.domain.submission.models import (
        BackendArtifactRef,
        RepositoryArtifactRef,
        SubmitAttemptState,
    )
    from tests.test_submit_transactions import _SHA_MANIFEST, _SHA_PACKAGE, _SHA_REPO

    transport = RecordingTransport()
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=transport,
    )
    operation_id = _accept_prepared_operation(
        harness.db_path,
        harness.artifact_store,
        repository_id=REPOSITORY_UUID,
    )
    _run_prepare_handler(harness.db_path, harness.artifact_store, operation_id)

    submit_id = submit_step_id(operation_id, SUBMIT_STEP_SUBMIT)
    worker_id = "worker-submit-w2"
    lease_token = "lease-submit-w2"
    backend_ref = BackendArtifactRef(
        artifact_id="backend-pkg-1",
        media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
        size_bytes=10,
        raw_sha256=_SHA_PACKAGE,
    )
    repository_ref = RepositoryArtifactRef(
        artifact_id="018f0f0f-3e7b-7c16-8a9e-2e4b9f4d2c12",
        media_type=REPOSITORY_IMPORT_MEDIA_TYPE,
        size_bytes=10,
        raw_sha256=_SHA_REPO,
    )
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        operation_record = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value
            for ref in operation_record.business_refs
            if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        updated = replace(
            attempt,
            state=SubmitAttemptState.EFFECT_PENDING,
            effect_pending_at=unit_of_work.operations.transaction_now,
            canonicalization_manifest_ref="manifest-1",
            canonicalization_manifest_digest=_SHA_MANIFEST,
            repository_import_artifact_ref=backend_ref,
            repository_artifact_ref=repository_ref,
            repository_operation_id=None,
            optimistic_version=attempt.optimistic_version + 1,
        )
        unit_of_work.submission.cas_update_attempt(updated, expected_version=attempt.optimistic_version)
        submit_step = unit_of_work.operations.get_step(submit_id)
        now = unit_of_work.operations.transaction_now
        running_submit = replace(
            submit_step,
            status=StepStatus.RUNNING,
            attempt_count=1,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_expires_at=now + timedelta(seconds=60),
            started_at=now,
            updated_at=now,
            checkpoint_ref=None,
            optimistic_version=submit_step.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            running_submit,
            WritePrecondition(
                expected_optimistic_version=submit_step.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )

    def control_transaction_factory() -> ControlDbUnitOfWork:
        return ControlDbUnitOfWork(harness.db_path)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(submit_id)
    assert step.checkpoint_ref is None

    handler = harness.handlers[SUBMIT_IMPORT_HANDLER]
    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation.operation_id,
        step_id=step.step_id,
        write_uow_factory=build_worker_write_uow_factory(control_transaction_factory),
        control=control,
        observer=lambda _event: None,
    )
    acknowledgment = handler(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        submit_step = unit_of_work.operations.get_step(step.step_id)
    assert submit_step.checkpoint_ref is not None


def test_submit_import_upload_response_loss_replays_via_recovery(tmp_path: Path) -> None:
    from dataclasses import replace
    from datetime import timedelta

    from gateway_backend.domain.submission.models import SubmitAttemptState

    transport = RecordingTransport()
    harness = build_submit_worker_harness(
        tmp_path / "worker-upload-replay",
        repository_base_url="http://repository.test",
        transport=transport,
    )
    operation_id = _accept_prepared_operation(
        harness.db_path,
        harness.artifact_store,
        repository_id=REPOSITORY_UUID,
    )
    _run_prepare_handler(harness.db_path, harness.artifact_store, operation_id)
    submit_id = submit_step_id(operation_id, SUBMIT_STEP_SUBMIT)
    worker_id = "worker-upload-replay"
    lease_token = "lease-upload-replay"
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_step = unit_of_work.operations.get_step(submit_id)
        now = unit_of_work.operations.transaction_now
        running_submit = replace(
            submit_step,
            status=StepStatus.RUNNING,
            attempt_count=1,
            worker_id=worker_id,
            lease_token=lease_token,
            lease_expires_at=now + timedelta(seconds=60),
            started_at=now,
            updated_at=now,
            checkpoint_ref=None,
            optimistic_version=submit_step.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            running_submit,
            WritePrecondition(
                expected_optimistic_version=submit_step.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        operation = unit_of_work.operations.get_operation(operation_id)
    recovery = build_submit_recovery_port(harness.submit_deps)
    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation.operation_id,
        step_id=submit_id,
        write_uow_factory=build_worker_write_uow_factory(
            lambda: ControlDbUnitOfWork(harness.db_path)
        ),
        control=control,
        observer=lambda _event: None,
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        step = unit_of_work.operations.get_step(submit_id)
    outcome = recovery.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.PUBLISHED
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        submit_step = unit_of_work.operations.get_step(submit_id)
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.EFFECT_PENDING
    assert attempt.repository_artifact_ref is not None
    assert submit_step.checkpoint_ref is not None
    assert any(request.url.endswith("/artifacts") for request in transport.requests)


def test_submit_import_prepared_without_prepare_checkpoint_stays_manual_recovery(
    tmp_path: Path,
) -> None:
    from gateway_backend.application.recovery import DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED
    from tests.test_submit_recovery import _seed_running_submit_without_checkpoint
    from tests.test_submit_transactions import seed_submit_ready_workspace

    harness = build_submit_worker_harness(
        tmp_path / "worker-upload-no-prepare",
        repository_base_url="http://127.0.0.1:9",
    )
    db_path = harness.db_path
    seed = seed_submit_ready_workspace(db_path, repository_id=REPOSITORY_UUID)
    attempt, operation, step, worker_id, lease_token = _seed_running_submit_without_checkpoint(
        db_path,
        seed,
    )
    recovery = build_submit_recovery_port(harness.submit_deps)
    control = ExecutionControl()
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation.operation_id,
        step_id=step.step_id,
        write_uow_factory=build_worker_write_uow_factory(
            lambda: ControlDbUnitOfWork(db_path)
        ),
        control=control,
        observer=lambda _event: None,
    )
    outcome = recovery.recover(operation, step, control, session)
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert outcome.diagnostic_code == DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        current = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
    assert current is not None
    assert current.state is SubmitAttemptState.PREPARED
