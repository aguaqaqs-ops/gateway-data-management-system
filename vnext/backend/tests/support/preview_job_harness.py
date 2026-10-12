"""Preview job composition and fixture helpers for S4 behavior tests."""

from __future__ import annotations

from collections.abc import Callable
import json
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from gateway_backend.application.job_definitions import build_job_worker_composition
from gateway_backend.application.preview_jobs import (
    PREVIEW_JOB_CONTRACT_VERSION,
    PREVIEW_JOB_KIND,
    PREVIEW_STEP_ASSEMBLE,
    PREVIEW_STEP_MATERIALIZE,
    PREVIEW_STEP_PUBLISH,
    PreviewControlTransaction,
    PreviewRuntimeDependencies,
    RepositoryProviderFactory,
    bind_control_transaction_factory,
    preview_composition_bundle,
)
from gateway_backend.application.workspace.preview import build_preview_job_payload
from gateway_backend.artifacts import InMemoryArtifactStore, put_with_built_ref
from gateway_backend.bootstrap.operation_worker import bootstrap_control_database
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
    WorkspaceState,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.operations import (
    OPERATION_RUNTIME_CONTRACT_VERSION,
    OperationRecord,
    OperationStatus,
    StepRecord,
    StepStatus,
    TransitionDisposition,
    operation_record_from_document,
    step_record_from_document,
)
from gateway_backend.operations.lease_session import LeaseSession
from gateway_backend.operations.persistence import OperationLifecycleActions
from gateway_backend.operations.worker import ClaimedExecutor, ExecutionControl, ExecutorAcknowledgment, WriteUnitOfWorkFactory
from tests.support.runtime_settings import make_operation_worker_settings
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    catalog_table,
    int_id_column,
    make_catalog,
)
from tests.support.canonical_metadata import (
    CatalogCommitCanonicalMetadataPort,
    MetadataControlDbUnitOfWork,
    metadata_for_catalog,
)
from tests.support.source_package_fixtures import pack_tar_gz
from tests.support.table_rules import _runtime_comparison_ruleset_digest
from tests.support.workspace_fixtures import MutableBaselineHeadReadPort, make_baseline_head

BASE_TIME = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
LEASE_EXPIRES_AT = BASE_TIME + timedelta(seconds=30)
BASELINE_HEAD = make_baseline_head(version=3, commit_id="commit-base")
REPOSITORY_ID = "repo-1"
WORKSPACE_ID = "ws-preview-1"
UPLOAD_REVISION_ID = "ur-preview-1"
IDEMPOTENCY_KEY = "preview-idem-1"

BASELINE_SQL = (
    "CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n"
    "INSERT INTO t VALUES (1);\n"
)
INITIAL_SQL = BASELINE_SQL
MODIFIED_SQL = (
    "CREATE TABLE t (id INT NOT NULL PRIMARY KEY);\n"
    "INSERT INTO t VALUES (1), (2);\n"
)
EMPTY_SQL = "SET FOREIGN_KEY_CHECKS=0;\n"


def preview_baseline_provider(
    *,
    commit_id: str = BASELINE_HEAD.business_baseline_commit_id,
    empty: bool = False,
) -> FakeRepositoryTableAccessProvider:
    if empty:
        catalog = make_catalog(
            (),
            repository_id=REPOSITORY_ID,
            ref=commit_id,
            commit=commit_id,
        )
        return FakeRepositoryTableAccessProvider(
            catalog=catalog,
            rows={},
            current_commit=commit_id,
        )
    table = catalog_table("t", (int_id_column(),))
    rows = {"t": ((1,),)}
    catalog = make_catalog(
        (table,),
        repository_id=REPOSITORY_ID,
        ref=commit_id,
        commit=commit_id,
    )
    return FakeRepositoryTableAccessProvider(
        catalog=catalog,
        rows=rows,
        current_commit=commit_id,
    )


def repository_provider_factory(
    provider: FakeRepositoryTableAccessProvider,
) -> RepositoryProviderFactory:
    def factory(repository_id: str, commit_id: str) -> FakeRepositoryTableAccessProvider:
        if repository_id != REPOSITORY_ID:
            raise ValueError(f"unexpected repository_id: {repository_id}")
        if commit_id != provider.current_commit:
            raise ValueError(f"unexpected commit_id: {commit_id}")
        return provider

    return factory


def store_source_package(
    store: InMemoryArtifactStore,
    sql_bytes: bytes,
    *,
    artifact_id: str,
) -> SourceArtifactBinding:
    payload = pack_tar_gz({"sql/dbcfg.sql": sql_bytes})
    ref = put_with_built_ref(
        store,
        payload,
        artifact_id=artifact_id,
        media_type="application/gzip",
    )
    return SourceArtifactBinding(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )


