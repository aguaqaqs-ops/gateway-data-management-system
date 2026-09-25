"""Prepare-import handler checkpoint publication and reuse tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from gateway_repository_contracts import VersionedOperation

from gateway_backend.application.submission.accept_transaction import (
    AcceptSubmitPreflight,
    accept_submit_transaction,
)
from gateway_backend.application.submission.job_payload import SUBMIT_STEP_PREPARE, SUBMIT_STEP_SUBMIT
from gateway_backend.application.submit_jobs import (
    SubmitControlTransactionFactory,
    SubmitRuntimeDependencies,
    _capability_storage_projection_version,
    bind_submit_control_transaction_factory,
    build_prepare_import_handler,
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


def _bound_control_transaction_factory(db_path: Path) -> SubmitControlTransactionFactory:
    return bind_submit_control_transaction_factory(lambda: ControlDbUnitOfWork(db_path))


def _submit_runtime_dependencies(
    db_path: Path,
    store: InMemoryArtifactStore,
) -> SubmitRuntimeDependencies:
    return SubmitRuntimeDependencies(
        artifact_store=store,
        publication=SubmitImportPublicationAdapter(),
        repository_write=_UnusedRepositoryWrite(),
        control_transaction_factory=_bound_control_transaction_factory(db_path),
        submission_id_factory=lambda: "sub-test-1",
    )


def _claimed_prepare_session(
    db_path: Path,
    operation_id: str,
) -> tuple[LeaseSession, ExecutionControl]:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
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
            _bound_control_transaction_factory(db_path),
        ),
        control=control,
        observer=lambda _event: None,
    )
    return session, control


def _run_prepare_handler(
    db_path: Path,
    store: InMemoryArtifactStore,
    operation_id: str,
) -> ExecutorAcknowledgment:
    handler = build_prepare_import_handler(_submit_runtime_dependencies(db_path, store))
    session, control = _claimed_prepare_session(db_path, operation_id)
    with ControlDbUnitOfWork(db_path, read_only=True) as unit_of_work:
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
