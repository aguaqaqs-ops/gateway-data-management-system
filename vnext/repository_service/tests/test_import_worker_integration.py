"""Integration tests for durable Versioned import workers against real Dolt."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

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
@pytest.mark.serial
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
            , cleanup_seq) VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle))
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


@pytest.mark.integration
@pytest.mark.serial
def test_repository_import_replays_oversized_single_row_insert_and_case_update(
    tmp_path: Path,
) -> None:
    """Exercise >4 MiB mutation statements through the production import replay worker."""

    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    runner = DoltRunner(settings, layout.root)
    providers: dict[UUID, CandidateAImportProvider] = {}
    repositories: dict[str, tuple[UUID, CandidateAImportProvider]] = {}

    for form in ("batch", "rowwise"):
        repository_id = uuid4()
        repository = published_repository_path(layout, repository_id)
        repository.mkdir(parents=True, exist_ok=True)
        cli = OfflineCliProvider(settings, layout, repository, runner)
        cli.initialize_repository()
        provider = CandidateAImportProvider(settings, layout, repository, runner)
        providers[repository_id] = provider
        repositories[form] = (repository_id, provider)

    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )

    def provider_factory(repository_id: UUID) -> CandidateAImportProvider:
        return providers[repository_id]

    pool = ImportWorkerPool(
        settings=settings,
        layout=layout,
        store=store,
        provider_factory=provider_factory,
        locks=RepositoryLockRegistry(),
    )
    pool.start()

    def import_sql(
        repository_id: UUID,
        provider: CandidateAImportProvider,
        *,
        sql: str,
        row_count: int,
        operation_name: str,
    ) -> None:
        artifact_id = uuid4()
        operation_id = uuid4()
        ready_path = artifact_ready_path(layout, repository_id, artifact_id)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "package_version": 1,
            "canonicalization_manifest_digest": f"large-replay-{operation_name}",
            "tables": [
                {
                    "name": "records",
                    "schema": {
                        "columns": [
                            {"name": "id", "sql_type": "BIGINT", "nullable": False},
                            {"name": "payload", "sql_type": "MEDIUMTEXT", "nullable": True},
                        ],
                        "primary_key": ["id"],
                    },
                    "row_count": row_count,
                }
            ],
        }
        payload = build_package_bytes(manifest=manifest, replay_sql=sql.encode("utf-8"))
        size_bytes, raw_sha256 = write_artifact(ready_path, payload)
        with store._lock:
            store.mutation_store._connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id, repository_scope, media_type, size_bytes, raw_sha256,
                    created_at, updated_at, cleanup_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?, (
                    SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle
                ))
                """,
                (
                    str(artifact_id),
                    repository_id.hex,
                    MEDIA_TYPE,
                    size_bytes,
                    raw_sha256,
                    "2026-10-27T00:00:00+00:00",
                    "2026-10-27T00:00:00+00:00",
                ),
            )
            store.mutation_store._connection.commit()

        binding = ImportRequestBinding(
            repository_id=repository_id,
            artifact_ref=RepositoryArtifactRef(
                artifact_id=artifact_id,
                media_type=MEDIA_TYPE,
                size_bytes=size_bytes,
                raw_sha256=raw_sha256,
            ),
            target_ref="main",
            expected_commit_id=provider.read_ref("main"),
            verification_policy=VerificationPolicy.STRUCTURAL,
            unknown_type_policy=UnknownTypePolicy.REJECT,
        )
        key_hash = IdempotencyKeyHash.from_raw_key(f"oversized-{operation_name}")
        store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash),
            operation_id=operation_id,
        )
        pool.notify()

        deadline = time.monotonic() + 180.0
        while time.monotonic() < deadline:
            operation = store.get_operation(repository_id, operation_id)
            if operation is not None and operation.status in {
                OperationStatus.SUCCEEDED,
                OperationStatus.FAILED,
            }:
                assert operation.status is OperationStatus.SUCCEEDED, (
                    operation.error.code if operation.error is not None else "import failed"
                )
                return
            time.sleep(0.05)
        raise AssertionError("large replay import did not reach a terminal status")

    try:
        for form, (repository_id, provider) in repositories.items():
            import_sql(
                repository_id,
                provider,
                sql=(
                    "CREATE TABLE records ("
                    "id BIGINT NOT NULL PRIMARY KEY, payload MEDIUMTEXT NULL);\n"
                    "INSERT INTO records (id, payload) VALUES (0, 'seed');\n"
                ),
                row_count=1,
                operation_name=f"{form}-base",
            )

        large_insert_value = "x" * (5 * 1024 * 1024)
        large_update_value = "y" * (5 * 1024 * 1024)
        large_insert_sql = (
            "INSERT INTO records (id, payload) VALUES (1, '"
            + large_insert_value
            + "');\n"
        )
        large_case_update_sql = (
            "UPDATE records SET payload=CASE WHEN id=1 THEN '"
            + large_update_value
            + "' ELSE payload END WHERE id IN (1);\n"
        )
        assert 5 * 1024 * 1024 < len(large_insert_sql.encode("utf-8")) < 8 * 1024 * 1024
        assert 5 * 1024 * 1024 < len(large_case_update_sql.encode("utf-8")) < 8 * 1024 * 1024

        for form, (repository_id, provider) in repositories.items():
            insert_sql = large_insert_sql
            update_sql = large_case_update_sql
            if form == "rowwise":
                update_sql = (
                    "UPDATE records SET payload='"
                    + large_update_value
                    + "' WHERE id=1;\n"
                )
            import_sql(
                repository_id,
                provider,
                sql=insert_sql,
                row_count=2,
                operation_name=f"{form}-insert",
            )
            import_sql(
                repository_id,
                provider,
                sql=update_sql,
                row_count=2,
                operation_name=f"{form}-update",
            )

        hashes: dict[str, str] = {}
        for form, (_, provider) in repositories.items():
            rows = provider._cli.query_json(
                f"oversized_{form}_table_hash",
                "SELECT DOLT_HASHOF_TABLE('records') AS table_hash;\n",
            )
            assert len(rows) == 1
            table_hash = rows[0].get("table_hash")
            assert isinstance(table_hash, str) and table_hash
            hashes[form] = table_hash
        assert hashes["batch"] == hashes["rowwise"]
    finally:
        pool.stop()
        control_store.close()


