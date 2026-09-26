"""Prepare-import handler checkpoint publication and reuse tests."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from gateway_repository_contracts import VersionedOperation

from gateway_backend.application.submission.job_payload import SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT
from gateway_backend.application.checkpoints import (
    load_checkpoint_envelope,
    put_checkpoint_envelope,
)
from gateway_backend.application.payloads import CheckpointDecodeError
from gateway_backend.application.submit_jobs import (
    SubmitControlTransactionFactory,
    SubmitRuntimeDependencies,
    _capability_storage_projection_version,
    bind_submit_control_transaction_factory,
    build_prepare_import_handler,
)
from gateway_backend.application.submission.accept_transaction import (
    AcceptSubmitPreflight,
    accept_submit_transaction,
)
from gateway_backend.operations.persistence import LEASE_DURATION
from gateway_backend.operations.state import WritePrecondition
from gateway_backend.operations.worker import StartupDisposition
from tests.support.submit_job_harness import (
    RecordingTransport,
    SubmitWorkerHarness,
    assert_occupancy_released,
    assert_occupancy_retained,
    build_submit_worker_harness,
)
from gateway_backend.capabilities.storage_projection import STORAGE_PROJECTION_VERSION
from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationPolicy,
    SnapshotMaterializationStatus,
)
from gateway_backend.application.submit_jobs import _submit_attempt_id_from_operation
from gateway_backend.domain.submission.models import RepositoryArtifactRef, SubmitAttemptState
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork, initialize_control_db
from gateway_backend.operations import StepStatus
from gateway_backend.operations.contracts import OperationStatus
from gateway_backend.operations.state import TransitionDisposition
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.worker import (
    ExecutionControl,
    ExecutorAcknowledgment,
    WriteUnitOfWorkFactory,
)
from gateway_backend.application.submission.errors import SubmitImportPublicationError
from gateway_backend.repository_import_artifact import SubmitImportPublicationAdapter
from tests.support.snapshot_materialization import materialize_sql
from tests.support.workspace_fixtures import FixedScopeResolutionPort
from tests.support.baseline_fixtures import read_authoritative_baseline_head
from tests.test_submit_transactions import (
    PREVIEW_READY_CLOSURE_DIGEST,
    SNAPSHOT_TABLE_SET_DIGEST,
    FakeBaselineCanonicalDigestPort,
    RecordingMainResolvePort,
    SubmitSeed,
    _SHA_INITIAL,
    _accept_command,
    _submit_job_registry,
    _uow_factory,
    seed_submit_ready_workspace,
)

pytestmark = pytest.mark.unit

TS1 = datetime(2024, 6, 1, 12, 30, 0, tzinfo=UTC)
_WORKER_ID = "worker-prepare-1"
_LEASE_TOKEN = "lease-prepare-1"
_NET_CFG_SQL = (
    "CREATE TABLE `net_cfg` (`board` VARCHAR NOT NULL, `link_no` INT NOT NULL, PRIMARY KEY (`board`, `link_no`));"
    "INSERT INTO `net_cfg` VALUES ('eth0', 1);"
)


@dataclass(frozen=True, slots=True)
class _UnusedRepositoryWrite:
    def upload_artifact(
        self,
        *,
        repository_id: str,
        idempotency_key: str,
        media_type: str,
        raw_sha256: str,
        body: bytes,
    ) -> RepositoryArtifactRef:
        raise AssertionError("prepare handler must not upload artifacts")

    def submit_versioned_import(
        self,
        *,
        repository_id: str,
        idempotency_key: str,
        artifact_ref: RepositoryArtifactRef,
        expected_commit_id: str,
    ) -> str:
        raise AssertionError("prepare handler must not submit imports")

    def get_operation(self, *, repository_id: str, operation_id: str) -> VersionedOperation:
        raise AssertionError("prepare handler must not poll repository operations")

    def wait_operation(
        self,
        *,
        repository_id: str,
        operation_id: str,
        deadline_seconds: float | None = None,
    ) -> VersionedOperation:
        raise AssertionError("prepare handler must not wait on repository operations")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "control.db"
    initialize_control_db(path)
    return path


def _materialize_snapshot(store: InMemoryArtifactStore) -> tuple[ArtifactRef, str]:
    result = materialize_sql(
        _NET_CFG_SQL,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.table_set is not None
    table = result.table_set.tables[0]
    assert table.artifact is not None
    return table.artifact.manifest_ref, table.artifact.manifest.snapshot_digest.value


def _accept_prepared_operation(
    db_path: Path,
    store: InMemoryArtifactStore,
    *,
    repository_id: str = "repo-1",
) -> str:
    seed = seed_submit_ready_workspace(db_path, repository_id=repository_id)
    snapshot_ref, snapshot_digest = _materialize_snapshot(store)
    protected_refs = tuple(
        ref for ref in seed.protected_refs if ref.artifact_id != "snap-1"
    ) + (snapshot_ref,)
    baseline_head = read_authoritative_baseline_head(db_path, repository_id)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.clear_artifact_protection(
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
        )
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
            intent="current-preview",
        )
    preflight = AcceptSubmitPreflight(
        snapshot_table_artifact_refs=(snapshot_ref.artifact_id,),
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        preview_operation_id=seed.preview_operation_id,
        protected_artifact_refs=protected_refs,
        snapshot_table_set_digest=SNAPSHOT_TABLE_SET_DIGEST,
    )
    accepted = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1", baseline_head=baseline_head),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=baseline_head,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
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


def _control_db_factory(
    db_path: Path,
    control_now: Callable[[], datetime] | None = None,
) -> Callable[[], ControlDbUnitOfWork]:
    def factory() -> ControlDbUnitOfWork:
        if control_now is not None:
            return ControlDbUnitOfWork(db_path, now=control_now)
        return ControlDbUnitOfWork(db_path)

    return factory


def _bound_control_transaction_factory(
    db_path: Path,
    control_now: Callable[[], datetime] | None = None,
) -> SubmitControlTransactionFactory:
    return bind_submit_control_transaction_factory(_control_db_factory(db_path, control_now))


def _submit_runtime_dependencies(
    db_path: Path,
    store: InMemoryArtifactStore,
    *,
    control_now: Callable[[], datetime] | None = None,
) -> SubmitRuntimeDependencies:
    return SubmitRuntimeDependencies(
        artifact_store=store,
        publication=SubmitImportPublicationAdapter(),
        repository_write=_UnusedRepositoryWrite(),
        control_transaction_factory=_bound_control_transaction_factory(db_path, control_now),
        submission_id_factory=lambda: "sub-test-1",
    )


def _claimed_prepare_session(
    db_path: Path,
    operation_id: str,
    *,
    control_now: Callable[[], datetime] | None = None,
) -> tuple[LeaseSession, ExecutionControl]:
    uow_factory = _control_db_factory(db_path, control_now)
    with uow_factory() as unit_of_work:
        transaction_now = unit_of_work.operations.transaction_now
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=transaction_now,
        ).claim_one(_WORKER_ID, _LEASE_TOKEN)
    assert claimed is not None
    claimed_operation, claimed_step = claimed
    assert claimed_operation.operation_id == operation_id
    assert claimed_step.step_name == SUBMIT_STEP_PREPARE

    control = ExecutionControl()
    session = LeaseSession(
        worker_id=_WORKER_ID,
        lease_token=_LEASE_TOKEN,
        operation_id=claimed_operation.operation_id,
        step_id=claimed_step.step_id,
        write_uow_factory=cast(
            WriteUnitOfWorkFactory,
            _bound_control_transaction_factory(db_path, control_now),
        ),
        control=control,
        observer=lambda _event: None,
    )
    return session, control


def _run_prepare_handler(
    db_path: Path,
    store: InMemoryArtifactStore,
    operation_id: str,
    *,
    control_now: Callable[[], datetime] | None = None,
) -> ExecutorAcknowledgment:
    handler = build_prepare_import_handler(
        _submit_runtime_dependencies(db_path, store, control_now=control_now)
    )
    session, control = _claimed_prepare_session(db_path, operation_id, control_now=control_now)
    uow_factory = _control_db_factory(db_path, control_now)
    with uow_factory() as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
    return handler(operation, step, control, session)


def test_capability_storage_projection_version_maps_contract_v1() -> None:
    assert _capability_storage_projection_version("v1") == STORAGE_PROJECTION_VERSION


def test_prepare_handler_publishes_checkpoint_and_successor(
    db_path: Path,
) -> None:
    store = InMemoryArtifactStore()
    operation_id = _accept_prepared_operation(db_path, store)
    artifact_count_before = len(store._artifacts)

    acknowledgment = _run_prepare_handler(db_path, store, operation_id)

    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
    assert len(store._artifacts) > artifact_count_before
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        steps, _cursor = unit_of_work.operations.list_steps(operation_id)
        prepare_step = next(step for step in steps if step.step_name == SUBMIT_STEP_PREPARE)
        submit_step = next(step for step in steps if step.step_name == SUBMIT_STEP_SUBMIT)
    assert prepare_step.status is StepStatus.SUCCEEDED
    assert prepare_step.checkpoint_ref is not None
    assert submit_step.status is StepStatus.PENDING
    assert operation.status is OperationStatus.RUNNING


def test_prepare_handler_publication_failure_marks_operation_failed(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryArtifactStore()
    operation_id = _accept_prepared_operation(db_path, store)

    def fail_publish(**_kwargs: object) -> object:
        raise SubmitImportPublicationError(
            "storage projection failed: UNSUPPORTED_TABLE: "
            "column scalar_type is not supported (table=t5)"
        )

    monkeypatch.setattr(
        "gateway_backend.application.submit_jobs.publish_prepare_import_package",
        fail_publish,
    )

    acknowledgment = _run_prepare_handler(db_path, store, operation_id)

    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        prepare_step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
    assert operation.status is OperationStatus.FAILED
    assert prepare_step.status is StepStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == "UNSUPPORTED_TABLE"
    assert "column scalar_type is not supported" in operation.diagnostic.message
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        submit_attempt_id = _submit_attempt_id_from_operation(operation)
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
        assert attempt is not None
        workspace_occupancy = unit_of_work.submission.get_workspace_occupancy(attempt.workspace_id)
        repository_occupancy = unit_of_work.submission.get_repository_occupancy(
            attempt.repository_id
        )
    assert attempt.state is SubmitAttemptState.ABORTED
    assert attempt.abort_code == "UNSUPPORTED_TABLE"
    assert workspace_occupancy is None
    assert repository_occupancy is None


def test_prepare_handler_reuses_checkpoint_on_replay(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryArtifactStore()
    operation_id = _accept_prepared_operation(db_path, store)

    def skip_successor(
        _self: LeaseSession,
        _builder: object,
    ) -> tuple[TransitionDisposition, TransitionDisposition]:
        return (TransitionDisposition.IDEMPOTENT, TransitionDisposition.IDEMPOTENT)

    monkeypatch.setattr(LeaseSession, "publish_successor", skip_successor)

    handler = build_prepare_import_handler(_submit_runtime_dependencies(db_path, store))
    session, control = _claimed_prepare_session(db_path, operation_id)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
    first_ack = handler(operation, step, control, session)
    assert first_ack is ExecutorAcknowledgment.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        checkpoint_step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
    assert checkpoint_step.checkpoint_ref is not None
    assert checkpoint_step.status is StepStatus.RUNNING
    artifact_count_after_first = len(store._artifacts)

    def fail_publish(*args: object, **kwargs: object) -> object:
        raise AssertionError("publish_prepare_import_package must not run during checkpoint reuse")

    monkeypatch.setattr(
        "gateway_backend.application.submit_jobs.publish_prepare_import_package",
        fail_publish,
    )

    session.refresh_control()
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
    second_ack = handler(operation, step, control, session)

    assert second_ack is ExecutorAcknowledgment.PUBLISHED
    assert len(store._artifacts) == artifact_count_after_first


_ATTEMPT_ID_JOB_STATE_KEY = "attempt_id"


def _skip_prepare_successor(
    _self: object,
    _builder: object,
) -> tuple[TransitionDisposition, TransitionDisposition]:
    return (TransitionDisposition.IDEMPOTENT, TransitionDisposition.IDEMPOTENT)


def _accept_prepared_with_seed(
    db_path: Path,
    store: InMemoryArtifactStore,
    *,
    repository_id: str = "repo-1",
    accept_now: datetime | None = None,
) -> tuple[str, SubmitSeed]:
    seed = seed_submit_ready_workspace(db_path, repository_id=repository_id)
    snapshot_ref, snapshot_digest = _materialize_snapshot(store)
    protected_refs = tuple(ref for ref in seed.protected_refs if ref.artifact_id != "snap-1") + (
        snapshot_ref,
    )
    baseline_head = read_authoritative_baseline_head(db_path, repository_id)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.clear_artifact_protection(
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
        )
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="current-preview",
            owner_id=seed.workspace.workspace_id,
            intent="current-preview",
        )
    preflight = AcceptSubmitPreflight(
        snapshot_table_artifact_refs=(snapshot_ref.artifact_id,),
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        preview_operation_id=seed.preview_operation_id,
        protected_artifact_refs=protected_refs,
        snapshot_table_set_digest=SNAPSHOT_TABLE_SET_DIGEST,
    )
    accepted = accept_submit_transaction(
        command=_accept_command(seed, idempotency_key="accept-key-1", baseline_head=baseline_head),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=seed.workspace.repository_id,
            baseline_head=baseline_head,
        ),
        unit_of_work_factory=_uow_factory(seed.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=preflight,
        now=accept_now or TS1,
    )
    uow_factory = _control_db_factory(
        db_path,
        (lambda: accept_now) if accept_now is not None else None,
    )
    with uow_factory() as unit_of_work:
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
    return accepted.operation_id, seed


def _tamper_checkpoint_attempt_id_in_store(
    db_path: Path,
    store: InMemoryArtifactStore,
    operation_id: str,
    *,
    control_now: Callable[[], datetime] | None = None,
) -> None:
    prepare_step_id = f"{operation_id}-step-1"
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        step = unit_of_work.operations.get_step(prepare_step_id)
        assert step.checkpoint_ref is not None
        checkpoint_ref = step.checkpoint_ref
    envelope = load_checkpoint_envelope(store, checkpoint_ref)
    tampered_state = dict(envelope.job_state)
    tampered_state[_ATTEMPT_ID_JOB_STATE_KEY] = "tampered-attempt-not-in-db"
    tampered_envelope = replace(envelope, job_state=tampered_state)
    tampered_ref = put_checkpoint_envelope(store, tampered_envelope)
    with _control_db_factory(db_path, control_now)() as unit_of_work:
        persisted = unit_of_work.operations.get_step(prepare_step_id)
        updated = replace(
            persisted,
            checkpoint_ref=tampered_ref,
            optimistic_version=persisted.optimistic_version + 1,
            updated_at=unit_of_work.operations.transaction_now,
        )
        unit_of_work.operations.compare_and_set_step(
            updated,
            WritePrecondition(
                expected_optimistic_version=persisted.optimistic_version,
                worker_id=persisted.worker_id,
                lease_token=persisted.lease_token,
            ),
        )


def _tamper_checkpoint_schema_version_in_store(
    db_path: Path,
    store: InMemoryArtifactStore,
    operation_id: str,
) -> None:
    prepare_step_id = f"{operation_id}-step-1"
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        step = unit_of_work.operations.get_step(prepare_step_id)
        assert step.checkpoint_ref is not None
        checkpoint_ref = step.checkpoint_ref
    envelope = load_checkpoint_envelope(store, checkpoint_ref)
    tampered_state = dict(envelope.job_state)
    tampered_state["schema_version"] = "backend-vnext/submit/wrong-schema/v1"
    tampered_envelope = replace(envelope, job_state=tampered_state)
    tampered_ref = put_checkpoint_envelope(store, tampered_envelope)
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        persisted = unit_of_work.operations.get_step(prepare_step_id)
        updated = replace(
            persisted,
            checkpoint_ref=tampered_ref,
            optimistic_version=persisted.optimistic_version + 1,
            updated_at=unit_of_work.operations.transaction_now,
        )
        unit_of_work.operations.compare_and_set_step(
            updated,
            WritePrecondition(
                expected_optimistic_version=persisted.optimistic_version,
                worker_id=persisted.worker_id,
                lease_token=persisted.lease_token,
            ),
        )


def _worker_startup_ready_after_lease_expiry(
    harness: SubmitWorkerHarness,
    clock: dict[str, datetime],
    operation_id: str,
) -> None:
    clock["value"] = clock["value"] + LEASE_DURATION + timedelta(seconds=1)
    startup = harness.runtime._startup
    disposition = startup.startup()
    for _ in range(4):
        if disposition is StartupDisposition.READY:
            return
        if disposition is StartupDisposition.RETRYABLE_BLOCK:
            with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
                retry_not_before = unit_of_work.operations.get_step(
                    f"{operation_id}-step-1"
                ).retry_not_before
            assert retry_not_before is not None
            clock["value"] = retry_not_before + timedelta(seconds=1)
            disposition = startup.startup()
            continue
        raise AssertionError(f"unexpected startup disposition: {disposition}")
    raise AssertionError("startup did not reach READY")


def test_prepare_checkpoint_payload_binding_mismatch_aborts_prepared_attempt(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryArtifactStore()
    monkeypatch.setattr(
        "gateway_backend.operations.lease_session.LeaseSession.publish_successor",
        _skip_prepare_successor,
    )
    operation_id = _accept_prepared_operation(db_path, store)
    handler = build_prepare_import_handler(_submit_runtime_dependencies(db_path, store))
    session, control = _claimed_prepare_session(db_path, operation_id)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
    assert handler(operation, step, control, session) is ExecutorAcknowledgment.PUBLISHED
    _tamper_checkpoint_attempt_id_in_store(db_path, store, operation_id)
    session.refresh_control()
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(f"{operation_id}-step-1")

    acknowledgment = handler(operation, step, control, session)
    assert acknowledgment is ExecutorAcknowledgment.PUBLISHED

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        prepare_step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
        submit_attempt_id = _submit_attempt_id_from_operation(operation)
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
    assert operation.status is OperationStatus.FAILED
    assert prepare_step.status is StepStatus.FAILED
    assert operation.diagnostic is not None
    assert operation.diagnostic.code == "CHECKPOINT_ATTEMPT_BINDING_MISMATCH"
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.ABORTED
    assert attempt.abort_code == "CHECKPOINT_ATTEMPT_BINDING_MISMATCH"
    assert_occupancy_released(
        db_path,
        workspace_id=attempt.workspace_id,
        repository_id=attempt.repository_id,
    )


def test_prepare_checkpoint_schema_mismatch_retains_occupancy(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryArtifactStore()
    monkeypatch.setattr(
        "gateway_backend.operations.lease_session.LeaseSession.publish_successor",
        _skip_prepare_successor,
    )
    operation_id = _accept_prepared_operation(db_path, store)
    handler = build_prepare_import_handler(_submit_runtime_dependencies(db_path, store))
    session, control = _claimed_prepare_session(db_path, operation_id)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(f"{operation_id}-step-1")
    assert handler(operation, step, control, session) is ExecutorAcknowledgment.PUBLISHED
    _tamper_checkpoint_schema_version_in_store(db_path, store, operation_id)
    session.refresh_control()
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        step = unit_of_work.operations.get_step(f"{operation_id}-step-1")

    with pytest.raises(CheckpointDecodeError):
        handler(operation, step, control, session)

    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = _submit_attempt_id_from_operation(operation)
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.PREPARED
    assert_occupancy_retained(
        db_path,
        workspace_id=attempt.workspace_id,
        repository_id=attempt.repository_id,
        submit_attempt_id=attempt.submit_attempt_id,
    )


@pytest.mark.serial
def test_prepare_checkpoint_payload_binding_mismatch_worker_aborts_and_allows_reaccept(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock: dict[str, datetime] = {"value": datetime(2026, 8, 24, 12, 0, tzinfo=UTC)}
    transport = RecordingTransport()
    harness = build_submit_worker_harness(
        tmp_path / "prepare-binding-worker",
        repository_base_url="http://repository.test",
        transport=transport,
        control_clock=clock,
    )
    monkeypatch.setattr(
        "gateway_backend.operations.lease_session.LeaseSession.publish_successor",
        _skip_prepare_successor,
    )
    def control_now() -> datetime:
        return clock["value"]

    operation_id, seed = _accept_prepared_with_seed(
        harness.db_path,
        harness.artifact_store,
        accept_now=clock["value"],
    )
    requests_before = len(transport.requests)
    _run_prepare_handler(
        harness.db_path,
        harness.artifact_store,
        operation_id,
        control_now=control_now,
    )
    assert len(transport.requests) == requests_before

    _tamper_checkpoint_attempt_id_in_store(
        harness.db_path,
        harness.artifact_store,
        operation_id,
        control_now=control_now,
    )
    _worker_startup_ready_after_lease_expiry(harness, clock, operation_id)

    work = harness.runtime._startup.claim_one()
    assert work is not None
    assert work.step.step_name == SUBMIT_STEP_PREPARE
    assert harness.runtime._lifecycle.mark_ready_to_claim() is False
    harness.runtime._run_claim(
        work,
        lambda: False,
        lambda _timeout: False,
        claim_anchor=time.monotonic(),
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        operation = unit_of_work.operations.get_operation(operation_id)
        submit_attempt_id = _submit_attempt_id_from_operation(operation)
        attempt = unit_of_work.submission.get_submit_attempt(submit_attempt_id)
    assert operation.status is OperationStatus.FAILED
    assert attempt is not None
    assert attempt.state is SubmitAttemptState.ABORTED
    assert_occupancy_released(
        harness.db_path,
        workspace_id=attempt.workspace_id,
        repository_id=attempt.repository_id,
    )

    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        fresh_workspace = unit_of_work.workspace.get_workspace(attempt.workspace_id)
    assert fresh_workspace is not None
    seed_for_reaccept = replace(seed, workspace=fresh_workspace)
    snapshot_ref, _ = _materialize_snapshot(harness.artifact_store)
    protected_refs = tuple(ref for ref in seed.protected_refs if ref.artifact_id != "snap-1") + (
        snapshot_ref,
    )
    baseline_head = read_authoritative_baseline_head(harness.db_path, attempt.repository_id)
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        unit_of_work.clear_artifact_protection(
            owner_kind="current-preview",
            owner_id=attempt.workspace_id,
        )
        unit_of_work.set_artifact_protection(
            protected_refs,
            owner_kind="current-preview",
            owner_id=attempt.workspace_id,
            intent="current-preview",
        )
    preflight = AcceptSubmitPreflight(
        snapshot_table_artifact_refs=(snapshot_ref.artifact_id,),
        preview_ready_closure_digest=PREVIEW_READY_CLOSURE_DIGEST,
        preview_operation_id=seed_for_reaccept.preview_operation_id,
        protected_artifact_refs=protected_refs,
        snapshot_table_set_digest=SNAPSHOT_TABLE_SET_DIGEST,
    )
    accepted = accept_submit_transaction(
        command=_accept_command(
            seed_for_reaccept,
            idempotency_key="accept-key-2",
            baseline_head=baseline_head,
        ),
        scope_resolution=FixedScopeResolutionPort(
            repository_id=attempt.repository_id,
            baseline_head=baseline_head,
        ),
        unit_of_work_factory=_uow_factory(harness.db_path),
        job_registry=_submit_job_registry(),
        baseline_digest=FakeBaselineCanonicalDigestPort(),
        main_resolve=RecordingMainResolvePort(),
        preflight=preflight,
        now=clock["value"] + timedelta(minutes=1),
    )
    assert accepted.operation_id != operation_id
    assert accepted.replay is False
