"""Readiness failure tests for SUCCEEDED mutation and filesystem contradictions."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from gateway_repository_service.create_repository.visibility import is_repository_visible
from gateway_repository_service.layout import repository_key
from gateway_repository_service.mutation_store import EffectStatus, IdempotencyScope
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
        assert not is_repository_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            settings=runtime.settings,
        )
        assert not runtime.is_ready()
        with ready_client(runtime) as client:
            ready = client.get("/readyz")
            assert ready.status_code == 503
            assert "inconsistent" in ready.json()["message"]
    finally:
        runtime.shutdown()


def test_readiness_fails_when_succeeded_create_head_mismatches_ledger(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    try:
        response = replay_create(runtime, idempotency_key="readiness-head-mismatch")
        repository_id = UUID(str(response.repository_id))
        published = runtime.layout.published_repository(repository_key(repository_id))
        shutil.rmtree(published / ".dolt")
        (published / ".dolt").mkdir()
        assert not is_repository_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            settings=runtime.settings,
        )
        assert not runtime.is_ready()
    finally:
        runtime.shutdown()


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
        assert is_repository_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            settings=runtime.settings,
        )
        assert runtime.is_ready()
        with ready_client(runtime) as client:
            ready = client.get("/readyz")
            assert ready.status_code == 200
    finally:
        runtime.shutdown()
