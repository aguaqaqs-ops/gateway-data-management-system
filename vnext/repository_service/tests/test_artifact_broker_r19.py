"""Round 19 directory-broker fail-closed, SCM_RIGHTS, and allowlist probes."""

from __future__ import annotations

import os
import socket
import stat
import struct
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest

from gateway_repository_service.artifact_broker import (
    ArtifactBrokerError,
    InProcessArtifactDirBroker,
    SocketArtifactDirBroker,
    get_artifact_broker,
    install_artifact_broker,
    resolve_broker_mode,
    set_artifact_broker,
    unlink_name_allowed,
)
from gateway_repository_service.artifact_broker_server import serve
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.upload_artifact.admission_pin import quarantine_name_for

ARTIFACT_ID = UUID("018f0f3e-7b0a-7c16-8a9e-2e4b9f4d2c21")
REPO_ID = UUID("018f0f3e-7b0a-7c15-8a9e-2e4b9f4d2c21")


def test_r19_production_forbids_inprocess_and_silent_fallback() -> None:
    with pytest.raises(ArtifactBrokerError, match="forbids"):
        resolve_broker_mode(profile="production", mode="inprocess")
    with pytest.raises(ArtifactBrokerError, match="requires"):
        resolve_broker_mode(profile="production", mode="auto", socket_path=None)
    with pytest.raises(ArtifactBrokerError, match="required"):
        resolve_broker_mode(profile="production", mode="socket", socket_path="/no/such.sock")


def test_r19_test_profile_explicit_inprocess_is_allowed() -> None:
    assert resolve_broker_mode(profile="test", mode="inprocess") == "inprocess"
    assert resolve_broker_mode(profile="test", mode="auto", socket_path=None) == "inprocess"


def test_r19_unlink_allowlist_rejects_ready_uuid() -> None:
    assert unlink_name_allowed(ARTIFACT_ID.hex) is False
    assert unlink_name_allowed(".deleting-1-g-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") is True
    assert unlink_name_allowed("victim") is True
    assert unlink_name_allowed("final-deadbeef") is True
    assert unlink_name_allowed("../etc") is False


def test_r19_inprocess_mkdir_link_rename_roundtrip(tmp_path: Path) -> None:
    ready = tmp_path / "ready"
    staging = tmp_path / "staging"
    ready.mkdir()
    staging.mkdir()
    staged = staging / f"{ARTIFACT_ID.hex}.abc123"
    staged.write_bytes(b"payload")
    broker = InProcessArtifactDirBroker()
    ready_fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
    staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
    try:
        src_fd = os.open(staged, os.O_RDONLY)
        try:
            broker.link_from_fd(ready_fd, ARTIFACT_ID.hex, src_fd)
        finally:
            os.close(src_fd)
        assert (ready / ARTIFACT_ID.hex).read_bytes() == b"payload"
        broker.rename_noreplace(ready_fd, ARTIFACT_ID.hex, ready_fd, "victim")
        assert not (ready / ARTIFACT_ID.hex).exists()
        assert (ready / "victim").is_file()
        st = (ready / "victim").stat()
        assert broker.unlink_if_match(
            ready_fd, "victim", expected_dev=int(st.st_dev), expected_ino=int(st.st_ino)
        )
        assert broker.unlink_if_match(
            ready_fd,
            ARTIFACT_ID.hex,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
        ) is False
    finally:
        os.close(ready_fd)
        os.close(staging_fd)


def _serve_broker(socket_path: Path, artifacts_root: Path, stop: threading.Event) -> None:
    serve(
        socket_path,
        expected_peer_uid=os.getuid(),
        artifacts_root=artifacts_root,
        stop=stop,
    )


