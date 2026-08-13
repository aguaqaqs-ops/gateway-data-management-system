"""Artifact directory-broker helper process (ADR 0011)."""

from __future__ import annotations

import argparse
import json
import os
import select
import signal
import socket
import stat
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from gateway_repository_service.artifact_broker import (
    InProcessArtifactDirBroker,
    _OPS,
    _MAX_JSON,
    _REQUEST_TIMEOUT_SECONDS,
    ArtifactBrokerError,
    is_hex32,
    mkdir_fixed_mode,
    mkdir_name_allowed,
    path_is_under,
    reclaim_stage_dir,
    rename_edge_allowed,
    unlink_identity_matches,
    unlink_name_allowed,
)
from gateway_repository_service.artifact_root import (
    ArtifactRootError,
    assert_no_symlink_ancestors,
    mnt_id_for_fd,
    open_dir_nofollow,
    same_mount,
)

_CMSG_SPACE = socket.CMSG_SPACE(4 * 8)
_MAX_WORKER_THREADS = 16
_CONTROL_WORKER_THREADS = 4
_IO_RESERVE_THREADS = _CONTROL_WORKER_THREADS
_CONTROL_OPS = frozenset({"ping", "bind", "shutdown", "assert_bound"})
_MAX_FDS = 8
_LAST_DIR_LOCKS: "_DirLocks | None" = None


@dataclass
class BrokerBindState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    pid: int | None = None
    pidfd: int | None = None
    starttime: int | None = None


@dataclass(frozen=True)
class FrozenArtifactsRoot:
    path: str
    dev: int
    ino: int
    mnt_id: int
    root_fd: int


class _DirLocks:
    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[tuple[int, int], threading.Lock] = {}
        self._refs: dict[tuple[int, int], int] = {}

    @property
    def retained(self) -> int:
        with self._guard:
            return len(self._locks)

    def acquire_keys(self, keys: list[tuple[int, int]]) -> list[tuple[int, int]]:
        ordered = sorted(set(keys))
        held: list[tuple[int, int]] = []
        try:
            for key in ordered:
                with self._guard:
                    lock = self._locks.get(key)
                    if lock is None:
                        lock = threading.Lock()
                        self._locks[key] = lock
                        self._refs[key] = 0
                lock.acquire()
                held.append(key)
                with self._guard:
                    self._refs[key] = self._refs.get(key, 0) + 1
            return held
        except BaseException:
            self.release_keys(held)
            raise

    def release_keys(self, keys: list[tuple[int, int]]) -> None:
        for key in reversed(keys):
            with self._guard:
                lock = self._locks.get(key)
            if lock is not None:
                lock.release()
            with self._guard:
                refs = self._refs.get(key, 0) - 1
                if refs <= 0:
                    self._refs.pop(key, None)
                    self._locks.pop(key, None)
                else:
                    self._refs[key] = refs

    def lock_for_key(self, key: tuple[int, int]) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
                self._refs[key] = 0
            return lock

    def lock_for(self, fd: int) -> threading.Lock:
        st = os.fstat(fd)
        return self.lock_for_key((int(st.st_dev), int(st.st_ino)))


def dir_lock_table_size() -> int:
    locks = _LAST_DIR_LOCKS
    if locks is None:
        return 0
    return locks.retained


def _send_json(conn: socket.socket, payload: dict[str, object]) -> None:
    data = json.dumps(payload).encode("utf-8")
    conn.sendall(struct.pack("!I", len(data)) + data)


def _extract_fds(ancdata: list[tuple[int, int, bytes]]) -> list[int]:
    fds: list[int] = []
    for cmsg_level, cmsg_type, cmsg_data in ancdata:
        if cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS:
            n = len(cmsg_data) // 4
            fds.extend(struct.unpack(f"{n}i", cmsg_data[: n * 4]))
    return fds


