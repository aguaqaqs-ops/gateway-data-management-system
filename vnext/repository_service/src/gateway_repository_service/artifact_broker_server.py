"""Artifact directory-broker helper process (ADR 0011)."""

from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import struct
from pathlib import Path

_OPS = frozenset({"unlink_if_match", "rmdir_if_empty", "ping"})


def _send_json(conn: socket.socket, payload: dict[str, object]) -> None:
    data = json.dumps(payload).encode("utf-8")
    conn.sendall(struct.pack("!I", len(data)) + data)


def _read_json(conn: socket.socket) -> dict[str, object]:
    hdr = b""
    while len(hdr) < 4:
        chunk = conn.recv(4 - len(hdr))
        if not chunk:
            raise ConnectionError("broker client closed")
        hdr += chunk
    (length,) = struct.unpack("!I", hdr)
    if length <= 0 or length > 1_048_576:
        raise ValueError("invalid broker message length")
    body = b""
    while len(body) < length:
        chunk = conn.recv(length - len(body))
        if not chunk:
            raise ConnectionError("broker client closed")
        body += chunk
    parsed = json.loads(body.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("broker message must be object")
    return parsed


def _unlink_if_match(dir_path: str, name: str, *, expected_dev: int, expected_ino: int) -> bool:
    dir_fd = os.open(dir_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
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
    finally:
        os.close(dir_fd)


def _rmdir_if_empty(dir_path: str, name: str) -> bool:
    dir_fd = os.open(dir_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            os.rmdir(name, dir_fd=dir_fd)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True
    finally:
        os.close(dir_fd)


def serve(socket_path: Path, *, expected_peer_uid: int) -> None:
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o660)
    server.listen(16)
    while True:
        conn, _ = server.accept()
        with conn:
            try:
                creds = conn.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                )
                _pid, uid, _gid = struct.unpack("3i", creds)
                if int(uid) != int(expected_peer_uid):
                    _send_json(conn, {"ok": False, "error": "peer_uid_rejected"})
                    continue
                req = _read_json(conn)
                op = str(req.get("op", ""))
                if op not in _OPS:
                    _send_json(conn, {"ok": False, "error": "unknown_op"})
                    continue
                if op == "ping":
                    _send_json(conn, {"ok": True})
                    continue
                dir_path = str(req["dir_path"])
                name = str(req["name"])
                if op == "unlink_if_match":
                    expected_dev = req["expected_dev"]
                    expected_ino = req["expected_ino"]
                    if not isinstance(expected_dev, int) or not isinstance(expected_ino, int):
                        _send_json(conn, {"ok": False, "error": "bad_identity"})
                        continue
                    ok = _unlink_if_match(
                        dir_path,
                        name,
                        expected_dev=expected_dev,
                        expected_ino=expected_ino,
                    )
                    _send_json(conn, {"ok": ok})
                elif op == "rmdir_if_empty":
                    _send_json(conn, {"ok": _rmdir_if_empty(dir_path, name)})
            except Exception as exc:
                try:
                    _send_json(conn, {"ok": False, "error": type(exc).__name__})
                except Exception:
                    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="artifact-broker")
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--peer-uid", type=int, required=True)
    args = parser.parse_args(argv)
    serve(args.socket, expected_peer_uid=args.peer_uid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
