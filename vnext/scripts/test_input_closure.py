#!/usr/bin/env python3
"""Hash the conservative input closure used by each vNext package test suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "gateway.vnext.test-input-closure"
SCHEMA_VERSION = 2
PACKAGES = (
    "shared_kernel",
    "repository_contracts",
    "repository_client",
    "backend",
    "repository_service",
)

PACKAGE_PATHS = {package: f"vnext/{package}" for package in PACKAGES}

# These edges are the path dependencies loaded by uv and by the backend's Rust
# extension. Keeping the graph explicit makes transitive paths part of the
# manifest even when a direct dependency's own pyproject changes.
PATH_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "vnext/shared_kernel": (),
    "vnext/repository_contracts": (),
    "vnext/repository_client": ("vnext/repository_contracts",),
    "vnext/repository_service": ("vnext/repository_contracts",),
    "vnext/backend": (
        "vnext/shared_kernel",
        "vnext/repository_contracts",
        "vnext/repository_client",
        "vnext/rust/gateway-compute-python",
    ),
    "vnext/rust/gateway-compute-python": (
        "vnext/rust/gateway-compute-python-impl",
        "vnext/rust/gateway-compute-core",
    ),
    "vnext/rust/gateway-compute-python-impl": ("vnext/rust/gateway-compute-core",),
    "vnext/rust/gateway-compute-core": ("vnext/rust/gateway-shared-kernel",),
    "vnext/rust/gateway-shared-kernel": (),
    "vnext/rust/gateway-architecture-check": (),
}

COMMON_GIT_COMPONENTS = (
    ("shared:fixtures", "vnext/fixtures", "Golden files, schemas, vectors, and package test fixtures."),
    ("shared:scripts", "vnext/scripts", "Authoritative runner, uv wrapper, and scripts invoked by tests."),
    (
        "shared:workspace-definition",
        "vnext/repository-workspace.toml",
        "Shared repository workspace configuration read by development tooling.",
    ),
    (
        "shared:rust-toolchain-selector",
        "vnext/rust/rust-toolchain.toml",
        "rustup reads this selector when the manifest records the effective rustc version.",
    ),
    ("shared:deployment", "vnext/deploy", "Compose and deployment inputs inspected or used by tests."),
    (
        "shared:lock-snapshot:backend",
        "vnext/backend/uv.lock",
        "uv-consume checks all five lockfiles before and after each package command.",
    ),
    (
        "shared:lock-snapshot:repository-service",
        "vnext/repository_service/uv.lock",
        "uv-consume checks all five lockfiles before and after each package command.",
    ),
    (
        "shared:lock-snapshot:repository-client",
        "vnext/repository_client/uv.lock",
        "uv-consume checks all five lockfiles before and after each package command.",
    ),
    (
        "shared:lock-snapshot:repository-contracts",
        "vnext/repository_contracts/uv.lock",
        "uv-consume checks all five lockfiles before and after each package command.",
    ),
    (
        "shared:lock-snapshot:shared-kernel",
        "vnext/shared_kernel/uv.lock",
        "uv-consume checks all five lockfiles before and after each package command.",
    ),
)

PACKAGE_GIT_COMPONENTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "repository_service": (
        (
            "test-authority:runtime-provider-feasibility",
            "docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md",
            "Repository-service audit-corrective tests read this authority document to verify the measurement methodology version.",
        ),
    ),
    "backend": (
        (
            "rust:workspace",
            "vnext/rust",
            "Cargo workspace, Cargo.lock, rust-toolchain.toml, and all transitive crate sources; Git trees exclude target/.",
        ),
    ),
}

PACKAGE_DOCKER_INPUTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "backend": (
        (
            "docker:context:vnext",
            "vnext",
            "Backend and worker Compose builds use vnext/ as context; the same journey also builds repository-service.",
        ),
        (
            "docker:compose:backend",
            "vnext/deploy/compose.yaml",
            "Backend Compose tests select services and build arguments from this file.",
        ),
        (
            "dockerfile:backend",
            "vnext/backend/Dockerfile",
            "Backend and worker images are built from this Dockerfile.",
        ),
        (
            "dockerfile:repository-service",
            "vnext/repository_service/Dockerfile",
            "Backend Compose journeys build the repository-service image from this Dockerfile.",
        ),
    ),
    "repository_service": (
        (
            "docker:context:vnext",
            "vnext",
            "Repository-service and repository-client Compose builds use vnext/ as context.",
        ),
        (
            "docker:compose:repository-service",
            "vnext/deploy/compose.yaml",
            "Repository-service Compose tests select services and build arguments from this file.",
        ),
        (
            "dockerfile:repository-service",
            "vnext/repository_service/Dockerfile",
            "Repository-service Compose image is built from this Dockerfile.",
        ),
        (
            "dockerfile:repository-client-e2e",
            "vnext/repository_client/tests/Dockerfile",
            "Lifecycle Compose tests build the client e2e image from this Dockerfile.",
        ),
        (
            "dockerfile:repository-client-dependency-base",
            "vnext/repository_client/tests/Dockerfile.dependency-base",
            "Lifecycle Compose tests build the client dependency base image from this Dockerfile.",
        ),
    ),
}


class ClosureError(RuntimeError):
    """The closure could not be measured without making an unsafe assumption."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ClosureError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def require_clean_worktree(repo_root: Path) -> None:
    """Apply the same porcelain-v1 cleanliness rule as require_clean_worktree()."""
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ClosureError("unable to determine worktree status")
    if completed.stdout:
        raise ClosureError("worktree is dirty; test input manifests require a committed clean tree")


