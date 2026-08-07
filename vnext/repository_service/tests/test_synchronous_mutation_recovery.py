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
from support.upload_harness import upload_sha256
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path, is_artifact_visible
from support.lifecycle_harness import lifecycle_settings
from support.recovery_harness import (
    CreateFaultPoint,
    UploadFaultPoint,
    assert_create_crash_disk_evidence,
    assert_create_replay_conflict,
    assert_no_sensitive_leaks,
    assert_upload_crash_disk_evidence,
    assert_upload_replay_conflict,
    count_effects,
    crash_create_subprocess,
    crash_upload_subprocess,
    effect_status,
    get_create_resource_id,
    get_upload_resource_id,
    is_terminal_not_published,
    open_mutation_store,
    replay_create,
    replay_upload,
    restart_runtime,
    setup_repository_for_upload,
    staging_dirs_for_key,
    upload_staging_files,
)

pytestmark = pytest.mark.integration

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


@pytest.mark.parametrize("point", CREATE_TERMINAL_POINTS)
def test_create_restart_marks_terminal_not_published(tmp_path: Path, point: CreateFaultPoint) -> None:
    settings = lifecycle_settings(tmp_path)
    idempotency_key = f"create-terminal-{point}"
    crash_create_subprocess(settings, idempotency_key=idempotency_key, point=point)
    repository_id = get_create_resource_id(settings, idempotency_key)
    assert_create_crash_disk_evidence(
        settings,
        repository_id=repository_id,
        idempotency_key=idempotency_key,
        point=point,
    )
    store = open_mutation_store(settings)
    try:
        effect_count = count_effects(store)
        assert effect_count == 1
    finally:
        store._connection.close()

    runtime = restart_runtime(settings)
    try:
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
        assert not is_repository_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            settings=runtime.settings,
        )
        assert runtime.is_ready()
        assert_create_replay_conflict(runtime, idempotency_key=idempotency_key)
        new_response = replay_create(runtime, idempotency_key=f"create-new-{point}")
        assert UUID(str(new_response.repository_id)) != repository_id
        assert count_effects(runtime.mutation_store) == effect_count + 1
    finally:
        runtime.shutdown()


def test_create_restart_reconciles_after_rename(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    idempotency_key = "create-after-rename"
    crash_create_subprocess(settings, idempotency_key=idempotency_key, point="after_rename")
    repository_id = get_create_resource_id(settings, idempotency_key)
    assert_create_crash_disk_evidence(
        settings,
        repository_id=repository_id,
        idempotency_key=idempotency_key,
        point="after_rename",
    )

    runtime = restart_runtime(settings)
    try:
        scope = IdempotencyScope.for_create()
        assert effect_status(runtime.mutation_store, scope=scope, idempotency_key=idempotency_key) == (
            EffectStatus.SUCCEEDED
        )
        assert is_repository_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            settings=runtime.settings,
        )
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
    settings = lifecycle_settings(tmp_path)
    idempotency_key = "create-after-succeeded"
    crash_create_subprocess(settings, idempotency_key=idempotency_key, point="after_succeeded")
    repository_id = get_create_resource_id(settings, idempotency_key)
    assert_create_crash_disk_evidence(
        settings,
        repository_id=repository_id,
        idempotency_key=idempotency_key,
        point="after_succeeded",
    )

    runtime = restart_runtime(settings)
    try:
        scope = IdempotencyScope.for_create()
        assert effect_status(runtime.mutation_store, scope=scope, idempotency_key=idempotency_key) == (
            EffectStatus.SUCCEEDED
        )
        replayed = replay_create(runtime, idempotency_key=idempotency_key)
        assert UUID(str(replayed.repository_id)) == repository_id
        assert is_repository_visible(
            runtime.mutation_store,
            runtime.layout,
            repository_id,
            settings=runtime.settings,
        )
        assert runtime.is_ready()
        assert count_effects(runtime.mutation_store) == 1
    finally:
        runtime.shutdown()


@pytest.mark.parametrize("point", UPLOAD_TERMINAL_POINTS)
def test_upload_restart_marks_terminal_not_published(tmp_path: Path, point: UploadFaultPoint) -> None:
    settings = lifecycle_settings(tmp_path)
    repository_id = setup_repository_for_upload(settings)
    payload = f"upload-terminal-{point}".encode()
    idempotency_key = f"upload-terminal-{point}"
    crash_upload_subprocess(
        settings,
        repository_id=repository_id,
        idempotency_key=idempotency_key,
        payload=payload,
        point=point,
    )
    artifact_id = get_upload_resource_id(settings, repository_id, idempotency_key)
    assert_upload_crash_disk_evidence(
        settings,
        repository_id=repository_id,
        artifact_id=artifact_id,
        payload=payload,
        point=point,
    )
    store = open_mutation_store(settings)
    try:
        effect_count = count_effects(store)
    finally:
        store._connection.close()

    runtime = restart_runtime(settings)
    try:
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
    settings = lifecycle_settings(tmp_path)
    repository_id = setup_repository_for_upload(settings)
    payload = b"upload-after-rename"
    idempotency_key = "upload-after-rename"
    crash_upload_subprocess(
        settings,
        repository_id=repository_id,
        idempotency_key=idempotency_key,
        payload=payload,
        point="after_rename",
    )
    artifact_id = get_upload_resource_id(settings, repository_id, idempotency_key)
    assert_upload_crash_disk_evidence(
        settings,
        repository_id=repository_id,
        artifact_id=artifact_id,
        payload=payload,
        point="after_rename",
    )

    runtime = restart_runtime(settings)
    try:
        scope = IdempotencyScope.for_upload(repository_id)
        assert effect_status(runtime.mutation_store, scope=scope, idempotency_key=idempotency_key) == (
            EffectStatus.SUCCEEDED
        )
        ready_path = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        assert ready_path.read_bytes() == payload
        from support.upload_harness import upload_sha256

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
    settings = lifecycle_settings(tmp_path)
    repository_id = setup_repository_for_upload(settings)
    payload = b"upload-after-succeeded"
    idempotency_key = "upload-after-succeeded"
    crash_upload_subprocess(
        settings,
        repository_id=repository_id,
        idempotency_key=idempotency_key,
        payload=payload,
        point="after_succeeded",
    )
    artifact_id = get_upload_resource_id(settings, repository_id, idempotency_key)
    assert_upload_crash_disk_evidence(
        settings,
        repository_id=repository_id,
        artifact_id=artifact_id,
        payload=payload,
        point="after_succeeded",
    )

    runtime = restart_runtime(settings)
    try:
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
        from support.upload_harness import upload_sha256

        assert replayed.artifact_ref.raw_sha256 == upload_sha256(payload)
        assert runtime.is_ready()
        assert count_effects(runtime.mutation_store) == 2
    finally:
        runtime.shutdown()


def test_recovery_errors_do_not_leak_sensitive_values(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    idempotency_key = "sensitive-create-key"
    token = "test-bearer-token"
    data_root = str(settings.data_root)
    crash_create_subprocess(settings, idempotency_key=idempotency_key, point="after_pending")
    runtime = restart_runtime(settings)
    try:
        with pytest.raises(ServiceError) as exc_info:
            replay_create(runtime, idempotency_key=idempotency_key)
        assert_no_sensitive_leaks(
            str(exc_info.value),
            idempotency_key=idempotency_key,
            token=token,
            data_root=data_root,
            payload="",
        )
    finally:
        runtime.shutdown()
