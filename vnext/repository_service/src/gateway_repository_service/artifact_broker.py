"""Artifact directory-broker API (ADR 0011).

Production dual-UID: SocketArtifactDirBroker talks to artifact-broker helper.
Test/dev: InProcessArtifactDirBroker (functional double; not OS isolation proof).
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
import stat
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ArtifactBrokerError(RuntimeError):
    """Raised when a broker directory operation fails closed."""


class ArtifactDirBroker(Protocol):
    def unlink_if_match(
        self,
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool: ...

    def rmdir_if_empty(self, dir_fd: int, name: str) -> bool: ...

    def link_from_fd(self, dir_fd: int, name: str, src_fd: int) -> None: ...

    def reserve_tombstone_slots(
        self,
        dir_fd: int,
        *,
        budget: int,
        projected_new: int,
    ) -> bool: ...

    def release_tombstone_reservation(self, dir_fd: int, *, projected_new: int) -> None: ...


def _dir_path_from_fd(dir_fd: int) -> str:
    return os.readlink(f"/proc/self/fd/{dir_fd}")


@dataclass
class _ReservationState:
    lock: threading.Lock
    reserved: int = 0


class InProcessArtifactDirBroker:
    """Same-process broker (tests / single-UID). Not a cross-principal proof."""

    def __init__(self) -> None:
        self._reservations: dict[int, _ReservationState] = {}
        self._meta_lock = threading.Lock()

    def _state_for(self, dir_fd: int) -> _ReservationState:
        st = os.fstat(dir_fd)
        key = (int(st.st_dev) << 32) ^ int(st.st_ino)
        with self._meta_lock:
            state = self._reservations.get(key)
            if state is None:
                state = _ReservationState(lock=threading.Lock())
                self._reservations[key] = state
            return state

    def unlink_if_match(
        self,
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        try:
            fd = os.open(name, open_flags, dir_fd=dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                return False
            if int(st.st_dev) != int(expected_dev) or int(st.st_ino) != int(expected_ino):
                return False
        except OSError:
            return False
        finally:
            os.close(fd)
        try:
            os.unlink(name, dir_fd=dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def rmdir_if_empty(self, dir_fd: int, name: str) -> bool:
        try:
            os.rmdir(name, dir_fd=dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def link_from_fd(self, dir_fd: int, name: str, src_fd: int) -> None:
        os.link(f"/proc/self/fd/{src_fd}", name, dst_dir_fd=dir_fd)

    def reserve_tombstone_slots(
        self,
        dir_fd: int,
        *,
        budget: int,
        projected_new: int,
    ) -> bool:
        if projected_new < 0:
            raise ArtifactBrokerError("projected_new must be non-negative")
        state = self._state_for(dir_fd)
        with state.lock:
            try:
                fcntl.flock(dir_fd, fcntl.LOCK_EX)
            except OSError:
                return False
            try:
                current = count_full_inventory_names(dir_fd)
                if current + state.reserved + projected_new > budget:
                    return False
                state.reserved += projected_new
                return True
            finally:
                try:
                    fcntl.flock(dir_fd, fcntl.LOCK_UN)
                except OSError:
                    pass

    def release_tombstone_reservation(self, dir_fd: int, *, projected_new: int) -> None:
        state = self._state_for(dir_fd)
        with state.lock:
            state.reserved = max(0, state.reserved - max(0, projected_new))


class SocketArtifactDirBroker:
    """Client for the artifact-broker helper (path-based ops + peer UID check)."""

    def __init__(self, socket_path: Path) -> None:
        self._socket_path = socket_path
        self._local = InProcessArtifactDirBroker()

    def _call(self, payload: dict[str, object]) -> dict[str, object]:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            conn.connect(str(self._socket_path))
            data = json.dumps(payload).encode("utf-8")
            conn.sendall(struct.pack("!I", len(data)) + data)
            hdr = b""
            while len(hdr) < 4:
                chunk = conn.recv(4 - len(hdr))
                if not chunk:
                    raise ArtifactBrokerError("broker closed")
                hdr += chunk
            (length,) = struct.unpack("!I", hdr)
            body = b""
            while len(body) < length:
                chunk = conn.recv(length - len(body))
                if not chunk:
                    raise ArtifactBrokerError("broker closed")
                body += chunk
            parsed = json.loads(body.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ArtifactBrokerError("invalid broker response")
            return parsed
        finally:
            conn.close()

    def unlink_if_match(
        self,
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        resp = self._call(
            {
                "op": "unlink_if_match",
                "dir_path": _dir_path_from_fd(dir_fd),
                "name": name,
                "expected_dev": int(expected_dev),
                "expected_ino": int(expected_ino),
            }
        )
        return bool(resp.get("ok"))

    def rmdir_if_empty(self, dir_fd: int, name: str) -> bool:
        resp = self._call(
            {
                "op": "rmdir_if_empty",
                "dir_path": _dir_path_from_fd(dir_fd),
                "name": name,
            }
        )
        return bool(resp.get("ok"))

    def link_from_fd(self, dir_fd: int, name: str, src_fd: int) -> None:
        # Link must run in the caller until SCM_RIGHTS src fd framing lands;
        # production publish still uses in-process when gateway retains create rights
        # during migration. Prefer local for link.
        self._local.link_from_fd(dir_fd, name, src_fd)

    def reserve_tombstone_slots(
        self,
        dir_fd: int,
        *,
        budget: int,
        projected_new: int,
    ) -> bool:
        return self._local.reserve_tombstone_slots(
            dir_fd, budget=budget, projected_new=projected_new
        )

    def release_tombstone_reservation(self, dir_fd: int, *, projected_new: int) -> None:
        self._local.release_tombstone_reservation(dir_fd, projected_new=projected_new)


def count_full_inventory_names(ready_dir_fd: int) -> int:
    from gateway_repository_service.upload_artifact.admission_pin import (
        parse_any_recoverable_sidecar,
        parse_unlink_stage_dir_name,
    )

    names = os.listdir(ready_dir_fd)
    count = 0
    for name in names:
        if parse_any_recoverable_sidecar(name) is not None:
            count += 1
        elif parse_unlink_stage_dir_name(name) is not None:
            count += 1
    return count


_BROKER: ArtifactDirBroker | None = None
_BROKER_LOCK = threading.Lock()


def get_artifact_broker() -> ArtifactDirBroker:
    global _BROKER
    with _BROKER_LOCK:
        if _BROKER is None:
            sock = os.environ.get("GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET")
            if sock and Path(sock).exists():
                _BROKER = SocketArtifactDirBroker(Path(sock))
            else:
                _BROKER = InProcessArtifactDirBroker()
        return _BROKER


def set_artifact_broker(broker: ArtifactDirBroker | None) -> None:
    global _BROKER
    with _BROKER_LOCK:
        _BROKER = broker
