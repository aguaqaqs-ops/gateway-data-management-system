"""History compare job composition and fixture helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from gateway_backend.application.history.compare import validate_history_compare_binding
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_ASSEMBLE_HANDLER,
    HISTORY_COMPARE_JOB_CONTRACT_VERSION,
    HISTORY_COMPARE_JOB_KIND,
    HISTORY_COMPARE_MATERIALIZE_HANDLER,
    HISTORY_COMPARE_PUBLISH_HANDLER,
    HISTORY_COMPARE_STEP_MATERIALIZE,
    HistoryCompareControlTransaction,
    HistoryCompareControlTransactionFactory,
    HistoryCompareRuntimeDependencies,
    history_compare_composition_bundle,
    history_compare_step_id,
)
from gateway_backend.application.history.contracts import (
    HistoryCompareAcceptCommand,
    HistoryCompareAcceptanceRecord,
    HistoryNodeRef,
    HistoryNodeRefKind,
    PERMISSION_READ_PROJECT_HISTORY,
)
from gateway_backend.application.job_definitions import build_job_worker_composition
from gateway_backend.artifacts import ArtifactStorePort, InMemoryArtifactStore
from gateway_backend.bootstrap.operation_worker import bootstrap_control_database
from gateway_backend.application.history.compare import build_history_compare_job_payload
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
from tests.support.baseline_fixtures import seed_provisioned_mapping_with_head
from tests.support.http_workspace_harness import BASELINE_HEAD
from tests.support.preview_job_harness import BASE_TIME
from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryCatalogTable, RepositoryColumn
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    RepositoryRows,
    catalog_table,
    catalog_without_tables,
    int_id_column,
    make_catalog,
)
from tests.support.canonical_metadata import MetadataControlDbUnitOfWork, metadata_for_catalog, CatalogCommitCanonicalMetadataPort
from tests.support.runtime_settings import make_operation_worker_settings
from tests.support.workspace_fixtures import make_identity
from tests.support.table_rules import _runtime_comparison_ruleset_digest

REPOSITORY_ID = "repo-1"
DEVICE_KEY = "device-1"
PROJECT_ID = "project-1"
IDEMPOTENCY_KEY = "history-compare-idem-1"
ORDERED_SYX_TABLE = "b1_n1_iec104_syx_list"
def ordered_syx_catalog_table() -> RepositoryCatalogTable:
    return catalog_table(
        ORDERED_SYX_TABLE,
        (
            RepositoryColumn(name="gid", ordinal=0, scalar_type="INT UNSIGNED", nullable=False),
            RepositoryColumn(name="no", ordinal=1, scalar_type="INT", nullable=False),
            RepositoryColumn(name="value", ordinal=2, scalar_type="VARCHAR(8)", nullable=True),
        ),
        primary_key=("gid",),
    )


def net_cfg_catalog_table() -> RepositoryCatalogTable:
    return catalog_table(
        "net_cfg",
        (
            RepositoryColumn(name="board", ordinal=0, scalar_type="VARCHAR(32)", nullable=False),
            RepositoryColumn(name="link_no", ordinal=1, scalar_type="INT", nullable=False),
            RepositoryColumn(name="value", ordinal=2, scalar_type="VARCHAR(8)", nullable=True),
        ),
        primary_key=(),
    )


def history_compare_net_cfg_provider(
    *,
    commit_id: str,
    rows: RepositoryRows,
) -> FakeRepositoryTableAccessProvider:
    table = net_cfg_catalog_table()
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


def history_compare_ordered_provider(
    *,
    commit_id: str,
    rows: RepositoryRows,
    missing_table_on_open: str | None = None,
) -> FakeRepositoryTableAccessProvider:
    table = ordered_syx_catalog_table()
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
        missing_table_on_open=missing_table_on_open,
    )


def history_compare_provider(
    *,
    commit_id: str,
    row_count: int = 1,
    declared_rows: RepositoryRows | None = None,
    per_read_rows: tuple[RepositoryRows, ...] = (),
    per_read_catalog_without: tuple[tuple[str, ...], ...] = (),
    missing_table_on_open: str | None = None,
    catalog_without: tuple[str, ...] = (),
) -> FakeRepositoryTableAccessProvider:
    table = catalog_table("t", (int_id_column(),), row_count=row_count)
    resolved_declared_rows = declared_rows or {
        "t": tuple((index,) for index in range(1, row_count + 1))
    }
    full_catalog = make_catalog(
        (table,),
        repository_id=REPOSITORY_ID,
        ref=commit_id,
        commit=commit_id,
    )
    session_catalog = (
        catalog_without_tables(full_catalog, drop=catalog_without)
        if catalog_without
        else full_catalog
    )
    return FakeRepositoryTableAccessProvider(
        catalog=session_catalog,
        base_catalog=full_catalog,
        rows=resolved_declared_rows,
        declared_rows=resolved_declared_rows,
        current_commit=commit_id,
        per_read_rows=per_read_rows,
        per_read_catalog_without=per_read_catalog_without,
        missing_table_on_open=missing_table_on_open,
    )


def history_compare_provider_factory(
    providers: dict[str, FakeRepositoryTableAccessProvider],
) -> Callable[[str, str], FakeRepositoryTableAccessProvider]:
    def factory(repository_id: str, commit_id: str) -> FakeRepositoryTableAccessProvider:
        if repository_id != REPOSITORY_ID:
            raise ValueError(f"unexpected repository_id: {repository_id}")
        provider = providers.get(commit_id)
        if provider is None:
            raise ValueError(f"unexpected commit_id: {commit_id}")
        return provider

    return factory


def seed_archived_baseline_node(
    db_path: Path,
    *,
    node_id: str,
    commit_id: str,
    created_at_us: int,
    parent_node_id: str = BASELINE_HEAD.business_baseline_node_id,
    source_submission_id: str = "submission-test",
    repository_id: str = REPOSITORY_ID,
    device_key: str = DEVICE_KEY,
    project_id: str = PROJECT_ID,
) -> None:
    with ControlDbUnitOfWork(db_path) as unit_of_work:
        unit_of_work.connection.execute(
            """
            INSERT INTO baseline_node_records (
                node_id, repository_id, gateway_device_external_key, business_project_id,
                commit_id, kind, parent_node_id, source_submission_id, created_at_us
            ) VALUES (?, ?, ?, ?, ?, 'ARCHIVED_SUBMISSION', ?, ?, ?)
            """,
            (
                node_id,
                repository_id,
                device_key,
                project_id,
                commit_id,
                parent_node_id,
                source_submission_id,
                created_at_us,
            ),
        )


@dataclass
class HistoryCompareJobHarness:
    db_path: Path
    artifact_store: ArtifactStorePort
    providers: dict[str, FakeRepositoryTableAccessProvider]
    deps: HistoryCompareRuntimeDependencies
    handlers: dict[str, ClaimedExecutor]
    job_payload: bytes
    operation_id: str
    publication_uow_factory: Callable[[], AbstractContextManager[HistoryCompareControlTransaction]]

    @property
    def control_transaction_factory(self) -> Callable[[], AbstractContextManager[HistoryCompareControlTransaction]]:
        return self.publication_uow_factory

    def executor(self, handler_identity: str) -> ClaimedExecutor:
        return self.handlers[handler_identity]

    def total_open_count(self) -> int:
        return sum(provider.open_count for provider in self.providers.values())


def build_history_compare_harness(
    tmp_path: Path,
    *,
    db_path: Path | None = None,
    artifact_store: ArtifactStorePort | None = None,
    node_specs: tuple[tuple[str, str], ...] = (
        (BASELINE_HEAD.business_baseline_node_id, BASELINE_HEAD.business_baseline_commit_id),
        ("bn-b", "commit-b"),
    ),
    custom_providers: dict[str, FakeRepositoryTableAccessProvider] | None = None,
    idempotency_key: str = IDEMPOTENCY_KEY,
    seed_acceptance: bool = True,
    existing_operation_id: str | None = None,
) -> HistoryCompareJobHarness:
    resolved_db_path = db_path or (tmp_path / "history-compare-control.sqlite3")
    if db_path is None:
        bootstrap_control_database(
            make_operation_worker_settings(resolved_db_path.parent, control_db_path=resolved_db_path)
        )
        seed_provisioned_mapping_with_head(resolved_db_path, baseline_head=BASELINE_HEAD)
    for index, (node_id, commit_id) in enumerate(node_specs):
        if node_id == BASELINE_HEAD.business_baseline_node_id:
            continue
        seed_archived_baseline_node(
            resolved_db_path,
            node_id=node_id,
            commit_id=commit_id,
            created_at_us=index + 1,
        )

    distinct_commits = tuple(dict.fromkeys(commit_id for _, commit_id in node_specs))
    if custom_providers is not None:
        providers = dict(custom_providers)
    else:
        providers = {
            commit_id: history_compare_provider(
                commit_id=commit_id,
            )
            for commit_id in distinct_commits
        }
    resolved_artifact_store = artifact_store or InMemoryArtifactStore()
    metadata_port = CatalogCommitCanonicalMetadataPort(
        {
            (REPOSITORY_ID, commit_id): metadata_for_catalog(
                provider.catalog,
                rows_by_table=provider.rows,
            )
            for commit_id, provider in providers.items()
        }
    )

    def control_transaction_factory() -> ControlDbUnitOfWork:
        return MetadataControlDbUnitOfWork(resolved_db_path, metadata_port)

    deps = HistoryCompareRuntimeDependencies(
        artifact_store=resolved_artifact_store,
        repository_provider_factory=history_compare_provider_factory(providers),
        control_transaction_factory=cast(
            HistoryCompareControlTransactionFactory,
            control_transaction_factory,
        ),
    )
    definitions, handlers, decoders, bound_deps = history_compare_composition_bundle(deps)
    publication_uow_factory = bound_deps.control_transaction_factory
    build_job_worker_composition(
        definitions,
        handlers,
        artifact_store=resolved_artifact_store,
        decoders=decoders,
    )

    if seed_acceptance:
        identity = make_identity(
            device_key=DEVICE_KEY,
            project_id=PROJECT_ID,
            permissions=frozenset({PERMISSION_READ_PROJECT_HISTORY}),
        )
        node_refs = tuple(
            HistoryNodeRef(HistoryNodeRefKind.BASELINE_NODE, node_id) for node_id, _ in node_specs
        )
        with ControlDbUnitOfWork(resolved_db_path) as unit_of_work:
            validation = validate_history_compare_binding(
                command=HistoryCompareAcceptCommand(
                    context=identity,
                    idempotency_key=idempotency_key,
                    node_refs=node_refs,
                ),
                unit_of_work=unit_of_work,
                comparison_ruleset_digest=_runtime_comparison_ruleset_digest(),
            )
            assert validation.operation_id is not None
            assert validation.acceptance_id is not None
            operation_id = validation.operation_id
            acceptance_id = validation.acceptance_id
            job_payload = build_history_compare_job_payload(
                validation=validation,
                acceptance_id=acceptance_id,
                idempotency_key=idempotency_key,
            )
            unit_of_work.history_compare.save_acceptance(
                HistoryCompareAcceptanceRecord(
                    acceptance_id=acceptance_id,
                    gateway_device_external_key=validation.gateway_device_external_key,
                    business_project_id=validation.business_project_id,
                    repository_id=validation.repository_id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=validation.request_fingerprint,
                    comparison_ruleset_digest=validation.comparison_ruleset_digest,
                    nodes=validation.nodes,
                    operation_id=operation_id,
                    created_at=BASE_TIME,
                )
            )
    else:
        if existing_operation_id is None:
            raise ValueError("existing_operation_id is required when seed_acceptance is False")
        operation_id = existing_operation_id
        with ControlDbUnitOfWork(resolved_db_path, read_only=True) as unit_of_work:
            operation = unit_of_work.operations.get_operation(operation_id)
        if operation.job_payload is None:
            raise ValueError("history compare operation is missing inline job_payload")
        job_payload = operation.job_payload

    return HistoryCompareJobHarness(
        db_path=resolved_db_path,
        artifact_store=resolved_artifact_store,
        providers=providers,
        deps=deps,
        handlers=dict(handlers),
        job_payload=job_payload,
        operation_id=operation_id,
        publication_uow_factory=publication_uow_factory,
    )


def history_compare_operation_document(
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
        "job_contract_version": HISTORY_COMPARE_JOB_CONTRACT_VERSION,
        "job_kind": HISTORY_COMPARE_JOB_KIND,
        "job_payload": payload_object,
        "job_payload_ref": None,
        "operation_id": operation_id,
        "optimistic_version": 0,
        "ready_closure_ref": None,
        "repository_operation_id": None,
        "status": OperationStatus.QUEUED.value,
        "updated_at": BASE_TIME.isoformat().replace("+00:00", "Z"),
    }


def history_compare_step_document(
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


def insert_history_compare_operation(harness: HistoryCompareJobHarness) -> None:
    operation = operation_record_from_document(
        history_compare_operation_document(
            harness.operation_id,
            payload_object=decode_payload_object(harness),
        )
    )
    step = step_record_from_document(
        history_compare_step_document(
            harness.operation_id,
            step_id=history_compare_step_id(harness.operation_id, HISTORY_COMPARE_STEP_MATERIALIZE),
            step_name=HISTORY_COMPARE_STEP_MATERIALIZE,
        )
    )
    with ControlDbUnitOfWork(harness.db_path) as unit_of_work:
        assert (
            unit_of_work.operations.insert_operation_with_initial_step(operation, step)
            is TransitionDisposition.APPLY
        )


def claim_next_step(
    harness: HistoryCompareJobHarness,
    *,
    worker_id: str = "worker-history-compare-1",
    lease_token: str = "lease-history-compare-1",
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
    harness: HistoryCompareJobHarness,
    handler_identity: str,
    session: LeaseSession,
    control: ExecutionControl,
    operation: OperationRecord,
    step: StepRecord,
) -> ExecutorAcknowledgment:
    return harness.executor(handler_identity)(operation, step, control, session)


def run_through_step(
    harness: HistoryCompareJobHarness,
    handler_identity: str,
) -> StepRecord:
    session, control, operation, step = claim_next_step(harness)
    run_claimed_handler(harness, handler_identity, session, control, operation, step)
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as unit_of_work:
        return unit_of_work.operations.get_step(step.step_id)


def decode_payload_object(harness: HistoryCompareJobHarness) -> dict[str, object]:
    payload = json.loads(harness.job_payload)
    if type(payload) is not dict:
        raise ValueError("history compare payload must be an object")
    return cast(dict[str, object], payload)


def run_full_history_compare_job(harness: HistoryCompareJobHarness) -> None:
    insert_history_compare_operation(harness)
    run_through_step(harness, HISTORY_COMPARE_MATERIALIZE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_ASSEMBLE_HANDLER)
    run_through_step(harness, HISTORY_COMPARE_PUBLISH_HANDLER)
