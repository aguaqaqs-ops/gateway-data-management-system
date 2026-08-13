"""Contract tests for the cooperative artifact cleaner."""

from __future__ import annotations

import os
import stat
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import MutationStore
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.store import ImportOperationStore
from support.artifact_cleanup_contract import (
    ARTIFACT_ID,
    CREATED_AT,
    OPERATION_ID,
    OTHER_ARTIFACT_ID,
    OTHER_REPOSITORY_ID,
    REPOSITORY_ID,
    cleaner,
    mark_succeeded_consumed,
    open_contract_stores,
    seed_artifact,
    seed_create_succeeded,
    write_ready,
)


@pytest.fixture
def layout(tmp_path: Path) -> DurableLayout:
    return DurableLayout.create_for_probe(tmp_path / "data-root")


@pytest.fixture
def stores(tmp_path: Path) -> tuple[ImportOperationStore, MutationStore]:
    return open_contract_stores(tmp_path)


def test_eligible_exact_ready_is_deleted(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")

    cleaner(layout, store, mutation_store).sweep_once()

    assert not ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_eligible_absent_is_idempotent_without_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="ok")
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    assert not ready.exists()

    cleaner(layout, store, mutation_store).sweep_once()

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_ineligible_absent_is_not_washed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_artifact(mutation_store, created_at=CREATED_AT)
    ready = write_ready(layout)
    ready.unlink()

    cleaner(layout, store, mutation_store, ttl=3600).sweep_once()

    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_symlink_is_retained_without_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="ok")
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    ready.symlink_to(ready.parent / "missing-target")

    cleaner(layout, store, mutation_store).sweep_once()

    assert ready.is_symlink()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_fifo_is_retained_without_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="ok")
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(ready, 0o644)
    assert stat.S_ISFIFO(ready.lstat().st_mode)

    cleaner(layout, store, mutation_store).sweep_once()

    assert ready.exists()
    assert stat.S_ISFIFO(ready.lstat().st_mode)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_unknown_and_cross_repository_entries_are_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")
    unknown = ready.parent / "not-a-uuid"
    unknown.write_bytes(b"unknown")
    foreign = write_ready(
        layout,
        artifact_id=OTHER_ARTIFACT_ID,
        repository_id=OTHER_REPOSITORY_ID,
    )

    cleaner(layout, store, mutation_store).sweep_once()

    assert not ready.exists()
    assert unknown.is_file()
    assert foreign.is_file()


def test_io_failure_retains_and_retries_after_cleared(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")
    calls = {"n": 0}
    import gateway_repository_service.artifact_cleanup as cleanup_mod

    original = cleanup_mod.try_unlink_ready_artifact_with_recheck

    def fail_once(*args: object, **kwargs: object) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "unlink_failed"
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cleanup_mod, "try_unlink_ready_artifact_with_recheck", fail_once)
    instance = cleaner(layout, store, mutation_store)
    instance.sweep_once()
    assert ready.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None

    instance.sweep_once()
    assert not ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_notify_restarts_cursor_so_low_seq_success_is_not_starved(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    created = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=10)
    created_at = created.isoformat()
    clock = {"now": created + timedelta(seconds=1)}
    ids = [UUID(int=ARTIFACT_ID.int + i) for i in range(70)]
    for aid in ids:
        seed_artifact(mutation_store, artifact_id=aid, created_at=created_at)
        write_ready(layout, artifact_id=aid)
    instance = cleaner(
        layout,
        store,
        mutation_store,
        clock=lambda: clock["now"],
    )
    instance.sweep_once()
    assert instance._cleanup_cursor is not None  # noqa: SLF001
    for aid in ids:
        assert artifact_ready_path(layout, REPOSITORY_ID, aid).is_file()
    low_id = ids[0]
    mark_succeeded_consumed(
        store,
        key="notify-low-seq",
        operation_id=UUID(int=OPERATION_ID.int + 1000),
        artifact_id=low_id,
    )
    clock["now"] = datetime.now(UTC) + timedelta(seconds=1)
    decision = store.evaluate_artifact_bytes_deletion(
        low_id,
        now=clock["now"],
        ttl_seconds=3600,
    )
    assert decision.eligible, (decision.reason, decision.earliest_eligible_at)
    instance.notify()
    instance.sweep_once()
    assert not artifact_ready_path(layout, REPOSITORY_ID, low_id).exists()
    for aid in ids[1:]:
        assert artifact_ready_path(layout, REPOSITORY_ID, aid).is_file()


def test_poison_row_does_not_starve_later_candidate(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    poison_id = uuid4()
    with mutation_store._lock:
        mutation_store._connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id,
                repository_scope,
                media_type,
                size_bytes,
                raw_sha256,
                created_at,
                updated_at,
                cleanup_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, (
                SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle
            ))
            """,
            (
                str(poison_id),
                "not-a-uuid",
                "application/vnd.gateway.repository-import.v1+tar+zstd",
                1,
                "a" * 64,
                CREATED_AT,
                CREATED_AT,
            ),
        )
        mutation_store._connection.commit()
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")

    cleaner(layout, store, mutation_store).sweep_once()
    assert not ready.exists()


def test_startup_reclaim_deletes_expired_orphans(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    ids = [UUID(int=ARTIFACT_ID.int + i) for i in range(70)]
    for aid in ids:
        seed_artifact(mutation_store, artifact_id=aid, created_at=CREATED_AT)
        write_ready(layout, artifact_id=aid)
    instance = cleaner(layout, store, mutation_store, ttl=60)

    def admitted() -> bool:
        return not any(
            artifact_ready_path(layout, REPOSITORY_ID, aid).exists() for aid in ids
        )

    instance.reclaim_until_disk_admission(admitted=admitted)
    assert admitted()


@pytest.mark.serial
def test_shutdown_leaves_no_cleaner_thread(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    instance = cleaner(layout, store, mutation_store, interval=60)
    instance.start()
    thread = instance._thread  # noqa: SLF001
    assert thread is not None and thread.is_alive()
    instance.stop(timeout=2.0)
    assert not thread.is_alive()
    instance.stop(timeout=1.0)


@pytest.mark.serial
def test_cleanup_retries_after_notification(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, mutation_store = stores
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    first_failure = threading.Event()
    calls = {"n": 0}
    import gateway_repository_service.artifact_cleanup as cleanup_mod

    original = cleanup_mod.try_unlink_ready_artifact_with_recheck

    def fail_once(*args: object, **kwargs: object) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            first_failure.set()
            return "unlink_failed"
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cleanup_mod, "try_unlink_ready_artifact_with_recheck", fail_once)
    instance = cleaner(layout, store, mutation_store, ttl=1, interval=3600)
    instance.start()
    try:
        assert first_failure.wait(timeout=2.0)
        assert ready.is_file()
        instance.notify()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and ready.exists():
            time.sleep(0.01)
        assert not ready.exists()
    finally:
        instance.stop(timeout=2.0)
