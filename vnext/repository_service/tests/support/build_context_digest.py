"""Deterministic digests for repository-service Docker build provenance."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BUILD_CONTEXT_SUBDIRS = ("repository_service", "repository_contracts")
IGNORED_DIR_NAMES = {
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "htmlcov",
    ".git",
}
IGNORED_FILE_SUFFIXES = (".pyc", ".pyo")


def _should_hash_file(path: Path) -> bool:
    if any(part in IGNORED_DIR_NAMES for part in path.parts):
        return False
    return path.suffix not in IGNORED_FILE_SUFFIXES


def vnext_root_from_here() -> Path:
    return Path(__file__).resolve().parents[3]


def repo_root_from_vnext(vnext_root: Path) -> Path:
    return vnext_root.parent


def build_context_paths(vnext_root: Path) -> tuple[Path, ...]:
    return tuple(vnext_root / subdir for subdir in BUILD_CONTEXT_SUBDIRS)


def is_build_context_clean(repo_root: Path) -> bool:
    paths = [f"vnext/{subdir}" for subdir in BUILD_CONTEXT_SUBDIRS]
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--", *paths],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return False
    return completed.stdout.strip() == ""


def _working_tree_digest(vnext_root: Path) -> str:
    digest = hashlib.sha256()
    for context_root in build_context_paths(vnext_root):
        if not context_root.is_dir():
            continue
        for path in sorted(context_root.rglob("*")):
            if not path.is_file() or not _should_hash_file(path):
                continue
            relative = path.relative_to(vnext_root).as_posix().encode("utf-8")
            digest.update(relative)
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def compute_source_tree_sha256(*, vnext_root: Path | None = None) -> str:
    root = vnext_root if vnext_root is not None else vnext_root_from_here()
    return f"sha256:{_working_tree_digest(root)}"


def compute_head_sha(*, vnext_root: Path | None = None) -> str:
    root = vnext_root if vnext_root is not None else vnext_root_from_here()
    repo_root = repo_root_from_vnext(root)
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def compute_build_input_revision(*, vnext_root: Path | None = None) -> str:
    """Return the latest commit that touched formal Docker build inputs."""

    root = vnext_root if vnext_root is not None else vnext_root_from_here()
    repo_root = repo_root_from_vnext(root)
    paths = [f"vnext/{subdir}" for subdir in BUILD_CONTEXT_SUBDIRS]
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "log", "-1", "--format=%H", "--", *paths],
        check=True,
        capture_output=True,
        text=True,
    )
    revision = completed.stdout.strip()
    if not revision:
        raise RuntimeError("unable to resolve build-input revision")
    return revision


def compute_build_revision(*, vnext_root: Path | None = None) -> str:
    return compute_build_input_revision(vnext_root=vnext_root)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or args[0] not in {
        "source-tree-sha256",
        "build-revision",
        "build-input-revision",
        "head-sha",
    }:
        raise SystemExit(
            "usage: build_context_digest.py "
            "<source-tree-sha256|build-revision|build-input-revision|head-sha>"
        )
    if args[0] == "source-tree-sha256":
        print(compute_source_tree_sha256())
    elif args[0] == "head-sha":
        print(compute_head_sha())
    else:
        print(compute_build_revision())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
