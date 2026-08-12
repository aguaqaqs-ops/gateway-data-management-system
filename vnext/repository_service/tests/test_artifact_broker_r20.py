"""Round 20 capability bind, mkdir side-effect, and helper ownership probes."""

from __future__ import annotations

import array
import json
import os
import signal
import socket
import stat
import struct
import subprocess
import sys
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
    ArtifactBrokerShutdownError,
    SocketArtifactDirBroker,
    mkdir_fixed_mode,
    stop_artifact_broker_helper,
)
from gateway_repository_service.artifact_broker_server import serve
from gateway_repository_service.layout import repository_key
from gateway_repository_service.runtime import ServiceRuntime
from gateway_repository_service.upload_artifact.admission_pin import (
    detach_name_for,
    quarantine_name_for,
    unlink_stage_dir_name,
    verify_sidecar_name_for,
)
from support.lifecycle_harness import lifecycle_settings

ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c21")
REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c21")

_ATTACKER = r"""
import array, json, os, socket, struct, sys

def rpc(sock, payload, fds=None):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(2.0)
    conn.connect(sock)
    blob = json.dumps(payload).encode("utf-8")
    header = struct.pack("!I", len(blob)) + blob
    if fds:
        conn.sendmsg([header], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds).tobytes())])
    else:
        conn.sendall(header)
    hdr = conn.recv(4)
    (length,) = struct.unpack("!I", hdr)
    body = conn.recv(length)
    conn.close()
    return json.loads(body.decode("utf-8"))

sock, ready, hex_name = sys.argv[1], sys.argv[2], sys.argv[3]
pidfd = os.pidfd_open(os.getpid())
try:
    bind = rpc(sock, {"op": "bind"}, [pidfd])
finally:
    os.close(pidfd)
if bind.get("ok") is True:
    raise SystemExit(11)
ready_fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
try:
    st = os.stat(os.path.join(ready, hex_name))
    attacks = [
        ("rename_noreplace", {"src_name": hex_name, "dst_name": ".deleting-" + str(st.st_ino) + "-g-" + hex_name}, [ready_fd, ready_fd]),
        ("rename_noreplace", {"src_name": hex_name, "dst_name": ".detach-" + str(st.st_ino) + "-g-" + hex_name}, [ready_fd, ready_fd]),
        ("rename_noreplace", {"src_name": hex_name, "dst_name": ".unlink-verify-" + str(st.st_ino) + "-g-" + hex_name + "-t0"}, [ready_fd, ready_fd]),
        ("unlink_if_match", {"name": hex_name, "expected_dev": int(st.st_dev), "expected_ino": int(st.st_ino)}, [ready_fd]),
    ]
    for op, payload, fds in attacks:
        payload = dict(payload, op=op)
        resp = rpc(sock, payload, fds)
        if resp.get("ok") is True:
            raise SystemExit(12)
finally:
    os.close(ready_fd)
raise SystemExit(0)
"""


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
        name="r20-broker",
    )
    thread.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not sock.exists():
        time.sleep(0.01)
    assert sock.exists()
    broker = SocketArtifactDirBroker(sock)
    broker.ping()
    broker.bind()
    try:
        yield broker
    finally:
        stop.set()
        thread.join(timeout=2.0)


def test_r20_mkdir_fixed_mode_whitelist() -> None:
    assert mkdir_fixed_mode("ready") == 0o750
    assert mkdir_fixed_mode("a" * 32) == 0o750
    assert mkdir_fixed_mode("staging") == 0o770
    assert mkdir_fixed_mode(".unlink-stage-" + "a" * 32 + "-tok") == 0o750