def _close_fds(fds: list[int], *, keep: set[int] | None = None) -> None:
    retained = keep or set()
    for fd in fds:
        if fd in retained:
            continue
        try:
            os.close(fd)
        except OSError:
            pass


def _recv_request(conn: socket.socket) -> tuple[dict[str, object], list[int]]:
    conn.settimeout(_REQUEST_TIMEOUT_SECONDS)
    msg, ancdata, _flags, _addr = conn.recvmsg(_MAX_JSON + 4, _CMSG_SPACE)
    fds = _extract_fds(ancdata)
    try:
        if len(msg) < 4:
            raise ArtifactBrokerError("short broker header")
        (length,) = struct.unpack("!I", msg[:4])
        if length <= 0 or length > _MAX_JSON:
            raise ArtifactBrokerError("invalid broker message length")
        body = msg[4:]
        while len(body) < length:
            chunk = conn.recv(length - len(body))
            if not chunk:
                raise ArtifactBrokerError("broker client closed")
            body += chunk
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ArtifactBrokerError("broker message must be object")
        return parsed, fds
    except Exception:
        _close_fds(fds)
        raise


def _fd_path(fd: int) -> str:
    return os.path.realpath(f"/proc/self/fd/{fd}")


def _require_dir_under_root(fd: int, artifacts_root: FrozenArtifactsRoot) -> None:
    try:
        root_st = os.fstat(artifacts_root.root_fd)
    except OSError as exc:
        raise ArtifactBrokerError("dirfd outside artifacts root") from exc
    if int(root_st.st_dev) != int(artifacts_root.dev) or int(root_st.st_ino) != int(
        artifacts_root.ino
    ):
        raise ArtifactBrokerError("dirfd outside artifacts root")
    try:
        if mnt_id_for_fd(artifacts_root.root_fd) != int(artifacts_root.mnt_id):
            raise ArtifactBrokerError("dirfd outside artifacts root")
    except ArtifactRootError as exc:
        raise ArtifactBrokerError("dirfd outside artifacts root") from exc
    path = _fd_path(fd)
    if not path_is_under(path, artifacts_root.path, canonicalize_root=False):
        raise ArtifactBrokerError("dirfd outside artifacts root")
    st = os.fstat(fd)
    if not (st.st_mode & 0o170000 == 0o040000):
        raise ArtifactBrokerError("dirfd is not a directory")
    try:
        if mnt_id_for_fd(fd) != int(artifacts_root.mnt_id):
            raise ArtifactBrokerError("dirfd outside artifacts root")
    except ArtifactRootError as exc:
        raise ArtifactBrokerError("dirfd outside artifacts root") from exc


def _proc_starttime(pid: int) -> int:
    raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    close = raw.rfind(")")
    fields = raw[close + 2 :].split()
    return int(fields[19])


def _pidfd_alive(pidfd: int) -> bool:
    """True while the pidfd's process has not exited.

    Do not use pidfd_send_signal: signaling another UID is EPERM without
    CAP_KILL, which is the production dual-UID layout. A pidfd becomes
    readable (POLLIN) when the referent process has terminated.
    """

    try:
        poller = select.poll()
        poller.register(pidfd, select.POLLIN)
        return not poller.poll(0)
    except OSError:
        return False


def _pidfd_nspid(pidfd: int) -> int:
    """Read the pidfd's target PID. Helper cannot pidfd_open() a different UID."""

    try:
        raw = Path(f"/proc/self/fdinfo/{pidfd}").read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactBrokerError("pidfd_identity_rejected") from exc
    for line in raw.splitlines():
        if line.startswith("NSpid:") or line.startswith("Pid:"):
            fields = line.split(":", 1)[1].split()
            if fields:
                return int(fields[0])
    raise ArtifactBrokerError("pidfd_identity_rejected")


