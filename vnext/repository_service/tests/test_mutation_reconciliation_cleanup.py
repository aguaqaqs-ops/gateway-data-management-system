"""Negative reconciliation tests for fail-closed staging cleanup."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from gateway_repository_service.create_repository.visibility import has_published_repository_tree
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import EffectStatus, IdempotencyScope
from gateway_repository_service.providers import ProviderError
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from support.lifecycle_harness import lifecycle_settings
from support.recovery_harness import (
    crash_create_subprocess,
    effect_status,
    get_create_resource_id,
    is_terminal_not_published,
    open_mutation_store,
    staging_dirs_for_key,
)

pytestmark = pytest.mark.integration


def test_startup_fails_when_create_staging_cleanup_fails(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    idempotency_key = "cleanup-fail-create"
    crash_create_subprocess(settings, idempotency_key=idempotency_key, point="after_staging")
    repository_id = get_create_resource_id(settings, idempotency_key)
    layout = DurableLayout.create_service(settings.data_root)
    assert staging_dirs_for_key(layout, repository_id)

    with patch.object(shutil, "rmtree", side_effect=OSError("cleanup denied")):
        with pytest.raises(ServiceStartupError):
            ServiceRuntime.start(settings)

    store = open_mutation_store(settings)
    try:
        scope = IdempotencyScope.for_create()
        assert effect_status(store, scope=scope, idempotency_key=idempotency_key) == EffectStatus.PENDING
        assert not is_terminal_not_published(store, scope=scope, idempotency_key=idempotency_key)
    finally:
        store._connection.close()
    assert staging_dirs_for_key(layout, repository_id)


def test_startup_fails_when_upload_staging_cleanup_fails(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    from support.recovery_harness import (
        crash_upload_subprocess,
        get_upload_resource_id,
        setup_repository_for_upload,
        upload_staging_files,
    )

    repository_id = setup_repository_for_upload(settings)
    payload = b"cleanup-fail-upload"
    idempotency_key = "cleanup-fail-upload"
    crash_upload_subprocess(
        settings,
        repository_id=repository_id,
        idempotency_key=idempotency_key,
        payload=payload,
        point="after_partial_body",
    )
    artifact_id = get_upload_resource_id(settings, repository_id, idempotency_key)
    layout = DurableLayout.create_service(settings.data_root)
    assert upload_staging_files(layout, repository_id, artifact_id)

    with patch.object(Path, "unlink", side_effect=OSError("cleanup denied")):
        with pytest.raises(ServiceStartupError):
            ServiceRuntime.start(settings)

    store = open_mutation_store(settings)
    try:
        scope = IdempotencyScope.for_upload(repository_id)
        assert effect_status(store, scope=scope, idempotency_key=idempotency_key) == EffectStatus.PENDING
        assert not is_terminal_not_published(store, scope=scope, idempotency_key=idempotency_key)
    finally:
        store._connection.close()


def test_startup_fails_when_pending_create_head_read_fails(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    idempotency_key = "pending-head-read-fail"
    crash_create_subprocess(settings, idempotency_key=idempotency_key, point="after_rename")
    repository_id = get_create_resource_id(settings, idempotency_key)
    layout = DurableLayout.create_service(settings.data_root)
    assert has_published_repository_tree(layout, repository_id)

    with patch(
        "gateway_repository_service.create_repository.visibility.OfflineCliProvider.head",
        side_effect=ProviderError("dolt head read failed"),
    ):
        with pytest.raises(ServiceStartupError):
            ServiceRuntime.start(settings)

    store = open_mutation_store(settings)
    try:
        scope = IdempotencyScope.for_create()
        assert effect_status(store, scope=scope, idempotency_key=idempotency_key) == EffectStatus.PENDING
        assert not is_terminal_not_published(store, scope=scope, idempotency_key=idempotency_key)
    finally:
        store._connection.close()
    assert has_published_repository_tree(layout, repository_id)