@pytest.fixture
def socket_broker(tmp_path: Path) -> Iterator[SocketArtifactDirBroker]:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    sock = tmp_path / "run" / "artifact-broker.sock"
    sock.parent.mkdir()
    stop = threading.Event()
    thread = threading.Thread(
        target=_serve_broker,
        args=(sock, artifacts, stop),
        daemon=True,
        name="r19-broker",
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


def test_r19_socket_ping_and_scmrights_mkdir(tmp_path: Path, socket_broker: SocketArtifactDirBroker) -> None:
    artifacts = tmp_path / "artifacts"
    key = repository_key(REPO_ID)
    fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    try:
        socket_broker.mkdir(fd, key, mode=0o750)
        socket_broker.mkdir(fd, key, mode=0o750)
        pytest.fail("duplicate mkdir must raise FileExistsError")
    except FileExistsError:
        pass
    finally:
        os.close(fd)
    assert (artifacts / key).is_dir()


def test_r19_socket_mkdir_applies_peer_gid_and_requested_mode(
    tmp_path: Path, socket_broker: SocketArtifactDirBroker
) -> None:
    artifacts = tmp_path / "artifacts"
    key = repository_key(REPO_ID)
    fd = os.open(artifacts, os.O_RDONLY | os.O_DIRECTORY)
    previous_umask = os.umask(0o077)
    try:
        socket_broker.mkdir(fd, key, mode=0o770)
    finally:
        os.umask(previous_umask)
        os.close(fd)
    st = os.stat(artifacts / key)
    assert stat.S_IMODE(st.st_mode) == 0o750
    assert st.st_uid == os.getuid()
    assert st.st_gid == os.getgid()


def test_r19_socket_rejects_path_strings_and_hex32_unlink(
    tmp_path: Path, socket_broker: SocketArtifactDirBroker
) -> None:
    artifacts = tmp_path / "artifacts"
    ready = artifacts / "ready"
    ready.mkdir()
    target = ready / ARTIFACT_ID.hex
    target.write_bytes(b"running")
    st = target.stat()
    fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert socket_broker.unlink_if_match(
            fd,
            ARTIFACT_ID.hex,
            expected_dev=int(st.st_dev),
            expected_ino=int(st.st_ino),
        ) is False
        assert target.is_file()
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(2.0)
        conn.connect(str(tmp_path / "run" / "artifact-broker.sock"))
        payload = b'{"op":"unlink_if_match","dir_path":"/etc","name":"passwd"}'
        conn.sendall(struct.pack("!I", len(payload)) + payload)
        hdr = conn.recv(4)
        (length,) = struct.unpack("!I", hdr)
        body = conn.recv(length)
        conn.close()
        assert b"path_string_rejected" in body or b"missing_dirfd" in body
    finally:
        os.close(fd)


def test_r19_socket_rejects_foreign_peer_uid(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    sock = tmp_path / "broker.sock"
    stop = threading.Event()

    def _run() -> None:
        serve(
            sock,
            expected_peer_uid=os.getuid() + 1,
            artifacts_root=artifacts,
            stop=stop,
        )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not sock.exists():
        time.sleep(0.01)
    try:
        broker = SocketArtifactDirBroker(sock)
        with pytest.raises(ArtifactBrokerError):
            broker.ping()
    finally:
        stop.set()
        thread.join(timeout=2.0)


def test_r19_socket_dirfd_outside_root_rejected(
    tmp_path: Path, socket_broker: SocketArtifactDirBroker
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    fd = os.open(outside, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ArtifactBrokerError, match="outside"):
            socket_broker.mkdir(fd, "ready", mode=0o700)
    finally:
        os.close(fd)


@pytest.mark.serial
def test_r19_concurrent_reservation_on_socket_broker(
    tmp_path: Path, socket_broker: SocketArtifactDirBroker
) -> None:
    ready = tmp_path / "artifacts" / "ready"
    ready.mkdir()
    fd = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
    results: list[bool] = []
    barrier = threading.Barrier(2)

    def _reserve() -> None:
        local = os.open(ready, os.O_RDONLY | os.O_DIRECTORY)
        try:
            barrier.wait(timeout=2.0)
            results.append(
                socket_broker.reserve_tombstone_slots(local, budget=1, projected_new=1)
            )
        finally:
            os.close(local)

    try:
        workers = [threading.Thread(target=_reserve) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5.0)
        assert results.count(True) == 1
        assert results.count(False) == 1
    finally:
        os.close(fd)


@pytest.mark.serial
def test_r19_partial_frame_does_not_block_other_pings(
    tmp_path: Path, socket_broker: SocketArtifactDirBroker
) -> None:
    stuck = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stuck.settimeout(2.0)
    stuck.connect(str(tmp_path / "run" / "artifact-broker.sock"))
    stuck.sendall(struct.pack("!I", 32))
    started = time.monotonic()
    socket_broker.ping()
    assert time.monotonic() - started < 2.0
    stuck.close()


def test_r19_layout_mkdir_goes_through_broker(tmp_path: Path) -> None:
    layout = DurableLayout.create_for_probe(tmp_path / "data-root")
    calls: list[str] = []
    inner = InProcessArtifactDirBroker()

    class _Probe:
        def ping(self) -> None:
            return None

        def bind(self) -> None:
            return None

        def mkdir(self, dir_fd: int, name: str, *, mode: int = 0o700) -> None:
            calls.append(name)
            inner.mkdir(dir_fd, name, mode=mode)

        def unlink_if_match(
            self, dir_fd: int, name: str, *, expected_dev: int, expected_ino: int
        ) -> bool:
            return inner.unlink_if_match(
                dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino
            )

        def rmdir_if_empty(self, dir_fd: int, name: str) -> bool:
            return inner.rmdir_if_empty(dir_fd, name)

        def link_from_fd(self, dir_fd: int, name: str, src_fd: int) -> None:
            inner.link_from_fd(dir_fd, name, src_fd)

        def rename_noreplace(
            self, src_dir_fd: int, src_name: str, dst_dir_fd: int, dst_name: str
        ) -> None:
            inner.rename_noreplace(src_dir_fd, src_name, dst_dir_fd, dst_name)

        def reserve_tombstone_slots(
            self, dir_fd: int, *, budget: int, projected_new: int
        ) -> bool:
            return inner.reserve_tombstone_slots(
                dir_fd, budget=budget, projected_new=projected_new
            )

        def release_tombstone_reservation(self, dir_fd: int, *, projected_new: int) -> None:
            inner.release_tombstone_reservation(dir_fd, projected_new=projected_new)

        def reclaim_stage(self, dir_fd: int, name: str) -> bool:
            return inner.reclaim_stage(dir_fd, name)

    set_artifact_broker(_Probe())
    staging, ready = layout.repository_artifact_directories(repository_key(REPO_ID))
    assert staging.is_dir() and ready.is_dir()
    assert repository_key(REPO_ID) in calls
    assert "ready" in calls
    assert "staging" in calls


def test_r19_gateway_sources_do_not_mkdir_link_rename_ready() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "gateway_repository_service"
    admission = (root / "upload_artifact" / "admission_pin.py").read_text(encoding="utf-8")
    assert "os.mkdir(" not in admission
    assert "os.link(" not in admission
    assert "renameat2_noreplace(" not in admission
    assert "os.rename(" not in admission
    layout = (root / "layout.py").read_text(encoding="utf-8")
    assert "ready.mkdir" not in layout
    cleaner = (root / "artifact_cleaner.py").read_text(encoding="utf-8")
    assert "os.link(" not in cleaner
    assert "renameat2_noreplace(" not in cleaner


def test_r19_install_broker_test_profile_is_inprocess() -> None:
    broker = install_artifact_broker(profile="test")
    assert isinstance(broker, InProcessArtifactDirBroker)
    assert get_artifact_broker() is broker


def test_r19_quarantine_name_still_unlinkable() -> None:
    name = quarantine_name_for(inode=7, artifact_id=ARTIFACT_ID, generation="abc")
    assert unlink_name_allowed(name) is True
