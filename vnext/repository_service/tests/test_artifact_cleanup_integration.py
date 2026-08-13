"""Contract tests for shared cooperative cleanup entry points."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from gateway_repository_contracts import OperationStatus
from gateway_repository_service import artifact_cleanup
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import MutationStore
from gateway_repository_service.upload_artifact.admission_pin import ArtifactAdmissionPin
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.command import ImportOperationExecutor
from gateway_repository_service.versioned_import.recovery import (
    cleanup_after_succeeded_correction,
)
from gateway_repository_service.versioned_import.store import ImportOperationStore
from support.artifact_cleanup_contract import (
    ARTIFACT_ID,
    ARTIFACT_PAYLOAD,
    OPERATION_ID,
    OTHER_ARTIFACT_ID,
    OTHER_OPERATION_ID,
    REPOSITORY_ID,
    SHA256,
    FakePrivateRefProvider,
    cleaner,
    mark_succeeded_consumed,
    open_contract_stores,
    seed_artifact,
    seed_create_succeeded,
    settings,
    write_ready,
)


@pytest.fixture
def layout(tmp_path: Path) -> DurableLayout:
    return DurableLayout.create_for_probe(tmp_path / "data-root")


@pytest.fixture
def stores(tmp_path: Path) -> tuple[ImportOperationStore, MutationStore]:
    return open_contract_stores(tmp_path)


def test_cleanup_failure_does_not_change_succeeded_result(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")
    before = store.get_operation(REPOSITORY_ID, OPERATION_ID)
    assert before is not None
    assert before.status is OperationStatus.SUCCEEDED
    assert before.result is not None
    result_before = before.result
    context = store.load_execution_context(OPERATION_ID)
    assert context is not None

    monkeypatch.setattr(
        artifact_cleanup,
        "try_unlink_ready_artifact_with_recheck",
        lambda *_args, **_kwargs: "unlink_failed",
    )
    ImportOperationExecutor(
        settings=settings(layout),
        layout=layout,
        store=store,
    )._best_effort_delete_artifact_bytes(context, ready)

    after = store.get_operation(REPOSITORY_ID, OPERATION_ID)
    assert after is not None
    assert after.status is OperationStatus.SUCCEEDED
    assert after.result == result_before
    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_worker_cleanup_deletes_eligible_ready_after_success(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")
    context = store.load_execution_context(OPERATION_ID)
    assert context is not None

    ImportOperationExecutor(
        settings=settings(layout),
        layout=layout,
        store=store,
    )._best_effort_delete_artifact_bytes(context, ready)

    after = store.get_operation(REPOSITORY_ID, OPERATION_ID)
    assert after is not None
    assert after.status is OperationStatus.SUCCEEDED
    assert after.result is not None
    assert not ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_admission_pin_blocks_shared_cleanup_entry(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")

    with ArtifactAdmissionPin(
        layout,
        REPOSITORY_ID,
        ARTIFACT_ID,
        size_bytes=len(ARTIFACT_PAYLOAD),
        raw_sha256=SHA256,
    ):
        cleaner(layout, store, mutation_store).sweep_once()
        assert ready.is_file()

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_worker_recovery_and_cleaner_share_cleanup_entry(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    hits: list[str] = []
    original = artifact_cleanup.cleanup_ready_artifact_bytes

    def wrapped(*args: object, **kwargs: object) -> str:
        hits.append("hit")
        return cast(Callable[..., str], original)(*args, **kwargs)

    monkeypatch.setattr(artifact_cleanup, "cleanup_ready_artifact_bytes", wrapped)

    cases = (
        (ARTIFACT_ID, OPERATION_ID, "share-worker"),
        (OTHER_ARTIFACT_ID, OTHER_OPERATION_ID, "share-recovery"),
        (UUID(int=ARTIFACT_ID.int + 2), UUID(int=OPERATION_ID.int + 2), "share-cleaner"),
    )
    paths: list[Path] = []
    for artifact_id, operation_id, key in cases:
        seed_artifact(mutation_store, artifact_id=artifact_id)
        paths.append(write_ready(layout, artifact_id=artifact_id))
        mark_succeeded_consumed(
            store,
            key=key,
            operation_id=operation_id,
            artifact_id=artifact_id,
        )

    context = store.load_execution_context(OPERATION_ID)
    assert context is not None
    ImportOperationExecutor(
        settings=settings(layout),
        layout=layout,
        store=store,
    )._best_effort_delete_artifact_bytes(context, paths[0])
    assert hits == ["hit"]
    assert not paths[0].exists()

    recovery_context = store.load_execution_context(OTHER_OPERATION_ID)
    assert recovery_context is not None
    cleanup_after_succeeded_correction(
        store=store,
        layout=layout,
        context=recovery_context,
        provider=FakePrivateRefProvider(),  # type: ignore[arg-type]
        candidate="commit-1",
        ttl_seconds=3600,
        tombstone_budget=50_000,
    )
    assert hits == ["hit", "hit"]
    assert not artifact_ready_path(layout, REPOSITORY_ID, OTHER_ARTIFACT_ID).exists()

    cleaner(layout, store, mutation_store).sweep_once()
    assert hits == ["hit", "hit", "hit"]
    assert not artifact_ready_path(
        layout,
        REPOSITORY_ID,
        UUID(int=ARTIFACT_ID.int + 2),
    ).exists()
