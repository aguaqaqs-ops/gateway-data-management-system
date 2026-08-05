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
from support.lifecycle_harness import dolt_available, lifecycle_settings
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

pytestmark = pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")


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
