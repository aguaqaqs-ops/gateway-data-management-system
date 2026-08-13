"""Contract tests for the cooperative artifact cleaner."""

from __future__ import annotations

import errno
import fcntl
import os
import re
import stat
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gateway_repository_service.artifact_cleaner import (
    ArtifactCleanerShutdownError,
    classify_ready_artifact_path,
)
from gateway_repository_service.artifact_retention import retention_explains_missing_ready_bytes
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.mutation_store import MutationStore
from gateway_repository_service.upload_artifact.admission_pin import OwnedPathError
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
    instance.sweep_once()
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
    assert (stage / "victim").is_file()
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
    assert used <= 64
    remaining = [path for path in sidecars if path.exists()]
    assert remaining
    assert len(remaining) < 80 or used <= 64
    assert not candidate.exists()
    leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert leftover is not None
    assert leftover.bytes_deleted_at is None

    for _ in range(8):
        instance.sweep_once()
        if not any(path.exists() for path in sidecars):
            break
    assert not any(path.exists() for path in sidecars)
    leftover = mutation_store.get_artifact_lifecycle(ARTIFACT_ID)
    assert leftover is not None
    assert leftover.bytes_deleted_at is not None


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
    assert page.cursor_artifact_id == poison_ids[-1]

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
