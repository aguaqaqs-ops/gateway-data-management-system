"""Startup recovery tests for interrupted Versioned import operations."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_contracts import OperationStatus, SimpleError
from gateway_repository_service.versioned_import.models import MANUAL_RECOVERY_REQUIRED_CODE
from gateway_repository_service.versioned_import.recovery import ImportStartupReconciler
from support.import_recovery_harness import (
    assert_crash_exit,
    crash_import_subprocess,
    restart_runtime,
    wait_for_import_status,
)
from support.import_worker_harness import WorkerTestEnvironment

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")
OTHER_REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-9a9e-2e4b9f4d2c11")


def _reconciler(env: WorkerTestEnvironment) -> ImportStartupReconciler:
    return ImportStartupReconciler(
        settings=env.settings,
        layout=env.layout,
        store=env.store,
        provider_factory=env._provider_factory,
    )


def _claim_running(env: WorkerTestEnvironment, operation_id: UUID) -> None:
    claimed = env.store.claim_if_queued(operation_id)
    assert claimed is not None


def test_queued_remains_queued_after_reconcile(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path)
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, operation_id=OPERATION_ID)
        result = _reconciler(env).reconcile()
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.QUEUED
        assert result.queued_operations == 1
    finally:
        env.close()


def test_published_marker_recovered_to_succeeded(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path)
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, operation_id=OPERATION_ID)
        _claim_running(env, operation_id)
        provider = env.provider_for(REPOSITORY_ID)
        context = env.store.load_execution_context(operation_id)
        assert context is not None
        provider.create_private_ref(context.private_ref_name, context.expected_commit_id)
        provider.checkout_private_ref(context.private_ref_name)
        candidate = provider.commit_operation_marker(context.private_ref_name, context.operation_marker)
        provider.publish_main(context.expected_commit_id, candidate)
        _reconciler(env).reconcile()
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.SUCCEEDED
        assert operation.result is not None
        assert operation.result.commit_id == candidate
    finally:
        env.close()


def test_continue_verification_without_sql_replay(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path)
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, operation_id=OPERATION_ID)
        _claim_running(env, operation_id)
        provider = env.provider_for(REPOSITORY_ID)
        context = env.store.load_execution_context(operation_id)
        assert context is not None
        provider.create_private_ref(context.private_ref_name, context.expected_commit_id)
        provider.checkout_private_ref(context.private_ref_name)
        candidate = provider.commit_operation_marker(context.private_ref_name, context.operation_marker)
        assert env.store.get_automatic_replay_count(operation_id) == 0
        _reconciler(env).reconcile()
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.SUCCEEDED
        assert operation.result is not None
        assert operation.result.commit_id == candidate
        assert env.store.get_automatic_replay_count(operation_id) == 0
        assert provider.replay_order == []
    finally:
        env.close()


def test_automatic_replay_happens_once(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path)
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, operation_id=OPERATION_ID)
        _claim_running(env, operation_id)
        _reconciler(env).reconcile()
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.SUCCEEDED
        assert env.store.get_automatic_replay_count(operation_id) == 1
    finally:
        env.close()


def test_second_missing_evidence_goes_manual(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path)
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, operation_id=OPERATION_ID)
        _claim_running(env, operation_id)
        env.store.increment_automatic_replay_count(operation_id)
        _reconciler(env).reconcile()
        operation = env.store.get_operation(REPOSITORY_ID, operation_id)
        assert operation is not None
        assert operation.status == OperationStatus.FAILED
        assert operation.error is not None
        assert operation.error.code == MANUAL_RECOVERY_REQUIRED_CODE
    finally:
        env.close()


def test_manual_barrier_seeded_in_registry(tmp_path: Path) -> None:
    env = WorkerTestEnvironment(tmp_path)
    try:
        operation_id = env.enqueue(REPOSITORY_ID, artifact_id=ARTIFACT_ID, operation_id=OPERATION_ID)
        _claim_running(env, operation_id)
        env.store.mark_failed(
            operation_id,
            error=SimpleError(
                code=MANUAL_RECOVERY_REQUIRED_CODE,
                message="manual",
                details={"reason": "test"},
                request_id=None,
            ),
        )
        env.locks.seed_manual_barriers(env.store.list_repositories_with_manual_barrier())
        assert env.locks.has_manual_barrier(REPOSITORY_ID)
        other_operation = env.enqueue(
            OTHER_REPOSITORY_ID,
            artifact_id=uuid4(),
            operation_id=uuid4(),
        )
        assert other_operation is not None
    finally:
        env.close()


@pytest.mark.integration
def test_subprocess_crash_then_runtime_restart_recovers(tmp_path: Path) -> None:
    from gateway_repository_contracts import RepositoryArtifactRef, UnknownTypePolicy, VerificationPolicy
    from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
    from gateway_repository_service.layout import DurableLayout
    from gateway_repository_service.mutation_store import IdempotencyKeyHash
    from gateway_repository_service.process import DoltRunner
    from gateway_repository_service.providers import OfflineCliProvider
    from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
    from gateway_repository_service.versioned_import import ImportOperationStore, ImportRequestBinding, versioned_import_fingerprint_v1
    from support.import_worker_harness import MEDIA_TYPE, published_repository_path
    from support.lifecycle_harness import lifecycle_settings
    from test_import_package import build_package_bytes, write_artifact

    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    repository = published_repository_path(layout, REPOSITORY_ID)
    repository.mkdir(parents=True, exist_ok=True)
    runner = DoltRunner(settings, layout.root)
    cli = OfflineCliProvider(settings, layout, repository, runner)
    cli.initialize_repository()
    expected_commit = cli.head()

    replay_sql = (
        "CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\n"
        "INSERT INTO records (id) VALUES (1);\n"
    )
    manifest = {
        "package_version": 1,
        "canonicalization_manifest_digest": "manifest-digest-1",
        "tables": [
            {
                "name": "records",
                "schema": {
                    "columns": [{"name": "id", "sql_type": "BIGINT", "nullable": False}],
                    "primary_key": ["id"],
                },
                "row_count": 1,
            }
        ],
    }
    payload = build_package_bytes(manifest=manifest, replay_sql=replay_sql.encode("utf-8"))
    ready_path = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    size_bytes, raw_sha256 = write_artifact(ready_path, payload)

    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    now = "2026-08-06T00:00:00+00:00"
    with store._lock:
        store.mutation_store._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id, repository_scope, media_type, size_bytes, raw_sha256, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (str(ARTIFACT_ID), REPOSITORY_ID.hex, MEDIA_TYPE, size_bytes, raw_sha256, now, now),
        )
        store.mutation_store._connection.commit()

    binding = ImportRequestBinding(
        repository_id=REPOSITORY_ID,
        artifact_ref=RepositoryArtifactRef(
            artifact_id=ARTIFACT_ID,
            media_type=MEDIA_TYPE,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        ),
        target_ref="main",
        expected_commit_id=expected_commit,
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    key_hash = IdempotencyKeyHash.from_raw_key("recovery-crash")
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        operation_id=OPERATION_ID,
    )
    control_store.close()

    completed = crash_import_subprocess(
        settings,
        repository_id=REPOSITORY_ID,
        operation_id=OPERATION_ID,
        fault_point="after_replay_before_marker",
    )
    assert_crash_exit(completed)

    restarted = restart_runtime(settings)
    try:
        operation = restarted.import_store.get_operation(REPOSITORY_ID, OPERATION_ID)
        assert operation is not None
        assert operation.status in {OperationStatus.RUNNING, OperationStatus.SUCCEEDED}
        wait_for_import_status(
            restarted,
            REPOSITORY_ID,
            OPERATION_ID,
            OperationStatus.SUCCEEDED,
            timeout=60.0,
        )
        assert restarted.import_locks.has_manual_barrier(REPOSITORY_ID) is False
    finally:
        restarted.shutdown()
