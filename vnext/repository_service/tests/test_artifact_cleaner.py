"""Contract tests for the cooperative artifact cleaner."""

from __future__ import annotations

import errno
import fcntl
import os
import re
import stat
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_service.artifact_cleaner import (
    ArtifactCleaner,
    ArtifactCleanerShutdownError,
    classify_ready_artifact_path,
    _HousekeepingBudget,
)
from gateway_repository_service.artifact_retention import retention_explains_missing_ready_bytes
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import ArtifactLifecycleRecord, MutationStore
from gateway_repository_service.upload_artifact.admission_pin import (
    OwnedPathError,
    open_owned_ready_dir,
)
from gateway_repository_service.upload_artifact.visibility import artifact_ready_path
from gateway_repository_service.versioned_import.store import ImportOperationStore
from support.artifact_cleanup_contract import (
    ARTIFACT_ID,
    ARTIFACT_PAYLOAD,
    BASE_NOW,
    CREATED_AT,
    OPERATION_ID,
    OTHER_ARTIFACT_ID,
    OTHER_OPERATION_ID,
    OTHER_REPOSITORY_ID,
    REPOSITORY_ID,
    SHA256,
    MEDIA_TYPE,
    cleaner,
    detach_name_for,
    enqueue,
    mark_succeeded_consumed,
    open_contract_stores,
    quarantine_name_for,
    seed_artifact,
    seed_artifact_residual,
    seed_bytes_delete_intent,
    seed_bytes_deleted_receipt,
    seed_create_succeeded,
    unlink_stage_dir_name,
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


def test_eligible_absent_is_idempotent_and_stamps(
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
    assert lifecycle.bytes_deleted_at is not None
    assert retention_explains_missing_ready_bytes(
        lifecycle=lifecycle,
        repository_id=REPOSITORY_ID,
        references=store.list_artifact_references(ARTIFACT_ID),
        ttl_seconds=3600,
        now=BASE_NOW,
        consumed_operation_artifact_id=ARTIFACT_ID,
    )


def test_ineligible_absent_is_not_washed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_artifact(mutation_store, created_at=CREATED_AT)
    ready = write_ready(layout)
    ready.unlink()

    cleaner(
        layout,
        store,
        mutation_store,
        ttl=3600,
        clock=datetime(2026, 8, 1, 0, 30, tzinfo=UTC),
    ).sweep_once()

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


@pytest.mark.parametrize("injected_errno", [errno.EIO, errno.EPERM])
def test_io_failure_retains_and_retries_after_cleared(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    injected_errno: int,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ok")
    calls = {"n": 0}
    import gateway_repository_service.artifact_cleanup as cleanup_mod

    original = cleanup_mod._unlink_ready_name

    def fail_once(name: str, *, dir_fd: int) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(injected_errno, "injected I/O failure")
        original(name, dir_fd=dir_fd)

    monkeypatch.setattr(cleanup_mod, "_unlink_ready_name", fail_once)
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
    for _ in range(16):
        instance.sweep_once()
        if not artifact_ready_path(layout, REPOSITORY_ID, low_id).exists():
            break
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

    original = cleanup_mod._unlink_ready_name

    def fail_once(name: str, *, dir_fd: int) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            first_failure.set()
            raise OSError(errno.EIO, "injected I/O failure")
        original(name, dir_fd=dir_fd)

    monkeypatch.setattr(cleanup_mod, "_unlink_ready_name", fail_once)
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


def test_cleanup_keyset_sql_limit_not_fetchall_slice(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    _store, mutation_store = stores
    for i in range(70):
        seed_artifact(
            mutation_store,
            artifact_id=UUID(int=ARTIFACT_ID.int + i),
            created_at=CREATED_AT,
        )
    page = mutation_store.list_artifacts_pending_byte_cleanup(limit=64)
    assert page.scanned == 64
    assert len(page.records) == 64
    last_seq = page.cursor_cleanup_seq
    rest = mutation_store.list_artifacts_pending_byte_cleanup(
        limit=64,
        after_cleanup_seq=last_seq,
    )
    assert rest.scanned == 6
    page_ids = {row.artifact_id for row in page.records}
    rest_ids = {row.artifact_id for row in rest.records}
    assert page_ids.isdisjoint(rest_ids)


def test_cleanup_multi_repo_keyset_is_globally_ordered(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    _store, mutation_store = stores
    for i in range(40):
        seed_artifact(
            mutation_store,
            artifact_id=UUID(int=ARTIFACT_ID.int + i),
            created_at=CREATED_AT,
        )
    for i in range(40, 80):
        seed_artifact(
            mutation_store,
            artifact_id=UUID(int=ARTIFACT_ID.int + i),
            repository_id=OTHER_REPOSITORY_ID,
            created_at=CREATED_AT,
        )
    page = mutation_store.list_artifacts_pending_byte_cleanup(limit=64)
    assert page.scanned == 64
    assert isinstance(page.cursor_cleanup_seq, int)
    repos = {record.repository_id for record in page.records}
    assert REPOSITORY_ID in repos
    assert OTHER_REPOSITORY_ID in repos
    rest = mutation_store.list_artifacts_pending_byte_cleanup(
        limit=64,
        after_cleanup_seq=page.cursor_cleanup_seq,
    )
    page_ids = {row.artifact_id for row in page.records}
    rest_ids = {row.artifact_id for row in rest.records}
    assert page_ids.isdisjoint(rest_ids)
    assert rest.scanned == 16


def test_cleanup_query_uses_keyset_index(
    stores: tuple[ImportOperationStore, MutationStore],
) -> None:
    _store, mutation_store = stores
    plan_rows = mutation_store._connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT artifact_id FROM artifact_lifecycle
        WHERE bytes_deleted_at IS NULL
        ORDER BY cleanup_seq ASC
        LIMIT 64
        """
    ).fetchall()
    plan = " ".join(" ".join(str(col) for col in row) for row in plan_rows)
    assert "artifact_lifecycle_cleanup_seq_idx" in plan
    assert "USE TEMP B-TREE FOR ORDER BY" not in plan


def test_cleanup_list_binds_integer_seq_not_str() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "gateway_repository_service"
        / "mutation_store.py"
    )
    text = source.read_text(encoding="utf-8")
    start = text.index("def list_artifacts_pending_byte_cleanup")
    end = text.index("def ", start + 4)
    body = text[start:end]
    assert "after_cleanup_seq" in body
    assert "int(after_cleanup_seq)" in body
    assert "str(row[8])" not in body
    assert "cursor_created_at" not in body


def test_keyset_page_does_not_starve_later_succeeded(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    old_ids = [UUID(int=ARTIFACT_ID.int + i) for i in range(64)]
    new_id = UUID(int=ARTIFACT_ID.int + 64)
    new_op = UUID(int=OPERATION_ID.int + 64)
    for i, aid in enumerate(old_ids):
        seed_artifact(mutation_store, artifact_id=aid)
        write_ready(layout, artifact_id=aid)
        enqueue(
            store,
            key=f"protected-{i}",
            operation_id=UUID(int=OPERATION_ID.int + i),
            artifact_id=aid,
        )
    seed_artifact(mutation_store, artifact_id=new_id, created_at="2026-08-01T01:00:00+00:00")
    new_ready = write_ready(layout, artifact_id=new_id)
    mark_succeeded_consumed(
        store,
        key="later-succeeded",
        operation_id=new_op,
        artifact_id=new_id,
    )
    instance = cleaner(layout, store, mutation_store)
    instance.sweep_once()
    assert new_ready.is_file()
    for aid in old_ids:
        assert artifact_ready_path(layout, REPOSITORY_ID, aid).is_file()
    for _ in range(16):
        instance.sweep_once()
        if not new_ready.exists():
            break
    assert not new_ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(new_id)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_classify_rejects_path_outside_layout_ready_dir(
    layout: DurableLayout,
    tmp_path: Path,
) -> None:
    expected = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    expected.parent.mkdir(parents=True, exist_ok=True)
    outsider = tmp_path / "other" / ARTIFACT_ID.hex
    outsider.parent.mkdir(parents=True, exist_ok=True)
    outsider.write_bytes(ARTIFACT_PAYLOAD)
    assert (
        classify_ready_artifact_path(outsider, expected=expected, artifact_id=ARTIFACT_ID)
        == "unexpected_path"
    )


def test_parent_symlink_escape_does_not_delete_outside_target(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    tmp_path: Path,
) -> None:
    from gateway_repository_service import artifact_cleanup

    store, _mutation_store = stores
    ready = write_ready(layout)
    outside_dir = tmp_path / "escape-ready"
    outside_dir.mkdir()
    outside_target = outside_dir / ARTIFACT_ID.hex
    ready.rename(outside_target)
    ready_dir = ready.parent
    ready_dir.rmdir()
    ready_dir.symlink_to(outside_dir)

    outcome = artifact_cleanup.cleanup_ready_artifact_bytes(
        store,
        layout,
        repository_id=REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        ttl_seconds=3600,
        recheck=lambda: True,
    )
    assert outcome == "unsafe_path"
    assert outside_target.is_file()
    assert outside_target.read_bytes() == ARTIFACT_PAYLOAD


def test_eligible_leftover_deleting_sidecar_does_not_starve_other_candidate(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    seed_artifact(mutation_store, artifact_id=OTHER_ARTIFACT_ID)
    leftover_ready = write_ready(layout)
    other_ready = write_ready(layout, artifact_id=OTHER_ARTIFACT_ID)
    mark_succeeded_consumed(store, key="leftover")
    mark_succeeded_consumed(
        store,
        key="other",
        operation_id=OTHER_OPERATION_ID,
        artifact_id=OTHER_ARTIFACT_ID,
    )
    st = leftover_ready.stat()
    generation = seed_bytes_delete_intent(
        mutation_store,
        artifact_id=ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
    )
    sidecar = leftover_ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation=generation,
    )
    os.link(leftover_ready, sidecar)
    leftover_ready.unlink()
    seed_artifact_residual(
        mutation_store,
        artifact_id=ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        kind="deleting",
        name=sidecar.name,
        parent_name="",
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        generation=generation,
        created_at=CREATED_AT,
    )

    cleaner(layout, store, mutation_store).sweep_once()

    leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert leftover is not None
    assert leftover.bytes_deleted_at is not None
    assert not sidecar.exists()
    assert store.list_artifact_residuals(artifact_id=ARTIFACT_ID).records == []
    assert not other_ready.exists()
    other = mutation_store.get_artifact_lifecycle(OTHER_ARTIFACT_ID)
    assert other is not None
    assert other.bytes_deleted_at is not None


def test_protected_leftover_sidecar_is_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    enqueue(store, key="protected-pending", operation_id=OPERATION_ID)
    st = ready.stat()
    sidecar = ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation="g1",
    )
    os.link(ready, sidecar)

    cleaner(layout, store, mutation_store).sweep_once()

    assert ready.is_file()
    assert sidecar.is_file()
    assert sidecar.read_bytes() == ARTIFACT_PAYLOAD
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_eligible_leftover_detach_sidecar_is_unlinked(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="detach-leftover")
    st = ready.stat()
    sidecar = ready.parent / detach_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation="g1",
    )
    os.link(ready, sidecar)
    ready.unlink()

    cleaner(layout, store, mutation_store).sweep_once()

    assert not sidecar.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_eligible_leftover_unlink_stage_is_removed(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="stage-leftover")
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    stage = ready.parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="tok1")
    stage.mkdir()
    os.chmod(stage, 0o700)
    (stage / "victim").write_bytes(ARTIFACT_PAYLOAD)

    cleaner(layout, store, mutation_store).sweep_once()

    assert not stage.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_malformed_leftover_name_is_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="malformed-neighbor")
    malformed = ready.parent / ".deleting-not-a-parseable-sidecar"
    malformed.write_bytes(b"keep-me")

    cleaner(layout, store, mutation_store).sweep_once()

    assert not ready.exists()
    assert malformed.is_file()
    assert malformed.read_bytes() == b"keep-me"


@pytest.mark.parametrize(
    "payload",
    [ARTIFACT_PAYLOAD, b""],
    ids=["full-payload", "size-0"],
)
def test_eligible_leftover_sidecar_is_unlinked_regardless_of_size(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    payload: bytes,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    ready.write_bytes(payload)
    mark_succeeded_consumed(store, key="size-leftover")
    st = ready.stat()
    sidecar = ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation="g1",
    )
    os.link(ready, sidecar)
    ready.unlink()

    cleaner(layout, store, mutation_store).sweep_once()

    assert not sidecar.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_leftover_hardlink_does_not_truncate_other_inode(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    tmp_path: Path,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="hardlink-leftover")
    st = ready.stat()
    sidecar = ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation="g1",
    )
    os.link(ready, sidecar)
    witness = tmp_path / "witness"
    os.link(ready, witness)

    cleaner(layout, store, mutation_store).sweep_once()

    assert not ready.exists()
    assert not sidecar.exists()
    assert witness.is_file()
    assert witness.read_bytes() == ARTIFACT_PAYLOAD
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


@pytest.mark.parametrize("injected_errno", [errno.EPERM, errno.EIO])
def test_housekeeping_leftover_unlink_io_failure_does_not_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    injected_errno: int,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="housekeeping-io")
    st = ready.stat()
    sidecar = ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation="g1",
    )
    os.link(ready, sidecar)
    ready.unlink()
    calls = {"n": 0}
    original = os.unlink

    def fail_once(path: str, *, dir_fd: int | None = None) -> None:
        name = path if isinstance(path, str) else os.fsdecode(path)
        if name.startswith(".deleting-") and calls["n"] == 0:
            calls["n"] += 1
            raise OSError(injected_errno, "injected housekeeping unlink")
        original(path, dir_fd=dir_fd)

    monkeypatch.setattr(os, "unlink", fail_once)
    instance = cleaner(layout, store, mutation_store)
    instance.sweep_once()
    assert sidecar.is_file()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None

    monkeypatch.undo()
    instance.sweep_once()
    assert not sidecar.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_facade_ready_directory_missing_does_not_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    from gateway_repository_service import artifact_cleanup

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="ready-dir-missing")
    ready.unlink()
    ready.parent.rmdir()

    outcome = artifact_cleanup.cleanup_ready_artifact_bytes(
        store,
        layout,
        repository_id=REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        ttl_seconds=3600,
        recheck=lambda: True,
    )
    assert outcome == "unlink_failed"
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_facade_ready_unavailable_does_not_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleanup

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    write_ready(layout)
    mark_succeeded_consumed(store, key="ready-unavailable")

    def boom(*_args: object, **_kwargs: object) -> tuple[int, int]:
        raise OwnedPathError("ready is unavailable")

    monkeypatch.setattr(artifact_cleanup, "open_owned_ready_artifact", boom)
    outcome = artifact_cleanup.cleanup_ready_artifact_bytes(
        store,
        layout,
        repository_id=REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        ttl_seconds=3600,
        recheck=lambda: True,
    )
    assert outcome == "unlink_failed"
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_facade_rejects_cross_repository_scope_without_unlink_or_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    from gateway_repository_service import artifact_cleanup

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    owned = write_ready(layout)
    mark_succeeded_consumed(store, key="cross-scope")
    foreign = write_ready(layout, repository_id=OTHER_REPOSITORY_ID)

    outcome = artifact_cleanup.cleanup_ready_artifact_bytes(
        store,
        layout,
        repository_id=OTHER_REPOSITORY_ID,
        artifact_id=ARTIFACT_ID,
        ttl_seconds=3600,
        recheck=lambda: True,
    )

    assert outcome == "ineligible"
    assert owned.is_file()
    assert owned.read_bytes() == ARTIFACT_PAYLOAD
    assert foreign.is_file()
    assert foreign.read_bytes() == ARTIFACT_PAYLOAD
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None
    assert lifecycle.repository_id == REPOSITORY_ID


def test_leftover_encoded_inode_mismatch_is_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="inode-mismatch")
    tmp = ready.parent / "inode-mismatch-tmp"
    tmp.write_bytes(ARTIFACT_PAYLOAD)
    actual_ino = int(tmp.stat().st_ino)
    encoded_ino = actual_ino + 1
    sidecar = ready.parent / quarantine_name_for(
        inode=encoded_ino,
        artifact_id=ARTIFACT_ID,
        generation="g1",
    )
    tmp.rename(sidecar)
    assert int(sidecar.stat().st_ino) == actual_ino
    assert int(sidecar.stat().st_ino) != encoded_ino
    ready.unlink()

    cleaner(layout, store, mutation_store).sweep_once()

    assert sidecar.is_file()
    assert sidecar.read_bytes() == ARTIFACT_PAYLOAD
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_unknown_unlink_stage_child_is_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="unknown-stage-child")
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    stage = ready.parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="tok1")
    stage.mkdir()
    os.chmod(stage, 0o700)
    (stage / "victim").write_bytes(ARTIFACT_PAYLOAD)
    unexpected = stage / "unexpected"
    unexpected.write_bytes(b"keep-me")

    cleaner(layout, store, mutation_store).sweep_once()

    assert stage.is_dir()
    assert unexpected.is_file()
    assert unexpected.read_bytes() == b"keep-me"
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_nonregular_leftover_sidecar_is_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    kind: str,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key=f"nonregular-{kind}")
    st = ready.stat()
    sidecar = ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation="g1",
    )
    target = ready.parent / "leftover-target"
    target.write_bytes(b"keep-target")
    if kind == "symlink":
        os.symlink(target.name, sidecar)
    else:
        os.mkfifo(sidecar)
    ready.unlink()

    cleaner(layout, store, mutation_store).sweep_once()

    assert sidecar.exists()
    if kind == "symlink":
        assert sidecar.is_symlink()
        assert target.read_bytes() == b"keep-target"
    else:
        assert stat.S_ISFIFO(sidecar.lstat().st_mode)
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_eligible_leftover_stage_with_known_children_converges(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="known-stage-children")
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    stage = ready.parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="tok2")
    stage.mkdir()
    os.chmod(stage, 0o700)
    (stage / "victim").write_bytes(ARTIFACT_PAYLOAD)
    (stage / "final-1").write_bytes(b"final")
    (stage / "doom-1").write_bytes(b"doom")

    cleaner(layout, store, mutation_store).sweep_once()

    assert not stage.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_eligible_leftover_stage_larger_than_budget_converges_across_sweeps(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="large-stage-children")
    ready = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID)
    ready.parent.mkdir(parents=True, exist_ok=True)
    stage = ready.parent / unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="tok3")
    stage.mkdir()
    os.chmod(stage, 0o700)
    (stage / "victim").write_bytes(ARTIFACT_PAYLOAD)
    for index in range(70):
        (stage / f"final-{index:02d}").write_bytes(b"final")

    instance = cleaner(layout, store, mutation_store)
    child_counts: list[int] = []
    for _ in range(8):
        instance.sweep_once()
        if stage.exists():
            child_counts.append(len(list(stage.iterdir())))
        else:
            child_counts.append(0)
            break
    assert child_counts
    assert child_counts[-1] == 0
    assert min(child_counts) < 71
    assert not stage.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None


def test_housekeeping_budget_does_not_starve_later_candidate(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="budget-candidate")
    layout.artifacts.mkdir(parents=True, exist_ok=True)
    for index in range(80):
        (layout.artifacts / f"unknown-{index:03d}").write_bytes(b"unknown")

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    instance.sweep_once()

    bounded = [
        event
        for event in events
        if event.get("cleanup_outcome") == "housekeeping_bounded"
    ]
    assert len(bounded) == 1
    assert bounded[0]["capacity"] == 64
    used = bounded[0]["in_use"]
    assert isinstance(used, int)
    assert used <= 64
    unknown_logs = [
        event
        for event in events
        if event.get("cleanup_outcome") == "unknown_path_inventory"
    ]
    assert len(unknown_logs) <= 64
    for _ in range(16):
        if not ready.exists():
            break
        instance.sweep_once()
    assert not ready.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is not None

    later_id = UUID(int=ARTIFACT_ID.int + 1)
    later_op = UUID(int=OPERATION_ID.int + 1)
    seed_artifact(mutation_store, artifact_id=later_id)
    later_ready = write_ready(layout, artifact_id=later_id)
    mark_succeeded_consumed(
        store,
        key="budget-later",
        operation_id=later_op,
        artifact_id=later_id,
    )
    instance.sweep_once()
    assert not later_ready.exists()
    later = mutation_store.get_artifact_lifecycle(later_id)
    assert later is not None
    assert later.bytes_deleted_at is not None
    assert (layout.artifacts / "unknown-000").is_file()


def test_housekeeping_budget_bounds_ready_leftovers_in_one_repository(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    seed_artifact(mutation_store, artifact_id=OTHER_ARTIFACT_ID)
    leftover_ready = write_ready(layout)
    mark_succeeded_consumed(store, key="budget-leftover")
    candidate = write_ready(layout, artifact_id=OTHER_ARTIFACT_ID)
    mark_succeeded_consumed(
        store,
        key="budget-candidate-uuid",
        operation_id=OTHER_OPERATION_ID,
        artifact_id=OTHER_ARTIFACT_ID,
    )
    ready_dir = leftover_ready.parent
    leftover_ready.unlink()
    sidecars: list[Path] = []
    for index in range(80):
        tmp = ready_dir / f"tmp-leftover-{index:02d}"
        tmp.write_bytes(ARTIFACT_PAYLOAD)
        st = tmp.stat()
        sidecar = ready_dir / quarantine_name_for(
            inode=int(st.st_ino),
            artifact_id=ARTIFACT_ID,
            generation=f"g{index:02d}",
        )
        tmp.rename(sidecar)
        sidecars.append(sidecar)

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    leftover_checks = {"n": 0}
    orig_leftover = ArtifactCleaner._artifact_has_parseable_leftovers

    def counting_leftover(
        self: ArtifactCleaner,
        repository_id: UUID,
        artifact_id: UUID,
    ) -> bool:
        leftover_checks["n"] += 1
        return orig_leftover(self, repository_id, artifact_id)

    enumerated = {"n": 0}
    orig_scandir = cleaner_mod._scandir_names

    def counting_scandir(dir_fd: int) -> Iterator[str]:
        for name in orig_scandir(dir_fd):
            enumerated["n"] += 1
            yield name

    monkeypatch.setattr(
        ArtifactCleaner, "_artifact_has_parseable_leftovers", counting_leftover
    )
    monkeypatch.setattr(cleaner_mod, "_scandir_names", counting_scandir)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    leftover_checks["n"] = 0
    enumerated["n"] = 0
    instance.sweep_once()

    bounded = [
        event
        for event in events
        if event.get("cleanup_outcome") == "housekeeping_bounded"
    ]
    assert len(bounded) == 1
    used = bounded[0]["in_use"]
    assert isinstance(used, int)
    assert used <= 64
    assert enumerated["n"] <= 64
    assert leftover_checks["n"] < 80
    remaining = [path for path in sidecars if path.exists()]
    assert remaining
    assert len(remaining) < 80 or used <= 64
    leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert leftover is not None
    assert leftover.bytes_deleted_at is None

    for _ in range(8):
        leftover_checks["n"] = 0
        enumerated["n"] = 0
        instance.sweep_once()
        assert enumerated["n"] <= 64
        assert leftover_checks["n"] < 80
        if not any(path.exists() for path in sidecars) and not candidate.exists():
            break
    assert not any(path.exists() for path in sidecars)
    assert not candidate.exists()
    leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert leftover is not None
    assert leftover.bytes_deleted_at is not None


def _count_housekeeping_yields(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    from gateway_repository_service import artifact_cleaner as cleaner_mod
    from gateway_repository_service.upload_artifact import admission_pin as pin_mod

    counts = {"os_scandir": 0, "scandir_names": 0, "stage_fd": 0}
    orig_os_scandir = os.scandir
    orig_scandir_names = cleaner_mod._scandir_names
    orig_stage = pin_mod.scandir_dir_fd_names

    class _CountingScandir:
        def __init__(self, wrapped: object) -> None:
            self._wrapped = wrapped

        def __enter__(self) -> Iterator[object]:
            inner = self._wrapped.__enter__()  # type: ignore[attr-defined]

            def _counted() -> Iterator[object]:
                for item in inner:
                    counts["os_scandir"] += 1
                    yield item

            return _counted()

        def __exit__(
            self,
            *args: object,
        ) -> None:
            self._wrapped.__exit__(*args)  # type: ignore[attr-defined]

    def counting_os_scandir(
        path: str | os.PathLike[str] | int,
        *args: object,
        **kwargs: object,
    ) -> object:
        wrapped = orig_os_scandir(path, *args, **kwargs)
        path_text = str(path)
        if path_text.startswith("/proc/self/fd/"):
            return wrapped
        return _CountingScandir(wrapped)

    def counting_scandir_names(dir_fd: int) -> Iterator[str]:
        for name in orig_scandir_names(dir_fd):
            counts["scandir_names"] += 1
            yield name

    def counting_stage(dir_fd: int) -> Iterator[str]:
        for name in orig_stage(dir_fd):
            counts["stage_fd"] += 1
            yield name

    monkeypatch.setattr(os, "scandir", counting_os_scandir)
    monkeypatch.setattr(cleaner_mod, "_scandir_names", counting_scandir_names)
    monkeypatch.setattr(pin_mod, "scandir_dir_fd_names", counting_stage)
    return counts


def _leftover_observation_sizes(instance: ArtifactCleaner) -> tuple[int, int, int]:
    buckets = instance._leftover_repos
    seen = sum(len(bucket.seen) for bucket in buckets.values())
    counts = sum(len(bucket.counts) for bucket in buckets.values())
    return len(buckets), seen, counts


def _assert_housekeeping_bounded(
    events: list[dict[str, object]],
    counts: dict[str, int],
) -> None:
    bounded = [
        event
        for event in events
        if event.get("cleanup_outcome") == "housekeeping_bounded"
    ]
    assert len(bounded) == 1
    used = bounded[0]["in_use"]
    assert isinstance(used, int)
    assert used <= 64
    assert counts["os_scandir"] <= 64
    assert counts["scandir_names"] <= 64
    assert counts["stage_fd"] <= 64


def test_housekeeping_budget_bounds_three_pages_of_same_artifact_sidecars(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    leftover_ready = write_ready(layout)
    mark_succeeded_consumed(store, key="budget-three-pages")
    ready_dir = leftover_ready.parent
    leftover_ready.unlink()
    sidecars: list[Path] = []
    for index in range(240):
        tmp = ready_dir / f"tmp-leftover-{index:03d}"
        tmp.write_bytes(ARTIFACT_PAYLOAD)
        st = tmp.stat()
        sidecar = ready_dir / quarantine_name_for(
            inode=int(st.st_ino),
            artifact_id=ARTIFACT_ID,
            generation=f"g{index:03d}",
        )
        tmp.rename(sidecar)
        sidecars.append(sidecar)

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    for _ in range(40):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        if not any(path.exists() for path in sidecars):
            break
    assert not any(path.exists() for path in sidecars)
    leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert leftover is not None
    assert leftover.bytes_deleted_at is not None


def test_housekeeping_budget_bounds_fifo_leftovers_across_artifacts(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    fifos: list[Path] = []
    for index in range(64):
        artifact_id = UUID(int=ARTIFACT_ID.int + index + 10)
        operation_id = UUID(int=OPERATION_ID.int + index + 10)
        seed_artifact(mutation_store, artifact_id=artifact_id)
        ready = write_ready(layout, artifact_id=artifact_id)
        mark_succeeded_consumed(
            store,
            key=f"fifo-{index:02d}",
            operation_id=operation_id,
            artifact_id=artifact_id,
        )
        st = ready.stat()
        sidecar = ready.parent / quarantine_name_for(
            inode=int(st.st_ino),
            artifact_id=artifact_id,
            generation="g1",
        )
        os.mkfifo(sidecar)
        ready.unlink()
        fifos.append(sidecar)

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    for _ in range(4):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
    assert all(path.exists() for path in fifos)
    for index in range(64):
        artifact_id = UUID(int=ARTIFACT_ID.int + index + 10)
        lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is None


def _proc_self_fd_count() -> int:
    return len(os.listdir("/proc/self/fd"))


class _PathDirEntry:
    def __init__(self, path: Path) -> None:
        self.path = str(path)
        self.name = path.name
        self._path = path

    def is_symlink(self) -> bool:
        return self._path.is_symlink()

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        if not follow_symlinks and self._path.is_symlink():
            return False
        return self._path.is_dir()


class _SortedRootScan:
    """Deterministic artifacts-root iterator so the 65th repo is last by name."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._iter = iter(sorted(os.listdir(root)))
        self._closed = False
        self._pending: str | None = None

    def take(self, budget: object) -> object:
        from gateway_repository_service.artifact_cleaner import (
            _HeldTake,
            _HeldTakeKind,
        )

        remaining = getattr(budget, "remaining")
        consume = getattr(budget, "consume")
        if self._closed:
            return _HeldTake(_HeldTakeKind.EOF)
        if remaining() <= 0:
            return _HeldTake(_HeldTakeKind.TRUNCATED)
        name = self._pending
        self._pending = None
        if name is None:
            try:
                name = next(self._iter)
            except StopIteration:
                self.close()
                return _HeldTake(_HeldTakeKind.EOF)
        if not consume():
            self._pending = name
            return _HeldTake(_HeldTakeKind.TRUNCATED)
        entry = _PathDirEntry(self._root / name)
        return _HeldTake(_HeldTakeKind.ITEM, name=name, entry=entry)  # type: ignore[arg-type]

    def close(self) -> None:
        self._closed = True
        self._pending = None


class _ErrorAfterFirstReady:
    """Ready iterator that notes one leftover then fails closed without EOF."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self._items = 0

    def take(self, budget: object) -> object:
        from gateway_repository_service.artifact_cleaner import (
            _HeldTake,
            _HeldTakeKind,
        )

        if self._items >= 1:
            self.close()
            return _HeldTake(_HeldTakeKind.ERROR)
        taken = getattr(self._inner, "take")(budget)
        if getattr(taken, "kind") is _HeldTakeKind.ITEM:
            self._items += 1
        return taken

    def close(self) -> None:
        close = getattr(self._inner, "close", None)
        if close is not None:
            close()


def _fifo_leftover(
    layout: DurableLayout,
    *,
    artifact_id: UUID,
    generation: str = "g1",
    repository_id: UUID = REPOSITORY_ID,
) -> Path:
    ready = write_ready(layout, artifact_id=artifact_id, repository_id=repository_id)
    st = ready.stat()
    sidecar = ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=artifact_id,
        generation=generation,
    )
    os.mkfifo(sidecar)
    ready.unlink()
    return sidecar


def _regular_leftover(
    layout: DurableLayout,
    *,
    artifact_id: UUID,
    generation: str,
    repository_id: UUID = REPOSITORY_ID,
) -> Path:
    ready = write_ready(layout, artifact_id=artifact_id, repository_id=repository_id)
    st = ready.stat()
    sidecar = ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=artifact_id,
        generation=generation,
    )
    ready.rename(sidecar)
    return sidecar


def _symlink_leftover(
    layout: DurableLayout,
    *,
    artifact_id: UUID,
    generation: str = "g1",
    repository_id: UUID = REPOSITORY_ID,
) -> Path:
    ready = write_ready(layout, artifact_id=artifact_id, repository_id=repository_id)
    st = ready.stat()
    sidecar = ready.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=artifact_id,
        generation=generation,
    )
    target = ready.parent / f"keep-{generation}"
    target.write_bytes(b"keep-target")
    os.symlink(target.name, sidecar)
    ready.unlink()
    return sidecar


@pytest.mark.parametrize("kind", ["regular", "fifo", "symlink"])
def test_held_recover_reaches_target_after_64_fifo_prefix(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    fifos: list[Path] = []
    for index in range(64):
        artifact_id = UUID(int=ARTIFACT_ID.int + index + 10)
        operation_id = UUID(int=OPERATION_ID.int + index + 10)
        seed_artifact(mutation_store, artifact_id=artifact_id)
        mark_succeeded_consumed(
            store,
            key=f"fifo-prefix-{index:02d}",
            operation_id=operation_id,
            artifact_id=artifact_id,
        )
        fifos.append(_fifo_leftover(layout, artifact_id=artifact_id, generation="p1"))

    target_id = UUID(int=ARTIFACT_ID.int + 200)
    target_op = UUID(int=OPERATION_ID.int + 200)
    seed_artifact(mutation_store, artifact_id=target_id)
    mark_succeeded_consumed(
        store,
        key="fifo-prefix-target",
        operation_id=target_op,
        artifact_id=target_id,
    )
    if kind == "regular":
        target = _regular_leftover(layout, artifact_id=target_id, generation="t1")
    elif kind == "fifo":
        target = _fifo_leftover(layout, artifact_id=target_id, generation="t1")
    else:
        target = _symlink_leftover(layout, artifact_id=target_id, generation="t1")

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    for key in counts:
        counts[key] = 0
    events.clear()
    instance.sweep_once()
    _assert_housekeeping_bounded(events, counts)
    target_life = mutation_store.get_artifact_lifecycle(target_id)
    assert target_life is not None
    assert target_life.bytes_deleted_at is None
    assert target.exists()
    assert all(path.exists() for path in fifos)

    for _ in range(24):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        target_life = mutation_store.get_artifact_lifecycle(target_id)
        assert target_life is not None
        if kind == "regular":
            if not target.exists() and target_life.bytes_deleted_at is not None:
                break
        elif target_life.bytes_deleted_at is not None:
            break
    assert all(path.exists() for path in fifos)
    for index in range(64):
        artifact_id = UUID(int=ARTIFACT_ID.int + index + 10)
        lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is None
    target_life = mutation_store.get_artifact_lifecycle(target_id)
    assert target_life is not None
    if kind == "regular":
        assert not target.exists()
        assert target_life.bytes_deleted_at is not None
    else:
        assert target.exists()
        assert target_life.bytes_deleted_at is None


def test_held_recover_reaches_legal_leftover_in_65th_repository(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    _store, mutation_store = stores
    poison_repos = [UUID(int=index) for index in range(1, 65)]
    legal_repo = UUID(int=65)
    for index, repo in enumerate(poison_repos):
        artifact_id = UUID(int=ARTIFACT_ID.int + 300 + index)
        seed_create_succeeded(mutation_store, repository_id=repo)
        seed_artifact(mutation_store, artifact_id=artifact_id, repository_id=repo)
        _fifo_leftover(
            layout,
            artifact_id=artifact_id,
            generation="r1",
            repository_id=repo,
        )
    seed_create_succeeded(mutation_store, repository_id=legal_repo)
    seed_artifact(mutation_store, artifact_id=ARTIFACT_ID, repository_id=legal_repo)
    target = _regular_leftover(
        layout,
        artifact_id=ARTIFACT_ID,
        generation="legal",
        repository_id=legal_repo,
    )

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    orig_from_path = cleaner_mod._HeldScan.from_path

    def from_path(path: str | Path) -> object:
        if Path(path).resolve() == layout.artifacts.resolve():
            return _SortedRootScan(layout.artifacts)
        return orig_from_path(path)

    monkeypatch.setattr(cleaner_mod._HeldScan, "from_path", from_path)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, _store, mutation_store)
    for _ in range(40):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert leftover is not None
        if not target.exists() and leftover.bytes_deleted_at is not None:
            break
    assert not target.exists()
    leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert leftover is not None
    assert leftover.bytes_deleted_at is not None


def test_held_recover_poison_prefix_does_not_starve_leftover_or_receipt(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    fifos: list[Path] = []
    for index in range(64):
        artifact_id = UUID(int=ARTIFACT_ID.int + index + 10)
        operation_id = UUID(int=OPERATION_ID.int + index + 10)
        seed_artifact(mutation_store, artifact_id=artifact_id)
        mark_succeeded_consumed(
            store,
            key=f"poison-prefix-{index:02d}",
            operation_id=operation_id,
            artifact_id=artifact_id,
        )
        fifos.append(_fifo_leftover(layout, artifact_id=artifact_id, generation="x1"))

    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="poison-prefix-legal")
    legal = _regular_leftover(layout, artifact_id=ARTIFACT_ID, generation="ok")

    seed_artifact(mutation_store, artifact_id=OTHER_ARTIFACT_ID)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=OTHER_ARTIFACT_ID,
        generation="g1",
    )
    write_ready(layout, artifact_id=OTHER_ARTIFACT_ID).unlink()

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    legal_done = False
    receipt_cleared = False
    for _ in range(40):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        later = mutation_store.get_artifact_lifecycle(OTHER_ARTIFACT_ID)
        assert leftover is not None
        assert later is not None
        if not legal.exists() and leftover.bytes_deleted_at is not None:
            legal_done = True
        if later.bytes_deleted_receipt_generation is None:
            receipt_cleared = True
        if legal_done and receipt_cleared:
            break
    assert legal_done
    assert receipt_cleared
    assert not legal.exists()
    assert all(path.exists() for path in fifos)
    leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert leftover is not None
    assert leftover.bytes_deleted_at is not None
    for index in range(64):
        artifact_id = UUID(int=ARTIFACT_ID.int + index + 10)
        lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is None


def test_operator_cleared_fifo_leftover_allows_stamp(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="operator-cleared-fifo")
    fifo = _fifo_leftover(layout, artifact_id=ARTIFACT_ID, generation="op")

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    for _ in range(8):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is None
    assert fifo.exists()
    fifo.unlink()
    stamped = False
    for _ in range(16):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert lifecycle is not None
        if lifecycle.bytes_deleted_at is not None:
            stamped = True
            break
    assert stamped


def test_operator_cleared_fifo_leftover_allows_receipt_gc(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store, artifact_id=OTHER_ARTIFACT_ID)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=OTHER_ARTIFACT_ID,
        generation="g1",
    )
    fifo = _fifo_leftover(layout, artifact_id=OTHER_ARTIFACT_ID, generation="op")

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    for _ in range(8):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        later = mutation_store.get_artifact_lifecycle(OTHER_ARTIFACT_ID)
        assert later is not None
        assert later.bytes_deleted_receipt_generation is not None
    assert fifo.exists()
    fifo.unlink()
    cleared = False
    for _ in range(16):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        later = mutation_store.get_artifact_lifecycle(OTHER_ARTIFACT_ID)
        assert later is not None
        if later.bytes_deleted_receipt_generation is None:
            cleared = True
            break
    assert cleared


def test_ready_open_failure_does_not_stamp_after_fifo_observation(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="open-fail-fifo")
    fifo = _fifo_leftover(layout, artifact_id=ARTIFACT_ID, generation="of")

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    for _ in range(8):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
    assert fifo.exists()
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None

    def fail_open(*_args: object, **_kwargs: object) -> int:
        raise OwnedPathError("ready dir unreadable")

    monkeypatch.setattr(
        "gateway_repository_service.artifact_cleaner.open_owned_ready_dir",
        fail_open,
    )
    for _ in range(8):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is None
    assert fifo.exists()


def test_leftover_observation_does_not_grow_with_retained_names(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    poison_repos = [UUID(int=index) for index in range(1, 6)]
    legal_repo = UUID(int=6)
    retained_names = 80
    for repo in poison_repos:
        artifact_id = UUID(int=ARTIFACT_ID.int + repo.int)
        seed_create_succeeded(mutation_store, repository_id=repo)
        seed_artifact(mutation_store, artifact_id=artifact_id, repository_id=repo)
        for index in range(retained_names):
            _fifo_leftover(
                layout,
                artifact_id=artifact_id,
                generation=f"n{index:02d}",
                repository_id=repo,
            )
    seed_create_succeeded(mutation_store, repository_id=legal_repo)
    seed_artifact(mutation_store, artifact_id=ARTIFACT_ID, repository_id=legal_repo)
    target = _regular_leftover(
        layout,
        artifact_id=ARTIFACT_ID,
        generation="legal",
        repository_id=legal_repo,
    )

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    orig_from_path = cleaner_mod._HeldScan.from_path

    def from_path(path: str | Path) -> object:
        if Path(path).resolve() == layout.artifacts.resolve():
            return _SortedRootScan(layout.artifacts)
        return orig_from_path(path)

    monkeypatch.setattr(cleaner_mod._HeldScan, "from_path", from_path)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    seen_samples: list[int] = []
    legal_done = False
    extra_cycles = 0
    for _ in range(80):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        _repo_n, seen_n, count_n = _leftover_observation_sizes(instance)
        seen_samples.append(seen_n)
        assert _repo_n <= 64
        assert count_n <= retained_names
        leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
        assert leftover is not None
        if not legal_done and not target.exists() and leftover.bytes_deleted_at is not None:
            legal_done = True
        elif legal_done:
            extra_cycles += 1
            if extra_cycles >= 16:
                break
    assert legal_done
    assert not target.exists()
    name_total = len(poison_repos) * retained_names
    assert max(seen_samples) <= len(poison_repos) + 1
    assert seen_samples[-1] <= len(poison_repos) + 1
    assert max(seen_samples) * 10 < name_total
    _repo_n, _seen_n, count_n = _leftover_observation_sizes(instance)
    assert count_n == 0 or instance._recover_ready is not None


def test_unique_artifact_leftovers_stamp_within_budget(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    ids = [UUID(int=10_000 + index) for index in range(200)]
    leftovers: list[Path] = []
    for index, artifact_id in enumerate(ids):
        seed_artifact(mutation_store, artifact_id=artifact_id)
        mark_succeeded_consumed(
            store,
            key=f"unique-legal-{index:03d}",
            operation_id=UUID(int=OPERATION_ID.int + index + 1),
            artifact_id=artifact_id,
        )
        leftovers.append(
            _regular_leftover(
                layout, artifact_id=artifact_id, generation=f"u{index:03d}"
            )
        )

    events: list[dict[str, object]] = []
    lookups = {"n": 0}
    stamps = {"n": 0}

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    orig_get = mutation_store.get_artifact_lifecycle
    orig_mark = store.mark_artifact_bytes_deleted

    def counting_get(artifact_id: UUID) -> ArtifactLifecycleRecord | None:
        lookups["n"] += 1
        return orig_get(artifact_id)

    def counting_mark(
        artifact_id: UUID,
        *,
        deleted_at: str | None = None,
        repository_id: UUID | None = None,
        expected_dev: int | None = None,
        expected_ino: int | None = None,
        expected_generation: str | None = None,
    ) -> None:
        stamps["n"] += 1
        orig_mark(
            artifact_id,
            deleted_at=deleted_at,
            repository_id=repository_id,
            expected_dev=expected_dev,
            expected_ino=expected_ino,
            expected_generation=expected_generation,
        )

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    monkeypatch.setattr(mutation_store, "get_artifact_lifecycle", counting_get)
    monkeypatch.setattr(store, "mark_artifact_bytes_deleted", counting_mark)
    instance = cleaner(layout, store, mutation_store)
    for _ in range(80):
        for key in counts:
            counts[key] = 0
        events.clear()
        lookups["n"] = 0
        stamps["n"] = 0
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        _repo_n, seen_n, _count_n = _leftover_observation_sizes(instance)
        assert _repo_n <= 64
        assert seen_n <= 64
        assert lookups["n"] <= 256
        assert stamps["n"] <= 64
        assert not any(
            event.get("cleanup_outcome") == "leftover_unlinked" for event in events
        )
        remaining = [path for path in leftovers if path.exists()]
        stamped = 0
        for artifact_id in ids:
            lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
            assert lifecycle is not None
            if lifecycle.bytes_deleted_at is not None:
                stamped += 1
        if not remaining and stamped == len(ids):
            break
    assert not any(path.exists() for path in leftovers)
    for artifact_id in ids:
        lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is not None


def test_leftover_observation_overflow_keeps_retained_fifo_unproven(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    ids = [UUID(int=20_000 + index) for index in range(65)]
    fifos: list[Path] = []
    for index, artifact_id in enumerate(ids):
        seed_artifact(mutation_store, artifact_id=artifact_id)
        mark_succeeded_consumed(
            store,
            key=f"overflow-fifo-{index:02d}",
            operation_id=UUID(int=OPERATION_ID.int + index + 1),
            artifact_id=artifact_id,
        )
        fifos.append(
            _fifo_leftover(layout, artifact_id=artifact_id, generation=f"o{index:02d}")
        )

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    overflowed = False
    for _ in range(24):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        _repo_n, seen_n, _count_n = _leftover_observation_sizes(instance)
        assert _repo_n <= 64
        assert seen_n <= 64
        if any(
            event.get("cleanup_outcome") == "leftover_observation_overflow"
            for event in events
        ):
            overflowed = True
        for artifact_id in ids:
            lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
            assert lifecycle is not None
            assert lifecycle.bytes_deleted_at is None
    assert overflowed
    assert all(path.exists() for path in fifos)
    last = mutation_store.get_artifact_lifecycle(ids[-1])
    assert last is not None
    assert last.bytes_deleted_at is None
    assert instance._leftover_presence(REPOSITORY_ID, ids[-1]) != "absent"


def test_multi_repository_observation_does_not_rescan_global_set(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    repos = [UUID(int=index) for index in range(1, 71)]
    for index, repo in enumerate(repos):
        artifact_id = UUID(int=30_000 + index)
        seed_create_succeeded(mutation_store, repository_id=repo)
        seed_artifact(mutation_store, artifact_id=artifact_id, repository_id=repo)
        _fifo_leftover(
            layout,
            artifact_id=artifact_id,
            generation="r1",
            repository_id=repo,
        )

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    orig_from_path = cleaner_mod._HeldScan.from_path

    def from_path(path: str | Path) -> object:
        if Path(path).resolve() == layout.artifacts.resolve():
            return _SortedRootScan(layout.artifacts)
        return orig_from_path(path)

    monkeypatch.setattr(cleaner_mod._HeldScan, "from_path", from_path)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    for _ in range(40):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        repo_n, seen_n, _count_n = _leftover_observation_sizes(instance)
        assert repo_n <= 64
        assert seen_n <= 64
    assert len(instance._leftover_repos) <= 64


def test_overflow_leftover_buckets_evict_oldest_non_current(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    repos = [UUID(int=index) for index in range(1, 66)]
    eligible: dict[UUID, UUID] = {}
    receipts: dict[UUID, UUID] = {}
    fifos_by_repo: dict[UUID, list[Path]] = {}
    for repo_index, repo in enumerate(repos):
        seed_create_succeeded(mutation_store, repository_id=repo)
        repo_fifos: list[Path] = []
        for leftover_index in range(65):
            artifact_id = UUID(int=80_000 + repo_index * 65 + leftover_index)
            seed_artifact(
                mutation_store, artifact_id=artifact_id, repository_id=repo
            )
            if leftover_index == 0:
                eligible[repo] = artifact_id
            repo_fifos.append(
                _fifo_leftover(
                    layout,
                    artifact_id=artifact_id,
                    generation=f"f{leftover_index:02d}",
                    repository_id=repo,
                )
            )
        receipt_id = UUID(int=90_000 + repo_index)
        seed_artifact(mutation_store, artifact_id=receipt_id, repository_id=repo)
        seed_bytes_deleted_receipt(
            mutation_store,
            artifact_id=receipt_id,
            repository_id=repo,
            generation="g1",
        )
        receipts[repo] = receipt_id
        fifos_by_repo[repo] = repo_fifos

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    orig_from_path = cleaner_mod._HeldScan.from_path

    def from_path(path: str | Path) -> object:
        if Path(path).resolve() == layout.artifacts.resolve():
            return _SortedRootScan(layout.artifacts)
        return orig_from_path(path)

    monkeypatch.setattr(cleaner_mod._HeldScan, "from_path", from_path)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    overflowed = False
    target = repos[0]
    for _ in range(400):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        repo_n, seen_n, _count_n = _leftover_observation_sizes(instance)
        assert repo_n <= 64
        assert seen_n <= 64 * 64
        if any(
            event.get("cleanup_outcome") == "leftover_observation_overflow"
            for event in events
        ):
            overflowed = True
        for repo, artifact_id in eligible.items():
            assert instance._leftover_presence(repo, artifact_id) != "absent"
            lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
            assert lifecycle is not None
            assert lifecycle.bytes_deleted_at is None
        for repo, artifact_id in receipts.items():
            assert instance._leftover_presence(repo, artifact_id) != "absent"
            lifecycle = mutation_store.get_artifact_lifecycle(artifact_id)
            assert lifecycle is not None
            assert lifecycle.bytes_deleted_receipt_generation is not None
        if overflowed and len(instance._leftover_repos) <= 64:
            break
    assert overflowed
    assert len(instance._leftover_repos) <= 64

    for path in fifos_by_repo[target]:
        path.unlink()
    stamped = False
    receipt_cleared = False
    for _ in range(400):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        repo_n, _seen_n, _count_n = _leftover_observation_sizes(instance)
        assert repo_n <= 64
        target_life = mutation_store.get_artifact_lifecycle(eligible[target])
        assert target_life is not None
        if target_life.bytes_deleted_at is not None:
            stamped = True
        target_receipt = mutation_store.get_artifact_lifecycle(receipts[target])
        assert target_receipt is not None
        if target_receipt.bytes_deleted_receipt_generation is None:
            receipt_cleared = True
        if stamped and receipt_cleared:
            break
    assert stamped
    assert receipt_cleared
    for repo in repos[1:]:
        lifecycle = mutation_store.get_artifact_lifecycle(eligible[repo])
        assert lifecycle is not None
        assert lifecycle.bytes_deleted_at is None
        assert all(path.exists() for path in fifos_by_repo[repo])


def test_iterator_error_incomplete_buckets_stay_within_repo_cap(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    repos = [UUID(int=index) for index in range(1, 66)]
    for index, repo in enumerate(repos):
        artifact_id = UUID(int=70_000 + index)
        seed_create_succeeded(mutation_store, repository_id=repo)
        seed_artifact(mutation_store, artifact_id=artifact_id, repository_id=repo)
        _fifo_leftover(
            layout,
            artifact_id=artifact_id,
            generation="e1",
            repository_id=repo,
        )

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    orig_from_path = cleaner_mod._HeldScan.from_path

    def from_path(path: str | Path) -> object:
        if Path(path).resolve() == layout.artifacts.resolve():
            return _SortedRootScan(layout.artifacts)
        return _ErrorAfterFirstReady(orig_from_path(path))

    monkeypatch.setattr(cleaner_mod._HeldScan, "from_path", from_path)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    saw_incomplete = False
    for _ in range(80):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        repo_n, seen_n, _count_n = _leftover_observation_sizes(instance)
        assert repo_n <= 64
        assert seen_n <= 64
        if instance._leftover_repos:
            saw_incomplete = True
            assert all(
                not bucket.complete for bucket in instance._leftover_repos.values()
            )
    assert saw_incomplete
    assert len(instance._leftover_repos) <= 64


def test_receipt_gc_bills_each_row_once(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store, artifact_id=OTHER_ARTIFACT_ID)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=OTHER_ARTIFACT_ID,
        generation="g1",
    )
    write_ready(layout, artifact_id=OTHER_ARTIFACT_ID).unlink()

    events: list[dict[str, object]] = []
    receipt_used: list[int] = []
    clear_calls = {"n": 0}

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    orig_gc = cleaner_mod.ArtifactCleaner._gc_bytes_deleted_receipts
    orig_clear = store.clear_artifact_bytes_deleted_receipt

    def counting_gc(self: ArtifactCleaner, budget: _HousekeepingBudget) -> None:
        before = budget.used
        orig_gc(self, budget)
        receipt_used.append(budget.used - before)

    def counting_clear(
        artifact_id: UUID,
        *,
        repository_id: UUID,
        expected_dev: int,
        expected_ino: int,
        expected_generation: str,
    ) -> None:
        clear_calls["n"] += 1
        orig_clear(
            artifact_id,
            repository_id=repository_id,
            expected_dev=expected_dev,
            expected_ino=expected_ino,
            expected_generation=expected_generation,
        )

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    monkeypatch.setattr(
        cleaner_mod.ArtifactCleaner,
        "_gc_bytes_deleted_receipts",
        counting_gc,
    )
    monkeypatch.setattr(store, "clear_artifact_bytes_deleted_receipt", counting_clear)
    instance = cleaner(layout, store, mutation_store)
    for _ in range(16):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        later = mutation_store.get_artifact_lifecycle(OTHER_ARTIFACT_ID)
        assert later is not None
        if later.bytes_deleted_receipt_generation is None:
            break
    later = mutation_store.get_artifact_lifecycle(OTHER_ARTIFACT_ID)
    assert later is not None
    assert later.bytes_deleted_receipt_generation is None
    assert clear_calls["n"] == 1
    billed = [used for used in receipt_used if used > 0]
    assert billed
    assert billed[0] == 1
    assert all(used <= 2 for used in billed)


def test_receipt_mixed_page_bills_scanned_rows_once(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    poison_id = UUID(int=1)
    legal_id = UUID(int=2)
    seed_artifact(mutation_store, artifact_id=poison_id)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=poison_id,
        generation="",
    )
    seed_artifact(mutation_store, artifact_id=legal_id)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=legal_id,
        generation="g1",
    )
    write_ready(layout, artifact_id=legal_id).unlink()

    events: list[dict[str, object]] = []
    receipt_used: list[int] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    orig_gc = cleaner_mod.ArtifactCleaner._gc_bytes_deleted_receipts

    def counting_gc(self: ArtifactCleaner, budget: _HousekeepingBudget) -> None:
        before = budget.used
        orig_gc(self, budget)
        receipt_used.append(budget.used - before)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    monkeypatch.setattr(
        cleaner_mod.ArtifactCleaner,
        "_gc_bytes_deleted_receipts",
        counting_gc,
    )
    instance = cleaner(layout, store, mutation_store)
    for _ in range(16):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        later = mutation_store.get_artifact_lifecycle(legal_id)
        assert later is not None
        if later.bytes_deleted_receipt_generation is None:
            break
    later = mutation_store.get_artifact_lifecycle(legal_id)
    assert later is not None
    assert later.bytes_deleted_receipt_generation is None
    billed = [used for used in receipt_used if used > 0]
    assert billed
    assert billed[0] == 2
    assert all(used <= 2 for used in billed)


@pytest.mark.serial
def test_held_recover_iterators_close_on_stop_and_restart(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    mark_succeeded_consumed(store, key="held-fd")
    leftover_ready = write_ready(layout)
    leftover_ready.unlink()
    ready_dir = artifact_ready_path(layout, REPOSITORY_ID, ARTIFACT_ID).parent
    for index in range(240):
        tmp = ready_dir / f"tmp-held-{index:03d}"
        tmp.write_bytes(ARTIFACT_PAYLOAD)
        st = tmp.stat()
        sidecar = ready_dir / quarantine_name_for(
            inode=int(st.st_ino),
            artifact_id=ARTIFACT_ID,
            generation=f"h{index:03d}",
        )
        tmp.rename(sidecar)

    instance = cleaner(layout, store, mutation_store, interval=1)
    baseline = _proc_self_fd_count()
    instance.sweep_once()
    instance.sweep_once()
    assert instance._recover_root is not None or instance._recover_ready_fd is not None
    held_ready = instance._recover_ready_fd
    held_stage = instance._recover_stage_fd
    instance.stop(timeout=2.0)
    assert instance._recover_root is None
    assert instance._recover_ready_fd is None
    assert instance._recover_stage_fd is None
    if held_ready is not None:
        with pytest.raises(OSError):
            os.fstat(held_ready)
    if held_stage is not None:
        with pytest.raises(OSError):
            os.fstat(held_stage)
    assert _proc_self_fd_count() <= baseline + 8

    instance.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if instance._recover_root is not None or instance._recover_ready_fd is not None:
                break
            time.sleep(0.01)
    finally:
        instance.stop(timeout=2.0)
    instance.sweep_once()
    instance.stop(timeout=2.0)


def test_recover_vanished_names_and_unreadable_dir_still_converge(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    leftover_ready = write_ready(layout)
    mark_succeeded_consumed(store, key="cursor-deleted")
    ready_dir = leftover_ready.parent
    leftover_ready.unlink()
    sidecars: list[Path] = []
    for index in range(80):
        tmp = ready_dir / f"tmp-cursor-{index:02d}"
        tmp.write_bytes(ARTIFACT_PAYLOAD)
        st = tmp.stat()
        sidecar = ready_dir / quarantine_name_for(
            inode=int(st.st_ino),
            artifact_id=ARTIFACT_ID,
            generation=f"c{index:02d}",
        )
        tmp.rename(sidecar)
        sidecars.append(sidecar)

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    fail_open = {"n": 0}

    def flaky_open(layout: DurableLayout, repository_id: UUID) -> int:
        if fail_open["n"] == 1:
            fail_open["n"] += 1
            raise OwnedPathError("ready dir unreadable")
        return open_owned_ready_dir(layout, repository_id)

    monkeypatch.setattr(
        "gateway_repository_service.artifact_cleaner.open_owned_ready_dir",
        flaky_open,
    )
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    for key in counts:
        counts[key] = 0
    instance.sweep_once()
    _assert_housekeeping_bounded(events, counts)
    remaining = [path for path in sidecars if path.exists()]
    for path in remaining[:8]:
        path.unlink()
    fail_open["n"] = 1
    for _ in range(16):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        if not any(path.exists() for path in sidecars):
            break
    assert not any(path.exists() for path in sidecars)


def _seed_large_foreign_stage(
    layout: DurableLayout,
    *,
    artifact_id: UUID,
    token: str,
    payload_path: Path,
    foreign_count: int = 239,
    repository_id: UUID = REPOSITORY_ID,
) -> Path:
    ready = artifact_ready_path(layout, repository_id, artifact_id)
    ready.parent.mkdir(parents=True, exist_ok=True)
    stage = ready.parent / unlink_stage_dir_name(artifact_id=artifact_id, token=token)
    stage.mkdir()
    os.chmod(stage, 0o700)
    os.link(payload_path, stage / "final-match")
    for index in range(foreign_count):
        (stage / f"final-x{index:03d}").write_bytes(b"foreign")
    return stage


def test_active_intent_large_stage_does_not_starve_later_receipt(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    st = ready.stat()
    seed_bytes_delete_intent(
        mutation_store,
        artifact_id=ARTIFACT_ID,
        repository_id=REPOSITORY_ID,
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        phase="quarantined",
        generation="intent1",
    )
    stage = _seed_large_foreign_stage(
        layout, artifact_id=ARTIFACT_ID, token="toki", payload_path=ready
    )
    ready.unlink()
    seed_artifact(mutation_store, artifact_id=OTHER_ARTIFACT_ID)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=OTHER_ARTIFACT_ID,
        generation="g1",
    )
    write_ready(layout, artifact_id=OTHER_ARTIFACT_ID).unlink()

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(
        layout,
        store,
        mutation_store,
        ttl=3600,
        clock=datetime(2026, 8, 1, 0, 30, tzinfo=UTC),
    )
    receipt_cleared = False
    for _ in range(24):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        later = mutation_store.get_artifact_lifecycle(OTHER_ARTIFACT_ID)
        assert later is not None
        if later.bytes_deleted_receipt_generation is None:
            receipt_cleared = True
            break
    assert receipt_cleared
    assert stage.is_dir()


def test_stamped_large_stage_does_not_starve_later_receipt(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    st = ready.stat()
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=ARTIFACT_ID,
        generation="g1",
        dev=int(st.st_dev),
        ino=int(st.st_ino),
    )
    enqueue(store, key="stamped-protected", operation_id=OPERATION_ID)
    stage = _seed_large_foreign_stage(
        layout, artifact_id=ARTIFACT_ID, token="toks", payload_path=ready
    )
    ready.unlink()
    seed_artifact(mutation_store, artifact_id=OTHER_ARTIFACT_ID)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=OTHER_ARTIFACT_ID,
        generation="g2",
    )
    write_ready(layout, artifact_id=OTHER_ARTIFACT_ID).unlink()

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    receipt_cleared = False
    for _ in range(24):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        later = mutation_store.get_artifact_lifecycle(OTHER_ARTIFACT_ID)
        assert later is not None
        if later.bytes_deleted_receipt_generation is None:
            receipt_cleared = True
            break
    assert receipt_cleared
    assert stage.is_dir()


def test_oversize_stage_skip_cache_evicts_oldest_keys(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    stages: list[Path] = []
    for index in range(65):
        artifact_id = UUID(int=60_000 + index)
        seed_artifact(mutation_store, artifact_id=artifact_id)
        ready = write_ready(layout, artifact_id=artifact_id)
        st = ready.stat()
        seed_bytes_delete_intent(
            mutation_store,
            artifact_id=artifact_id,
            repository_id=REPOSITORY_ID,
            dev=int(st.st_dev),
            ino=int(st.st_ino),
            phase="quarantined",
            generation=f"osi{index:02d}",
        )
        stages.append(
            _seed_large_foreign_stage(
                layout,
                artifact_id=artifact_id,
                token=f"t{index:02d}",
                payload_path=ready,
                foreign_count=80,
            )
        )
        ready.unlink()

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    counts = _count_housekeeping_yields(monkeypatch)
    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(
        layout,
        store,
        mutation_store,
        ttl=3600,
        clock=datetime(2026, 8, 1, 0, 30, tzinfo=UTC),
    )
    max_keys = 0
    paused = False
    for _ in range(250):
        for key in counts:
            counts[key] = 0
        events.clear()
        instance.sweep_once()
        _assert_housekeeping_bounded(events, counts)
        key_n = len(instance._oversize_stage_keys)
        max_keys = max(max_keys, key_n)
        assert key_n <= 64
        if any(
            event.get("cleanup_outcome") == "unlink_stage_scan_truncated"
            for event in events
        ):
            paused = True
        if paused and max_keys == 64:
            break
    assert paused
    assert max_keys == 64
    assert len(instance._oversize_stage_keys) <= 64
    assert all(stage.is_dir() for stage in stages)


def test_receipt_poison_page_advances_raw_cursor_to_later_row(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    ids = sorted((UUID(int=index) for index in range(1, 66)), key=str)
    poison_ids = ids[:64]
    legal_id = ids[64]
    for poison_id in poison_ids:
        seed_artifact(mutation_store, artifact_id=poison_id)
        seed_bytes_deleted_receipt(
            mutation_store,
            artifact_id=poison_id,
            generation="",
        )
    seed_artifact(mutation_store, artifact_id=legal_id)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=legal_id,
        generation="g1",
    )
    write_ready(layout, artifact_id=legal_id).unlink()

    page = mutation_store.list_artifacts_with_bytes_deleted_receipt(limit=64)
    assert page.scanned == 64
    assert page.records == []
    assert page.cursor_artifact_id == str(poison_ids[-1])

    rest = mutation_store.list_artifacts_with_bytes_deleted_receipt(
        limit=64,
        after_artifact_id=page.cursor_artifact_id,
    )
    assert rest.scanned == 1
    assert len(rest.records) == 1
    assert rest.records[0].artifact_id == legal_id

    instance = cleaner(layout, store, mutation_store)
    instance.sweep_once()
    first = mutation_store.get_artifact_lifecycle(legal_id)
    assert first is not None
    assert first.bytes_deleted_receipt_generation is not None
    for _ in range(4):
        instance.sweep_once()
        later = mutation_store.get_artifact_lifecycle(legal_id)
        assert later is not None
        if later.bytes_deleted_receipt_generation is None:
            break
    later = mutation_store.get_artifact_lifecycle(legal_id)
    assert later is not None
    assert later.bytes_deleted_receipt_generation is None
    assert later.bytes_deleted_at is not None


def test_receipt_malformed_artifact_id_advances_raw_cursor_and_charges_budget(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    poison_ids = [f"000-poison-{index:02d}" for index in range(64)]
    legal_id = ARTIFACT_ID
    with mutation_store._lock:
        for poison_id in poison_ids:
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
                    bytes_deleted_at,
                    bytes_deleted_receipt_dev,
                    bytes_deleted_receipt_ino,
                    bytes_deleted_receipt_generation,
                    cleanup_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, (
                    SELECT COALESCE(MAX(cleanup_seq), 0) + 1 FROM artifact_lifecycle
                ))
                """,
                (
                    poison_id,
                    REPOSITORY_ID.hex,
                    MEDIA_TYPE,
                    len(ARTIFACT_PAYLOAD),
                    SHA256,
                    CREATED_AT,
                    CREATED_AT,
                    CREATED_AT,
                    1,
                    1,
                    "g1",
                ),
            )
        mutation_store._connection.commit()
    seed_artifact(mutation_store, artifact_id=legal_id)
    seed_bytes_deleted_receipt(
        mutation_store,
        artifact_id=legal_id,
        generation="g1",
    )
    write_ready(layout, artifact_id=legal_id).unlink()

    page = mutation_store.list_artifacts_with_bytes_deleted_receipt(limit=64)
    assert page.scanned == 64
    assert page.records == []
    assert page.cursor_artifact_id == poison_ids[-1]

    rest = mutation_store.list_artifacts_with_bytes_deleted_receipt(
        limit=64,
        after_artifact_id=page.cursor_artifact_id,
    )
    assert rest.scanned == 1
    assert len(rest.records) == 1
    assert rest.records[0].artifact_id == legal_id

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    instance = cleaner(layout, store, mutation_store)
    instance.sweep_once()
    bounded = [
        event
        for event in events
        if event.get("cleanup_outcome") == "housekeeping_bounded"
    ]
    assert len(bounded) == 1
    used = bounded[0]["in_use"]
    assert isinstance(used, int)
    assert used == 64
    first = mutation_store.get_artifact_lifecycle(legal_id)
    assert first is not None
    assert first.bytes_deleted_receipt_generation is not None
    for _ in range(4):
        instance.sweep_once()
        later = mutation_store.get_artifact_lifecycle(legal_id)
        assert later is not None
        if later.bytes_deleted_receipt_generation is None:
            break
    later = mutation_store.get_artifact_lifecycle(legal_id)
    assert later is not None
    assert later.bytes_deleted_receipt_generation is None
    assert later.bytes_deleted_at is not None


def test_leftover_sidecar_in_other_repository_is_retained(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    foreign = write_ready(layout, repository_id=OTHER_REPOSITORY_ID)
    st = foreign.stat()
    sidecar = foreign.parent / quarantine_name_for(
        inode=int(st.st_ino),
        artifact_id=ARTIFACT_ID,
        generation="g1",
    )
    os.link(foreign, sidecar)
    foreign.unlink()

    cleaner(
        layout,
        store,
        mutation_store,
        ttl=3600,
        clock=datetime(2026, 8, 1, 0, 30, tzinfo=UTC),
    ).sweep_once()

    assert sidecar.is_file()
    assert sidecar.read_bytes() == ARTIFACT_PAYLOAD
    lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert lifecycle is not None
    assert lifecycle.bytes_deleted_at is None


def test_production_src_has_no_deleted_cleanup_writers() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    forbidden = (
        "begin_artifact_bytes_delete_intent",
        "insert_artifact_residual",
        "remove_empty_stage_dir_if_same_inode",
        "_list_artifact_unlink_stages",
        "_stage_dir_is_empty",
        "list_unlink_stage_dir_names",
    )
    hits: list[str] = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text):
                hits.append(f"{path.relative_to(src)}:{name}")
    import_store = (
        src / "gateway_repository_service" / "versioned_import" / "store.py"
    )
    text = import_store.read_text(encoding="utf-8")
    if re.search(
        r"(?<![A-Za-z0-9_])def list_artifacts_with_bytes_deleted_receipt(?![A-Za-z0-9_])",
        text,
    ):
        hits.append("versioned_import/store.py:list_artifacts_with_bytes_deleted_receipt")
    assert hits == []


@pytest.mark.serial
def test_admission_pin_blocks_cleaner_thread_until_released(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gateway_repository_service import artifact_cleanup

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="pin-thread")
    outcomes: list[str] = []
    original = artifact_cleanup.cleanup_ready_artifact_bytes

    def wrapped(
        pinned_store: ImportOperationStore,
        pinned_layout: DurableLayout,
        *,
        repository_id: UUID,
        artifact_id: UUID,
        ttl_seconds: int,
        deleted_at: str | None = None,
        recheck: Callable[[], bool] | None = None,
    ) -> str:
        result = original(
            pinned_store,
            pinned_layout,
            repository_id=repository_id,
            artifact_id=artifact_id,
            ttl_seconds=ttl_seconds,
            deleted_at=deleted_at,
            recheck=recheck,
        )
        outcomes.append(result)
        return result

    monkeypatch.setattr(artifact_cleanup, "cleanup_ready_artifact_bytes", wrapped)
    file_fd = os.open(ready, os.O_RDONLY)
    try:
        fcntl.flock(file_fd, fcntl.LOCK_EX)
        instance = cleaner(layout, store, mutation_store, interval=60)
        instance.start()
        try:
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not outcomes:
                time.sleep(0.01)
            assert outcomes == ["busy"]
            assert ready.is_file()
            lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
            assert lifecycle is not None
            assert lifecycle.bytes_deleted_at is None
            fcntl.flock(file_fd, fcntl.LOCK_UN)
            instance.notify()
            gone_deadline = time.monotonic() + 2.0
            while time.monotonic() < gone_deadline and ready.exists():
                time.sleep(0.01)
            assert not ready.exists()
            lifecycle = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
            assert lifecycle is not None
            assert lifecycle.bytes_deleted_at is not None
        finally:
            instance.stop(timeout=2.0)
    finally:
        os.close(file_fd)


@pytest.mark.serial
def test_cleanup_failure_retries_after_interval_fallback(
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

    original = cleanup_mod._unlink_ready_name

    def fail_once(name: str, *, dir_fd: int) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            first_failure.set()
            raise OSError(errno.EIO, "injected I/O failure")
        original(name, dir_fd=dir_fd)

    monkeypatch.setattr(cleanup_mod, "_unlink_ready_name", fail_once)
    instance = cleaner(layout, store, mutation_store, ttl=1, interval=1)
    instance.start()
    try:
        assert first_failure.wait(timeout=2.0)
        assert ready.is_file()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and ready.exists():
            time.sleep(0.01)
        assert not ready.exists()
        assert calls["n"] == 2
    finally:
        instance.stop(timeout=2.0)


@pytest.mark.serial
def test_join_timeout_raises(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
) -> None:
    store, mutation_store = stores
    hang = threading.Event()
    instance = cleaner(layout, store, mutation_store, interval=60)

    def hanging_sweep() -> None:
        hang.wait(timeout=5.0)

    setattr(instance, "_sweep", hanging_sweep)
    instance.start()
    try:
        with pytest.raises(ArtifactCleanerShutdownError):
            instance.stop(timeout=0.05)
    finally:
        hang.set()
        thread = instance._thread  # noqa: SLF001
        if thread is not None and thread.is_alive():
            with instance._condition:  # noqa: SLF001
                instance._stopping = True  # noqa: SLF001
                instance._pending = True  # noqa: SLF001
                instance._condition.notify_all()  # noqa: SLF001
            thread.join(timeout=2.0)
            instance._thread = None  # noqa: SLF001
            instance._started = False  # noqa: SLF001