def build_upload_revision(
    *,
    input_completeness: InputCompleteness,
    initial_binding: SourceArtifactBinding | None,
    modified_binding: SourceArtifactBinding,
    generation: int = 1,
) -> UploadRevision:
    source_artifacts: dict[SourceArtifactRole, SourceArtifactBinding] = {
        SourceArtifactRole.MODIFIED: modified_binding,
    }
    if initial_binding is not None:
        source_artifacts[SourceArtifactRole.INITIAL] = initial_binding
    return UploadRevision(
        upload_revision_id=UPLOAD_REVISION_ID,
        workspace_id=WORKSPACE_ID,
        generation=generation,
        input_completeness=input_completeness,
        source_artifacts=source_artifacts,
        idempotency_key="upload-idem-1",
        request_fingerprint="fp-upload-preview",
        created_by="actor-1",
        created_at=BASE_TIME,
    )


def build_workspace(*, generation: int = 1) -> Workspace:
    return Workspace(
        workspace_id=WORKSPACE_ID,
        owner_actor_id="actor-1",
        gateway_device_external_key="device-1",
        business_project_id="project-1",
        repository_id=REPOSITORY_ID,
        state=WorkspaceState.OPEN,
        generation=generation,
        optimistic_version=1,
        current_upload_revision_id=UPLOAD_REVISION_ID,
        current_preview_result_id=None,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


@dataclass
class PreviewJobHarness:
    db_path: Path
    artifact_store: InMemoryArtifactStore
    baseline_provider: FakeRepositoryTableAccessProvider
    baseline_head_read: MutableBaselineHeadReadPort
    deps: PreviewRuntimeDependencies
    handlers: dict[str, ClaimedExecutor]
    upload_revision: UploadRevision
    job_payload: bytes
    publication_uow_factory: Callable[[], AbstractContextManager[PreviewControlTransaction]]

    @property
    def control_transaction_factory(self) -> Callable[[], AbstractContextManager[PreviewControlTransaction]]:
        return self.publication_uow_factory

    def executor(self, handler_identity: str) -> ClaimedExecutor:
        return self.handlers[handler_identity]

    def seed_workspace(self) -> None:
        workspace = build_workspace(generation=self.upload_revision.generation)
        with ControlDbUnitOfWork(self.db_path) as unit_of_work:
            if unit_of_work.workspace.get_workspace(workspace.workspace_id) is not None:
                return
            unit_of_work.workspace.save_workspace(workspace, expected_version=workspace.optimistic_version)
            unit_of_work.workspace.save_upload_revision(self.upload_revision)


def build_preview_harness(
    tmp_path: Path,
    *,
    input_completeness: InputCompleteness = InputCompleteness.FULL,
    canonical_noop: bool = False,
    empty_baseline: bool = False,
) -> PreviewJobHarness:
    db_path = tmp_path / "preview-control.sqlite3"
    bootstrap_control_database(make_operation_worker_settings(db_path.parent, control_db_path=db_path))
    artifact_store = InMemoryArtifactStore()
    if empty_baseline and canonical_noop:
        modified_sql = EMPTY_SQL
        initial_sql = EMPTY_SQL
    else:
        modified_sql = BASELINE_SQL if canonical_noop else MODIFIED_SQL
        initial_sql = BASELINE_SQL if canonical_noop else INITIAL_SQL
    modified_binding = store_source_package(
        artifact_store,
        modified_sql.encode("utf-8"),
        artifact_id="modified-package",
    )
    initial_binding = None
    if input_completeness is InputCompleteness.FULL:
        initial_binding = store_source_package(
            artifact_store,
            initial_sql.encode("utf-8"),
            artifact_id="initial-package",
        )
    upload_revision = build_upload_revision(
        input_completeness=input_completeness,
        initial_binding=initial_binding,
        modified_binding=modified_binding,
    )
    baseline_provider = preview_baseline_provider(empty=empty_baseline)
    baseline_head_read = MutableBaselineHeadReadPort({REPOSITORY_ID: BASELINE_HEAD})
    metadata_port = CatalogCommitCanonicalMetadataPort(
        {
            (REPOSITORY_ID, BASELINE_HEAD.business_baseline_commit_id): metadata_for_catalog(
                baseline_provider.catalog,
                initial=empty_baseline,
            )
        }
    )
    def control_uow_factory() -> MetadataControlDbUnitOfWork:
        return MetadataControlDbUnitOfWork(db_path, metadata_port)
    deps = PreviewRuntimeDependencies(
        artifact_store=artifact_store,
        repository_provider_factory=repository_provider_factory(baseline_provider),
        baseline_head_read=baseline_head_read,
        control_transaction_factory=control_uow_factory,
    )
    definitions, handlers, decoders = preview_composition_bundle(deps)
    publication_uow_factory = bind_control_transaction_factory(control_uow_factory)
    build_job_worker_composition(
        definitions,
        handlers,
        artifact_store=artifact_store,
        decoders=decoders,
    )
    job_payload = build_preview_job_payload(
        workspace_id=WORKSPACE_ID,
        upload_revision=upload_revision,
        repository_id=REPOSITORY_ID,
        business_baseline_node_id=BASELINE_HEAD.business_baseline_node_id,
        business_baseline_commit_id=BASELINE_HEAD.business_baseline_commit_id,
        baseline_head_version=BASELINE_HEAD.baseline_head_version,
        idempotency_key=IDEMPOTENCY_KEY,
        comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
    )
    return PreviewJobHarness(
        db_path=db_path,
        artifact_store=artifact_store,
        baseline_provider=baseline_provider,
        baseline_head_read=baseline_head_read,
        deps=deps,
        handlers=dict(handlers),
        upload_revision=upload_revision,
        job_payload=job_payload,
        publication_uow_factory=publication_uow_factory,
    )


def preview_operation_document(
    operation_id: str,
    *,
    payload_object: dict[str, object],
) -> dict[str, object]:
    return {
        "artifact_refs": [],
        "business_refs": [],
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": BASE_TIME.isoformat().replace("+00:00", "Z"),
        "diagnostic": None,
        "document_type": "operation",
        "job_contract_version": PREVIEW_JOB_CONTRACT_VERSION,
        "job_kind": PREVIEW_JOB_KIND,
        "job_payload": payload_object,
        "job_payload_ref": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "ready_closure_ref": None,
        "repository_operation_id": None,
        "status": OperationStatus.QUEUED.value,
        "updated_at": BASE_TIME.isoformat().replace("+00:00", "Z"),
    }


def preview_step_document(
    operation_id: str,
    *,
    step_id: str,
    step_name: str,
) -> dict[str, object]:
    return {
        "attempt_count": 0,
        "cancel_requested": False,
        "checkpoint_ref": None,
        "completed_at": None,
        "contract_version": OPERATION_RUNTIME_CONTRACT_VERSION,
        "created_at": BASE_TIME.isoformat().replace("+00:00", "Z"),
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
        "updated_at": BASE_TIME.isoformat().replace("+00:00", "Z"),
        "worker_id": None,
    }


def insert_preview_operation(harness: PreviewJobHarness, operation_id: str = "op-preview-1") -> None:
    harness.seed_workspace()
    operation = operation_record_from_document(
        preview_operation_document(operation_id, payload_object=decode_payload_object(harness))
    )
    step = step_record_from_document(
        preview_step_document(
            operation_id,
            step_id=f"{operation_id}-step-1",
            step_name=PREVIEW_STEP_MATERIALIZE,
        )
    )
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )


