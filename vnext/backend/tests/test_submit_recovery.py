"""Submit external-effect recovery and operator abort integration tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from gateway_backend.application.recovery import (
    DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED,
    DIAGNOSTIC_RECONCILE_TIMEOUT,
    RecoveryOutcomeDisposition,
)
from gateway_backend.application.submit_jobs import (
    build_await_import_result_handler,
    build_submit_recovery_port,
)
from gateway_backend.application.submission.errors import RepositoryWriteTimeoutError
from gateway_backend.application.submission.abort_transaction import (
    AbortSubmitTransactionRequest,
    abort_submit_transaction,
)
from gateway_backend.application.submission.accept_transaction import accept_submit_transaction
from gateway_backend.application.submit_registry import submit_job_registry
from gateway_backend.application.submission.contracts import (
    MatchingAbortProof,
    RepositoryOperationTerminalStatus,
)
from gateway_backend.application.submission.job_payload import SUBMIT_STEP_AWAIT, SUBMIT_STEP_SUBMIT
from gateway_backend.domain.submission.models import SubmitAttempt, SubmitAttemptState
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.database import initialize_control_db
from gateway_backend.operations import (
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    WritePrecondition,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.worker import ExecutionControl, ExecutorAcknowledgment
from gateway_backend.infrastructure.repository_write.http import HttpRepositoryWriteClient
from gateway_backend.bootstrap.operation_worker import build_worker_write_uow_factory
from gateway_backend.infrastructure.repository_write.abort_evidence import HttpRepositoryAbortEvidencePort
from tests.support.submit_job_harness import (
    RecordingTransport,
    assert_occupancy_released,
    assert_occupancy_retained,
    build_submit_worker_harness,
    repository_service_session,
    submit_step_id,
)
from tests.test_submit_job_effect import (
    _await_lease_identity,
    _lease_session,
    _operation_poll_handler,
    _prepare_manifest_digest,
    _run_submit_to_await_claim,
)
from tests.support.workspace_fixtures import FixedScopeResolutionPort
from tests.test_submit_transactions import (
    BASELINE_HEAD,
    FakeAbortEvidencePort,
    FakeBaselineCanonicalDigestPort,
    RecordingMainResolvePort,
    SubmitSeed,
    _accept_command,
    _preflight,
    _seed_effect_pending_attempt,
    _uow_factory,
    seed_submit_ready_workspace,
)

pytestmark = pytest.mark.integration

TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)


def _initialized_db_path(tmp_path: Path, name: str) -> Path:
    db_path = tmp_path / name
    initialize_control_db(db_path)
    return db_path


def _seed_running_submit_without_checkpoint(
    db_path: Path,
    seed: SubmitSeed,
) -> tuple[SubmitAttempt, OperationRecord, StepRecord, str, str]:
    from gateway_backend.application.submission.job_payload import SUBMIT_STEP_PREPARE
    prepare_worker_id = "worker-prepare"
    prepare_lease_token = "lease-prepare"
    submit_worker_id = "worker-submit"
    submit_lease_token = "lease-submit"
    accepted = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-recovery-running"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    prepare_id = submit_step_id(accepted.operation_id, SUBMIT_STEP_PREPARE)
    submit_id = submit_step_id(accepted.operation_id, SUBMIT_STEP_SUBMIT)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(accepted.submit_attempt_id)
        assert attempt is not None
        now = unit_of_work.operations.transaction_now
        lease_expires_at = now + timedelta(seconds=60)
        prepare = unit_of_work.operations.get_step(prepare_id)
        running_prepare = replace(
            prepare,
            status=StepStatus.RUNNING,
            attempt_count=1,
            started_at=now,
            updated_at=now,
            worker_id=prepare_worker_id,
            lease_token=prepare_lease_token,
            lease_expires_at=lease_expires_at,
            optimistic_version=prepare.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            running_prepare,
            WritePrecondition(
                expected_optimistic_version=prepare.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        succeeded_prepare = replace(
            running_prepare,
            status=StepStatus.SUCCEEDED,
            completed_at=now,
            updated_at=now,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            optimistic_version=running_prepare.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            succeeded_prepare,
            WritePrecondition(
                expected_optimistic_version=running_prepare.optimistic_version,
                worker_id=prepare_worker_id,
                lease_token=prepare_lease_token,
            ),
            require_live_lease=True,
        )
        pending_submit = StepRecord(
            contract_version=prepare.contract_version,
            step_id=submit_id,
            operation_id=accepted.operation_id,
            step_name=SUBMIT_STEP_SUBMIT,
            status=StepStatus.PENDING,
            attempt_count=0,
            diagnostic=None,
            cancel_requested=False,
            retry_not_before=None,
            worker_id=None,
            lease_token=None,
            lease_expires_at=None,
            checkpoint_ref=None,
            prior_output_refs=(),
            created_at=now,
            updated_at=now,
            started_at=None,
            completed_at=None,
            optimistic_version=0,
        )
        unit_of_work.operations.insert_successor_step(pending_submit)
        running_submit = replace(
            pending_submit,
            status=StepStatus.RUNNING,
            attempt_count=1,
            worker_id=submit_worker_id,
            lease_token=submit_lease_token,
            lease_expires_at=lease_expires_at,
            started_at=now,
            updated_at=now,
            optimistic_version=pending_submit.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_step(
            running_submit,
            WritePrecondition(
                expected_optimistic_version=pending_submit.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
        operation = unit_of_work.operations.get_operation(accepted.operation_id)
        running_operation = replace(
            operation,
            status=OperationStatus.RUNNING,
            updated_at=now,
            optimistic_version=operation.optimistic_version + 1,
        )
        unit_of_work.operations.compare_and_set_operation(
            running_operation,
            WritePrecondition(
                expected_optimistic_version=operation.optimistic_version,
                worker_id=None,
                lease_token=None,
            ),
        )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        return (
            attempt,
            unit_of_work.operations.get_operation(accepted.operation_id),
            unit_of_work.operations.get_step(submit_id),
            submit_worker_id,
            submit_lease_token,
        )


def test_submit_recovery_without_checkpoint_retains_occupancy(tmp_path: Path) -> None:
    harness = build_submit_worker_harness(
        tmp_path / "worker",
        repository_base_url="http://127.0.0.1:9",
    )
    db_path = harness.db_path
    seed = seed_submit_ready_workspace(db_path)
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
    assert_occupancy_retained(
        db_path,
        workspace_id=seed.workspace.workspace_id,
        repository_id=seed.workspace.repository_id,
        submit_attempt_id=attempt.submit_attempt_id,
    )


def test_prepared_attempt_operator_abort_retains_occupancy(tmp_path: Path) -> None:
    db_path = _initialized_db_path(tmp_path, "recovery-prepared-abort.sqlite3")
    seed = seed_submit_ready_workspace(db_path)
    accepted = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-prepared-abort"),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=BASELINE_HEAD,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=_preflight(seed),
        now=TS1,
    )
    with pytest.raises(ValueError, match="abort requires EFFECT_PENDING attempt"):
        abort_submit_transaction(
            request=AbortSubmitTransactionRequest(
                submit_attempt_id=accepted.submit_attempt_id,
                proof=MatchingAbortProof(
                    repository_id=seed.workspace.repository_id,
                    repository_operation_id="repo-op-1",
                    terminal_status=RepositoryOperationTerminalStatus.FAILED,
                    stable_failure_code="IMPORT_REJECTED",
                ),
                aborted_at=TS1,
            ),
            evidence=FakeAbortEvidencePort(),
            unit_of_work_factory=_uow_factory(db_path),
        )
    assert_occupancy_retained(
        db_path,
        workspace_id=seed.workspace.workspace_id,
        repository_id=seed.workspace.repository_id,
        submit_attempt_id=accepted.submit_attempt_id,
    )


def test_operator_abort_import_rejected_releases_occupancy(tmp_path: Path) -> None:
    db_path = _initialized_db_path(tmp_path, "recovery-abort.sqlite3")
    seed = seed_submit_ready_workspace(db_path)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    result = abort_submit_transaction(
        request=AbortSubmitTransactionRequest(
            submit_attempt_id=attempt.submit_attempt_id,
            proof=MatchingAbortProof(
                repository_id=seed.workspace.repository_id,
                repository_operation_id="repo-op-1",
                terminal_status=RepositoryOperationTerminalStatus.FAILED,
                stable_failure_code="IMPORT_REJECTED",
            ),
            aborted_at=TS1,
            worker_id="worker-test",
            lease_token="lease-test",
        ),
        evidence=FakeAbortEvidencePort(),
        unit_of_work_factory=_uow_factory(db_path),
    )
    assert result.replay is False
    assert result.attempt.state is SubmitAttemptState.ABORTED
    assert_occupancy_released(
        db_path,
        workspace_id=seed.workspace.workspace_id,
        repository_id=seed.workspace.repository_id,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(attempt.operation_id)
    assert operation.status is OperationStatus.FAILED


@pytest.mark.serial
def test_operator_abort_evidence_rejects_unknown_repository_operation(
    tmp_path: Path,
    requires_dolt: None,
) -> None:
    db_path = _initialized_db_path(tmp_path, "recovery-live-abort.sqlite3")
    repository_id = str(uuid4())
    seed = seed_submit_ready_workspace(db_path, repository_id=repository_id)
    attempt = _seed_effect_pending_attempt(db_path, seed)
    from gateway_repository_client.errors import RepositoryClientError

    with repository_service_session(tmp_path / "repository-live-abort") as service:
        seeded = service.repository_id_factory(idempotency_key="create-live-abort")
        evidence = HttpRepositoryAbortEvidencePort(client=service.write_client())
        with pytest.raises(RepositoryClientError, match="operation was not found"):
            evidence.validate_matching_stable_failure(
                attempt=attempt,
                proof=MatchingAbortProof(
                    repository_id=seeded.repository_id,
                    repository_operation_id="00000000-0000-0000-0000-000000000001",
                    terminal_status=RepositoryOperationTerminalStatus.FAILED,
                    stable_failure_code="IMPORT_REJECTED",
                ),
            )
    assert_occupancy_retained(
        db_path,
        workspace_id=seed.workspace.workspace_id,
        repository_id=seed.workspace.repository_id,
        submit_attempt_id=attempt.submit_attempt_id,
    )


def test_submit_recovery_maps_value_error_to_manual_recovery() -> None:
    from gateway_backend.application.submit_jobs import _map_handler_failure_to_recovery_outcome

    outcome = _map_handler_failure_to_recovery_outcome(ValueError("simulated crossing failure"))
    assert outcome is not None
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert outcome.diagnostic_code == DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED


def test_submit_recovery_maps_timeout_to_manual_recovery() -> None:
    from gateway_backend.application.submit_jobs import _map_handler_failure_to_recovery_outcome

    outcome = _map_handler_failure_to_recovery_outcome(
        RepositoryWriteTimeoutError("reconcile deadline exhausted")
    )
    assert outcome is not None
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert outcome.diagnostic_code == DIAGNOSTIC_RECONCILE_TIMEOUT


def test_submit_recovery_maps_abort_proof_not_satisfied_to_manual_recovery() -> None:
    from gateway_backend.application.submit_jobs import _map_handler_failure_to_recovery_outcome
    from gateway_backend.application.submission.errors import AbortProofNotSatisfied

    outcome = _map_handler_failure_to_recovery_outcome(
        AbortProofNotSatisfied("matching evidence missing")
    )
    assert outcome is not None
    assert outcome.disposition is RecoveryOutcomeDisposition.MANUAL_RECOVERY
    assert outcome.diagnostic_code == DIAGNOSTIC_MANUAL_RECOVERY_REQUIRED


def test_submit_recovery_leaves_unmapped_errors_unhandled() -> None:
    from gateway_backend.application.submit_jobs import _map_handler_failure_to_recovery_outcome

    assert _map_handler_failure_to_recovery_outcome(AttributeError("programming error")) is None


@pytest.mark.serial
def test_operator_abort_import_rejected_via_recovery_port(
    tmp_path: Path,
    requires_dolt: None,
) -> None:
    import hashlib

    from gateway_backend.application.submit_jobs import (
        bind_submit_control_transaction_factory,
        build_submit_operator_recovery_port,
        _read_write_factory,
    )
    from gateway_backend.application.submit_registry import submit_job_registry
    from gateway_backend.application.submission.job_payload import SUBMIT_STEP_AWAIT
    from gateway_backend.operations import TransitionDisposition
    from gateway_backend.operations.recovery import (
        OperatorRecoveryCommand,
        OperatorRecoveryRequest,
    )
    from tests.support.http_workspace_harness import (
        _submit_recovery_capability_lookup,
        promote_submit_recovery_target,
    )

    invalid_body = b"not-a-valid-package"
    invalid_sha = hashlib.sha256(invalid_body).hexdigest()
    with repository_service_session(tmp_path / "repository-live-abort-port") as service:
        seeded = service.repository_id_factory(idempotency_key="create-live-abort-port")
        write_client = service.write_client()
        artifact_ref = write_client.upload_artifact(
            repository_id=seeded.repository_id,
            idempotency_key="upload-live-abort-port",
            media_type="application/vnd.gateway.repository-import.v1+tar+zstd",
            raw_sha256=invalid_sha,
            body=invalid_body,
        )
        repository_operation_id = write_client.submit_versioned_import(
            repository_id=seeded.repository_id,
            idempotency_key="import-live-abort-port",
            artifact_ref=artifact_ref,
            expected_commit_id=seeded.initial_commit_id,
        )
        failed_operation = write_client.wait_operation(
            repository_id=seeded.repository_id,
            operation_id=repository_operation_id,
            deadline_seconds=60.0,
        )
        assert failed_operation.status.value == "FAILED"
        assert failed_operation.error is not None
        assert failed_operation.error.code == "IMPORT_REJECTED"

        db_path = _initialized_db_path(tmp_path, "recovery-operator-port.sqlite3")
        seed = seed_submit_ready_workspace(db_path, repository_id=seeded.repository_id)
        attempt = _seed_effect_pending_attempt(db_path, seed)
        with ControlDbUnitOfWork(db_path) as unit_of_work:
            current = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
            assert current is not None
            updated = replace(
                current,
                repository_operation_id=repository_operation_id,
                optimistic_version=current.optimistic_version + 1,
            )
            unit_of_work.submission.cas_update_attempt(
                updated,
                expected_version=current.optimistic_version,
            )
        await_step_id = submit_step_id(attempt.operation_id, SUBMIT_STEP_AWAIT)
        with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
            await_step = unit_of_work.operations.get_step(await_step_id)
        promote_submit_recovery_target(
            db_path,
            operation_id=attempt.operation_id,
            step_id=await_step_id,
            when=await_step.updated_at,
        )
        evidence = HttpRepositoryAbortEvidencePort(client=write_client)
        assert (
            evidence.resolve_stable_failure_code(
                repository_id=seeded.repository_id,
                repository_operation_id=repository_operation_id,
            )
            == "IMPORT_REJECTED"
        )

        def control_transaction_factory() -> ControlDbUnitOfWork:
            return ControlDbUnitOfWork(db_path)

        harness = build_submit_worker_harness(
            tmp_path / "worker-operator-port",
            repository_base_url=service.base_url,
        )
        port = build_submit_operator_recovery_port(
            write_uow_factory=control_transaction_factory,
            capability_lookup=_submit_recovery_capability_lookup(submit_job_registry()),
            submit_control_uow_factory=_read_write_factory(
                bind_submit_control_transaction_factory(control_transaction_factory)
            ),
            abort_evidence=evidence,
            submit_deps=harness.submit_deps,
        )
        with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
            operation = unit_of_work.operations.get_operation(attempt.operation_id)
            await_step = unit_of_work.operations.get_step(await_step_id)
        request = OperatorRecoveryRequest(
            command=OperatorRecoveryCommand.ABORT_CONFIRMED_FAILURE,
            operation_id=operation.operation_id,
            step_id=await_step.step_id,
            expected_operation_optimistic_version=operation.optimistic_version,
            expected_step_optimistic_version=await_step.optimistic_version,
            reason="operator confirmed repository import rejected",
        )
        assert port.execute_recovery(request) is TransitionDisposition.APPLY

    assert_occupancy_released(
        db_path,
        workspace_id=seed.workspace.workspace_id,
        repository_id=seed.workspace.repository_id,
    )
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        persisted_attempt = unit_of_work.submission.get_submit_attempt(attempt.submit_attempt_id)
        persisted_operation = unit_of_work.operations.get_operation(attempt.operation_id)
    assert persisted_attempt is not None
    assert persisted_attempt.state is SubmitAttemptState.ABORTED
    assert persisted_operation.status is OperationStatus.FAILED


def test_await_import_replay_after_finalize_commit_before_worker_ack(tmp_path: Path) -> None:
    harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(harness)
    manifest_digest = _prepare_manifest_digest(harness, operation_id)
    write_client = cast(HttpRepositoryWriteClient, harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(_operation_poll_handler(manifest_digest)),
    )
    await_deps = replace(harness.submit_deps, repository_write=await_write)
    handler = build_await_import_result_handler(await_deps)
    worker_id, lease_token = _await_lease_identity(await_work)
    control, session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=await_work.operation.operation_id,
        step_id=await_work.step.step_id,
    )
    assert (
        handler(await_work.operation, await_work.step, control, session)
        is ExecutorAcknowledgment.PUBLISHED
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        submit_attempt_id = next(
            ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        submission = unit_of_work.submission.get_submission_by_attempt(submit_attempt_id)
        row_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM submission_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        ).fetchone()[0]
    assert operation.status is OperationStatus.SUCCEEDED
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.FINALIZED
    assert submission is not None
    assert row_count == 1

    replay_control, replay_session = _lease_session(
        harness,
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation.operation_id,
        step_id=await_step.step_id,
    )
    assert (
        handler(operation, await_step, replay_control, replay_session)
        is ExecutorAcknowledgment.PUBLISHED
    )
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        replay_rows = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM submission_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        ).fetchone()[0]
    assert replay_rows == 1
