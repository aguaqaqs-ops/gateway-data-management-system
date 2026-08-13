"""Contract tests for shared cooperative cleanup entry points."""

from __future__ import annotations

import errno
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from gateway_repository_contracts import OperationStatus
from gateway_repository_service import artifact_cleanup
from gateway_repository_service.artifact_cleaner import ArtifactCleaner
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import IdempotencyKeyHash, MutationStore
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.upload_artifact.admission_pin import ArtifactAdmissionPin
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import import versioned_import_fingerprint_v1
from gateway_repository_service.versioned_import.command import ImportOperationExecutor
from gateway_repository_service.versioned_import.models import ImportArtifactBindingRejected
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
    binding,
    cleaner,
    enqueue,
    mark_succeeded_consumed,
    open_contract_stores,
    seed_artifact,
    seed_bytes_delete_intent,
    seed_create_succeeded,
    settings,
    write_ready,
)
from support.lifecycle_harness import lifecycle_settings
from support.recovery_harness import ready_client, replay_create
from support.upload_harness import upload_headers


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

    def fail_unlink(_name: str, *, dir_fd: int) -> None:
        del _name, dir_fd
        raise OSError(errno.EIO, "injected I/O failure")

    monkeypatch.setattr(artifact_cleanup, "_unlink_ready_name", fail_unlink)
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


def test_eligibility_is_reread_under_cleanup_pin(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    original = artifact_cleanup.cleanup_ready_artifact_bytes

    def wrapped(*args: object, **kwargs: object) -> str:
        enqueue(store, key="pending-after-precheck", operation_id=OPERATION_ID)
        return cast(Callable[..., str], original)(*args, **kwargs)

    monkeypatch.setattr(artifact_cleanup, "cleanup_ready_artifact_bytes", wrapped)
    cleaner(layout, store, mutation_store).sweep_once()
    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_leftover_intent_on_eligible_artifact_is_projected_and_stamped(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")
    st = ready.stat()
    seed_bytes_delete_intent(
        mutation_store,
        artifact_id=ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
    )
    before = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert before is not None
    assert before.bytes_delete_intent_at is not None

    cleaner(layout, store, mutation_store).sweep_once()

    assert not ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None
    assert lifecycle.bytes_delete_intent_at is None
    assert lifecycle.bytes_delete_dev is None
    assert lifecycle.bytes_delete_ino is None
    assert lifecycle.bytes_delete_phase is None
    assert lifecycle.bytes_delete_generation is None
    assert lifecycle.bytes_deleted_receipt_dev is None


def test_leftover_intent_on_protected_artifact_still_blocks_admission(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    enqueue(store, key="protected-pending", operation_id=OPERATION_ID)
    st = ready.stat()
    seed_bytes_delete_intent(
        mutation_store,
        artifact_id=ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
    )

    cleaner(layout, store, mutation_store).sweep_once()

    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    assert lifecycle.bytes_delete_intent_at is not None
    request = binding()
    key_hash = IdempotencyKeyHash.from_raw_key("second-admit")
    with pytest.raises(ImportArtifactBindingRejected, match="delete intent"):
        store.admit_new_import(
            request,
            key_hash=key_hash,
            fingerprint=versioned_import_fingerprint_v1(binding=request, key_hash=key_hash),
            max_queued_imports=8,
        )


@pytest.mark.integration
@pytest.mark.serial
def test_legal_ttl_delete_survives_restart_readiness(tmp_path: Path) -> None:
    runtime_settings = lifecycle_settings(tmp_path)
    runtime_settings = runtime_settings.model_copy(
        update={
            "artifact_ttl_seconds": 1,
            "artifact_cleanup_interval_seconds": 3600,
            "max_import_workers": 1,
        }
    )
    runtime = ServiceRuntime.start(runtime_settings)
    try:
        repository_id = UUID(
            str(replay_create(runtime, idempotency_key="cleanup-create").repository_id)
        )
        payload = b"cleanup-orphan-upload"
        headers = upload_headers(idempotency_key="cleanup-upload", payload=payload)
        with ready_client(runtime) as client:
            upload = client.post(
                f"/v1/repositories/{repository_id}/artifacts",
                headers=headers,
                content=payload,
            )
            assert upload.status_code == 201
            artifact_id = UUID(str(upload.json()["artifact_ref"]["artifact_id"]))

        past = (datetime.now(UTC) - timedelta(seconds=10)).replace(microsecond=0).isoformat()
        with runtime.mutation_store._lock:
            runtime.mutation_store._connection.execute(
                "UPDATE artifact_lifecycle SET created_at = ? WHERE artifact_id = ?",
                (past, str(artifact_id)),
            )
            runtime.mutation_store._connection.commit()

        instance = runtime.artifact_cleaner
        assert isinstance(instance, ArtifactCleaner)
        instance.notify()
        ready = artifact_ready_path(runtime.layout, repository_id, artifact_id)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and ready.exists():
            time.sleep(0.05)
        assert not ready.exists()
        lifecycle = runtime.mutation_store.get_artifact_lifecycle(artifact_id)
        assert lifecycle is not None and lifecycle.bytes_deleted_at is not None
        assert runtime.is_ready()
    finally:
        runtime.shutdown()

    restarted = ServiceRuntime.start(runtime_settings)
    try:
        assert restarted.is_ready()
    finally:
        restarted.shutdown()
