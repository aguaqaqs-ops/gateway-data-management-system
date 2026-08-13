"""Readiness failure tests for SUCCEEDED mutation and filesystem contradictions."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from gateway_repository_service.create_repository.visibility import is_repository_visible
from gateway_repository_service.layout import repository_key
from gateway_repository_service.mutation_store import EffectStatus, IdempotencyScope
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.upload_artifact import visibility as upload_visibility
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path, is_artifact_visible
from support.lifecycle_harness import lifecycle_settings
from support.recovery_harness import (
    crash_create_subprocess,
    effect_status,
    get_create_resource_id,
    ready_client,
    replay_create,
    restart_runtime,
    start_runtime,
)
from support.upload_harness import upload_headers, upload_sha256

pytestmark = pytest.mark.integration


def test_readiness_fails_when_succeeded_create_repository_missing(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    try:
        response = replay_create(runtime, idempotency_key="readiness-create")
        repository_id = UUID(str(response.repository_id))
        assert runtime.is_ready()
        published = runtime.layout.published_repository(repository_key(repository_id))
        shutil.rmtree(published)
        assert not is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)
        assert not runtime.is_ready()
        with ready_client(runtime) as client:
            ready = client.get("/readyz")
            assert ready.status_code == 503
            assert "inconsistent" in ready.json()["message"]
    finally:
        runtime.shutdown()


def test_startup_marks_unreadable_create_head_inconsistent(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    try:
        response = replay_create(runtime, idempotency_key="startup-head-unreadable")
        repository_id = UUID(str(response.repository_id))
        published = runtime.layout.published_repository(repository_key(repository_id))
        shutil.rmtree(published / ".dolt")
        (published / ".dolt").mkdir()
    finally:
        runtime.shutdown()

    restarted = ServiceRuntime.start(settings)
    try:
        assert restarted.reconciliation_failures
        assert not restarted.is_ready()
    finally:
        restarted.shutdown()


def test_readiness_fails_when_succeeded_upload_artifact_missing(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    payload = b"readiness-upload"
    try:
        repository_id = UUID(str(replay_create(runtime, idempotency_key="readiness-upload-create").repository_id))
        headers = upload_headers(idempotency_key="readiness-upload", payload=payload)
        with ready_client(runtime) as client:
            upload = client.post(
                f"/v1/repositories/{repository_id}/artifacts",
                headers=headers,
                content=payload,
            )
            assert upload.status_code == 201
            artifact_id = UUID(upload.json()["artifact_ref"]["artifact_id"])
        assert runtime.is_ready()
        ready_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        ready_path.unlink()
        assert not is_artifact_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            artifact_id,
            size_bytes=len(payload),
            raw_sha256=upload_sha256(payload),
        )
        assert not runtime.is_ready()
        with ready_client(runtime) as client:
            ready = client.get("/readyz")
            assert ready.status_code == 503
    finally:
        runtime.shutdown()


def test_readiness_bounded_probe_does_not_rehash_artifacts(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    payload = b"readiness-no-rehash"
    try:
        repository_id = UUID(str(replay_create(runtime, idempotency_key="readiness-no-rehash-create").repository_id))
        headers = upload_headers(idempotency_key="readiness-no-rehash-upload", payload=payload)
        with ready_client(runtime) as client:
            upload = client.post(
                f"/v1/repositories/{repository_id}/artifacts",
                headers=headers,
                content=payload,
            )
            assert upload.status_code == 201
        with patch.object(
            upload_visibility,
            "has_published_artifact_file",
            wraps=upload_visibility.has_published_artifact_file,
        ) as full_check:
            assert runtime.is_ready()
            with ready_client(runtime) as client:
                for _ in range(3):
                    assert client.get("/readyz").status_code == 200
            full_check.assert_not_called()
    finally:
        runtime.shutdown()


def test_readiness_probe_does_not_invoke_dolt_cli_or_scan_ledger(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    try:
        replay_create(runtime, idempotency_key="readiness-no-cli")
        with patch.object(
            OfflineCliProvider,
            "head",
            wraps=OfflineCliProvider.head,
        ) as head_spy, patch.object(
            runtime.mutation_store,
            "iter_effects_by_status",
            wraps=runtime.mutation_store.iter_effects_by_status,
        ) as ledger_spy:
            head_spy.reset_mock()
            ledger_spy.reset_mock()
            with ready_client(runtime) as client:
                for _ in range(3):
                    assert client.get("/readyz").status_code == 200
            head_spy.assert_not_called()
            ledger_spy.assert_not_called()
    finally:
        runtime.shutdown()


def test_create_remains_consistent_after_main_advances(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    try:
        response = replay_create(runtime, idempotency_key="advanced-main")
        repository_id = UUID(str(response.repository_id))
        initial_commit_id = response.initial_commit_id
        published = runtime.layout.published_repository(repository_key(repository_id))
        runner = DoltRunner(runtime.settings, runtime.layout.root)
        provider = OfflineCliProvider(runtime.settings, runtime.layout, published, runner)
        advance_sql = tmp_path / "advance-main.sql"
        advance_sql.write_text(
            "CREATE TABLE advance_probe (id INT NOT NULL PRIMARY KEY);",
            encoding="utf-8",
        )
        provider.replay(advance_sql)
        provider.commit_marker("advance-main")
        assert provider.head() != initial_commit_id
        assert provider.commit_reachable_from_main(initial_commit_id)
    finally:
        runtime.shutdown()

    restarted = restart_runtime(settings)
    try:
        assert is_repository_visible(restarted.mutation_store, restarted.layout, repository_id)
        assert restarted.is_ready()
    finally:
        restarted.shutdown()


def test_startup_marks_bad_initial_commit_inconsistent(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    try:
        response = replay_create(runtime, idempotency_key="startup-bad-initial-check")
        repository_id = UUID(str(response.repository_id))
        runtime.control_store.connection.execute(
            """
            UPDATE synchronous_mutation_effects
            SET response_body = ?
            WHERE resource_id = ?
            """,
            (
                json.dumps(
                    {
                        "repository_id": str(repository_id),
                        "default_ref": "main",
                        "initial_commit_id": "deadbeefdeadbeefdeadbeefdeadbeef",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                str(repository_id),
            ),
        )
        runtime.control_store.connection.commit()
    finally:
        runtime.shutdown()

    restarted = ServiceRuntime.start(settings)
    try:
        assert restarted.reconciliation_failures
        assert not restarted.is_ready()
    finally:
        restarted.shutdown()


def test_readiness_recovers_after_pending_create_reconciled(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    idempotency_key = "readiness-reconcile-create"
    crash_create_subprocess(settings, idempotency_key=idempotency_key, point="after_rename")
    repository_id = get_create_resource_id(settings, idempotency_key)
    runtime = restart_runtime(settings)
    try:
        assert effect_status(
            runtime.mutation_store,
            scope=IdempotencyScope.for_create(),
            idempotency_key=idempotency_key,
        ) == EffectStatus.SUCCEEDED
        assert is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)
        assert runtime.is_ready()
        with ready_client(runtime) as client:
            ready = client.get("/readyz")
            assert ready.status_code == 200
    finally:
        runtime.shutdown()


@pytest.mark.integration
@pytest.mark.serial
def test_consumed_artifact_missing_bytes_does_not_block_readiness(tmp_path: Path) -> None:
    import time

    from gateway_repository_contracts import OperationStatus, RepositoryArtifactRef, UnknownTypePolicy, VerificationPolicy
    from gateway_repository_service.mutation_store import IdempotencyKeyHash
    from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
    from gateway_repository_service.versioned_import import ImportRequestBinding, versioned_import_fingerprint_v1
    from support.import_worker_harness import MEDIA_TYPE
    from test_import_package import build_package_bytes, write_artifact

    settings, runtime = start_runtime(tmp_path)
    try:
        create = replay_create(runtime, idempotency_key="consumed-artifact-create")
        repository_id = UUID(str(create.repository_id))
        expected_commit = create.initial_commit_id
        artifact_id = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c12")
        operation_id = UUID("018f0f3e-7b0a-7c17-8a9e-2e4b9f4d2c12")
        replay_sql = (
            "CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\n"
            "INSERT INTO records (id) VALUES (1);\n"
        )
        manifest = {
            "package_version": 1,
            "canonicalization_manifest_digest": "manifest-digest-readiness",
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
        ready_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        size_bytes, raw_sha256 = write_artifact(ready_path, payload)
        now = "2026-08-06T00:00:00+00:00"
        runtime.import_store.mutation_store._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id, repository_scope, media_type, size_bytes, raw_sha256, created_at, updated_at
            , cleanup_seq) VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle))
            """,
            (str(artifact_id), repository_id.hex, MEDIA_TYPE, size_bytes, raw_sha256, now, now),
        )
        runtime.import_store.mutation_store._connection.commit()
        runtime.register_succeeded_upload(repository_id, artifact_id, size_bytes)

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
        key_hash = IdempotencyKeyHash.from_raw_key("consumed-artifact-import")
        fingerprint = versioned_import_fingerprint_v1(binding=binding, key_hash=key_hash)
        runtime.import_store.claim_or_enqueue(
            binding,
            key_hash=key_hash,
            fingerprint=fingerprint,
            operation_id=operation_id,
        )
        runtime.import_worker_pool.notify()
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            operation = runtime.import_store.get_operation(repository_id, operation_id)
            if operation is not None and operation.status == OperationStatus.SUCCEEDED:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("import did not succeed")

        from gateway_repository_service.artifact_cleaner import ArtifactCleaner

        cleaner = runtime.artifact_cleaner
        if isinstance(cleaner, ArtifactCleaner):
            cleaner.sweep_once()
        if ready_path.exists():
            ready_path.unlink()
        assert runtime.is_ready()
    finally:
        runtime.shutdown()

    restarted = restart_runtime(settings)
    try:
        assert not restarted.reconciliation_failures
        assert restarted.is_ready()
    finally:
        restarted.shutdown()
