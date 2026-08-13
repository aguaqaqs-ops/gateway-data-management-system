"""Round 22 probes: shared SQLite tx, root freeze, retain unwind, control isolation."""

from __future__ import annotations

import os
import signal
import socket
import sqlite3
import stat
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from gateway_repository_service.artifact_broker import (
    ArtifactBrokerError,
    SocketArtifactDirBroker,
    set_artifact_broker,
)
from gateway_repository_service.artifact_broker_server import dir_lock_table_size, serve
from gateway_repository_service.artifact_layout import prepare_artifact_layout
from gateway_repository_service.artifact_root import ArtifactRootError
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.locking import DurableRootLock, RootLockBusy
from gateway_repository_service.mutation_store import MutationStore
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from gateway_repository_service.upload_artifact.admission_pin import (
    StageDirStatus,
    lookup_unlink_stage_dir,
    unlink_stage_dir_name,
)
from gateway_repository_service.versioned_import.admin import main as admin_main
from gateway_repository_service.versioned_import.store import ImportOperationStore
from support.lifecycle_harness import lifecycle_settings
from test_artifact_cleanup import (
    ARTIFACT_ID,
    CREATED_AT,
    MEDIA_TYPE,
    REPOSITORY_ID,
    SHA256,
    _insert_residual,
    _seed_artifact,
    _seed_create_succeeded,
    _sweep,
    _write_ready,
)

REPO_ID = REPOSITORY_ID


def _serve_broker(socket_path: Path, artifacts_root: Path, stop: threading.Event) -> None:
    serve(
        socket_path,
        expected_peer_uid=os.getuid(),
        artifacts_root=artifacts_root,
        stop=stop,
    )


@pytest.fixture
def bound_socket_broker(tmp_path: Path) -> Iterator[SocketArtifactDirBroker]:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    sock = tmp_path / "run" / "artifact-broker.sock"
    sock.parent.mkdir()
    stop = threading.Event()
    thread = threading.Thread(
        target=_serve_broker, args=(sock, artifacts, stop), daemon=True, name="r22-broker"
    )
    thread.start()
    deadline = time.monotonic() + 2.0
    control_sock = sock.parent / f"{sock.stem}-control.sock"
    while time.monotonic() < deadline and not (sock.exists() and control_sock.exists()):
        time.sleep(0.01)
    assert sock.exists() and control_sock.exists()
    broker = SocketArtifactDirBroker(sock)
    broker.ping()
    broker.bind()
    set_artifact_broker(broker)
    try:
        yield broker
    finally:
        stop.set()
        thread.join(timeout=2.0)
        set_artifact_broker(None)


