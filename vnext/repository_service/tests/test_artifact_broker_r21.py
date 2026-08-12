"""Round 21 broker fd/thread bounds, bind readiness, and residual adoption probes."""

from __future__ import annotations

import array
import gc
import json
import os
import socket
import struct
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway_repository_service.app import create_app
from gateway_repository_service.artifact_broker import (
    ArtifactBrokerError,
    SocketArtifactDirBroker,
    set_artifact_broker,
)
from gateway_repository_service.artifact_broker_server import (
    _IO_RESERVE_THREADS,
    _MAX_WORKER_THREADS,
    serve,
)
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.runtime import ServiceRuntime, ServiceStartupError
from gateway_repository_service.upload_artifact.admission_pin import unlink_stage_dir_name
from gateway_repository_service.versioned_import.admin import _run_adopt_residual
from support.lifecycle_harness import lifecycle_settings

ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c21")
REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c21")


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
        target=_serve_broker,
        args=(sock, artifacts, stop),
        daemon=True,
        name="r21-broker",
    )
    thread.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not sock.exists():
        time.sleep(0.01)
    assert sock.exists()
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


def _fd_count() -> int:
    return len(os.listdir("/proc/self/fd"))


def _broker_threads() -> list[threading.Thread]:
    return [item for item in threading.enumerate() if "artifact-broker" in item.name]


def _rpc(
    sock: Path,
    payload: dict[str, object],
    fds: list[int] | None = None,
    *,
    timeout: float = 2.0,
) -> dict[str, object]:
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(timeout)
    conn.connect(str(sock))
    blob = json.dumps(payload).encode("utf-8")
    header = struct.pack("!I", len(blob)) + blob
    try:
        if fds:
            conn.sendmsg(
                [header],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds).tobytes())],
            )
        else:
            conn.sendall(header)
        hdr = conn.recv(4)
        if len(hdr) < 4:
            return {"ok": False, "error": "short"}
        (length,) = struct.unpack("!I", hdr)
        body = b""
        while len(body) < length:
            chunk = conn.recv(length - len(body))
            if not chunk:
                break
            body += chunk
        parsed: object = json.loads(body.decode("utf-8"))
        assert isinstance(parsed, dict)
        return parsed
    finally:
        conn.close()


def _open_dummy_fds(n: int) -> list[int]:
    fds = [os.open(os.devnull, os.O_RDONLY) for _ in range(n)]
    return fds


@pytest.mark.serial
def test_r21_control_ops_close_extra_fds(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    sock = tmp_path / "run" / "artifact-broker.sock"
    before = _fd_count()
    cases: list[tuple[dict[str, object], int]] = [
        ({"op": "ping"}, 0),
        ({"op": "ping"}, 1),
        ({"op": "ping"}, 8),
        ({"op": "unknown-op"}, 0),
        ({"op": "unknown-op"}, 1),
        ({"op": "unknown-op"}, 8),
        ({"op": "mkdir", "dir_path": "/tmp", "name": "ready"}, 0),
        ({"op": "mkdir", "path": "/tmp", "name": "ready"}, 1),
        ({"op": "shutdown", "src_path": "/tmp"}, 8),
        ({"op": "bind"}, 0),
        ({"op": "assert_bound"}, 1),
        ({"op": "assert_bound"}, 8),
    ]
    for payload, n_fds in cases:
        fds = _open_dummy_fds(n_fds) if n_fds else None
        try:
            _rpc(sock, payload, fds)
        finally:
            for fd in fds or []:
                try:
                    os.close(fd)
                except OSError:
                    pass
    gc.collect()
    after = _fd_count()
    assert after <= before + 2


@pytest.mark.serial
def test_r21_malformed_and_disconnect_close_fds(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    sock = tmp_path / "run" / "artifact-broker.sock"
    before = _fd_count()
    fds = _open_dummy_fds(2)
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(1.0)
    conn.connect(str(sock))
    conn.sendmsg(
        [b"{not-json"],
        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds).tobytes())],
    )
    conn.close()
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass

    fds = _open_dummy_fds(1)
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(1.0)
    conn.connect(str(sock))
    conn.sendmsg(
        [struct.pack("!I", 4)],
        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds).tobytes())],
    )
    conn.close()
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass

    fds = _open_dummy_fds(1)
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(0.2)
    conn.connect(str(sock))
    conn.sendmsg(
        [struct.pack("!I", 32)],
        [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds).tobytes())],
    )
    time.sleep(0.3)
    conn.close()
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass
    gc.collect()
    after = _fd_count()
    assert after <= before + 2


