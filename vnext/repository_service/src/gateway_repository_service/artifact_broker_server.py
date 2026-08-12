"""Artifact directory-broker helper process (ADR 0011)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import struct
import threading
from pathlib import Path

from gateway_repository_service.artifact_broker import (
    InProcessArtifactDirBroker,
    _OPS,
    _MAX_JSON,
    _REQUEST_TIMEOUT_SECONDS,
    ArtifactBrokerError,
    link_or_rename_name_allowed,
    mkdir_name_allowed,
    path_is_under,
    unlink_name_allowed,
)

_CMSG_SPACE = socket.CMSG_SPACE(4 * 8)


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


def _require_dir_under_root(fd: int, artifacts_root: str) -> None:
    path = _fd_path(fd)
    if not path_is_under(path, artifacts_root):
        raise ArtifactBrokerError("dirfd outside artifacts root")
    st = os.fstat(fd)
    if not (st.st_mode & 0o170000 == 0o040000):
        raise ArtifactBrokerError("dirfd is not a directory")


def _own_mkdir_child(dir_fd: int, name: str, *, mode: int, peer_gid: int) -> None:
    """Force broker-uid:gateway-gid and the requested mode (ADR 0011)."""

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
    artifacts_root: str,
    impl: InProcessArtifactDirBroker,
) -> None:
    try:
        creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", creds)
        if int(uid) != int(expected_peer_uid):
            _send_json(conn, {"ok": False, "error": "peer_uid_rejected"})
            return
        req, fds = _recv_request(conn)
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
                mode_raw = req.get("mode", 0o700)
                mode = int(mode_raw) if isinstance(mode_raw, int) else 0o700
                existed = False
                try:
                    impl.mkdir(fds[0], name, mode=mode)
                except FileExistsError:
                    existed = True
                _own_mkdir_child(
                    fds[0], name, mode=mode, peer_gid=expected_peer_gid
                )
                if existed:
                    raise FileExistsError(name)
                _send_json(conn, {"ok": True})
            elif op == "unlink_if_match":
                name = str(req["name"])
                if not unlink_name_allowed(name):
                    _send_json(conn, {"ok": False, "error": "name_rejected"})
                    return
                expected_dev = req["expected_dev"]
                expected_ino = req["expected_ino"]
                if not isinstance(expected_dev, int) or not isinstance(expected_ino, int):
                    _send_json(conn, {"ok": False, "error": "bad_identity"})
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
            elif op == "link_from_fd":
                if len(fds) < 2:
                    _send_json(conn, {"ok": False, "error": "missing_srcfd"})
                    return
                name = str(req["name"])
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
                if not link_or_rename_name_allowed(src_name) or not link_or_rename_name_allowed(
                    dst_name
                ):
                    _send_json(conn, {"ok": False, "error": "name_rejected"})
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
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o660)
    server.listen(16)
    server.settimeout(1.0)
    root = os.path.realpath(str(artifacts_root))
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
                args=(conn, expected_peer_uid, peer_gid, root, impl),
                daemon=True,
                name="artifact-broker-conn",
            )
            workers.append(thread)
            thread.start()
    finally:
        server.close()
        for thread in workers:
            thread.join(timeout=2.0)


def _serve_one(
    conn: socket.socket,
    expected_peer_uid: int,
    expected_peer_gid: int,
    artifacts_root: str,
    impl: InProcessArtifactDirBroker,
) -> None:
    with conn:
        _handle(
            conn,
            expected_peer_uid=expected_peer_uid,
            expected_peer_gid=expected_peer_gid,
            artifacts_root=artifacts_root,
            impl=impl,
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
