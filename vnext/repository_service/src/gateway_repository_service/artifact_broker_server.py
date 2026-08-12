"""Artifact directory-broker helper process (ADR 0011)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import stat
import struct
import threading
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

_CMSG_SPACE = socket.CMSG_SPACE(4 * 8)


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


def _send_json(conn: socket.socket, payload: dict[str, object]) -> None:
    data = json.dumps(payload).encode("utf-8")
    conn.sendall(struct.pack("!I", len(data)) + data)


def _recv_request(conn: socket.socket) -> tuple[dict[str, object], list[int]]:
    conn.settimeout(_REQUEST_TIMEOUT_SECONDS)
    msg, ancdata, _flags, _addr = conn.recvmsg(_MAX_JSON + 4, _CMSG_SPACE)
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
    fds: list[int] = []
    for cmsg_level, cmsg_type, cmsg_data in ancdata:
        if cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS:
            n = len(cmsg_data) // 4
            fds.extend(struct.unpack(f"{n}i", cmsg_data[: n * 4]))
    return parsed, fds


def _fd_path(fd: int) -> str:
    return os.path.realpath(f"/proc/self/fd/{fd}")


def _require_dir_under_root(fd: int, artifacts_root: FrozenArtifactsRoot) -> None:
    try:
        root_st = os.lstat(artifacts_root.path)
    except OSError as exc:
        raise ArtifactBrokerError("dirfd outside artifacts root") from exc
    if stat.S_ISLNK(root_st.st_mode):
        raise ArtifactBrokerError("dirfd outside artifacts root")
    if int(root_st.st_dev) != int(artifacts_root.dev) or int(root_st.st_ino) != int(
        artifacts_root.ino
    ):
        raise ArtifactBrokerError("dirfd outside artifacts root")
    path = _fd_path(fd)
    if not path_is_under(path, artifacts_root.path, canonicalize_root=False):
        raise ArtifactBrokerError("dirfd outside artifacts root")
    st = os.fstat(fd)
    if not (st.st_mode & 0o170000 == 0o040000):
        raise ArtifactBrokerError("dirfd is not a directory")


def _proc_starttime(pid: int) -> int:
    raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    close = raw.rfind(")")
    fields = raw[close + 2 :].split()
    return int(fields[19])


def _pidfd_alive(pidfd: int) -> bool:
    send_signal = getattr(os, "pidfd_send_signal", None) or getattr(
        signal, "pidfd_send_signal", None
    )
    if send_signal is None:
        return False
    try:
        send_signal(pidfd, 0)
    except (ProcessLookupError, OSError):
        return False
    return True


def _bind_peer(state: BrokerBindState, pid: int) -> None:
    starttime = _proc_starttime(pid)
    with state.lock:
        if state.pidfd is not None and _pidfd_alive(state.pidfd):
            if state.pid != pid or state.starttime != starttime:
                raise ArtifactBrokerError("peer_pid_rejected")
            return
        if state.pidfd is not None:
            try:
                os.close(state.pidfd)
            except OSError:
                pass
        state.pid = pid
        state.pidfd = os.pidfd_open(pid)
        state.starttime = starttime


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
) -> None:
    try:
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, _gid = struct.unpack("3i", creds)
        req, fds = _recv_request(conn)
        if int(uid) != int(expected_peer_uid):
            for fd in fds:
                try:
                    os.close(fd)
                except OSError:
                    pass
            _send_json(conn, {"ok": False, "error": "peer_uid_rejected"})
            return
        op = str(req.get("op", ""))
        if "dir_path" in req or "src_path" in req or "path" in req:
            _send_json(conn, {"ok": False, "error": "path_string_rejected"})
            return
        if op not in _OPS:
            _send_json(conn, {"ok": False, "error": "unknown_op"})
            return
        if op == "ping":
            _send_json(conn, {"ok": True})
            return
        if op == "bind":
            try:
                _bind_peer(bind_state, int(pid))
            except ArtifactBrokerError as exc:
                _send_json(conn, {"ok": False, "error": str(exc)})
                return
            except OSError as exc:
                _send_json(conn, {"ok": False, "error": type(exc).__name__})
                return
            _send_json(conn, {"ok": True})
            return
        if not _peer_is_bound(bind_state, int(pid)):
            _send_json(conn, {"ok": False, "error": "peer_pid_rejected"})
            return
        if not fds:
            _send_json(conn, {"ok": False, "error": "missing_dirfd"})
            return
        try:
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
                _send_json(conn, {"ok": reclaim_stage_dir(fds[0], name)})
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
            for fd in fds:
                try:
                    os.close(fd)
                except OSError:
                    pass
    except Exception as exc:
        try:
            _send_json(conn, {"ok": False, "error": type(exc).__name__})
        except Exception:
            pass


def serve(
    socket_path: Path,
    *,
    expected_peer_uid: int,
    artifacts_root: Path,
    stop: threading.Event | None = None,
    expected_peer_gid: int | None = None,
) -> None:
    impl = InProcessArtifactDirBroker()
    bind_state = BrokerBindState()
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o660)
    server.listen(16)
    server.settimeout(1.0)
    resolved = os.path.realpath(str(artifacts_root))
    root_st = os.stat(resolved)
    root = FrozenArtifactsRoot(path=resolved, dev=int(root_st.st_dev), ino=int(root_st.st_ino))
    peer_gid = os.getgid() if expected_peer_gid is None else expected_peer_gid
    workers: list[threading.Thread] = []
    try:
        while stop is None or not stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            except OSError:
                if stop is not None and stop.is_set():
                    break
                raise
            thread = threading.Thread(
                target=_serve_one,
                args=(conn, expected_peer_uid, peer_gid, root, impl, bind_state),
                daemon=True,
                name="artifact-broker-conn",
            )
            workers.append(thread)
            thread.start()
    finally:
        server.close()
        if bind_state.pidfd is not None:
            try:
                os.close(bind_state.pidfd)
            except OSError:
                pass
        for thread in workers:
            thread.join(timeout=2.0)


def _serve_one(
    conn: socket.socket,
    expected_peer_uid: int,
    expected_peer_gid: int,
    artifacts_root: FrozenArtifactsRoot,
    impl: InProcessArtifactDirBroker,
    bind_state: BrokerBindState,
) -> None:
    with conn:
        _handle(
            conn,
            expected_peer_uid=expected_peer_uid,
            expected_peer_gid=expected_peer_gid,
            artifacts_root=artifacts_root,
            impl=impl,
            bind_state=bind_state,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="artifact-broker")
    parser.add_argument("--socket", type=Path, required=True)
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
        expected_peer_uid=args.peer_uid,
        expected_peer_gid=args.peer_gid,
        artifacts_root=args.artifacts_root,
        stop=stop,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
