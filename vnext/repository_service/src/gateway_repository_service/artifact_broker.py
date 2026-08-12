"""Artifact directory-broker API (ADR 0011).

Production dual-UID: SocketArtifactDirBroker talks to artifact-broker helper
via SCM_RIGHTS. Test/dev: InProcessArtifactDirBroker is an explicit functional
double (``GATEWAY_REPOSITORY_ARTIFACT_BROKER_MODE=inprocess``), not an OS
isolation proof.
"""

from __future__ import annotations

import array
import fcntl
import json
import os
import socket
import stat
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from gateway_repository_service.publication import renameat2_noreplace

_HEX32 = frozenset("0123456789abcdef")
_REQUEST_TIMEOUT_SECONDS = 5.0
_MAX_JSON = 65_536
_OPS = frozenset(
    {
        "ping",
        "bind",
        "mkdir",
        "link_from_fd",
        "rename_noreplace",
        "unlink_if_match",
        "rmdir_if_empty",
        "reclaim_stage",
        "reserve_tombstone_slots",
        "release_tombstone_reservation",
    }
)


class ArtifactBrokerError(RuntimeError):
    """Raised when a broker directory operation fails closed."""


class ArtifactBrokerShutdownError(ArtifactBrokerError):
    """Raised when the helper cannot be joined; durable ownership must be retained."""


class ArtifactDirBroker(Protocol):
    def ping(self) -> None: ...

    def bind(self) -> None: ...

    def mkdir(self, dir_fd: int, name: str, *, mode: int = 0o700) -> None: ...

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

    def rename_noreplace(
        self,
        src_dir_fd: int,
        src_name: str,
        dst_dir_fd: int,
        dst_name: str,
    ) -> None: ...

    def reserve_tombstone_slots(
        self,
        dir_fd: int,
        *,
        budget: int,
        projected_new: int,
    ) -> bool: ...

    def release_tombstone_reservation(self, dir_fd: int, *, projected_new: int) -> None: ...

    def reclaim_stage(self, dir_fd: int, name: str) -> bool: ...


def is_single_path_component(name: str) -> bool:
    return bool(name) and "/" not in name and name not in {".", ".."} and "\x00" not in name


def is_hex32(name: str) -> bool:
    return len(name) == 32 and all(ch in _HEX32 for ch in name)


def _is_staging_upload_name(name: str) -> bool:
    if "." not in name:
        return False
    hex_part, nonce = name.split(".", 1)
    return is_hex32(hex_part) and bool(nonce) and nonce.isalnum() and len(nonce) <= 32


def _is_stage_child_name(name: str) -> bool:
    return name == "victim" or name.startswith("final-") or name.startswith("doom-")


def unlink_name_allowed(name: str) -> bool:
    """Ready UUID names are not unlinkable by peer RPC (protected bytes)."""

    if not is_single_path_component(name):
        return False
    if is_hex32(name):
        return False
    return (
        name.startswith(".deleting-")
        or name.startswith(".detach-")
        or name.startswith(".unlink-verify-")
        or name.startswith(".unlink-stage-")
        or _is_stage_child_name(name)
    )


def mkdir_name_allowed(name: str) -> bool:
    if not is_single_path_component(name):
        return False
    return name in {"ready", "staging"} or is_hex32(name) or name.startswith(".unlink-stage-")


def mkdir_fixed_mode(name: str) -> int:
    """Server-side mode whitelist; caller-supplied mode is ignored."""

    if name == "staging":
        return 0o770
    if name.startswith(".unlink-stage-"):
        return 0o750
    return 0o750


def link_or_rename_name_allowed(name: str) -> bool:
    if not is_single_path_component(name):
        return False
    return (
        is_hex32(name)
        or name.startswith(".deleting-")
        or name.startswith(".detach-")
        or name.startswith(".unlink-verify-")
        or name.startswith(".unlink-stage-")
        or _is_stage_child_name(name)
        or _is_staging_upload_name(name)
    )


