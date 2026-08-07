"""Integration tests for durable Versioned import workers against real Dolt."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_contracts import OperationStatus, RepositoryArtifactRef, UnknownTypePolicy, VerificationPolicy
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import IdempotencyKeyHash
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import ImportOperationStore, ImportRequestBinding, versioned_import_fingerprint_v1
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from gateway_repository_service.versioned_import.worker import ImportWorkerPool
from support.import_worker_harness import MEDIA_TYPE, published_repository_path
from support.lifecycle_harness import lifecycle_settings
from test_import_package import build_package_bytes, write_artifact

REPOSITORY_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c11")
ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c11")
OPERATION_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c11")


@pytest.fixture
def integration_env(tmp_path: Path) -> Iterator[tuple[ImportWorkerPool, ImportOperationStore, DurableLayout, CandidateAImportProvider]]:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    repository = published_repository_path(layout, REPOSITORY_ID)
    repository.mkdir(parents=True, exist_ok=True)
    runner = DoltRunner(settings, layout.root)
    cli = OfflineCliProvider(settings, layout, repository, runner)
    cli.initialize_repository()
    provider = CandidateAImportProvider(settings, layout, repository, runner)

    db_path = settings.control_db_path
    control_store = ControlStore.open(
        db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )

    def provider_factory(_repository_id: UUID) -> CandidateAImportProvider:
        return provider

    pool = ImportWorkerPool(
        settings=settings,
        layout=layout,
        store=store,
        provider_factory=provider_factory,
        locks=RepositoryLockRegistry(),
    )
    pool.start()
    try:
        yield pool, store, layout, provider
    finally:
        pool.stop()
        control_store.close()


@pytest.mark.integration
def test_dolt_worker_happy_path(
    integration_env: tuple[ImportWorkerPool, ImportOperationStore, DurableLayout, CandidateAImportProvider],
) -> None:
    pool, store, layout, provider = integration_env
    expected_commit = provider.read_ref("main")

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

    now = "2026-08-06T00:00:00+00:00"
    with store._lock:
        store.mutation_store._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id,
                repository_scope,
                media_type,
                size_bytes,
                raw_sha256,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ARTIFACT_ID),
                REPOSITORY_ID.hex,
                MEDIA_TYPE,
                size_bytes,
                raw_sha256,
                now,
                now,
            ),
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
    key_hash = IdempotencyKeyHash.from_raw_key("integration-happy-path")
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        operation_id=OPERATION_ID,
    )
    pool.notify()

    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        operation = store.get_operation(REPOSITORY_ID, OPERATION_ID)
        lifecycle = store.mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        if (
            operation is not None
            and operation.status == OperationStatus.SUCCEEDED
            and lifecycle is not None
            and lifecycle.bytes_deleted_at is not None
        ):
            break
        time.sleep(0.1)
    else:
        raise AssertionError("operation did not succeed with artifact cleanup")

    operation = store.get_operation(REPOSITORY_ID, OPERATION_ID)
    assert operation is not None
    assert operation.result is not None
    assert provider.read_ref("main") == operation.result.commit_id
    assert operation.result.expected_commit_id == expected_commit
    assert not ready_path.exists()

    lifecycle = store.mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.consumed_by_operation_id == OPERATION_ID
    assert lifecycle.bytes_deleted_at is not None

    private_ref = f"gateway-import-{OPERATION_ID.hex}"
    with pytest.raises(Exception):
        provider.read_ref(private_ref)