def test_r22_residual_commit_does_not_commit_foreign_transaction(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    DurableLayout.create_service(settings.data_root)
    control = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    try:
        mutation = MutationStore(control.connection, transaction_lock=control.transaction_lock)
        store = ImportOperationStore(control.connection, transaction_lock=control.transaction_lock)
        _seed_create_succeeded(mutation)
        _seed_artifact(mutation)
        ready = threading.Event()
        errors: list[BaseException] = []

        def thread_a() -> None:
            try:
                mutation._lock.acquire()
                control.connection.execute("BEGIN IMMEDIATE")
                control.connection.execute(
                    "UPDATE artifact_lifecycle SET media_type = 'stolen' WHERE artifact_id = ?",
                    (str(ARTIFACT_ID),),
                )
                ready.set()
                time.sleep(0.2)
                control.connection.rollback()
            except BaseException as exc:
                errors.append(exc)
            finally:
                try:
                    mutation._lock.release()
                except RuntimeError:
                    pass

        def thread_b() -> None:
            try:
                assert ready.wait(timeout=2.0)
                store.insert_artifact_residual(
                    ARTIFACT_ID,
                    repository_id=REPO_ID,
                    kind="deleting",
                    name="sidecar",
                    parent_name="",
                    dev=1,
                    ino=2,
                    generation="g",
                    created_at=CREATED_AT,
                )
            except BaseException as exc:
                errors.append(exc)

        workers = [threading.Thread(target=thread_a), threading.Thread(target=thread_b)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5.0)
        assert errors == []
        row = control.connection.execute(
            "SELECT media_type FROM artifact_lifecycle WHERE artifact_id = ?",
            (str(ARTIFACT_ID),),
        ).fetchone()
        assert row is not None
        value_after_forced_rollback = 1 if str(row[0]) == "stolen" else 0
        residuals = store.list_artifact_residuals(artifact_id=ARTIFACT_ID)
        print(
            {
                "value_after_forced_rollback": value_after_forced_rollback,
                "residuals": residuals.scanned,
                "errors": errors,
            }
        )
        assert value_after_forced_rollback == 0
        assert residuals.scanned == 1
    finally:
        control.close()


def test_r22_artifacts_root_symlink_and_bind_mount_leave_target(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    data_root.mkdir()
    real_artifacts = tmp_path / "external-artifacts"
    real_artifacts.mkdir()
    marker = real_artifacts / "keep"
    marker.write_text("payload", encoding="utf-8")
    os.chmod(real_artifacts, 0o700)
    before = real_artifacts.stat()
    artifacts = data_root / "artifacts"
    artifacts.symlink_to(real_artifacts)
    with pytest.raises(ArtifactRootError):
        prepare_artifact_layout(
            data_root=data_root,
            run_dir=data_root / "run",
            artifacts=artifacts,
            broker_uid=os.getuid(),
            gateway_gid=os.getgid(),
        )
    after = real_artifacts.stat()
    assert after.st_uid == before.st_uid
    assert after.st_gid == before.st_gid
    assert stat.S_IMODE(after.st_mode) == stat.S_IMODE(before.st_mode)
    assert marker.read_text(encoding="utf-8") == "payload"
    assert artifacts.is_symlink()

    ancestor = tmp_path / "link-parent"
    ancestor.symlink_to(data_root)
    with pytest.raises(ArtifactRootError):
        prepare_artifact_layout(
            data_root=ancestor / "nested",
            run_dir=ancestor / "nested" / "run",
            artifacts=ancestor / "nested" / "artifacts",
            broker_uid=os.getuid(),
            gateway_gid=os.getgid(),
        )

    mounted = tmp_path / "data-root-bind" / "artifacts"
    mounted.parent.mkdir()
    mounted.mkdir()
    bind_target = tmp_path / "bind-target"
    bind_target.mkdir()
    bind_marker = bind_target / "keep"
    bind_marker.write_text("bind-payload", encoding="utf-8")
    os.chmod(bind_target, 0o700)
    before_bind = bind_target.stat()
    mounted_ok = subprocess.run(
        ["mount", "--bind", str(bind_target), str(mounted)],
        check=False,
        capture_output=True,
        text=True,
    )
    if mounted_ok.returncode != 0:
        pytest.skip(f"bind-mount unavailable: {mounted_ok.stderr.strip()}")
    try:
        with pytest.raises(ArtifactRootError):
            prepare_artifact_layout(
                data_root=mounted.parent,
                run_dir=mounted.parent / "run",
                artifacts=mounted,
                broker_uid=os.getuid(),
                gateway_gid=os.getgid(),
            )
        after_bind = bind_target.stat()
        assert after_bind.st_uid == before_bind.st_uid
        assert after_bind.st_gid == before_bind.st_gid
        assert stat.S_IMODE(after_bind.st_mode) == stat.S_IMODE(before_bind.st_mode)
        assert bind_marker.read_text(encoding="utf-8") == "bind-payload"
        errors: list[BaseException] = []

        def _serve_bind() -> None:
            try:
                serve(
                    tmp_path / "bind-broker.sock",
                    expected_peer_uid=os.getuid(),
                    artifacts_root=mounted,
                    stop=threading.Event(),
                )
            except ArtifactRootError as exc:
                errors.append(exc)
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=_serve_bind, daemon=True)
        worker.start()
        worker.join(timeout=2.0)
        assert any(isinstance(item, ArtifactRootError) for item in errors)
    finally:
        subprocess.run(["umount", str(mounted)], check=False, capture_output=True)


@pytest.mark.serial
def test_r22_startup_join_timeout_retains_lock_and_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tmp_path / "data-root" / "artifacts"
    artifacts.mkdir(parents=True)
    sock = tmp_path / "brk.sock"
    control = tmp_path / "brk-control.sock"
    script = tmp_path / "stall.py"
    script.write_text(
        "\n".join(
            [
                "import os, signal, sys",
                "from pathlib import Path",
                "from threading import Event",
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)",
                "sys.path.insert(0, os.environ['PYTHONPATH'].split(':')[0])",
                "from gateway_repository_service.artifact_broker_server import serve",
                f"serve(Path({str(sock)!r}), expected_peer_uid=os.getuid(), "
                f"artifacts_root=Path({str(artifacts)!r}), stop=None, "
                f"control_socket_path=Path({str(control)!r}))",
            ]
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    src = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = str(src) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.Popen([sys.executable, str(script)], env=env)
    pidfile = tmp_path / "brk.pid"
    pidfile.write_text(str(proc.pid), encoding="utf-8")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not (sock.exists() and control.exists()):
        time.sleep(0.05)
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_MODE", "socket")
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET", str(sock))
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_CONTROL_SOCKET", str(control))
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE", str(pidfile))
    monkeypatch.setattr(
        "gateway_repository_service.runtime._retain_startup_ownership",
        lambda: None,
    )

    class _Gate:
        @classmethod
        def verify(cls, settings: object, layout: object) -> "_Gate":
            del settings, layout
            return cls()

    class _Reconcile:
        blocking_failures: tuple[str, ...] = ()
        consistency_watch = None

        def reconcile(self) -> "_Reconcile":
            return self

    class _Blocked:
        blocking_failures = ("forced reconcile failure",)

        def reconcile(self) -> "_Blocked":
            return self

    monkeypatch.setattr(
        "gateway_repository_service.runtime.DoltRunner",
        lambda settings, root: object(),
    )
    monkeypatch.setattr(
        "gateway_repository_service.runtime.OfflineCliCapabilityGate",
        _Gate,
    )
    monkeypatch.setattr(
        "gateway_repository_service.runtime.SynchronousMutationReconciler",
        lambda **_kwargs: _Reconcile(),
    )
    monkeypatch.setattr(
        "gateway_repository_service.runtime.ImportStartupReconciler",
        lambda **_kwargs: _Blocked(),
    )
    settings = lifecycle_settings(tmp_path)
    settings = settings.model_copy(update={"import_shutdown_grace_seconds": 0.2})
    try:
        with pytest.raises(ServiceStartupError):
            ServiceRuntime.start(settings)
        layout = DurableLayout.bind_existing(settings.data_root)
        with pytest.raises(RootLockBusy):
            DurableRootLock(layout.service_lock).acquire()
    finally:
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=2.0)


@pytest.mark.serial
def test_r22_partial_frames_do_not_starve_control(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    sock = tmp_path / "run" / "artifact-broker.sock"
    stuck: list[socket.socket] = []
    try:
        for _ in range(128):
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(0.5)
            try:
                conn.connect(str(sock))
            except OSError:
                conn.close()
                continue
            try:
                conn.sendall(struct.pack("!I", 64))
            except OSError:
                conn.close()
                continue
            stuck.append(conn)
        started = time.monotonic()
        bound_socket_broker.ping()
        bound_socket_broker.assert_bound()
        elapsed = time.monotonic() - started
        print({"partial_connections": len(stuck), "control_ping_s": elapsed})
        assert elapsed < 2.0
    finally:
        for conn in stuck:
            conn.close()


@pytest.mark.serial
def test_r22_dir_locks_release_src_inodes(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    artifacts = tmp_path / "artifacts"
    key = repository_key(REPO_ID)
    artifacts_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(artifacts_fd, key, mode=0o750)
    finally:
        os.close(artifacts_fd)
    repo_fd = os.open(artifacts / key, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(repo_fd, "ready", mode=0o750)
    finally:
        os.close(repo_fd)
    ready = artifacts / key / "ready"
    before = dir_lock_table_size()
    for i in range(32):
        name = f"{uuid4().hex}"
        path = ready / name
        path.write_bytes(b"x")
        st = path.stat()
        ready_fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
        try:
            bound_socket_broker.unlink_if_match(
                ready_fd, name, expected_dev=int(st.st_dev), expected_ino=int(st.st_ino)
            )
        except ArtifactBrokerError:
            pass
        finally:
            os.close(ready_fd)
    after = dir_lock_table_size()
    print({"lock_table_before": before, "lock_table_after": after})
    assert after <= before + 2

    src_dir = tmp_path / "src-inodes"
    src_dir.mkdir()
    ready_fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
    try:
        before_link = dir_lock_table_size()
        for i in range(16):
            src = src_dir / f"{i:032x}"
            src.write_bytes(b"src")
            src_fd = os.open(src, os.O_RDONLY)
            try:
                bound_socket_broker.link_from_fd(ready_fd, f"{i:032x}", src_fd)
            finally:
                os.close(src_fd)
        after_link = dir_lock_table_size()
    finally:
        os.close(ready_fd)
    print({"lock_table_before_link": before_link, "lock_table_after_link": after_link})
    assert after_link <= before_link + 2


def test_r22_stage_parent_matrix_only_enoent_clears_proof(
    tmp_path: Path,
) -> None:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_service(settings.data_root)
    control = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(control.connection, transaction_lock=control.transaction_lock)
    mutation = MutationStore(control.connection, transaction_lock=control.transaction_lock)
    try:
        _seed_create_succeeded(mutation)
        _seed_artifact(mutation)
        ready_file = _write_ready(layout)
        ready = ready_file.parent
        stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="m")
        ready_fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
        try:
            absent = lookup_unlink_stage_dir(ready_fd, stage_name)
            assert absent.status is StageDirStatus.ABSENT
            (ready / "not-a-dir").write_bytes(b"x")
            mismatch = lookup_unlink_stage_dir(ready_fd, "not-a-dir")
            assert mismatch.status is StageDirStatus.MISMATCH
            link = ready / "stage-link"
            link.symlink_to(ready)
            linked = lookup_unlink_stage_dir(ready_fd, link.name)
            assert linked.status is StageDirStatus.MISMATCH
        finally:
            os.close(ready_fd)

        _insert_residual(
            store, kind="stage_child", name="victim-absent", parent_name=stage_name, dev=1, ino=2
        )
        _sweep(store, mutation, layout)
        names = {row.name for row in store.list_artifact_residuals(artifact_id=ARTIFACT_ID).records}
        assert "victim-absent" not in names

        link = ready / "stage-link"
        _insert_residual(
            store,
            kind="stage_child",
            name="victim-symlink",
            parent_name=link.name,
            dev=1,
            ino=3,
        )
        _sweep(store, mutation, layout)
        names = {row.name for row in store.list_artifact_residuals(artifact_id=ARTIFACT_ID).records}
        assert "victim-symlink" in names

        _insert_residual(
            store,
            kind="stage_child",
            name="victim-file",
            parent_name="not-a-dir",
            dev=1,
            ino=4,
        )
        _sweep(store, mutation, layout)
        names = {row.name for row in store.list_artifact_residuals(artifact_id=ARTIFACT_ID).records}
        assert "victim-file" in names

        _insert_residual(
            store,
            kind="deleting",
            name="gone-sidecar",
            dev=1,
            ino=2,
            generation="g1",
        )
        _sweep(store, mutation, layout)
        names = {row.name for row in store.list_artifact_residuals(artifact_id=ARTIFACT_ID).records}
        assert "gone-sidecar" not in names
        assert "victim-symlink" in names
        assert "victim-file" in names
    finally:
        control.close()


def test_r22_malformed_residual_page_reaches_successor(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_service(settings.data_root)
    control = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    store = ImportOperationStore(control.connection, transaction_lock=control.transaction_lock)
    mutation = MutationStore(control.connection, transaction_lock=control.transaction_lock)
    try:
        _seed_create_succeeded(mutation)
        _seed_artifact(mutation)
        with mutation._lock:
            for i in range(64):
                mutation._connection.execute(
                    """
                    INSERT INTO artifact_residual (
                        artifact_id, repository_scope, kind, name, parent_name,
                        dev, ino, generation, created_at
                    ) VALUES (?, ?, 'deleting', ?, '', 1, ?, NULL, ?)
                    """,
                    (f"not-a-uuid-{i}", "not-hex", f"poison-{i}", i + 1, CREATED_AT),
                )
            mutation._connection.commit()
        _insert_residual(store, kind="deleting", name="legal-successor", dev=1, ino=99)
        page = store.list_artifact_residuals(limit=64)
        assert page.scanned == 64
        assert page.records == []
        assert page.cursor_residual_id is not None
        second = store.list_artifact_residuals(limit=64, after_residual_id=page.cursor_residual_id)
        assert any(row.name == "legal-successor" for row in second.records)
        _write_ready(layout)
        _sweep(store, mutation, layout)
        names = {row.name for row in store.list_artifact_residuals(artifact_id=ARTIFACT_ID).records}
        assert "legal-successor" not in names
        poison = store.list_artifact_residuals(limit=64)
        assert poison.scanned == 64
        assert poison.records == []
    finally:
        control.close()


def test_r22_v15_migrates_null_blob_cleanup_seq_and_pages(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    DurableLayout.create_service(settings.data_root)
    v14 = ControlStore.open(
        settings.control_db_path,
        expected_version=14,
        busy_timeout_ms=1000,
    )
    try:
        v14.connection.execute("DROP TRIGGER IF EXISTS artifact_lifecycle_assign_cleanup_seq")
        for i in range(32):
            v14.connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id, repository_scope, media_type, size_bytes,
                    raw_sha256, created_at, updated_at, cleanup_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    f"not-a-uuid-null-{i}",
                    "not-hex",
                    MEDIA_TYPE,
                    1,
                    "a" * 64,
                    CREATED_AT,
                    CREATED_AT,
                ),
            )
        for i in range(32):
            v14.connection.execute(
                """
                INSERT INTO artifact_lifecycle (
                    artifact_id, repository_scope, media_type, size_bytes,
                    raw_sha256, created_at, updated_at, cleanup_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"not-a-uuid-blob-{i}",
                    "not-hex",
                    MEDIA_TYPE,
                    1,
                    "a" * 64,
                    CREATED_AT,
                    CREATED_AT,
                    sqlite3.Binary(f"blob-seq-{i}".encode()),
                ),
            )
        successor = ARTIFACT_ID
        v14.connection.execute(
            """
            INSERT INTO artifact_lifecycle (
                artifact_id, repository_scope, media_type, size_bytes,
                raw_sha256, created_at, updated_at, cleanup_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1000)
            """,
            (
                str(successor),
                REPO_ID.hex,
                MEDIA_TYPE,
                1,
                SHA256,
                CREATED_AT,
                CREATED_AT,
            ),
        )
        v14.connection.commit()
    finally:
        v14.close()

    control = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    try:
        mutation = MutationStore(control.connection, transaction_lock=control.transaction_lock)
        first = mutation.list_artifacts_pending_byte_cleanup(limit=64)
        assert first.scanned == 64
        assert first.cursor_cleanup_seq is not None
        assert all(record.artifact_id != ARTIFACT_ID for record in first.records)
        second = mutation.list_artifacts_pending_byte_cleanup(
            limit=64, after_cleanup_seq=first.cursor_cleanup_seq
        )
        assert any(record.artifact_id == ARTIFACT_ID for record in second.records)
        seqs = [
            int(row[0])
            for row in control.connection.execute(
                "SELECT cleanup_seq FROM artifact_lifecycle ORDER BY cleanup_seq"
            ).fetchall()
        ]
        assert all(seq > 0 for seq in seqs)
        with pytest.raises(sqlite3.IntegrityError):
            control.connection.execute(
                "UPDATE artifact_lifecycle SET cleanup_seq = cleanup_seq + 1"
            )
    finally:
        control.close()


def test_r22_adopt_residual_is_rejected(tmp_path: Path) -> None:
    settings = lifecycle_settings(tmp_path)
    DurableLayout.create_service(settings.data_root)
    ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    ).close()
    with pytest.raises(SystemExit):
        admin_main(
            [
                "adopt-residual",
                "--artifact-id",
                str(ARTIFACT_ID),
                "--repository-id",
                str(REPO_ID),
                "--kind",
                "deleting",
                "--name",
                "forged",
                "--dev",
                "1",
                "--ino",
                "2",
                "--data-root",
                str(settings.data_root),
            ]
        )
    control = ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    )
    try:
        page = MutationStore(control.connection).list_artifact_residuals()
        assert page.scanned == 0
        audits = control.connection.execute(
            "SELECT COUNT(*) FROM repository_import_recovery_audit"
        ).fetchone()
        assert audits is not None
        assert int(audits[0]) == 0
    finally:
        control.close()