def path_is_under(path: str, root: str, *, canonicalize_root: bool = True) -> bool:
    real_path = os.path.realpath(path)
    real_root = os.path.realpath(root) if canonicalize_root else os.path.normpath(root)
    return real_path == real_root or real_path.startswith(real_root.rstrip("/") + "/")


@dataclass
class _ReservationState:
    lock: threading.Lock
    reserved: int = 0


class InProcessArtifactDirBroker:
    """Same-process broker (tests / explicit inprocess mode). Not a cross-principal proof."""

    def __init__(self) -> None:
        self._reservations: dict[int, _ReservationState] = {}
        self._meta_lock = threading.Lock()

    def ping(self) -> None:
        return None

    def bind(self) -> None:
        return None

    def _state_for(self, dir_fd: int) -> _ReservationState:
        st = os.fstat(dir_fd)
        key = (int(st.st_dev) << 32) ^ int(st.st_ino)
        with self._meta_lock:
            state = self._reservations.get(key)
            if state is None:
                state = _ReservationState(lock=threading.Lock())
                self._reservations[key] = state
            return state

    def mkdir(self, dir_fd: int, name: str, *, mode: int = 0o700) -> None:
        if not mkdir_name_allowed(name):
            raise ArtifactBrokerError("mkdir name rejected")
        os.mkdir(name, mode, dir_fd=dir_fd)

    def unlink_if_match(
        self,
        dir_fd: int,
        name: str,
        *,
        expected_dev: int,
        expected_ino: int,
    ) -> bool:
        if not unlink_name_allowed(name):
            return False
        return _unlink_if_match_fd(dir_fd, name, expected_dev=expected_dev, expected_ino=expected_ino)

    def rmdir_if_empty(self, dir_fd: int, name: str) -> bool:
        if not is_single_path_component(name):
            return False
        try:
            os.rmdir(name, dir_fd=dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def link_from_fd(self, dir_fd: int, name: str, src_fd: int) -> None:
        if not link_or_rename_name_allowed(name):
            raise ArtifactBrokerError("link name rejected")
        os.link(f"/proc/self/fd/{src_fd}", name, dst_dir_fd=dir_fd)

    def rename_noreplace(
        self,
        src_dir_fd: int,
        src_name: str,
        dst_dir_fd: int,
        dst_name: str,
    ) -> None:
        if not link_or_rename_name_allowed(src_name) or not link_or_rename_name_allowed(dst_name):
            raise ArtifactBrokerError("rename name rejected")
        renameat2_noreplace(src_dir_fd, src_name, dst_dir_fd, dst_name)

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

    def reclaim_stage(self, dir_fd: int, name: str) -> bool:
        return reclaim_stage_dir(dir_fd, name)


def _unlink_if_match_fd(
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


def reclaim_stage_dir(ready_dir_fd: int, name: str) -> bool:
    """Unlink size-0 stage children then rmdir if empty. Broker-principal path."""

    from gateway_repository_service.upload_artifact.admission_pin import parse_unlink_stage_dir_name

    if parse_unlink_stage_dir_name(name) is None:
        return False
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        stage_fd = os.open(name, flags, dir_fd=ready_dir_fd)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    try:
        try:
            fcntl.flock(stage_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        try:
            try:
                children = os.listdir(stage_fd)
            except OSError:
                return False
            for child in children:
                if not _is_stage_child_name(child):
                    continue
                open_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                try:
                    child_fd = os.open(child, open_flags, dir_fd=stage_fd)
                except FileNotFoundError:
                    continue
                except OSError:
                    continue
                try:
                    st = os.fstat(child_fd)
                except OSError:
                    continue
                finally:
                    os.close(child_fd)
                if not stat.S_ISREG(st.st_mode) or int(st.st_size) != 0:
                    continue
                _unlink_if_match_fd(
                    stage_fd,
                    child,
                    expected_dev=int(st.st_dev),
                    expected_ino=int(st.st_ino),
                )
            os.rmdir(name, dir_fd=ready_dir_fd)
            return True
        except OSError:
            return False
        finally:
            try:
                fcntl.flock(stage_fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(stage_fd)


def _dir_basename(dir_fd: int) -> str:
    return os.path.basename(os.path.realpath(f"/proc/self/fd/{dir_fd}"))


def _fstat_name(dir_fd: int, name: str) -> os.stat_result | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except OSError:
        return None
    try:
        return os.fstat(fd)
    except OSError:
        return None
    finally:
        os.close(fd)


def rename_edge_allowed(
    src_dir_fd: int,
    src_name: str,
    dst_dir_fd: int,
    dst_name: str,
) -> bool:
    """Strict source/destination role matrix for rename_noreplace."""

    from gateway_repository_service.upload_artifact.admission_pin import (
        parse_any_recoverable_sidecar,
        parse_detach_name,
        parse_quarantine_name,
        parse_unlink_stage_dir_name,
    )

    if not link_or_rename_name_allowed(src_name) or not link_or_rename_name_allowed(dst_name):
        return False
    src_base = _dir_basename(src_dir_fd)
    dst_base = _dir_basename(dst_dir_fd)
    src_is_stage = parse_unlink_stage_dir_name(src_base) is not None
    dst_is_stage = parse_unlink_stage_dir_name(dst_base) is not None
    src_is_ready = src_base == "ready"
    dst_is_ready = dst_base == "ready"
    src_is_staging = src_base == "staging"

    if (
        src_is_staging
        and dst_is_ready
        and _is_staging_upload_name(src_name)
        and is_hex32(dst_name)
    ):
        return True

    if src_is_ready and dst_is_ready and is_hex32(src_name):
        parsed = parse_quarantine_name(dst_name) or parse_detach_name(dst_name)
        if parsed is None:
            return False
        st = _fstat_name(src_dir_fd, src_name)
        if st is None or not stat.S_ISREG(st.st_mode):
            return False
        name_ino, artifact_id, _generation = parsed
        return int(name_ino) == int(st.st_ino) and artifact_id.hex == src_name

    if src_is_ready and dst_is_ready and is_hex32(dst_name):
        parsed = parse_quarantine_name(src_name) or parse_detach_name(src_name)
        if parsed is None:
            return False
        _ino, artifact_id, _generation = parsed
        return artifact_id.hex == dst_name

    if src_is_ready and dst_is_stage and dst_name == "victim":
        return is_hex32(src_name) or parse_any_recoverable_sidecar(src_name) is not None

    if src_is_stage and dst_is_stage and _is_stage_child_name(src_name) and _is_stage_child_name(
        dst_name
    ):
        return True

    if src_is_stage and dst_is_ready and src_name == "victim":
        return is_hex32(dst_name) or parse_quarantine_name(dst_name) is not None

    return False


def unlink_identity_matches(
    dir_fd: int,
    name: str,
    *,
    expected_dev: int,
    expected_ino: int,
) -> bool:
    """Require fstat identity to match both caller tuple and name-encoded ino."""

    from gateway_repository_service.upload_artifact.admission_pin import parse_any_recoverable_sidecar

    if is_hex32(name) or not unlink_name_allowed(name):
        return False
    st = _fstat_name(dir_fd, name)
    if st is None or not stat.S_ISREG(st.st_mode):
        return False
    if int(st.st_dev) != int(expected_dev) or int(st.st_ino) != int(expected_ino):
        return False
    parsed = parse_any_recoverable_sidecar(name)
    if parsed is not None and int(parsed[0]) != int(st.st_ino):
        return False
    return True


def _pack_request(payload: dict[str, object]) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    if len(data) > _MAX_JSON:
        raise ArtifactBrokerError("broker request too large")
    return struct.pack("!I", len(data)) + data


def _recv_exact(conn: socket.socket, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = conn.recv(size - len(buf))
        if not chunk:
            raise ArtifactBrokerError("broker closed")
        buf += chunk
    return buf


class SocketArtifactDirBroker:
    """Client: JSON + SCM_RIGHTS dir/src fds. No path-string reopen on the server."""

    def __init__(self, socket_path: Path, *, timeout: float = _REQUEST_TIMEOUT_SECONDS) -> None:
        self._socket_path = socket_path
        self._timeout = timeout

    def ping(self) -> None:
        resp = self._call({"op": "ping"})
        if not resp.get("ok"):
            raise ArtifactBrokerError("broker ping failed")

    def bind(self) -> None:
        # Dual-UID: helper cannot pidfd_open(peer); send self pidfd via SCM_RIGHTS.
        pidfd = os.pidfd_open(os.getpid())
        try:
            resp = self._call({"op": "bind"}, fds=[pidfd])
        finally:
            os.close(pidfd)
        if not resp.get("ok"):
            raise ArtifactBrokerError(str(resp.get("error", "broker bind failed")))

    def _connect(self) -> socket.socket:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(self._timeout)
        conn.connect(str(self._socket_path))
        return conn

    def _call(
        self,
        payload: dict[str, object],
        *,
        fds: list[int] | None = None,
    ) -> dict[str, object]:
        conn = self._connect()
        try:
            blob = _pack_request(payload)
            if fds:
                conn.sendmsg(
                    [blob],
                    [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds).tobytes())],
                )
            else:
                conn.sendall(blob)
            hdr = _recv_exact(conn, 4)
            (length,) = struct.unpack("!I", hdr)
            if length <= 0 or length > _MAX_JSON:
                raise ArtifactBrokerError("invalid broker response")
            body = _recv_exact(conn, length)
            parsed = json.loads(body.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise ArtifactBrokerError("invalid broker response")
            return parsed
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            raise ArtifactBrokerError(f"broker transport failed: {type(exc).__name__}") from exc
        finally:
            conn.close()

    def mkdir(self, dir_fd: int, name: str, *, mode: int = 0o700) -> None:
        resp = self._call({"op": "mkdir", "name": name, "mode": int(mode)}, fds=[dir_fd])
        if not resp.get("ok"):
            error = str(resp.get("error", "mkdir failed"))
            if error == "FileExistsError":
                raise FileExistsError(name)
            raise ArtifactBrokerError(error)

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
                "name": name,
                "expected_dev": int(expected_dev),
                "expected_ino": int(expected_ino),
            },
            fds=[dir_fd],
        )
        return bool(resp.get("ok"))

    def rmdir_if_empty(self, dir_fd: int, name: str) -> bool:
        resp = self._call({"op": "rmdir_if_empty", "name": name}, fds=[dir_fd])
        return bool(resp.get("ok"))

    def link_from_fd(self, dir_fd: int, name: str, src_fd: int) -> None:
        resp = self._call({"op": "link_from_fd", "name": name}, fds=[dir_fd, src_fd])
        if not resp.get("ok"):
            error = str(resp.get("error", "link failed"))
            if error == "FileExistsError":
                raise FileExistsError(name)
            raise ArtifactBrokerError(error)

    def rename_noreplace(
        self,
        src_dir_fd: int,
        src_name: str,
        dst_dir_fd: int,
        dst_name: str,
    ) -> None:
        resp = self._call(
            {"op": "rename_noreplace", "src_name": src_name, "dst_name": dst_name},
            fds=[src_dir_fd, dst_dir_fd],
        )
        if not resp.get("ok"):
            error = str(resp.get("error", "rename failed"))
            if error == "FileExistsError":
                raise FileExistsError(dst_name)
            raise ArtifactBrokerError(error)

    def reserve_tombstone_slots(
        self,
        dir_fd: int,
        *,
        budget: int,
        projected_new: int,
    ) -> bool:
        resp = self._call(
            {
                "op": "reserve_tombstone_slots",
                "budget": int(budget),
                "projected_new": int(projected_new),
            },
            fds=[dir_fd],
        )
        return bool(resp.get("ok"))

    def release_tombstone_reservation(self, dir_fd: int, *, projected_new: int) -> None:
        self._call(
            {"op": "release_tombstone_reservation", "projected_new": int(projected_new)},
            fds=[dir_fd],
        )

    def reclaim_stage(self, dir_fd: int, name: str) -> bool:
        resp = self._call({"op": "reclaim_stage", "name": name}, fds=[dir_fd])
        return bool(resp.get("ok"))


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


def resolve_broker_mode(
    *,
    profile: str | None = None,
    socket_path: str | None = None,
    mode: str | None = None,
) -> Literal["inprocess", "socket"]:
    chosen = (mode or os.environ.get("GATEWAY_REPOSITORY_ARTIFACT_BROKER_MODE") or "auto").lower()
    sock = socket_path if socket_path is not None else os.environ.get("GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET")
    effective_profile = profile or os.environ.get("GATEWAY_REPOSITORY_PROFILE") or "production"
    if chosen == "inprocess":
        if effective_profile == "production":
            raise ArtifactBrokerError("production forbids in-process artifact broker")
        return "inprocess"
    if chosen == "socket":
        if not sock or not Path(sock).exists():
            raise ArtifactBrokerError("artifact broker socket is required")
        return "socket"
    # auto
    if sock and Path(sock).exists():
        return "socket"
    if effective_profile == "production":
        raise ArtifactBrokerError("production requires artifact broker socket")
    return "inprocess"


def get_artifact_broker() -> ArtifactDirBroker:
    global _BROKER
    with _BROKER_LOCK:
        if _BROKER is None:
            _BROKER = _make_broker(resolve_broker_mode())
        return _BROKER


def set_artifact_broker(broker: ArtifactDirBroker | None) -> None:
    global _BROKER
    with _BROKER_LOCK:
        _BROKER = broker


def install_artifact_broker(*, profile: str) -> ArtifactDirBroker:
    """Bind the process-wide broker from profile + env (Runtime startup)."""

    mode = resolve_broker_mode(profile=profile)
    broker = _make_broker(mode)
    set_artifact_broker(broker)
    broker.bind()
    return broker


def ping_artifact_broker() -> None:
    get_artifact_broker().ping()


def artifact_broker_helper_alive() -> bool:
    """Return True when no helper pidfile is configured, or the process still exists."""

    pidfile = os.environ.get("GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE")
    if not pidfile:
        return True
    try:
        pid = int(Path(pidfile).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop_artifact_broker_helper(*, timeout: float = 2.0) -> None:
    """SIGTERM the entrypoint-supervised helper when a pidfile is present.

    Join timeout is observable: callers must retain durable ownership.
    """

    pidfile = os.environ.get("GATEWAY_REPOSITORY_ARTIFACT_BROKER_PIDFILE")
    if not pidfile:
        return
    try:
        raw = Path(pidfile).read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (OSError, ValueError) as exc:
        raise ArtifactBrokerShutdownError("artifact-broker pidfile is unreadable") from exc
    if pid <= 1:
        raise ArtifactBrokerShutdownError("artifact-broker pidfile is invalid")
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return
    except OSError as exc:
        raise ArtifactBrokerShutdownError("artifact-broker SIGTERM failed") from exc
    deadline = time.monotonic() + max(timeout, 0.0)
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.05)
    raise ArtifactBrokerShutdownError("artifact-broker join timed out")


def _make_broker(mode: Literal["inprocess", "socket"]) -> ArtifactDirBroker:
    if mode == "socket":
        sock = os.environ.get("GATEWAY_REPOSITORY_ARTIFACT_BROKER_SOCKET")
        if not sock:
            raise ArtifactBrokerError("artifact broker socket is required")
        return SocketArtifactDirBroker(Path(sock))
    return InProcessArtifactDirBroker()
