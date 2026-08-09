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


def _archive_digest(repo_root: Path) -> str:
    archive_paths = [f"vnext/{subdir}" for subdir in BUILD_CONTEXT_SUBDIRS]
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "HEAD", *archive_paths],
        check=True,
        capture_output=True,
    )
    return hashlib.sha256(completed.stdout).hexdigest()


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
    repo_root = repo_root_from_vnext(root)
    if is_build_context_clean(repo_root):
        return f"sha256:{_archive_digest(repo_root)}"
    return f"sha256:{_working_tree_digest(root)}"


def compute_build_revision(*, vnext_root: Path | None = None) -> str:
    root = vnext_root if vnext_root is not None else vnext_root_from_here()
    repo_root = repo_root_from_vnext(root)
    head = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if is_build_context_clean(repo_root):
        return head
    short_digest = compute_source_tree_sha256(vnext_root=root).removeprefix("sha256:")[:12]
    return f"{head}-dirty-{short_digest}"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or args[0] not in {"source-tree-sha256", "build-revision"}:
        raise SystemExit("usage: build_context_digest.py <source-tree-sha256|build-revision>")
    if args[0] == "source-tree-sha256":
        print(compute_source_tree_sha256())
    else:
        print(compute_build_revision())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