def expand_path_dependencies(
    node: str,
    graph: Mapping[str, Sequence[str]] = PATH_DEPENDENCIES,
) -> tuple[str, ...]:
    """Return all transitive dependency nodes in stable traversal order."""
    result: list[str] = []
    visited: set[str] = set()
    active: set[str] = set()

    def visit(current: str) -> None:
        if current in active:
            raise ClosureError(f"path dependency cycle includes {current}")
        if current in visited:
            return
        active.add(current)
        for dependency in graph.get(current, ()):
            if dependency not in visited:
                result.append(dependency)
            visit(dependency)
        active.remove(current)
        visited.add(current)

    visit(node)
    return tuple(result)


def _component_specs(package: str) -> list[dict[str, str]]:
    if package not in PACKAGE_PATHS:
        raise ClosureError(f"unknown package: {package}")
    package_path = PACKAGE_PATHS[package]
    specs = [
        {
            "name": f"package:{package}",
            "path": package_path,
            "reason": "Package source, tests, pyproject.toml, lockfile, and Python selector.",
        }
    ]
    for dependency in expand_path_dependencies(package_path):
        specs.append(
            {
                "name": f"path-dependency:{dependency}",
                "path": dependency,
                "reason": "Transitive uv or Rust path dependency of this package.",
            }
        )
    for name, path, reason in COMMON_GIT_COMPONENTS:
        specs.append({"name": name, "path": path, "reason": reason})
    for name, path, reason in PACKAGE_GIT_COMPONENTS.get(package, ()):
        specs.append({"name": name, "path": path, "reason": reason})
    for name, path, reason in PACKAGE_DOCKER_INPUTS.get(package, ()):
        specs.append({"name": name, "path": path, "reason": reason})
    return specs


