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
    CREATED_AT,
    OPERATION_ID,
    OTHER_ARTIFACT_ID,
    OTHER_REPOSITORY_ID,
    REPOSITORY_ID,
    BASE_NOW,
    cleaner,
    enqueue,
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


@pytest.mark.parametrize(
    ("legacy_name", "is_dir"),
    [
        (f".deleting-123-g1-{ARTIFACT_ID.hex}", False),
        (f".detach-123-g1-{ARTIFACT_ID.hex}", False),
        (f".unlink-verify-123-g1-{ARTIFACT_ID.hex}-tok1", False),
        (f".unlink-stage-{ARTIFACT_ID.hex}-tok1", True),
        (".deleting-not-a-parseable-sidecar", False),
    ],
)
def test_legacy_sidecar_and_stage_names_are_retained_and_diagnosed_as_unknown(
    stores: tuple[ImportOperationStore, MutationStore],
    layout: DurableLayout,
    monkeypatch: pytest.MonkeyPatch,
    legacy_name: str,
    is_dir: bool,
) -> None:
    from gateway_repository_service import artifact_cleaner as cleaner_mod

    store, mutation_store = stores
    seed_create_succeeded(mutation_store)
    seed_artifact(mutation_store)
    ready = write_ready(layout)
    mark_succeeded_consumed(store, key="legacy-unknown")
    legacy_path = ready.parent / legacy_name
    if is_dir:
        legacy_path.mkdir()
        (legacy_path / "victim").write_bytes(b"keep-me")
    else:
        legacy_path.write_bytes(b"keep-me")

    events: list[dict[str, object]] = []

    def capture_log(*args: object, **kwargs: object) -> None:
        del args
        events.append(kwargs)

    monkeypatch.setattr(cleaner_mod, "log_event", capture_log)
    cleaner(layout, store, mutation_store).sweep_once()

    assert not ready.exists()
    assert legacy_path.exists()
    if is_dir:
        assert (legacy_path / "victim").read_bytes() == b"keep-me"
    else:
        assert legacy_path.read_bytes() == b"keep-me"
    assert any(
        event.get("cleanup_outcome") == "unknown_path_inventory"
        for event in events
    )


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


def test_production_src_has_no_deleted_cleanup_writers() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    forbidden = (
        "begin_artifact_bytes_delete_intent",
        "insert_artifact_residual",
        "remove_empty_stage_dir_if_same_inode",
        "_list_artifact_unlink_stages",
        "_stage_dir_is_empty",
        "list_unlink_stage_dir_names",
        "list_artifacts_with_bytes_deleted_receipt",
        "clear_artifact_residual",
        "list_artifact_residuals",
        "clear_artifact_bytes_delete_intent",
        "clear_artifact_bytes_deleted_receipt",
        "parse_any_recoverable_sidecar",
        "parse_unlink_stage_dir_name",
        "destroy_owned_bytes_and_reclaim_names",
        "artifact_residual",
        "bytes_delete_intent_at",
        "bytes_delete_dev",
        "bytes_delete_ino",
        "bytes_delete_phase",
        "bytes_delete_generation",
        "bytes_deleted_receipt_dev",
        "bytes_deleted_receipt_ino",
        "bytes_deleted_receipt_generation",
    )
    hits: list[str] = []
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text):
                hits.append(f"{path.relative_to(src)}:{name}")
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