def test_r20_existing_mkdir_is_side_effect_free(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    artifacts = tmp_path / "artifacts"
    key = repository_key(REPO_ID)
    artifacts_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(artifacts_fd, key, mode=0o777)
    finally:
        os.close(artifacts_fd)
    repo = artifacts / key
    repo_fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(repo_fd, "ready", mode=0o700)
        bound_socket_broker.mkdir(repo_fd, "staging", mode=0o700)
        before = {
            name: (
                os.stat(repo / name).st_uid,
                os.stat(repo / name).st_gid,
                stat.S_IMODE(os.stat(repo / name).st_mode),
            )
            for name in ("ready", "staging")
        }
        for mode in (0o000, 0o700, 0o750, 0o770, 0o777):
            for name in ("ready", "staging"):
                with pytest.raises(FileExistsError):
                    bound_socket_broker.mkdir(repo_fd, name, mode=mode)
                st = os.stat(repo / name)
                assert (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode)) == before[name]
        st_repo = os.stat(repo)
        assert stat.S_IMODE(st_repo.st_mode) == 0o750
        with pytest.raises(FileExistsError):
            artifacts_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
            try:
                bound_socket_broker.mkdir(artifacts_fd, key, mode=0o777)
            finally:
                os.close(artifacts_fd)
        assert stat.S_IMODE(os.stat(repo).st_mode) == 0o750
    finally:
        os.close(repo_fd)


def _plant_protected(tmp_path: Path, broker: SocketArtifactDirBroker) -> Path:
    artifacts = tmp_path / "artifacts"
    key = repository_key(REPO_ID)
    fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        broker.mkdir(fd, key, mode=0o750)
    finally:
        os.close(fd)
    repo = artifacts / key
    ready = repo / "ready"
    ready.mkdir()
    protected = ready / ARTIFACT_ID.hex
    protected.write_bytes(b"keep-me")
    return protected