def _legacy_content_digest(path: Path) -> str:
    if not path.exists():
        raise ClosureError(f"legacy input directory is missing: {path}")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise ClosureError(f"legacy input is not a directory: {path}")

    entries: list[tuple[str, Path]] = []
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            candidate = current_path / dirname
            if candidate.is_symlink():
                resolved = candidate.resolve(strict=True)
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise ClosureError(f"legacy symlink escapes its root: {candidate}") from exc
                if resolved.is_dir():
                    raise ClosureError(f"legacy contains a directory symlink: {candidate}")
                entries.append((candidate.relative_to(root).as_posix(), candidate))
            else:
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            candidate = current_path / filename
            resolved = candidate.resolve(strict=True)
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ClosureError(f"legacy symlink escapes its root: {candidate}") from exc
            entries.append((candidate.relative_to(root).as_posix(), candidate))

    digest = hashlib.sha256()
    for relative, candidate in sorted(entries, key=lambda item: item[0]):
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        if candidate.is_symlink():
            target = os.readlink(candidate).encode("utf-8")
            digest.update(b"symlink\0")
            digest.update(len(target).to_bytes(8, "big"))
            digest.update(target)
            source = candidate.resolve(strict=True)
        else:
            digest.update(b"file\0")
            source = candidate
        size = source.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _environment_content_digest(path: Path) -> str:
    """Hash the package's non-Git uv environment, excluding derived bytecode."""
    if not path.exists():
        raise ClosureError(f"package virtual environment is missing: {path}")
    resolved_root = path.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ClosureError(f"package virtual environment is not a directory: {path}")

    digest = hashlib.sha256()
    if path.is_symlink():
        link_target = os.readlink(path).encode("utf-8")
        digest.update(b"root-symlink\0")
        digest.update(len(link_target).to_bytes(8, "big"))
        digest.update(link_target)

    entries: list[tuple[str, Path, str]] = []
    def raise_walk_error(error: OSError) -> None:
        raise ClosureError(f"could not enumerate package virtual environment: {error}")

    for current, dirnames, filenames in os.walk(
        resolved_root,
        followlinks=False,
        onerror=raise_walk_error,
    ):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            candidate = current_path / dirname
            relative = candidate.relative_to(resolved_root).as_posix()
            if dirname == "__pycache__" or candidate.is_symlink():
                if dirname != "__pycache__":
                    entries.append((relative, candidate, "symlink"))
                continue
            entries.append((relative, candidate, "directory"))
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            if filename.endswith((".pyc", ".pyo")):
                continue
            candidate = current_path / filename
            relative = candidate.relative_to(resolved_root).as_posix()
            entries.append((relative, candidate, "symlink" if candidate.is_symlink() else "file"))

    for relative, candidate, entry_kind in sorted(entries, key=lambda item: item[0]):
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(entry_kind.encode("ascii") + b"\0")
        file_mode = candidate.lstat().st_mode & 0o777
        digest.update(file_mode.to_bytes(2, "big"))
        if entry_kind == "symlink":
            target = os.readlink(candidate).encode("utf-8")
            digest.update(len(target).to_bytes(8, "big"))
            digest.update(target)
        elif entry_kind == "file":
            size = candidate.stat().st_size
            digest.update(size.to_bytes(8, "big"))
            with candidate.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    return digest.hexdigest()


def _hypothesis_storage_path(repo_root: Path, package: str) -> Path:
    """Return Hypothesis's effective storage directory for the runner's package cwd."""
    project_dir = repo_root / PACKAGE_PATHS[package]
    configured_path = os.environ.get("HYPOTHESIS_STORAGE_DIRECTORY")
    if not configured_path:
        return project_dir / ".hypothesis"
    path = Path(configured_path)
    return path if path.is_absolute() else project_dir / path


def _pytest_cache_path(repo_root: Path, package: str) -> Path:
    """Return pytest's package-local default cache directory for the runner cwd."""
    return repo_root / PACKAGE_PATHS[package] / ".pytest_cache"


def _directory_content_digest(path: Path) -> str:
    """Hash a non-Git input directory, including names, types, modes, and bytes."""
    digest = hashlib.sha256()
    if not path.exists() and not path.is_symlink():
        digest.update(b"directory-missing\0")
        return digest.hexdigest()

    try:
        resolved_root = path.resolve(strict=True)
    except OSError as exc:
        raise ClosureError(f"could not resolve input directory {path}: {exc}") from exc
    if not resolved_root.is_dir():
        raise ClosureError(f"input path is not a directory: {path}")

    digest.update(b"directory\0")
    digest.update((resolved_root.stat().st_mode & 0o777).to_bytes(2, "big"))
    if path.is_symlink():
        link_target = os.readlink(path).encode("utf-8")
        digest.update(b"root-symlink\0")
        digest.update(len(link_target).to_bytes(8, "big"))
        digest.update(link_target)

    entries: list[tuple[str, Path, str]] = []

    def raise_walk_error(error: OSError) -> None:
        raise ClosureError(f"could not enumerate input directory {path}: {error}")

    for current, dirnames, filenames in os.walk(
        resolved_root,
        followlinks=False,
        onerror=raise_walk_error,
    ):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            candidate = current_path / dirname
            if candidate.is_symlink():
                raise ClosureError(f"input directory contains a directory symlink: {candidate}")
            entries.append((candidate.relative_to(resolved_root).as_posix(), candidate, "directory"))
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            candidate = current_path / filename
            entries.append(
                (
                    candidate.relative_to(resolved_root).as_posix(),
                    candidate,
                    "symlink" if candidate.is_symlink() else "file",
                )
            )

    for relative, candidate, entry_kind in sorted(entries, key=lambda item: item[0]):
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(entry_kind.encode("ascii") + b"\0")
        digest.update((candidate.lstat().st_mode & 0o777).to_bytes(2, "big"))
        if entry_kind == "directory":
            continue
        if entry_kind == "symlink":
            link_target = os.readlink(candidate).encode("utf-8")
            digest.update(len(link_target).to_bytes(8, "big"))
            digest.update(link_target)
            source = candidate.resolve(strict=True)
            if not source.is_file():
                raise ClosureError(f"input file symlink does not resolve to a file: {candidate}")
        else:
            source = candidate
        size = source.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _uv_environment_path(repo_root: Path, package: str) -> Path:
    project_dir = repo_root / PACKAGE_PATHS[package]
    configured_path = os.environ.get("UV_PROJECT_ENVIRONMENT")
    if not configured_path:
        return project_dir / ".venv"
    path = Path(configured_path)
    return path if path.is_absolute() else project_dir / path