REPOSITORY_B_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c12")
ARTIFACT_B_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c13")
OPERATION_B_ID = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c13")


def _seed_import_operation(
    *,
    store: ImportOperationStore,
    layout: DurableLayout,
    repository_id: UUID,
    artifact_id: UUID,
    operation_id: UUID,
    expected_commit: str,
    key: str,
) -> None:
    replay_sql = (
        "CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\n"
        "INSERT INTO records (id) VALUES (1);\n"
    )
    manifest = {
        "package_version": 1,
        "canonicalization_manifest_digest": f"manifest-digest-{operation_id.hex[:8]}",
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
    ready_path = artifact_ready_path(layout, repository_id, artifact_id)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    size_bytes, raw_sha256 = write_artifact(ready_path, payload)
    now = "2026-08-06T00:00:00+00:00"
    with store._lock:
        store.mutation_store._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id, repository_scope, media_type, size_bytes, raw_sha256, created_at, updated_at
            , cleanup_seq) VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle))
            """,
            (str(artifact_id), repository_id.hex, MEDIA_TYPE, size_bytes, raw_sha256, now, now),
        )
        store.mutation_store._connection.commit()
    binding = ImportRequestBinding(
        repository_id=repository_id,
        artifact_ref=RepositoryArtifactRef(
            artifact_id=artifact_id,
            media_type=MEDIA_TYPE,
            size_bytes=size_bytes,
            raw_sha256=raw_sha256,
        ),
        target_ref="main",
        expected_commit_id=expected_commit,
        verification_policy=VerificationPolicy.STRUCTURAL,
        unknown_type_policy=UnknownTypePolicy.REJECT,
    )
    key_hash = IdempotencyKeyHash.from_raw_key(key)
    fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
    store.claim_or_enqueue(
        binding,
        key_hash=key_hash,
        fingerprint=fingerprint,
        operation_id=operation_id,
    )


@pytest.mark.integration
@pytest.mark.serial
def test_multirepo_running_interrupt_restart_recovery(tmp_path: Path) -> None:
    from gateway_repository_service.runtime import ServiceRuntime

    settings = lifecycle_settings(tmp_path)
    settings = settings.model_copy(update={"max_import_workers": 2})
    layout = DurableLayout.create_for_probe(settings.data_root)

    repositories = []
    for repository_id in (REPOSITORY_ID, REPOSITORY_B_ID):
        repository = published_repository_path(layout, repository_id)
        repository.mkdir(parents=True, exist_ok=True)
        runner = DoltRunner(settings, layout.root)
        cli = OfflineCliProvider(settings, layout, repository, runner)
        cli.initialize_repository()
        repositories.append((repository_id, cli.head()))

    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    _seed_import_operation(
        store=store,
        layout=layout,
        repository_id=REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        operation_id=OPERATION_ID,
        expected_commit=repositories[0][1],
        key="integration-running-a",
    )
    control_store.close()

    from support.import_recovery_harness import assert_crash_exit, crash_import_subprocess, wait_for_import_status

    completed = crash_import_subprocess(
        settings,
        repository_id=REPOSITORY_ID,
        operation_id=OPERATION_ID,
        fault_point="after_replay_before_marker",
    )
    assert_crash_exit(completed)

    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    _seed_import_operation(
        store=store,
        layout=layout,
        repository_id=REPOSITORY_B_ID,
        artifact_id=ARTIFACT_B_ID,
        operation_id=OPERATION_B_ID,
        expected_commit=repositories[1][1],
        key="integration-running-b",
    )
    op_a = store.get_operation(REPOSITORY_ID, OPERATION_ID)
    assert op_a is not None and op_a.status == OperationStatus.RUNNING
    control_store.close()

    completed = crash_import_subprocess(
        settings,
        repository_id=REPOSITORY_B_ID,
        operation_id=OPERATION_B_ID,
        fault_point="after_replay_before_marker",
    )
    assert_crash_exit(completed)

    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    op_a = store.get_operation(REPOSITORY_ID, OPERATION_ID)
    op_b = store.get_operation(REPOSITORY_B_ID, OPERATION_B_ID)
    assert op_a is not None and op_a.status == OperationStatus.RUNNING
    assert op_b is not None and op_b.status == OperationStatus.RUNNING
    control_store.close()

    runtime = ServiceRuntime.start(settings)
    try:
        wait_for_import_status(
            runtime,
            REPOSITORY_ID,
            OPERATION_ID,
            OperationStatus.SUCCEEDED,
            timeout=90.0,
        )
        wait_for_import_status(
            runtime,
            REPOSITORY_B_ID,
            OPERATION_B_ID,
            OperationStatus.SUCCEEDED,
            timeout=90.0,
        )
        assert runtime.is_ready()
    finally:
        runtime.shutdown()


@pytest.mark.integration
@pytest.mark.serial
def test_restart_recovery_multirepo_concurrent_claim(tmp_path: Path) -> None:
    from gateway_repository_service.runtime import ServiceRuntime

    settings = lifecycle_settings(tmp_path)
    settings = settings.model_copy(update={"max_import_workers": 2})
    layout = DurableLayout.create_for_probe(settings.data_root)

    repositories = []
    for repository_id in (REPOSITORY_ID, REPOSITORY_B_ID):
        repository = published_repository_path(layout, repository_id)
        repository.mkdir(parents=True, exist_ok=True)
        runner = DoltRunner(settings, layout.root)
        cli = OfflineCliProvider(settings, layout, repository, runner)
        cli.initialize_repository()
        repositories.append((repository_id, cli.head()))

    control_store = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(
        control_store.connection,
        transaction_lock=control_store.transaction_lock,
    )
    _seed_import_operation(
        store=store,
        layout=layout,
        repository_id=REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        operation_id=OPERATION_ID,
        expected_commit=repositories[0][1],
        key="integration-restart-a",
    )
    _seed_import_operation(
        store=store,
        layout=layout,
        repository_id=REPOSITORY_B_ID,
        artifact_id=ARTIFACT_B_ID,
        operation_id=OPERATION_B_ID,
        expected_commit=repositories[1][1],
        key="integration-restart-b",
    )
    control_store.close()

    runtime = ServiceRuntime.start(settings)
    try:
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            op_a = runtime.import_store.get_operation(REPOSITORY_ID, OPERATION_ID)
            op_b = runtime.import_store.get_operation(REPOSITORY_B_ID, OPERATION_B_ID)
            if (
                op_a is not None
                and op_b is not None
                and op_a.status == OperationStatus.SUCCEEDED
                and op_b.status == OperationStatus.SUCCEEDED
            ):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("both repositories did not complete import after restart")

        assert runtime.is_ready()
    finally:
        runtime.shutdown()

    restarted = ServiceRuntime.start(settings)
    try:
        op_a = restarted.import_store.get_operation(REPOSITORY_ID, OPERATION_ID)
        op_b = restarted.import_store.get_operation(REPOSITORY_B_ID, OPERATION_B_ID)
        assert op_a is not None and op_a.status == OperationStatus.SUCCEEDED
        assert op_b is not None and op_b.status == OperationStatus.SUCCEEDED
        assert restarted.is_ready()
    finally:
        restarted.shutdown()