def _bind_peer(state: BrokerBindState, pid: int, pidfd: int) -> bool:
    """Take ownership of the peer-supplied self pidfd (SCM_RIGHTS).

    Dual-UID production cannot ``pidfd_open(cred.pid)`` from the helper: that
    is a PTRACE_MODE_READ_FSCREDS check and returns EPERM across UIDs. The
    gateway opens its own pidfd (always allowed) and passes it.
    """

    if _pidfd_nspid(pidfd) != pid:
        raise ArtifactBrokerError("pidfd_identity_rejected")
    if not _pidfd_alive(pidfd):
        raise ArtifactBrokerError("peer_pid_rejected")
    starttime = _proc_starttime(pid)
    with state.lock:
        if state.pidfd is not None and _pidfd_alive(state.pidfd):
            if state.pid != pid or state.starttime != starttime:
                raise ArtifactBrokerError("peer_pid_rejected")
            os.close(pidfd)
            return False
        if state.pidfd is not None:
            try:
                os.close(state.pidfd)
            except OSError:
                pass
        state.pid = pid
        state.pidfd = pidfd
        state.starttime = starttime
        return True


def _peer_is_bound(state: BrokerBindState, pid: int) -> bool:
    with state.lock:
        if state.pid is None or state.pidfd is None or state.starttime is None:
            return False
        if state.pid != pid:
            return False
        if not _pidfd_alive(state.pidfd):
            return False
        try:
            return _proc_starttime(pid) == state.starttime
        except OSError:
            return False


