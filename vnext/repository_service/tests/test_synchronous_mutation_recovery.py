"""Fresh-process restart recovery matrix for synchronous create/upload mutations."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_contracts import REPOSITORY_IMPORT_MEDIA_TYPE
from gateway_repository_service.create_repository.visibility import is_repository_visible
from gateway_repository_service.http.errors import ServiceError
from gateway_repository_service.layout import repository_key
from gateway_repository_service.mutation_store import EffectStatus, IdempotencyScope
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path, is_artifact_visible
from support.lifecycle_harness import dolt_available
from support.recovery_harness import (
    CreateFaultPoint,
    UploadFaultPoint,
    assert_create_replay_conflict,
    assert_no_sensitive_leaks,
    assert_upload_replay_conflict,
    count_effects,
    create_repository_for_upload,
    effect_status,
    is_terminal_not_published,
    replay_create,
    replay_upload,
    restart_runtime,
    run_create_until_fault,
    run_upload_until_fault,
    staging_dirs_for_key,
    start_runtime,
    upload_staging_files,
)
from support.upload_harness import upload_sha256

pytestmark = pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")

CREATE_TERMINAL_POINTS: tuple[CreateFaultPoint, ...] = (
    "after_pending",
    "after_staging",
    "after_dolt_init",
    "before_rename",
)
UPLOAD_TERMINAL_POINTS: tuple[UploadFaultPoint, ...] = (
    "after_pending",
    "after_partial_body",
    "after_complete_close",
    "before_rename",
)


def _create_resource_id(runtime: ServiceRuntime, idempotency_key: str) -> UUID:
    key_hash = runtime.mutation_store.hash_idempotency_key(idempotency_key)
    row = runtime.mutation_store._connection.execute(
        """
        SELECT e.resource_id
        FROM synchronous_mutation_effects AS e
        JOIN mutation_idempotency AS i ON i.id = e.idempotency_id
        WHERE i.mutation_kind = 'create_repository'
          AND i.repository_scope = ''
          AND i.key_hash = ?
        """,
        (key_hash.digest,),
    ).fetchone()
    assert row is not None
    return UUID(str(row["resource_id"]))


def _upload_resource_id(runtime: ServiceRuntime, repository_id: UUID, idempotency_key: str) -> UUID:
    scope = IdempotencyScope.for_upload(repository_id)
    key_hash = runtime.mutation_store.hash_idempotency_key(idempotency_key)
    row = runtime.mutation_store._connection.execute(
        """
        SELECT e.resource_id
        FROM synchronous_mutation_effects AS e
        JOIN mutation_idempotency AS i ON i.id = e.idempotency_id
        WHERE i.mutation_kind = 'upload_artifact'
          AND i.repository_scope = ?
          AND i.key_hash = ?
        """,
        (scope.repository_scope(), key_hash.digest),
    ).fetchone()
    assert row is not None
    return UUID(str(row["resource_id"]))


@pytest.mark.parametrize("point", CREATE_TERMINAL_POINTS)
def test_create_restart_marks_terminal_not_published(tmp_path: Path, point: CreateFaultPoint) -> None:
    settings, runtime = start_runtime(tmp_path)
    idempotency_key = f"create-terminal-{point}"
    effect_count = 0
    try:
        run_create_until_fault(runtime, idempotency_key=idempotency_key, point=point)
        effect_count = count_effects(runtime.mutation_store)
        assert effect_count == 1
        repository_id = _create_resource_id(runtime, idempotency_key)
        runtime.shutdown()
        runtime = restart_runtime(settings)
        scope = IdempotencyScope.for_create()
        assert is_terminal_not_published(
            runtime.mutation_store,
            scope=scope,
            idempotency_key=idempotency_key,
        )
        assert effect_status(runtime.mutation_store, scope=scope, idempotency_key=idempotency_key) == (
            EffectStatus.PENDING
        )
        assert staging_dirs_for_key(runtime.layout, repository_id) == []
        assert not is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)
        assert runtime.is_ready()
        assert_create_replay_conflict(runtime, idempotency_key=idempotency_key)
        new_response = replay_create(runtime, idempotency_key=f"create-new-{point}")
        assert UUID(str(new_response.repository_id)) != repository_id
        assert count_effects(runtime.mutation_store) == effect_count + 1
    finally:
        runtime.shutdown()


def test_create_restart_reconciles_after_rename(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    idempotency_key = "create-after-rename"
    try:
        run_create_until_fault(runtime, idempotency_key=idempotency_key, point="after_rename")
        repository_id = _create_resource_id(runtime, idempotency_key)
        runtime.shutdown()
        runtime = restart_runtime(settings)
        scope = IdempotencyScope.for_create()
        assert effect_status(runtime.mutation_store, scope=scope, idempotency_key=idempotency_key) == (
            EffectStatus.SUCCEEDED
        )
        assert is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)
        assert runtime.is_ready()
        replayed = replay_create(runtime, idempotency_key=idempotency_key)
        published = runtime.layout.published_repository(repository_key(repository_id))
        assert published.is_dir()
        assert count_effects(runtime.mutation_store) == 1
        assert replayed.default_ref == "main"
        assert len(replayed.initial_commit_id) > 0
    finally:
        runtime.shutdown()


def test_create_restart_preserves_succeeded_response_loss(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    idempotency_key = "create-after-succeeded"
    try:
        run_create_until_fault(runtime, idempotency_key=idempotency_key, point="after_succeeded")
        repository_id = _create_resource_id(runtime, idempotency_key)
        runtime.shutdown()
        runtime = restart_runtime(settings)
        scope = IdempotencyScope.for_create()
        assert effect_status(runtime.mutation_store, scope=scope, idempotency_key=idempotency_key) == (
            EffectStatus.SUCCEEDED
        )
        replayed = replay_create(runtime, idempotency_key=idempotency_key)
        assert UUID(str(replayed.repository_id)) == repository_id
        assert is_repository_visible(runtime.mutation_store, runtime.layout, repository_id)
        assert runtime.is_ready()
        assert count_effects(runtime.mutation_store) == 1
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("point", UPLOAD_TERMINAL_POINTS)
def test_upload_restart_marks_terminal_not_published(tmp_path: Path, point: UploadFaultPoint) -> None:
    settings, runtime = start_runtime(tmp_path)
    repository_id = create_repository_for_upload(runtime)
    payload = f"upload-terminal-{point}".encode()
    idempotency_key = f"upload-terminal-{point}"
    effect_count = 0
    try:
        asyncio.run(
            run_upload_until_fault(
                runtime,
                repository_id=repository_id,
                idempotency_key=idempotency_key,
                payload=payload,
                point=point,
            )
        )
        effect_count = count_effects(runtime.mutation_store)
        artifact_id = _upload_resource_id(runtime, repository_id, idempotency_key)
        runtime.shutdown()
        runtime = restart_runtime(settings)
        scope = IdempotencyScope.for_upload(repository_id)
        assert is_terminal_not_published(
            runtime.mutation_store,
            scope=scope,
            idempotency_key=idempotency_key,
        )
        assert effect_status(runtime.mutation_store, scope=scope, idempotency_key=idempotency_key) == (
            EffectStatus.PENDING
        )
        assert upload_staging_files(runtime.layout, repository_id, artifact_id) == []
        ready_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        assert not ready_path.exists()
        assert not is_artifact_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            artifact_id,
            size_bytes=len(payload),
            raw_sha256=upload_sha256(payload),
        )
        assert runtime.is_ready()
        asyncio.run(
            assert_upload_replay_conflict(
                runtime,
                repository_id=repository_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        )
        new_response = asyncio.run(
            replay_upload(
                runtime,
                repository_id=repository_id,
                idempotency_key=f"upload-new-{point}",
                payload=payload,
            )
        )
        assert UUID(str(new_response.artifact_ref.artifact_id)) != artifact_id
        assert count_effects(runtime.mutation_store) == effect_count + 1
    finally:
        runtime.shutdown()


def test_upload_restart_reconciles_after_rename(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    repository_id = create_repository_for_upload(runtime)
    payload = b"upload-after-rename"
    idempotency_key = "upload-after-rename"
    try:
        asyncio.run(
            run_upload_until_fault(
                runtime,
                repository_id=repository_id,
                idempotency_key=idempotency_key,
                payload=payload,
                point="after_rename",
            )
        )
        artifact_id = _upload_resource_id(runtime, repository_id, idempotency_key)
        runtime.shutdown()
        runtime = restart_runtime(settings)
        scope = IdempotencyScope.for_upload(repository_id)
        assert effect_status(runtime.mutation_store, scope=scope, idempotency_key=idempotency_key) == (
            EffectStatus.SUCCEEDED
        )
        ready_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        assert ready_path.read_bytes() == payload
        assert is_artifact_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            artifact_id,
            size_bytes=len(payload),
            raw_sha256=upload_sha256(payload),
        )
        assert runtime.is_ready()
        replayed = asyncio.run(
            replay_upload(
                runtime,
                repository_id=repository_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        )
        assert UUID(str(replayed.artifact_ref.artifact_id)) == artifact_id
        assert count_effects(runtime.mutation_store) == 2
    finally:
        runtime.shutdown()


def test_upload_restart_preserves_succeeded_response_loss(tmp_path: Path) -> None:
    settings, runtime = start_runtime(tmp_path)
    repository_id = create_repository_for_upload(runtime)
    payload = b"upload-after-succeeded"
    idempotency_key = "upload-after-succeeded"
    try:
        asyncio.run(
            run_upload_until_fault(
                runtime,
                repository_id=repository_id,
                idempotency_key=idempotency_key,
                payload=payload,
                point="after_succeeded",
            )
        )
        artifact_id = _upload_resource_id(runtime, repository_id, idempotency_key)
        runtime.shutdown()
        runtime = restart_runtime(settings)
        replayed = asyncio.run(
            replay_upload(
                runtime,
                repository_id=repository_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
        )
        assert UUID(str(replayed.artifact_ref.artifact_id)) == artifact_id
        assert replayed.artifact_ref.media_type == REPOSITORY_IMPORT_MEDIA_TYPE
        assert replayed.artifact_ref.size_bytes == len(payload)
        assert replayed.artifact_ref.raw_sha256 == upload_sha256(payload)
        assert runtime.is_ready()
        assert count_effects(runtime.mutation_store) == 2
    finally:
        runtime.shutdown()


def test_recovery_errors_do_not_leak_sensitive_values(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings, runtime = start_runtime(tmp_path)
    idempotency_key = "sensitive-create-key"
    token = "test-bearer-token"
    data_root = str(settings.data_root)
    try:
        with caplog.at_level("ERROR"):
            run_create_until_fault(runtime, idempotency_key=idempotency_key, point="after_pending")
        with pytest.raises(ServiceError) as exc_info:
            replay_create(runtime, idempotency_key=idempotency_key)
        combined = caplog.text + str(exc_info.value)
        assert_no_sensitive_leaks(
            combined,
            idempotency_key=idempotency_key,
            token=token,
            data_root=data_root,
            payload="",
        )
    finally:
        runtime.shutdown()
