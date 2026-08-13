"""Root-only layout preparation for artifacts without following mounts."""

from __future__ import annotations

import argparse
import os
import pwd
import stat
from pathlib import Path

from gateway_repository_service.artifact_root import (
    ArtifactRootError,
    assert_no_symlink_ancestors,
    lstat_is_symlink,
    open_dir_nofollow,
    same_mount,
)

_HEX32 = frozenset("0123456789abcdef")
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)


def _is_hex32(name: str) -> bool:
    return len(name) == 32 and all(ch in _HEX32 for ch in name)


def _fchown_chmod(fd: int, *, uid: int, gid: int, mode: int) -> None:
    os.fchown(fd, uid, gid)
    os.fchmod(fd, mode)


def _lexists(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    return True


def _ensure_real_dir(
    path: Path,
    *,
    uid: int,
    gid: int,
    mode: int,
    require_same_parent_mount: bool,
) -> int:
    assert_no_symlink_ancestors(path)
    parent = path.parent
    if _lexists(path):
        if lstat_is_symlink(path):
            raise ArtifactRootError(f"refusing symlink directory: {path}")
        fd = open_dir_nofollow(path)
        if require_same_parent_mount and parent != path:
            if lstat_is_symlink(parent):
                os.close(fd)
                raise ArtifactRootError(f"refusing symlink directory: {parent}")
            parent_fd = open_dir_nofollow(parent)
            try:
                if not same_mount(parent_fd, fd):
                    os.close(fd)
                    raise ArtifactRootError(f"refusing bind-mount directory: {path}")
            finally:
                os.close(parent_fd)
        _fchown_chmod(fd, uid=uid, gid=gid, mode=mode)
        return fd
    if not _lexists(parent):
        parent_fd = _ensure_real_dir(
            parent,
            uid=uid,
            gid=gid,
            mode=0o750,
            require_same_parent_mount=require_same_parent_mount,
        )
    else:
        if lstat_is_symlink(parent):
            raise ArtifactRootError(f"refusing symlink directory: {parent}")
        parent_fd = open_dir_nofollow(parent)
    try:
        try:
            os.mkdir(path.name, mode, dir_fd=parent_fd)
        except FileExistsError:
            pass
        fd = os.open(path.name, _DIR_FLAGS, dir_fd=parent_fd)
        if require_same_parent_mount and not same_mount(parent_fd, fd):
            os.close(fd)
            raise ArtifactRootError(f"refusing bind-mount directory: {path}")
        _fchown_chmod(fd, uid=uid, gid=gid, mode=mode)
        return fd
    finally:
        os.close(parent_fd)


def _open_child_dir(parent_fd: int, name: str) -> int | None:
    try:
        st = os.lstat(name, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        return None
    try:
        child_fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError:
        return None
    if not same_mount(parent_fd, child_fd):
        os.close(child_fd)
        return None
    return child_fd


def prepare_artifact_layout(
    *,
    data_root: Path,
    artifacts: Path,
    gateway_uid: int,
    gateway_gid: int,
) -> None:
    data_root = Path(data_root)
    artifacts = Path(artifacts)
    assert_no_symlink_ancestors(data_root)
    assert_no_symlink_ancestors(artifacts)
    data_fd = _ensure_real_dir(
        data_root,
        uid=gateway_uid,
        gid=gateway_gid,
        mode=0o750,
        require_same_parent_mount=False,
    )
    os.close(data_fd)
    artifacts_fd = _ensure_real_dir(
        artifacts,
        uid=gateway_uid,
        gid=gateway_gid,
        mode=0o750,
        require_same_parent_mount=True,
    )
    try:
        for name in os.listdir(artifacts_fd):
            if not _is_hex32(name):
                continue
            repo_fd = _open_child_dir(artifacts_fd, name)
            if repo_fd is None:
                continue
            try:
                _fchown_chmod(repo_fd, uid=gateway_uid, gid=gateway_gid, mode=0o750)
                ready_fd = _open_child_dir(repo_fd, "ready")
                if ready_fd is not None:
                    try:
                        _fchown_chmod(ready_fd, uid=gateway_uid, gid=gateway_gid, mode=0o750)
                    finally:
                        os.close(ready_fd)
                staging_fd = _open_child_dir(repo_fd, "staging")
                if staging_fd is not None:
                    try:
                        _fchown_chmod(
                            staging_fd, uid=gateway_uid, gid=gateway_gid, mode=0o750
                        )
                    finally:
                        os.close(staging_fd)
            finally:
                os.close(repo_fd)
    finally:
        os.close(artifacts_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="artifact-layout")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--gateway-user", required=True)
    args = parser.parse_args(argv)
    try:
        gateway_pw = pwd.getpwnam(args.gateway_user)
        prepare_artifact_layout(
            data_root=args.data_root,
            artifacts=args.artifacts,
            gateway_uid=gateway_pw.pw_uid,
            gateway_gid=gateway_pw.pw_gid,
        )
    except ArtifactRootError as exc:
        print(str(exc), flush=True)
        return 1
    except OSError as exc:
        print(str(exc), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