def claim_next_step(
    harness: PreviewJobHarness,
    *,
    worker_id: str = "worker-preview-1",
    lease_token: str = "lease-preview-1",
) -> tuple[LeaseSession, ExecutionControl, OperationRecord, StepRecord]:
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        transaction_now = unit_of_work.operations.transaction_now
        claimed = OperationLifecycleActions(
            unit_of_work.operations,
            transaction_now=transaction_now,
        ).claim_one(worker_id, lease_token)
    assert claimed is not None
    operation, step = claimed
    control = ExecutionControl()
    write_uow_factory = cast(WriteUnitOfWorkFactory, harness.control_transaction_factory)
    session = LeaseSession(
        worker_id=worker_id,
        lease_token=lease_token,
        operation_id=operation.operation_id,
        step_id=step.step_id,
        write_uow_factory=write_uow_factory,
        control=control,
        observer=lambda _event: None,
    )
    return session, control, operation, step


def run_claimed_handler(
    harness: PreviewJobHarness,
    handler_identity: str,
    session: LeaseSession,
    control: ExecutionControl,
    operation: OperationRecord,
    step: StepRecord,
) -> ExecutorAcknowledgment:
    return harness.executor(handler_identity)(operation, step, control, session)


def step_id_for(operation_id: str, step_name: str) -> str:
    suffix = {
        PREVIEW_STEP_MATERIALIZE: "1",
        PREVIEW_STEP_ASSEMBLE: "2",
        PREVIEW_STEP_PUBLISH: "3",
    }[step_name]
    return f"{operation_id}-step-{suffix}"


def decode_payload_object(harness: PreviewJobHarness) -> dict[str, object]:
    payload = json.loads(harness.job_payload)
    if type(payload) is not dict:
        raise ValueError("preview payload must be an object")
    return cast(dict[str, object], payload)
