"""Submit external-effect recovery and operator abort integration tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
import time

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
from gateway_backend.application.submission.accept_transaction import (
    accept_submit_transaction,
)
from gateway_backend.application.submit_registry import submit_job_registry
from gateway_backend.application.submission.contracts import (
    MatchingAbortProof,
    RepositoryOperationTerminalStatus,
)
from gateway_backend.application.submission.contracts import PrepareImportBuildInput
from gateway_backend.application.submission.job_payload import SUBMIT_STEP_AWAIT, SUBMIT_STEP_SUBMIT
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.artifacts.store import ArtifactStorePort
from gateway_backend.domain.submission.models import SubmitAttempt, SubmitAttemptState
from gateway_backend.infrastructure.control_db import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.database import initialize_control_db
from gateway_backend.operations import (
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    TransitionDisposition,
    WritePrecondition,
)
from gateway_backend.operations.store import OperationUnitOfWork
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.worker import (
    ClaimedWork,
    ExecutionControl,
    ExecutorAcknowledgment,
    StartupDisposition,
    WriteUnitOfWorkFactory,
)
from gateway_backend.infrastructure.repository_write.http import HttpRepositoryWriteClient
from gateway_backend.bootstrap.operation_worker import build_worker_write_uow_factory
from gateway_backend.infrastructure.repository_write.abort_evidence import HttpRepositoryAbortEvidencePort
from tests.support.submit_job_harness import (
    RecordingTransport,
    SubmitWorkerHarness,
    assert_occupancy_released,
    assert_occupancy_retained,
    build_submit_worker_harness,
    build_dolt_compatible_prepare_publication,
    default_repository_handler,
    repository_service_session,
    shutdown_repository_service_client,
    start_repository_service_client,
    submit_step_id,
)
from tests.test_submit_job_effect import (
    _assert_submit_checkpoint_protection_released,
    _operation_poll_handler,
    _prepare_manifest_digest,
    _run_submit_to_await_claim,
)
from tests.support.workspace_fixtures import FixedScopeResolutionPort
from tests.support.baseline_fixtures import read_authoritative_baseline_head
from tests.test_submit_job_prepare import _materialize_ready_preview, _run_prepare_handler
from tests.test_submit_transactions import (
    FakeAbortEvidencePort,
    RecordingMainResolvePort,
    SubmitSeed,
    _SHA_INITIAL,
    _accept_command,
    _preflight,
    _seed_effect_pending_attempt,
    _submit_job_registry,
    _uow_factory,
    seed_submit_ready_workspace,
)

pytestmark = pytest.mark.integration

TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)
FAULT_AFTER_BUSINESS_FINALIZE_COMMIT_BEFORE_WORKER_ACK = (
    "after_business_finalize_commit_before_worker_ack"
)


def _authoritative_accept_scope(
    db_path: Path, seed: SubmitSeed
) -> tuple[object, FixedScopeResolutionPort]:
    baseline_head = read_authoritative_baseline_head(db_path, seed.workspace.repository_id)
    return baseline_head, FixedScopeResolutionPort(
        repository_id=seed.workspace.repository_id,
        baseline_head=baseline_head,
    )


class _FaultAfterCommitUnitOfWork:
    def __init__(self, inner: OperationUnitOfWork) -> None:
        self._inner = inner

    def __enter__(self) -> OperationUnitOfWork:
        return self._inner.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        result = self._inner.__exit__(exc_type, exc, tb)  # type: ignore[func-returns-value]
        if exc_type is None:
            raise RuntimeError(FAULT_AFTER_BUSINESS_FINALIZE_COMMIT_BEFORE_WORKER_ACK)
        return result

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


_ORIGINAL_PUBLISH_OPERATION = LeaseSession.publish_operation
_INJECT_FINALIZE_PUBLISH_FAULT = False


def _publish_operation_fault_after_commit(
    lease_session: LeaseSession,
    builder: Callable[[OperationRecord, StepRecord, datetime], tuple[StepRecord, OperationRecord]],
) -> tuple[TransitionDisposition, TransitionDisposition]:
    if not _INJECT_FINALIZE_PUBLISH_FAULT:
        return _ORIGINAL_PUBLISH_OPERATION(lease_session, builder)

    original_factory = lease_session._write_uow_factory

    def fault_factory() -> _FaultAfterCommitUnitOfWork:
        return _FaultAfterCommitUnitOfWork(original_factory())

    lease_session._write_uow_factory = cast(WriteUnitOfWorkFactory, fault_factory)
    try:
        return _ORIGINAL_PUBLISH_OPERATION(lease_session, builder)
    finally:
        lease_session._write_uow_factory = original_factory


def _accept_prepared_operation_for_repository(
    db_path: Path,
    store: InMemoryArtifactStore,
    *,
    repository_id: str,
    expected_commit_id: str,
) -> str:
    seed = seed_submit_ready_workspace(db_path, repository_id=repository_id)
    seed, _snapshot_ref, snapshot_digest = _materialize_ready_preview(seed, store)
    preflight = _preflight(seed)
    baseline_head, scope_resolution = _authoritative_accept_scope(db_path, seed)
    accepted = accept_submit_transaction(
        command=_accept_command(
            seed,
            idempotency_key="accept-key-live-restart",
            baseline_head=baseline_head,  # type: ignore[arg-type]
        ),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        main_resolve=RecordingMainResolvePort(
            commit_id=baseline_head.business_baseline_commit_id
        ),
        preflight=preflight,
        now=TS1,
    )
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        attempt = unit_of_work.submission.get_submit_attempt(accepted.submit_attempt_id)
        assert attempt is not None
        unit_of_work.submission.cas_update_attempt(
            replace(
                attempt,
                source_digest=_SHA_INITIAL,
                snapshot_digest=snapshot_digest,
            ),
            expected_version=attempt.optimistic_version,
        )
    return accepted.operation_id


def _run_submit_import_for_repository(
    harness: SubmitWorkerHarness,
    *,
    repository_id: str,
    expected_commit_id: str,
) -> str:
    operation_id = _accept_prepared_operation_for_repository(
        harness.db_path,
        harness.artifact_store,
        repository_id=repository_id,
        expected_commit_id=expected_commit_id,
    )
    _run_prepare_handler(harness.db_path, harness.artifact_store, operation_id)
    startup = harness.runtime._startup
    assert startup.startup() is StartupDisposition.READY
    submit_work = startup.claim_one()
    assert submit_work is not None
    assert submit_work.step.step_name == SUBMIT_STEP_SUBMIT
    assert submit_work.step.worker_id is not None
    assert submit_work.step.lease_token is not None
    submit_control = ExecutionControl()
    submit_session = LeaseSession(
        worker_id=submit_work.step.worker_id,
        lease_token=submit_work.step.lease_token,
        operation_id=submit_work.operation.operation_id,
        step_id=submit_work.step.step_id,
        write_uow_factory=build_worker_write_uow_factory(
            lambda: ControlDbUnitOfWork(harness.db_path)
        ),
        control=submit_control,
        observer=lambda _event: None,
    )
    assert (
        submit_work.executor(
            submit_work.operation,
            submit_work.step,
            submit_control,
            submit_session,
        )
        is ExecutorAcknowledgment.PUBLISHED
    )
    return operation_id


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
    baseline_head, scope_resolution = _authoritative_accept_scope(db_path, seed)
    accepted = accept_submit_transaction(
        command=_accept_command(
            seed,
            idempotency_key="accept-key-recovery-running",
            baseline_head=baseline_head,  # type: ignore[arg-type]
        ),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=submit_job_registry(),
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
    baseline_head, scope_resolution = _authoritative_accept_scope(db_path, seed)
    accepted = accept_submit_transaction(
        command=_accept_command(
            seed,
            idempotency_key="accept-key-prepared-abort",
            baseline_head=baseline_head,  # type: ignore[arg-type]
        ),
        scope_resolution=scope_resolution,
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=submit_job_registry(),
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


@pytest.mark.integration
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


@pytest.mark.integration
def test_operator_abort_import_rejected_via_recovery_port(
    tmp_path: Path,
    requires_dolt: None,
) -> None:
    import hashlib

    from gateway_backend.application.submit_jobs import (
        bind_submit_control_transaction_factory,
        build_submit_operator_recovery_port,
        read_write_factory,
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
            submit_control_uow_factory=read_write_factory(
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


def test_await_import_finalize_commits_lease_acknowledgment_via_worker_runtime(
    tmp_path: Path,
) -> None:
    seed_harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(seed_harness)
    manifest_digest = _prepare_manifest_digest(seed_harness, operation_id)
    write_client = cast(HttpRepositoryWriteClient, seed_harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(_operation_poll_handler(manifest_digest)),
    )
    await_deps = replace(seed_harness.submit_deps, repository_write=await_write)
    await_executor = build_await_import_result_handler(await_deps)
    with ControlDbUnitOfWork(seed_harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        assert await_work.step.worker_id is not None
        assert await_work.step.lease_token is not None
    work = ClaimedWork(operation, await_step, await_executor)
    assert seed_harness.runtime._lifecycle.mark_ready_to_claim() is False
    seed_harness.runtime._run_claim(
        work,
        lambda: False,
        lambda timeout: False,
        claim_anchor=time.monotonic(),
    )
    with ControlDbUnitOfWork(seed_harness.db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        submit_attempt_id = next(
            ref.value for ref in persisted_operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        submission = unit_of_work.submission.get_submission_by_attempt(submit_attempt_id)
        row_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM submission_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        ).fetchone()[0]
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_await_step.status is StepStatus.SUCCEEDED
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.FINALIZED
    assert submission is not None
    assert row_count == 1


def test_await_import_finalize_response_loss_after_terminal_commit_before_worker_ack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Contract §7 ``after_business_finalize_commit_before_worker_ack`` crash barrier owner.

    Design §11 "replay 返回既有 Submission" 指 T3 business finalize 已 durable；此窗口内 worker
    行为是 terminal durable fact eliminates reclaim，而非再次 claim/re-execute handler。
    """
    captured_sessions: list[LeaseSession] = []
    original_init = LeaseSession.__init__

    def tracking_init(self: LeaseSession, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        captured_sessions.append(self)

    monkeypatch.setattr(LeaseSession, "__init__", tracking_init)
    monkeypatch.setattr(
        LeaseSession,
        "publish_operation",
        _publish_operation_fault_after_commit,
    )

    seed_harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(),
    )
    await_work, operation_id = _run_submit_to_await_claim(seed_harness)
    manifest_digest = _prepare_manifest_digest(seed_harness, operation_id)
    write_client = cast(HttpRepositoryWriteClient, seed_harness.submit_deps.repository_write)
    await_write = replace(
        write_client,
        transport=RecordingTransport(_operation_poll_handler(manifest_digest)),
    )
    await_deps = replace(seed_harness.submit_deps, repository_write=await_write)
    await_executor = build_await_import_result_handler(await_deps)
    with ControlDbUnitOfWork(seed_harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        assert await_work.step.worker_id is not None
        assert await_work.step.lease_token is not None
    work = ClaimedWork(operation, await_step, await_executor)
    assert seed_harness.runtime._lifecycle.mark_ready_to_claim() is False
    monkeypatch.setattr(
        "tests.test_submit_recovery._INJECT_FINALIZE_PUBLISH_FAULT",
        True,
    )
    try:
        with pytest.raises(RuntimeError, match=FAULT_AFTER_BUSINESS_FINALIZE_COMMIT_BEFORE_WORKER_ACK):
            seed_harness.runtime._run_claim(
                work,
                lambda: False,
                lambda timeout: False,
                claim_anchor=time.monotonic(),
            )
    finally:
        monkeypatch.setattr(
            "tests.test_submit_recovery._INJECT_FINALIZE_PUBLISH_FAULT",
            False,
        )
    assert captured_sessions
    assert captured_sessions[-1].completion_acknowledgment() is None

    with ControlDbUnitOfWork(seed_harness.db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        submit_attempt_id = next(
            ref.value for ref in persisted_operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        submission = unit_of_work.submission.get_submission_by_attempt(submit_attempt_id)
        row_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM submission_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        ).fetchone()[0]
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_await_step.status is StepStatus.SUCCEEDED
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.FINALIZED
    assert submission is not None
    assert row_count == 1

    startup = seed_harness.runtime._startup
    assert startup.startup() is StartupDisposition.READY
    assert startup.claim_one() is None


@pytest.mark.integration
@pytest.mark.serial
def test_await_import_result_consumes_matching_terminal_after_repository_restart(
    tmp_path: Path,
    requires_dolt: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository restart consumer journey owner (execution-plan §490).

    Restart semantics: ``shutdown_repository_service_client`` stops the fixture via
    ``os.killpg(pgid, SIGTERM)``. The starter runs uvicorn on a non-main thread, so
    ``capture_signals`` does not apply and the process exits immediately (hard kill),
    not production graceful shutdown (main-thread uvicorn SIGTERM → ``should_exit`` →
    ``runtime.shutdown()``). This owner proves durable await markers survive hard kill
    and can be consumed by a new repository-service process; it does not cover graceful
    restart.
    """
    from gateway_backend.application.submission.contracts import PrepareImportPublicationResult
    from gateway_backend.infrastructure.repository_write.import_publication import (
        SubmitImportPublicationAdapter,
    )

    def _dolt_compatible_prepare_publication(
        self: SubmitImportPublicationAdapter,
        *,
        build_input: PrepareImportBuildInput,
        store: ArtifactStorePort,
    ) -> PrepareImportPublicationResult:
        del self
        return build_dolt_compatible_prepare_publication(
            build_input=build_input,
            store=store,
        )

    monkeypatch.setattr(
        SubmitImportPublicationAdapter,
        "build_and_publish",
        _dolt_compatible_prepare_publication,
    )

    data_root = tmp_path / "repo-restart-journey"
    service1 = start_repository_service_client(data_root)
    repository_operation_id = ""
    workspace_id = ""
    operation_id = ""
    seeded_repository_id = ""
    harness: SubmitWorkerHarness | None = None
    try:
        seeded = service1.repository_id_factory(idempotency_key="create-repo-restart-journey")
        seeded_repository_id = seeded.repository_id
        harness = build_submit_worker_harness(
            tmp_path / "worker-repo-restart",
            repository_base_url=service1.base_url,
        )
        operation_id = _run_submit_import_for_repository(
            harness,
            repository_id=seeded.repository_id,
            expected_commit_id=seeded.initial_commit_id,
        )
        write_client = service1.write_client()
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
            operation = unit_of_work.operations.get_operation(operation_id)
            submit_step = unit_of_work.operations.get_step(
                submit_step_id(operation_id, SUBMIT_STEP_SUBMIT)
            )
            assert submit_step.checkpoint_ref is not None
            submit_attempt_id = next(
                ref.value for ref in operation.business_refs if ref.kind == "submit_attempt"
            )
            attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
            assert attempt is not None
            assert attempt.repository_operation_id is not None
            repository_operation_id = attempt.repository_operation_id
            workspace_id = attempt.workspace_id
        terminal_operation = write_client.wait_operation(
            repository_id=seeded.repository_id,
            operation_id=repository_operation_id,
            deadline_seconds=120.0,
        )
        assert terminal_operation.status.value == "SUCCEEDED"
    finally:
        service1_process = service1._process
        shutdown_repository_service_client(service1, preserve_data=True)
        if service1_process is not None:
            assert service1_process.poll() is not None

    assert harness is not None
    service2 = start_repository_service_client(data_root)
    try:
        restarted_client = service2.write_client()
        restarted_terminal = restarted_client.get_operation(
            repository_id=seeded_repository_id,
            operation_id=repository_operation_id,
        )
        assert restarted_terminal.status.value == "SUCCEEDED"

        await_deps = replace(
            harness.submit_deps,
            repository_write=restarted_client,
        )
        startup = harness.runtime._startup
        assert startup.startup() is StartupDisposition.READY
        await_work = startup.claim_one()
        assert await_work is not None
        assert await_work.step.step_name == SUBMIT_STEP_AWAIT
        assert await_work.step.worker_id is not None
        assert await_work.step.lease_token is not None
        await_work = replace(
            await_work,
            executor=build_await_import_result_handler(await_deps),
        )
        assert harness.runtime._lifecycle.mark_ready_to_claim() is False
        harness.runtime._run_claim(
            await_work,
            lambda: False,
            lambda timeout: False,
            claim_anchor=time.monotonic(),
        )
    finally:
        shutdown_repository_service_client(service2, preserve_data=False)

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        submit_attempt_id = next(
            ref.value for ref in persisted_operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        submission = unit_of_work.submission.get_submission_by_attempt(submit_attempt_id)
        row_count = unit_of_work.connection.execute(
            "SELECT COUNT(*) FROM submission_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        ).fetchone()[0]
    assert attempt is not None
    assert persisted_operation.status is OperationStatus.SUCCEEDED
    assert persisted_await_step.status is StepStatus.SUCCEEDED
    assert attempt.state is SubmitAttemptState.FINALIZED
    assert submission is not None
    assert row_count == 1
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy(workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(
            seeded_repository_id
        )
    assert repository_occupancy is None
    assert workspace_occupancy is not None
    assert workspace_occupancy.active_submission_id == submission.submission_id


def test_await_import_stable_abort_completes_via_worker_runtime(
    tmp_path: Path,
) -> None:
    def _import_rejected_handler(request: httpx.Request) -> httpx.Response:
        if "/operations/" in request.url.path and request.method == "GET":
            operation_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json={
                    "operation": {
                        "operation_id": operation_id,
                        "status": "FAILED",
                        "error": {
                            "code": "IMPORT_REJECTED",
                            "message": "import rejected",
                            "request_id": None,
                        },
                        "result": None,
                    }
                },
                headers={"X-Request-ID": "req-operation"},
            )
        return default_repository_handler(request)

    seed_harness = build_submit_worker_harness(
        tmp_path,
        repository_base_url="http://repository.test",
        transport=RecordingTransport(_import_rejected_handler),
    )
    await_work, operation_id = _run_submit_to_await_claim(seed_harness)
    await_executor = build_await_import_result_handler(seed_harness.submit_deps)
    with ControlDbUnitOfWork(seed_harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        assert await_work.step.worker_id is not None
        assert await_work.step.lease_token is not None
    work = ClaimedWork(operation, await_step, await_executor)
    assert seed_harness.runtime._lifecycle.mark_ready_to_claim() is False
    seed_harness.runtime._run_claim(
        work,
        lambda: False,
        lambda timeout: False,
        claim_anchor=time.monotonic(),
    )
    with ControlDbUnitOfWork(seed_harness.db_path, read_only=True) as unit_of_work:
        persisted_operation = unit_of_work.operations.get_operation(operation_id)
        persisted_await_step = unit_of_work.operations.get_step(
            submit_step_id(operation_id, SUBMIT_STEP_AWAIT)
        )
        submit_attempt_id = next(
            ref.value for ref in persisted_operation.business_refs if ref.kind == "submit_attempt"
        )
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert persisted_operation.status is OperationStatus.FAILED
        assert persisted_await_step.status is StepStatus.FAILED
        assert attempt is not None
        assert attempt.state is SubmitAttemptState.ABORTED
        _assert_submit_checkpoint_protection_released(
            unit_of_work,
            operation_id=operation_id,
            submit_attempt_id=submit_attempt_id,
        )
