"""Root-only layout preparation for artifacts without following mounts."""

from __future__ import annotations

import argparse
import os
import pwd
import stat
from pathlib import Path

from gateway_repository_service.layout import DurableLayout, LayoutError
from gateway_repository_service.deployment_config import StorageLayoutConfig
from gateway_repository_service.storage_roots import RepositoryRoots

from gateway_repository_service.artifact_root import (
    ArtifactRootError,
    assert_no_symlink_ancestors,
    open_owned_directory,
    same_mount,
)

_HEX32 = frozenset("0123456789abcdef")
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)


def _is_hex32(name: str) -> bool:
    return len(name) == 32 and all(ch in _HEX32 for ch in name)


def _fchown_chmod(fd: int, *, uid: int, gid: int, mode: int) -> None:
    os.fchown(fd, uid, gid)
    os.fchmod(fd, mode)


def _prepare_owned_directory(path: Path, root: Path, *, uid: int, gid: int, mode: int) -> int:
    descriptor = open_owned_directory(root, path, create=True, mode=mode)
    assert descriptor is not None
    _fchown_chmod(descriptor, uid=uid, gid=gid, mode=mode)
    return descriptor


def _open_child_dir(parent_fd: int, name: str, *, label: str) -> int | None:
    try:
        st = os.lstat(name, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ArtifactRootError(f"{label} is unavailable: {name}") from exc
    if stat.S_ISLNK(st.st_mode):
        raise ArtifactRootError(f"refusing symlink directory: {name}")
    if not stat.S_ISDIR(st.st_mode):
        raise ArtifactRootError(f"refusing non-directory {label}: {name}")
    try:
        child_fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise ArtifactRootError(f"{label} is unavailable: {name}") from exc
    if not same_mount(parent_fd, child_fd):
        os.close(child_fd)
        raise ArtifactRootError(f"refusing bind-mount directory: {name}")
    return child_fd


def prepare_artifact_layout(
    *,
    artifacts: Path,
    gateway_uid: int,
    gateway_gid: int,
) -> None:
    artifacts = Path(artifacts)
    assert_no_symlink_ancestors(artifacts)
    artifacts_fd = _prepare_owned_directory(artifacts, artifacts,
        uid=gateway_uid, gid=gateway_gid, mode=0o750)
    try:
        for name in os.listdir(artifacts_fd):
            if not _is_hex32(name):
                continue
            repo_fd = _open_child_dir(artifacts_fd, name, label="repository")
            if repo_fd is None:
                continue
            try:
                _fchown_chmod(repo_fd, uid=gateway_uid, gid=gateway_gid, mode=0o750)
                ready_fd = _open_child_dir(repo_fd, "ready", label="ready")
                if ready_fd is not None:
                    try:
                        _fchown_chmod(ready_fd, uid=gateway_uid, gid=gateway_gid, mode=0o750)
                    finally:
                        os.close(ready_fd)
                staging_fd = _open_child_dir(repo_fd, "staging", label="staging")
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
    parser.add_argument("--storage-layout-file", type=Path, required=True)
    parser.add_argument("--gateway-user", required=True)
    args = parser.parse_args(argv)
    try:
        gateway_pw = pwd.getpwnam(args.gateway_user)
        roots = RepositoryRoots.from_config(StorageLayoutConfig.load(args.storage_layout_file))
        # Full deployment attestation belongs to bootstrap. This check rejects
        # missing roots and all existing redirected prefixes before permission changes.
        layout = DurableLayout(roots)
        layout.validate_preparation_paths()
        for root in roots.paths():
            fd = _prepare_owned_directory(root, root, uid=gateway_pw.pw_uid,
                gid=gateway_pw.pw_gid, mode=0o750)
            os.close(fd)
        for path, root in layout.components():
            fd = _prepare_owned_directory(path, root, uid=gateway_pw.pw_uid,
                gid=gateway_pw.pw_gid, mode=0o750)
            os.close(fd)
        prepare_artifact_layout(
            artifacts=roots.artifacts,
            gateway_uid=gateway_pw.pw_uid,
            gateway_gid=gateway_pw.pw_gid,
        )
    except (ArtifactRootError, LayoutError, ValueError) as exc:
        print(str(exc), flush=True)
        return 1
    except OSError as exc:
        print(str(exc), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