def _manifest_path(repo_root: Path, path: Path) -> str:
    absolute = Path(os.path.abspath(path))
    try:
        return absolute.relative_to(repo_root).as_posix()
    except ValueError:
        return str(absolute)


def _command_output(command: Sequence[str], *, cwd: Path) -> str:
    executable = shutil.which(command[0]) if not Path(command[0]).is_absolute() else command[0]
    if not executable:
        raise ClosureError(f"required environment tool is missing: {command[0]}")
    completed = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    if completed.returncode != 0 or not output:
        raise ClosureError(
            f"could not read version for {command[0]}: {output or completed.returncode}"
        )
    return output


def collect_environment(repo_root: Path, package: str) -> dict[str, str]:
    """Read versions from the interpreter and tools used by the authoritative runner."""
    package_path = PACKAGE_PATHS[package]
    project_dir = repo_root / package_path
    uv_executable = shutil.which("uv")
    if not uv_executable:
        raise ClosureError("required environment tool is missing: uv")
    python_result = subprocess.run(
        [
            uv_executable,
            "--no-config",
            "python",
            "find",
            "--project",
            str(project_dir),
        ],
        cwd=project_dir,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if python_result.returncode != 0:
        message = "\n".join(
            part.strip() for part in (python_result.stdout, python_result.stderr) if part.strip()
        )
        raise ClosureError(f"could not resolve {package} Python interpreter: {message}")
    python_executable = python_result.stdout.strip()
    if not python_executable:
        raise ClosureError(f"uv did not return a Python interpreter for {package}")
    python_output = _command_output([python_executable, "-VV"], cwd=project_dir)
    python_unicode_data_version = _command_output(
        [python_executable, "-c", "import unicodedata; print(unicodedata.unidata_version)"],
        cwd=project_dir,
    )
    versions = {
        "python_-VV": python_output,
        "python_unicode_data_version": python_unicode_data_version,
        "dolt_version": _command_output(["dolt", "version"], cwd=repo_root),
        "uv_version": _command_output(["uv", "--version"], cwd=repo_root),
        "rustc_version": _command_output(["rustc", "--version"], cwd=repo_root / "vnext" / "rust"),
    }
    if package in PACKAGE_DOCKER_INPUTS:
        versions["docker_client_version"] = _command_output(["docker", "--version"], cwd=repo_root)
        versions["docker_server_version"] = _command_output(
            ["docker", "version", "--format", "{{.Server.Version}}"], cwd=repo_root
        )
        versions["docker_compose_version"] = _command_output(
            ["docker", "compose", "version"], cwd=repo_root
        )
        image_references = {"python:3.14.6-slim-bookworm"}
        if package == "backend":
            image_references.add("rust:1.97.0-bookworm")
        if package == "repository_service":
            image_references.add(
                os.environ.get(
                    "GATEWAY_REPOSITORY_BASE_IMAGE",
                    "python:3.14.6-slim-bookworm",
                )
                or "python:3.14.6-slim-bookworm"
            )
        image_ids = {
            reference: _command_output(
                ["docker", "image", "inspect", "--format", "{{.Id}}", reference],
                cwd=repo_root,
            )
            for reference in sorted(image_references)
        }
        versions["docker_base_image_ids"] = json.dumps(
            image_ids,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return versions


def _git_component_identity(repo_root: Path, revision: str, path: str) -> tuple[str, str]:
    object_id = _run_git(repo_root, "rev-parse", "--verify", f"{revision}:{path}")
    if len(object_id) != 40 or any(character not in "0123456789abcdef" for character in object_id):
        raise ClosureError(f"unexpected Git object id for {path}: {object_id}")
    object_type = _run_git(repo_root, "cat-file", "-t", object_id)
    if object_type not in {"blob", "tree"}:
        raise ClosureError(f"unexpected Git object type for {path}: {object_type}")
    return object_id, object_type


def _finish_manifest(
    *,
    package: str,
    head: str,
    worktree_head: str,
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    digest_components = [
        {
            key: component[key]
            for key in ("name", "kind", "git_object_type", "paths", "digest")
        }
        for component in components
    ]
    manifest_components = []
    for component in components:
        rendered = dict(component)
        manifest_components.append(rendered)
    payload = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "package": package,
        "components": digest_components,
    }
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "package": package,
        "components": manifest_components,
        "head": head,
        "worktree_head": worktree_head,
        "clean_worktree": True,
        "total_digest": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }


def build_manifest(
    repo_root: Path,
    package: str,
    *,
    revision: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve(strict=True)
    require_clean_worktree(repo_root)
    if package not in PACKAGE_PATHS:
        raise ClosureError(f"unknown package: {package}")
    head = _run_git(repo_root, "rev-parse", "--verify", "HEAD^{commit}")
    selected_revision = _run_git(
        repo_root,
        "rev-parse",
        "--verify",
        f"{revision or head}^{{commit}}",
    )

    components: list[dict[str, Any]] = []
    for spec in _component_specs(package):
        object_id, object_type = _git_component_identity(
            repo_root,
            selected_revision,
            spec["path"],
        )
        components.append(
            {
                "name": spec["name"],
                "kind": "git",
                "git_object_type": object_type,
                "paths": [spec["path"]],
                "digest": object_id,
                "reason": spec["reason"],
            }
        )

    legacy_path = repo_root / "legacy"
    components.append(
        {
            "name": "non-git:legacy-content",
            "kind": "content",
            "git_object_type": None,
            "paths": ["legacy"],
            "digest": _legacy_content_digest(legacy_path),
            "reason": "The table-rules resolver tests use the untracked legacy reference tree.",
        }
    )

    environment_path = _uv_environment_path(repo_root, package)
    components.append(
        {
            "name": "non-git:package-uv-environment",
            "kind": "content",
            "git_object_type": None,
            "paths": [_manifest_path(repo_root, environment_path)],
            "digest": _environment_content_digest(environment_path),
            "reason": (
                "Installed Python and native test dependencies are read from this uv environment; "
                "the digest includes its files and executable modes, excluding __pycache__ and "
                ".pyc/.pyo files derived from locked sources and the recorded interpreter."
            ),
        }
    )

    hypothesis_storage_path = _hypothesis_storage_path(repo_root, package)
    components.append(
        {
            "name": "non-git:hypothesis-storage",
            "kind": "content",
            "git_object_type": None,
            "paths": [_manifest_path(repo_root, hypothesis_storage_path)],
            "digest": _directory_content_digest(hypothesis_storage_path),
            "reason": (
                "Hypothesis may read cached constants, Unicode data, and examples while generating "
                "test inputs; hash the effective package storage directory, including an explicit "
                "missing-directory state."
            ),
        }
    )

    pytest_cache_path = _pytest_cache_path(repo_root, package)
    components.append(
        {
            "name": "non-git:pytest-cache",
            "kind": "content",
            "git_object_type": None,
            "paths": [_manifest_path(repo_root, pytest_cache_path)],
            "digest": _directory_content_digest(pytest_cache_path),
            "reason": (
                "pytest's cache provider reads and writes the package-local .pytest_cache directory; "
                "hash its complete content and permissions, including an explicit missing-directory state."
            ),
        }
    )

    environment_values = dict(environment) if environment is not None else collect_environment(
        repo_root, package
    )
    if not environment_values:
        raise ClosureError("environment version set must not be empty")
    components.append(
        {
            "name": "environment:python-dolt-uv-rustc",
            "kind": "environment",
            "git_object_type": None,
            "paths": [],
            "digest": hashlib.sha256(_canonical_json(environment_values)).hexdigest(),
            "values": environment_values,
            "reason": "Runtime and build tool versions used by the package test environment.",
        }
    )
    components.sort(key=lambda component: component["name"])
    return _finish_manifest(
        package=package,
        head=selected_revision,
        worktree_head=head,
        components=components,
    )


def compare_manifests(source: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    for manifest_name, manifest in (("source", source), ("current", current)):
        if manifest.get("schema") != SCHEMA or manifest.get("schema_version") != SCHEMA_VERSION:
            raise ClosureError(f"{manifest_name} manifest has an unsupported schema")
        if manifest.get("clean_worktree") is not True:
            raise ClosureError(f"{manifest_name} manifest was not measured from a clean worktree")
    source_package = source.get("package")
    current_package = current.get("package")
    if source_package != current_package:
        raise ClosureError("source and current manifests are for different packages")
    if not isinstance(source_package, str) or source_package not in PACKAGES:
        raise ClosureError("manifest package is unknown")

    def by_name(manifest: Mapping[str, Any], *, manifest_name: str) -> dict[str, Mapping[str, Any]]:
        raw_components = manifest.get("components")
        if not isinstance(raw_components, list):
            raise ClosureError("manifest components must be a list")
        result: dict[str, Mapping[str, Any]] = {}
        for raw_component in raw_components:
            if not isinstance(raw_component, dict) or not isinstance(raw_component.get("name"), str):
                raise ClosureError("manifest component is malformed")
            name = raw_component["name"]
            if name in result:
                raise ClosureError(f"duplicate manifest component: {name}")
            if (
                not isinstance(raw_component.get("kind"), str)
                or raw_component.get("git_object_type") not in {None, "blob", "tree"}
                or not isinstance(raw_component.get("paths"), list)
                or any(not isinstance(path, str) for path in raw_component["paths"])
                or not isinstance(raw_component.get("digest"), str)
            ):
                raise ClosureError(f"manifest component is malformed: {name}")
            result[name] = raw_component

        digest_payload = {
            "schema": manifest["schema"],
            "schema_version": manifest["schema_version"],
            "package": manifest["package"],
            "components": [
                {
                    key: component[key]
                    for key in ("name", "kind", "git_object_type", "paths", "digest")
                }
                for component in sorted(result.values(), key=lambda item: item["name"])
            ],
        }
        expected_total_digest = hashlib.sha256(_canonical_json(digest_payload)).hexdigest()
        if manifest.get("total_digest") != expected_total_digest:
            raise ClosureError(f"{manifest_name} manifest total digest is invalid")
        return result

    source_components = by_name(source, manifest_name="source")
    current_components = by_name(current, manifest_name="current")
    changed: list[dict[str, Any]] = []
    for name in sorted(source_components.keys() | current_components.keys()):
        source_component = source_components.get(name)
        current_component = current_components.get(name)
        source_signature = (
            {
                key: source_component[key]
                for key in ("kind", "git_object_type", "paths", "digest")
            }
            if source_component
            else None
        )
        current_signature = (
            {
                key: current_component[key]
                for key in ("kind", "git_object_type", "paths", "digest")
            }
            if current_component
            else None
        )
        if source_signature == current_signature:
            continue
        changed.append({
            "component": name,
            "source_kind": source_component.get("kind") if source_component else None,
            "current_kind": current_component.get("kind") if current_component else None,
            "source_git_object_type": (
                source_component.get("git_object_type") if source_component else None
            ),
            "current_git_object_type": (
                current_component.get("git_object_type") if current_component else None
            ),
            "source_paths": source_component.get("paths") if source_component else None,
            "current_paths": current_component.get("paths") if current_component else None,
            "source_digest": source_component.get("digest") if source_component else None,
            "current_digest": current_component.get("digest") if current_component else None,
        })
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "package": source_package,
        "source_head": source.get("head"),
        "current_head": current.get("head"),
        "source_total_digest": source.get("total_digest"),
        "current_total_digest": current.get("total_digest"),
        "status": "可沿用" if not changed else "运行",
        "changed_components": changed,
    }


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError(f"could not read manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ClosureError(f"manifest must be a JSON object: {path}")
    return value


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    manifest_parser = subparsers.add_parser("manifest", help="emit one package manifest as JSON")
    manifest_parser.add_argument("--root", type=Path, default=_default_repo_root())
    manifest_parser.add_argument("--package", choices=PACKAGES, required=True)
    manifest_parser.add_argument("--revision", help="measure tracked inputs at this commit")
    compare_parser = subparsers.add_parser("compare", help="compare source and current manifests")
    compare_parser.add_argument("--root", type=Path, default=_default_repo_root())
    compare_parser.add_argument("--source", type=Path, required=True)
    compare_parser.add_argument("--current", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        repo_root = args.root.resolve(strict=True)
        require_clean_worktree(repo_root)
        if args.command == "manifest":
            result = build_manifest(
                repo_root,
                args.package,
                revision=args.revision,
            )
        else:
            current_manifest = _read_manifest(args.current)
            current_head = _run_git(repo_root, "rev-parse", "--verify", "HEAD^{commit}")
            if current_manifest.get("head") != current_head:
                raise ClosureError("current manifest HEAD does not match the clean worktree HEAD")
            result = compare_manifests(_read_manifest(args.source), current_manifest)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (ClosureError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