def _own_mkdir_child(dir_fd: int, name: str, *, mode: int, peer_gid: int) -> None:
    """Force broker-uid:gateway-gid and the fixed whitelist mode (ADR 0011)."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    child = os.open(name, flags, dir_fd=dir_fd)
    try:
        os.fchown(child, os.getuid(), peer_gid)
        os.fchmod(child, mode)
    finally:
        os.close(child)


def _handle(
    conn: socket.socket,
    *,
    expected_peer_uid: int,
    expected_peer_gid: int,
    artifacts_root: FrozenArtifactsRoot,
    impl: InProcessArtifactDirBroker,
    bind_state: BrokerBindState,
    stop: threading.Event | None,
    dir_locks: _DirLocks,
    control_only: bool,
) -> None:
    fds: list[int] = []
    keep: set[int] = set()
    try:
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, _gid = struct.unpack("3i", creds)
        req, fds = _recv_request(conn)
        if len(fds) > _MAX_FDS:
            _send_json(conn, {"ok": False, "error": "extra_fds"})
            return
        if int(uid) != int(expected_peer_uid):
            _send_json(conn, {"ok": False, "error": "peer_uid_rejected"})
            return
        op = str(req.get("op", ""))
        if "dir_path" in req or "src_path" in req or "path" in req:
            _send_json(conn, {"ok": False, "error": "path_string_rejected"})
            return
        if op not in _OPS:
            _send_json(conn, {"ok": False, "error": "unknown_op"})
            return
        if control_only and op not in _CONTROL_OPS:
            _send_json(conn, {"ok": False, "error": "control_only"})
            return
        if not control_only and op in _CONTROL_OPS:
            _send_json(conn, {"ok": False, "error": "data_socket_rejected"})
            return
        if op == "ping":
            if fds:
                _send_json(conn, {"ok": False, "error": "extra_fds"})
                return
            _send_json(conn, {"ok": True})
            return
        if op == "bind":
            if len(fds) != 1:
                _send_json(conn, {"ok": False, "error": "missing_pidfd"})
                return
            try:
                owned = _bind_peer(bind_state, int(pid), fds[0])
            except ArtifactBrokerError as exc:
                _send_json(conn, {"ok": False, "error": str(exc)})
                return
            except OSError as exc:
                _send_json(conn, {"ok": False, "error": type(exc).__name__})
                return
            if owned:
                keep.add(fds[0])
            _send_json(conn, {"ok": True})
            return
        if not _peer_is_bound(bind_state, int(pid)):
            _send_json(conn, {"ok": False, "error": "peer_pid_rejected"})
            return
        if op == "assert_bound":
            if fds:
                _send_json(conn, {"ok": False, "error": "extra_fds"})
                return
            _send_json(conn, {"ok": True})
            return
        if op == "shutdown":
            if fds:
                _send_json(conn, {"ok": False, "error": "extra_fds"})
                return
            if stop is not None:
                stop.set()
            _send_json(conn, {"ok": True})
            return
        expected_fds = 2 if op in {"link_from_fd", "rename_noreplace"} else 1
        if len(fds) < expected_fds:
            missing = "missing_srcfd" if op == "link_from_fd" else (
                "missing_dstfd" if op == "rename_noreplace" else "missing_dirfd"
            )
            _send_json(conn, {"ok": False, "error": missing})
            return
        if len(fds) > expected_fds:
            _send_json(conn, {"ok": False, "error": "extra_fds"})
            return
        acquired_keys: list[tuple[int, int]] = []
        try:
            keys: list[tuple[int, int]] = []
            seen: set[tuple[int, int]] = set()
            dir_fds = [fds[0]]
            if op == "rename_noreplace":
                dir_fds = [fds[0], fds[1]]
            for fd in dir_fds:
                st = os.fstat(fd)
                if not stat.S_ISDIR(st.st_mode):
                    continue
                key = (int(st.st_dev), int(st.st_ino))
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
            acquired_keys = dir_locks.acquire_keys(keys)
            _require_dir_under_root(fds[0], artifacts_root)
            if op == "mkdir":
                name = str(req["name"])
                if not mkdir_name_allowed(name):
                    _send_json(conn, {"ok": False, "error": "name_rejected"})
                    return
                mode = mkdir_fixed_mode(name)
                try:
                    impl.mkdir(fds[0], name, mode=mode)
                except FileExistsError:
                    raise FileExistsError(name)
                _own_mkdir_child(
                    fds[0], name, mode=mode, peer_gid=expected_peer_gid
                )
                _send_json(conn, {"ok": True})
            elif op == "unlink_if_match":
                name = str(req["name"])
                if is_hex32(name) or not unlink_name_allowed(name):
                    _send_json(conn, {"ok": False, "error": "name_rejected"})
                    return
                expected_dev = req["expected_dev"]
                expected_ino = req["expected_ino"]
                if not isinstance(expected_dev, int) or not isinstance(expected_ino, int):
                    _send_json(conn, {"ok": False, "error": "bad_identity"})
                    return
                flags = (
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_NONBLOCK", 0)
                )
                try:
                    probe = os.open(name, flags, dir_fd=fds[0])
                except FileNotFoundError:
                    _send_json(conn, {"ok": True})
                    return
                except OSError:
                    _send_json(conn, {"ok": False})
                    return
                os.close(probe)
                if not unlink_identity_matches(
                    fds[0],
                    name,
                    expected_dev=expected_dev,
                    expected_ino=expected_ino,
                ):
                    _send_json(conn, {"ok": False, "error": "identity_rejected"})
                    return
                ok = impl.unlink_if_match(
                    fds[0], name, expected_dev=expected_dev, expected_ino=expected_ino
                )
                _send_json(conn, {"ok": ok})
            elif op == "rmdir_if_empty":
                name = str(req["name"])
                if not unlink_name_allowed(name) and not mkdir_name_allowed(name):
                    _send_json(conn, {"ok": False, "error": "name_rejected"})
                    return
                _send_json(conn, {"ok": impl.rmdir_if_empty(fds[0], name)})
            elif op == "reclaim_stage":
                name = str(req["name"])
                raw_children = req.get("children", [])
                children: list[tuple[str, int, int]] = []
                if isinstance(raw_children, list):
                    for item in raw_children:
                        if not isinstance(item, dict):
                            continue
                        child_name = str(item.get("name", ""))
                        child_dev = item.get("expected_dev")
                        child_ino = item.get("expected_ino")
                        if isinstance(child_dev, int) and isinstance(child_ino, int):
                            children.append((child_name, child_dev, child_ino))
                _send_json(
                    conn,
                    {"ok": reclaim_stage_dir(fds[0], name, children=children)},
                )
            elif op == "link_from_fd":
                if len(fds) < 2:
                    _send_json(conn, {"ok": False, "error": "missing_srcfd"})
                    return
                name = str(req["name"])
                from gateway_repository_service.artifact_broker import link_or_rename_name_allowed

                if not link_or_rename_name_allowed(name):
                    _send_json(conn, {"ok": False, "error": "name_rejected"})
                    return
                impl.link_from_fd(fds[0], name, fds[1])
                _send_json(conn, {"ok": True})
            elif op == "rename_noreplace":
                if len(fds) < 2:
                    _send_json(conn, {"ok": False, "error": "missing_dstfd"})
                    return
                _require_dir_under_root(fds[1], artifacts_root)
                src_name = str(req["src_name"])
                dst_name = str(req["dst_name"])
                if not rename_edge_allowed(fds[0], src_name, fds[1], dst_name):
                    _send_json(conn, {"ok": False, "error": "rename_edge_rejected"})
                    return
                impl.rename_noreplace(fds[0], src_name, fds[1], dst_name)
                _send_json(conn, {"ok": True})
            elif op == "reserve_tombstone_slots":
                budget = req["budget"]
                projected = req["projected_new"]
                if not isinstance(budget, int) or not isinstance(projected, int):
                    _send_json(conn, {"ok": False, "error": "bad_budget"})
                    return
                ok = impl.reserve_tombstone_slots(
                    fds[0], budget=budget, projected_new=projected
                )
                _send_json(conn, {"ok": ok})
            elif op == "release_tombstone_reservation":
                projected = req["projected_new"]
                if not isinstance(projected, int):
                    _send_json(conn, {"ok": False, "error": "bad_budget"})
                    return
                impl.release_tombstone_reservation(fds[0], projected_new=projected)
                _send_json(conn, {"ok": True})
            else:
                _send_json(conn, {"ok": False, "error": "unhandled"})
        except FileExistsError:
            _send_json(conn, {"ok": False, "error": "FileExistsError"})
        except ArtifactBrokerError as exc:
            _send_json(conn, {"ok": False, "error": str(exc)})
        except OSError as exc:
            _send_json(conn, {"ok": False, "error": type(exc).__name__})
        finally:
            dir_locks.release_keys(acquired_keys)
    except Exception as exc:
        try:
            _send_json(conn, {"ok": False, "error": type(exc).__name__})
        except Exception:
            pass
    finally:
        _close_fds(fds, keep=keep)


def _default_control_socket(socket_path: Path) -> Path:
    return socket_path.parent / f"{socket_path.stem}-control.sock"


def serve(
    socket_path: Path,
    *,
    expected_peer_uid: int,
    artifacts_root: Path,
    stop: threading.Event | None = None,
    expected_peer_gid: int | None = None,
    control_socket_path: Path | None = None,
) -> None:
    global _LAST_DIR_LOCKS
    impl = InProcessArtifactDirBroker()
    bind_state = BrokerBindState()
    dir_locks = _DirLocks()
    _LAST_DIR_LOCKS = dir_locks
    control_path = control_socket_path or _default_control_socket(socket_path)
    for path in (socket_path, control_path):
        if path.exists():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
    artifacts_root = Path(artifacts_root)
    assert_no_symlink_ancestors(artifacts_root)
    root_fd = open_dir_nofollow(artifacts_root)
    try:
        parent = artifacts_root.parent
        if parent != artifacts_root:
            parent_fd = open_dir_nofollow(parent)
            try:
                if not same_mount(parent_fd, root_fd):
                    raise ArtifactRootError(
                        f"refusing bind-mount artifacts root: {artifacts_root}"
                    )
            finally:
                os.close(parent_fd)
        root_st = os.fstat(root_fd)
        root = FrozenArtifactsRoot(
            path=os.path.normpath(str(artifacts_root)),
            dev=int(root_st.st_dev),
            ino=int(root_st.st_ino),
            mnt_id=mnt_id_for_fd(root_fd),
            root_fd=root_fd,
        )
    except BaseException:
        os.close(root_fd)
        raise
    peer_gid = os.getgid() if expected_peer_gid is None else expected_peer_gid
    data_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    control_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    data_slots = threading.BoundedSemaphore(_MAX_WORKER_THREADS)
    control_slots = threading.BoundedSemaphore(_CONTROL_WORKER_THREADS)
    data_executor = ThreadPoolExecutor(
        max_workers=_MAX_WORKER_THREADS,
        thread_name_prefix="artifact-broker-data",
    )
    control_executor = ThreadPoolExecutor(
        max_workers=_CONTROL_WORKER_THREADS,
        thread_name_prefix="artifact-broker-ctrl",
    )
    try:
        data_server.bind(str(socket_path))
        control_server.bind(str(control_path))
        os.chmod(socket_path, 0o660)
        os.chmod(control_path, 0o660)
        data_server.listen(_MAX_WORKER_THREADS)
        control_server.listen(max(_CONTROL_WORKER_THREADS * 8, _MAX_WORKER_THREADS))
        data_server.settimeout(1.0)
        control_server.settimeout(1.0)
        while stop is None or not stop.is_set():
            ready, _, _ = select.select([data_server, control_server], [], [], 1.0)
            for listener in ready:
                try:
                    conn, _ = listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if stop is not None and stop.is_set():
                        break
                    raise
                control_only = listener is control_server
                slots = control_slots if control_only else data_slots
                executor = control_executor if control_only else data_executor
                if not _try_acquire(slots):
                    try:
                        _send_json(conn, {"ok": False, "error": "overloaded"})
                    except OSError:
                        pass
                    conn.close()
                    continue
                try:
                    executor.submit(
                        _serve_one,
                        conn,
                        expected_peer_uid,
                        peer_gid,
                        root,
                        impl,
                        bind_state,
                        stop,
                        dir_locks,
                        slots,
                        control_only,
                    )
                except RuntimeError:
                    conn.close()
                    slots.release()
    finally:
        data_server.close()
        control_server.close()
        data_executor.shutdown(wait=False, cancel_futures=True)
        control_executor.shutdown(wait=False, cancel_futures=True)
        os.close(root_fd)
        if bind_state.pidfd is not None:
            try:
                os.close(bind_state.pidfd)
            except OSError:
                pass


def _try_acquire(slots: threading.BoundedSemaphore) -> bool:
    return bool(slots.acquire(blocking=False))


def _serve_one(
    conn: socket.socket,
    expected_peer_uid: int,
    expected_peer_gid: int,
    artifacts_root: FrozenArtifactsRoot,
    impl: InProcessArtifactDirBroker,
    bind_state: BrokerBindState,
    stop: threading.Event | None,
    dir_locks: _DirLocks,
    dir_sema: threading.Semaphore,
    control_only: bool,
) -> None:
    try:
        _handle(
            conn,
            expected_peer_uid=expected_peer_uid,
            expected_peer_gid=expected_peer_gid,
            artifacts_root=artifacts_root,
            impl=impl,
            bind_state=bind_state,
            stop=stop,
            dir_locks=dir_locks,
            control_only=control_only,
        )
    finally:
        dir_sema.release()
        try:
            conn.close()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="artifact-broker")
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--control-socket", type=Path, default=None)
    parser.add_argument("--peer-uid", type=int, required=True)
    parser.add_argument("--peer-gid", type=int, required=True)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    args = parser.parse_args(argv)
    stop = threading.Event()

    def _stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    serve(
        args.socket,
        control_socket_path=args.control_socket,
        expected_peer_uid=args.peer_uid,
        expected_peer_gid=args.peer_gid,
        artifacts_root=args.artifacts_root,
        stop=stop,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