def test_r20_unbound_peer_cannot_run_confused_deputy_matrix(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    protected = _plant_protected(tmp_path, bound_socket_broker)
    sock = str(tmp_path / "run" / "artifact-broker.sock")
    completed = subprocess.run(
        [sys.executable, "-c", _ATTACKER, sock, str(protected.parent), ARTIFACT_ID.hex],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert protected.is_file()
    assert protected.read_bytes() == b"keep-me"


def test_r20_second_pid_and_fork_child_cannot_bind(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    protected = _plant_protected(tmp_path, bound_socket_broker)
    sock = str(tmp_path / "run" / "artifact-broker.sock")
    script = r"""
import array, json, os, socket, struct, sys
sock = sys.argv[1]
if os.fork() == 0:
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(2.0)
    conn.connect(sock)
    payload = json.dumps({"op": "bind"}).encode("utf-8")
    header = struct.pack("!I", len(payload)) + payload
    pidfd = os.pidfd_open(os.getpid())
    try:
        conn.sendmsg(
            [header],
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [pidfd]).tobytes())],
        )
    finally:
        os.close(pidfd)
    hdr = conn.recv(4)
    (length,) = struct.unpack("!I", hdr)
    body = json.loads(conn.recv(length).decode("utf-8"))
    conn.close()
    os._exit(0 if body.get("ok") is not True else 11)
pid, status = os.waitpid(-1, 0)
raise SystemExit(os.waitstatus_to_exitcode(status))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, sock],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    dolt_child = subprocess.run(
        [sys.executable, "-c", _ATTACKER, sock, str(protected.parent), ARTIFACT_ID.hex],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert dolt_child.returncode == 0, dolt_child.stderr
    assert protected.is_file()


def _raw_bind(sock: str, fds: list[int] | None = None) -> dict[str, object]:
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(2.0)
    conn.connect(sock)
    payload = json.dumps({"op": "bind"}).encode("utf-8")
    header = struct.pack("!I", len(payload)) + payload
    if fds:
        conn.sendmsg(
            [header],
            [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds).tobytes())],
        )
    else:
        conn.sendall(header)
    hdr = conn.recv(4)
    (length,) = struct.unpack("!I", hdr)
    parsed = json.loads(conn.recv(length).decode("utf-8"))
    conn.close()
    if not isinstance(parsed, dict):
        raise AssertionError("broker bind response must be an object")
    return parsed


def test_r20_bind_requires_self_pidfd(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    sock = str(tmp_path / "run" / "artifact-broker.sock")
    missing = _raw_bind(sock)
    assert missing.get("ok") is not True
    assert missing.get("error") == "missing_pidfd"
    artifacts = tmp_path / "artifacts"
    dir_fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        forged = _raw_bind(sock, [dir_fd])
    finally:
        os.close(dir_fd)
    assert forged.get("ok") is not True
    assert forged.get("error") == "pidfd_identity_rejected"


def test_r20_pidfd_alive_uses_poll_not_signal() -> None:
    from gateway_repository_service.artifact_broker_server import _pidfd_alive

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    pidfd = os.pidfd_open(child.pid)
    try:
        assert _pidfd_alive(pidfd) is True
        child.kill()
        child.wait(timeout=5)
        assert _pidfd_alive(pidfd) is False
    finally:
        os.close(pidfd)
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_r20_bound_peer_cannot_unlink_hex32(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    artifacts = tmp_path / "artifacts"
    key = repository_key(REPO_ID)
    fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(fd, key, mode=0o750)
    finally:
        os.close(fd)
    ready = artifacts / key / "ready"
    ready.mkdir()
    target = ready / ARTIFACT_ID.hex
    target.write_bytes(b"running")
    st = target.stat()
    ready_fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert bound_socket_broker.unlink_if_match(
            ready_fd,
            ARTIFACT_ID.hex,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
        ) is False
        detach = detach_name_for(
            inode=int(st.st_ino), artifact_id=ARTIFACT_ID, generation="g0"
        )
        bound_socket_broker.rename_noreplace(ready_fd, ARTIFACT_ID.hex, ready_fd, detach)
        assert not target.exists()
        st2 = (ready / detach).stat()
        assert bound_socket_broker.unlink_if_match(
            ready_fd,
            detach,
            expected_dev=int(st2.st_dev),
            expected_ino=int(st2.st_ino),
        )
        restored = ready / ARTIFACT_ID.hex
        restored.write_bytes(b"running")
        st3 = restored.stat()
        verify = verify_sidecar_name_for(
            inode=int(st3.st_ino),
            generation="g1",
            artifact_id=ARTIFACT_ID,
            token="t0",
        )
        stage = unlink_stage_dir_name(artifact_id=ARTIFACT_ID, token="atk")
        with pytest.raises(ArtifactBrokerError):
            bound_socket_broker.rename_noreplace(ready_fd, ARTIFACT_ID.hex, ready_fd, verify)
        with pytest.raises(ArtifactBrokerError):
            bound_socket_broker.rename_noreplace(ready_fd, ARTIFACT_ID.hex, ready_fd, stage)
        deleting_ok = quarantine_name_for(
            inode=int(st3.st_ino), artifact_id=ARTIFACT_ID, generation="g1"
        )
        bound_socket_broker.rename_noreplace(ready_fd, ARTIFACT_ID.hex, ready_fd, deleting_ok)
        assert (ready / deleting_ok).is_file()
    finally:
        os.close(ready_fd)


def test_r20_artifacts_root_replace_symlink_and_external_dirfd(
    tmp_path: Path, bound_socket_broker: SocketArtifactDirBroker
) -> None:
    artifacts = tmp_path / "artifacts"
    key = repository_key(REPO_ID)
    fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        bound_socket_broker.mkdir(fd, key, mode=0o750)
    finally:
        os.close(fd)
    outside = tmp_path / "outside"
    outside.mkdir()
    trap_fd = os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ArtifactBrokerError, match="outside"):
            bound_socket_broker.mkdir(trap_fd, "ready", mode=0o750)
    finally:
        os.close(trap_fd)
    relocated = tmp_path / "artifacts.real"
    artifacts.rename(relocated)
    artifacts.symlink_to(outside)
    relocated_fd = os.open(relocated, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ArtifactBrokerError, match="outside"):
            bound_socket_broker.mkdir(relocated_fd, "ready", mode=0o750)
    finally:
        os.close(relocated_fd)
    outside_fd = os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ArtifactBrokerError, match="outside"):
            bound_socket_broker.mkdir(outside_fd, "ready", mode=0o750)
    finally:
        os.close(outside_fd)
    assert (relocated / key).is_dir()


@pytest.mark.integration
def test_r20_helper_death_fails_readiness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ignored = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    pidfile = tmp_path / "broker.pid"
    pidfile.write_text(str(ignored.pid), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE", str(pidfile))
    settings = lifecycle_settings(tmp_path)
    runtime = ServiceRuntime.start(settings)
    try:
        assert runtime.is_ready()
        ignored.kill()
        ignored.wait(timeout=5)
        assert not runtime.is_ready()
        assert "artifact directory-broker" in runtime.not_ready_message()
    finally:
        runtime.shutdown()


@pytest.mark.integration
def test_r20_helper_death_blocks_new_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ignored = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    pidfile = tmp_path / "broker.pid"
    pidfile.write_text(str(ignored.pid), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE", str(pidfile))
    settings = lifecycle_settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/readyz").status_code == 200
        ignored.kill()
        ignored.wait(timeout=5)
        readyz = client.get("/readyz")
        assert readyz.status_code == 503
        create = client.post(
            "/v1/repositories",
            headers={
                "Authorization": "Bearer test-bearer-token",
                "Idempotency-Key": "r20-helper-death",
            },
        )
        assert create.status_code == 503
        runtime = cast(FastAPI, client.app).state.runtime
        pending = runtime.control_store.connection.execute(
            "SELECT COUNT(*) FROM synchronous_mutation_effects WHERE status = 'PENDING'"
        ).fetchone()
        assert int(pending[0]) == 0


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["cleaner", "worker", "upload"])
def test_r20_shutdown_broker_last_while_helper_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    helper = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    pidfile = tmp_path / "broker.pid"
    pidfile.write_text(str(helper.pid), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE", str(pidfile))
    settings = lifecycle_settings(tmp_path)
    runtime = ServiceRuntime.start(settings)
    order: list[str] = []
    original_cleaner_stop = runtime.artifact_cleaner.stop
    original_worker_stop = runtime.import_worker_pool.stop
    original_drain = runtime._wait_for_admission_drain

    def _assert_helper_alive() -> None:
        os.kill(helper.pid, 0)

    def _cleaner_stop(*, timeout: float | None = None) -> None:
        _assert_helper_alive()
        order.append("cleaner")
        original_cleaner_stop(timeout=timeout)

    def _worker_stop(*, timeout: float | None = None) -> None:
        _assert_helper_alive()
        order.append("worker")
        original_worker_stop(timeout=timeout)

    def _drain(*, timeout: float) -> bool:
        if "broker" not in order:
            _assert_helper_alive()
            order.append("drain")
        return original_drain(timeout=timeout)

    def _broker_stop(*, timeout: float = 2.0) -> None:
        order.append("broker")
        helper.terminate()
        helper.wait(timeout=5)

    monkeypatch.setattr(runtime.artifact_cleaner, "stop", _cleaner_stop)
    monkeypatch.setattr(runtime.import_worker_pool, "stop", _worker_stop)
    monkeypatch.setattr(runtime, "_wait_for_admission_drain", _drain)
    monkeypatch.setattr(
        "gateway_repository_service.runtime.stop_artifact_broker_helper",
        _broker_stop,
    )
    try:
        runtime.shutdown()
        assert order.index(kind if kind != "upload" else "drain") < order.index("broker")
        assert order.index("cleaner") < order.index("broker")
        assert order.index("worker") < order.index("broker")
    finally:
        if helper.poll() is None:
            helper.kill()
            helper.wait(timeout=5)


@pytest.mark.integration
@pytest.mark.serial
def test_r20_broker_join_timeout_retains_root_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stubborn = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
        ],
        start_new_session=True,
    )
    pidfile = tmp_path / "broker.pid"
    pidfile.write_text(str(stubborn.pid), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE", str(pidfile))
    settings = lifecycle_settings(tmp_path)
    runtime = ServiceRuntime.start(settings)
    try:
        with pytest.raises(ArtifactBrokerShutdownError):
            runtime.shutdown()
        assert runtime.root_lock.is_held()
        assert runtime.control_store.is_open()
    finally:
        stubborn.send_signal(signal.SIGKILL)
        stubborn.wait(timeout=5)
        if runtime.root_lock.is_held():
            runtime.root_lock.release()
        if runtime.control_store.is_open():
            runtime.control_store.close()


def test_r20_stop_helper_timeout_is_observable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stubborn = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
        ],
        start_new_session=True,
    )
    pidfile = tmp_path / "broker.pid"
    pidfile.write_text(str(stubborn.pid), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE", str(pidfile))
    try:
        with pytest.raises(ArtifactBrokerShutdownError, match="timed out"):
            stop_artifact_broker_helper(timeout=0.2)
    finally:
        stubborn.send_signal(signal.SIGKILL)
        stubborn.wait(timeout=5)