@pytest.mark.serial
def test_r21_10k_rpc_returns_to_fd_thread_baseline(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    for _ in range(64):
        bound_socket_broker.ping()
    gc.collect()
    mid_fds = _fd_count()
    mid_threads = len(_broker_threads())
    for _ in range(10_000):
        bound_socket_broker.ping()
        bound_socket_broker.assert_bound()
    gc.collect()
    after_fds = _fd_count()
    after_threads = len(_broker_threads())
    after_alive = sum(1 for item in gc.get_objects() if isinstance(item, threading.Thread) and item.is_alive())
    print(
        f"r21_10k mid_fds={mid_fds} after_fds={after_fds} "
        f"mid_threads={mid_threads} after_threads={after_threads} after_alive={after_alive}"
    )
    assert after_fds <= mid_fds + 4
    assert after_threads <= _MAX_WORKER_THREADS + _IO_RESERVE_THREADS + 4
    assert after_alive <= _MAX_WORKER_THREADS + _IO_RESERVE_THREADS + 16
    assert mid_fds >= 0 and after_fds >= 0
    assert mid_threads >= 0 and after_threads >= 0


@pytest.mark.serial
def test_r21_partial_frames_over_limit_still_serve_bound_ping(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    sock = tmp_path / "run" / "artifact-broker.sock"
    stuck: list[socket.socket] = []
    try:
        for _ in range(_MAX_WORKER_THREADS + 4):
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(2.0)
            for _attempt in range(20):
                try:
                    conn.connect(str(sock))
                    break
                except BlockingIOError:
                    time.sleep(0.01)
            else:
                conn.close()
                continue
            conn.sendall(struct.pack("!I", 64))
            stuck.append(conn)
        assert len(stuck) >= _MAX_WORKER_THREADS
        started = time.monotonic()
        bound_socket_broker.ping()
        bound_socket_broker.assert_bound()
        assert time.monotonic() - started < 2.0
    finally:
        for conn in stuck:
            conn.close()
    gc.collect()
    assert len(_broker_threads()) <= _MAX_WORKER_THREADS + _IO_RESERVE_THREADS + 4


@pytest.mark.serial
def test_r21_concurrent_unlink_does_not_drop_replacement(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    artifacts = tmp_path / "artifacts"
    key = repository_key(REPO_ID)
    artifacts_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(artifacts_fd, key, mode=0o750)
    finally:
        os.close(artifacts_fd)
    repo = artifacts / key
    repo_fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(repo_fd, "ready", mode=0o750)
    finally:
        os.close(repo_fd)
    ready = repo / "ready"
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="race")
    ready_fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(ready_fd, stage_name, mode=0o750)
    finally:
        os.close(ready_fd)
    stage = ready / stage_name
    original = stage / "victim"
    original.write_bytes(b"old")
    st = original.stat()
    replacement = stage / "final-r21"
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def unlink_old() -> None:
        fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
        try:
            barrier.wait(timeout=2.0)
            bound_socket_broker.unlink_if_match(
                fd, original.name, expected_dev=int(st.st_dev), expected_ino=int(st.st_ino)
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            os.close(fd)

    def rename_replacement() -> None:
        fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
        try:
            barrier.wait(timeout=2.0)
            bound_socket_broker.rename_noreplace(fd, original.name, fd, replacement.name)
        except BaseException as exc:
            errors.append(exc)
        finally:
            os.close(fd)

    workers = [threading.Thread(target=unlink_old), threading.Thread(target=rename_replacement)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5.0)
    assert errors == [] or all(isinstance(item, ArtifactBrokerError) for item in errors)
    if replacement.is_file():
        assert replacement.read_bytes() == b"old"
    elif original.is_file():
        assert original.read_bytes() == b"old"


@pytest.mark.serial
@pytest.mark.integration
def test_r21_helper_restart_loses_bind_and_blocks_readyz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tmp_path / "data-root" / "artifacts"
    artifacts.mkdir(parents=True)
    sock = tmp_path / "brk.sock"
    stop = threading.Event()
    thread = threading.Thread(
        target=_serve_broker, args=(sock, artifacts, stop), daemon=True, name="r21-helper-a"
    )
    thread.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not sock.exists():
        time.sleep(0.01)
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_MODE", "socket")
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET", str(sock))
    settings = lifecycle_settings(tmp_path)
    runtime = ServiceRuntime.start(settings)
    try:
        assert runtime.is_ready()
        stop.set()
        thread.join(timeout=2.0)
        if sock.exists():
            sock.unlink()
        stop2 = threading.Event()
        thread2 = threading.Thread(
            target=_serve_broker, args=(sock, artifacts, stop2), daemon=True, name="r21-helper-b"
        )
        thread2.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not sock.exists():
            time.sleep(0.01)
        rebound = SocketArtifactDirBroker(sock)
        rebound.ping()
        with pytest.raises(ArtifactBrokerError):
            rebound.assert_bound()
        set_artifact_broker(rebound)
        assert not runtime.is_ready()
        assert "artifact directory-broker" in runtime.not_ready_message()
    finally:
        runtime.shutdown()
        stop.set()
        thread.join(timeout=1.0)
        if "stop2" in locals():
            stop2.set()
            thread2.join(timeout=1.0)

    stop2 = threading.Event()
    if sock.exists():
        sock.unlink()
    thread2 = threading.Thread(
        target=_serve_broker, args=(sock, artifacts, stop2), daemon=True, name="r21-helper-c"
    )
    thread2.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not sock.exists():
        time.sleep(0.01)
    try:
        with TestClient(create_app(settings)) as client:
            runtime = cast(FastAPI, client.app).state.runtime
            assert client.get("/readyz").status_code == 200
            stop2.set()
            thread2.join(timeout=2.0)
            if sock.exists():
                sock.unlink()
            stop3 = threading.Event()
            thread3 = threading.Thread(
                target=_serve_broker,
                args=(sock, artifacts, stop3),
                daemon=True,
                name="r21-helper-d",
            )
            thread3.start()
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline and not sock.exists():
                time.sleep(0.01)
            unbound = SocketArtifactDirBroker(sock)
            unbound.ping()
            set_artifact_broker(unbound)
            readyz = client.get("/readyz")
            assert readyz.status_code == 503
            create = client.post(
                "/v1/repositories",
                headers={
                    "Authorization": "Bearer test-bearer-token",
                    "Idempotency-Key": "r21-unbound",
                },
            )
            assert create.status_code == 503
            pending = runtime.control_store.connection.execute(
                "SELECT COUNT(*) FROM synchronous_mutation_effects WHERE status = 'PENDING'"
            ).fetchone()
            assert int(pending[0]) == 0
            stop3.set()
            thread3.join(timeout=2.0)
    finally:
        stop2.set()
        thread2.join(timeout=1.0)


@pytest.mark.serial
@pytest.mark.integration
def test_r21_startup_reconcile_failure_unwinds_helper_lock_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tmp_path / "data-root" / "artifacts"
    artifacts.mkdir(parents=True)
    sock = tmp_path / "brk.sock"
    stop = threading.Event()
    thread = threading.Thread(
        target=_serve_broker, args=(sock, artifacts, stop), daemon=True, name="r21-unwind"
    )
    thread.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not sock.exists():
        time.sleep(0.01)
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_MODE", "socket")
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET", str(sock))
    settings = lifecycle_settings(tmp_path)

    class _Blocked:
        blocking_failures = ("forced reconcile failure",)

        def reconcile(self) -> "_Blocked":
            return self

    monkeypatch.setattr(
        "gateway_repository_service.runtime.ImportStartupReconciler",
        lambda **_kwargs: _Blocked(),
    )
    with pytest.raises(ServiceStartupError, match="import startup recovery is blocked"):
        ServiceRuntime.start(settings)
    layout = DurableLayout.bind_existing(settings.data_root)
    with DurableRootLock(layout.service_lock):
        pass
    stop.set()
    thread.join(timeout=2.0)


def test_r21_admin_adopt_residual_inserts_without_scanning(
    tmp_path: Path,
) -> None:
    from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore

    settings = lifecycle_settings(tmp_path)
    DurableLayout.create_service(settings.data_root)
    ControlStore.open(
        settings.control_db_path,
        expected_version=CONTROL_DB_USER_VERSION,
        busy_timeout_ms=1000,
    ).close()
    unknown = settings.data_root / "artifacts" / ("b" * 32) / "ready" / "forged-name"
    unknown.parent.mkdir(parents=True, exist_ok=True)
    unknown.write_bytes(b"leave-me")
    st = unknown.stat()
    code = _run_adopt_residual(
        settings=settings,
        artifact_id=ARTIFACT_ID,
        repository_id=REPO_ID,
        kind="deleting",
        name=unknown.name,
        parent_name="",
        dev=int(st.st_dev),
        ino=int(st.st_ino),
        generation="adopt",
    )
    assert code == 0
    assert unknown.is_file()


def test_r21_entrypoint_does_not_find_chown_unknown() -> None:
    entrypoint = (
        Path(__file__).resolve().parents[1] / "docker-entrypoint.sh"
    ).read_text(encoding="utf-8")
    assert "find " not in entrypoint
    assert "chown -R" not in entrypoint
    assert "_is_hex32" in entrypoint
    assert "unlink-stage" not in entrypoint


def test_r21_reclaim_stage_without_children_leaves_victim(
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
    stage_name = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="r21s")
    stage = ready / stage_name
    stage.mkdir()
    victim = stage / "victim"
    victim.write_bytes(b"")
    ready_fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert bound_socket_broker.reclaim_stage(ready_fd, stage_name, children=[]) is False
    finally:
        os.close(ready_fd)
    assert victim.is_file()
    assert stage.is_dir()
