#!/usr/bin/env python3
"""Hash the conservative input closure used by each vNext package test suite."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tomllib
import zlib
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "gateway.vnext.test-input-closure"
SCHEMA_VERSION = 10
MAX_GZIP_JSON_PAYLOAD_BYTES = 64 * 1024 * 1024
RUST_PACKAGE = "rust"
PYTHON_PACKAGES = (
    "shared_kernel",
    "repository_contracts",
    "repository_client",
    "backend",
    "repository_service",
)
PACKAGES = (RUST_PACKAGE, *PYTHON_PACKAGES)

PACKAGE_PATHS = {package: f"vnext/{package}" for package in PACKAGES}

# Environment variables that change what cargo, rustc, or PyO3's build script
# produce. The runner's CARGO_TARGET_DIR is a build cache, not an input.
RUST_ENVIRONMENT_PREFIXES = ("CARGO_", "RUST", "PYO3_")
RUST_ENVIRONMENT_NAMES = ("CONDA_PREFIX", "HOME", "LANG", "LC_ALL", "PATH", "TZ", "VIRTUAL_ENV")
RUST_ENVIRONMENT_EXCLUDED = frozenset({"CARGO_TARGET_DIR"})

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
    RUST_PACKAGE: (
        (
            "rust:cargo-lock",
            "vnext/rust/Cargo.lock",
            "cargo runs with --locked --offline; the lockfile pins every crate the workspace builds.",
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
            "dockerfile:backend-dependency-base",
            "vnext/backend/Dockerfile.dependency-base",
            "The retained backend dependency-base image is built from this Dockerfile.",
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

DOCKER_INPUT_ENVIRONMENT: dict[str, tuple[str, ...]] = {
    "backend": (
        "DOCKER_CERT_PATH",
        "DOCKER_CONFIG",
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "GATEWAY_BACKEND_UV_BOOTSTRAP_INDEX_URL",
        "GATEWAY_BACKEND_UV_BOOTSTRAP_TRUSTED_HOST",
        "GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE",
        "GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES",
        "GATEWAY_COMPOSE_GATE_PREBUILT",
        "GATEWAY_COMPOSE_GATE_PROJECT_NAME",
        "GATEWAY_COMPOSE_GATE_SESSION",
        "GATEWAY_DOCKER_BUILD_NETWORK",
        "GATEWAY_P2R1_CACHE_URL",
        "GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE",
        "GATEWAY_P2R1_BUILD_INPUT_REVISION",
        "GATEWAY_P2R1_CANDIDATE_SHA",
        "GATEWAY_P2R1_SOURCE_TREE_SHA256",
        "GATEWAY_P2R1_UV_LOCK_SHA256",
        "GATEWAY_UV_CONSUME",
        "GATEWAY_VNEXT_LOCK_ROOT",
        "GATEWAY_REPOSITORY_BASE_IMAGE",
        "GATEWAY_REPOSITORY_DOLT_DOWNLOAD_URL",
        "GATEWAY_REPOSITORY_SERVICE_IMAGE",
        "GATEWAY_REPOSITORY_UV_BOOTSTRAP_INDEX_URL",
        "GATEWAY_REPOSITORY_UV_BOOTSTRAP_TRUSTED_HOST",
        "GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "HOME",
        "LANG",
        "LC_ALL",
        "NO_PROXY",
        "PATH",
        "PYTHONPATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TMPDIR",
        "TZ",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    ),
    "repository_service": (
        "DOCKER_CERT_PATH",
        "DOCKER_CONFIG",
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "GATEWAY_DOCKER_BUILD_NETWORK",
        "GATEWAY_P2R1_CACHE_URL",
        "GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE",
        "GATEWAY_P2R1_BUILD_INPUT_REVISION",
        "GATEWAY_P2R1_CANDIDATE_SHA",
        "GATEWAY_P2R1_SOURCE_TREE_SHA256",
        "GATEWAY_P2R1_UV_LOCK_SHA256",
        "GATEWAY_UV_CONSUME",
        "GATEWAY_VNEXT_LOCK_ROOT",
        "GATEWAY_REPOSITORY_BASE_IMAGE",
        "GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE",
        "GATEWAY_REPOSITORY_DOLT_DOWNLOAD_URL",
        "GATEWAY_REPOSITORY_SERVICE_IMAGE",
        "GATEWAY_REPOSITORY_UV_BOOTSTRAP_INDEX_URL",
        "GATEWAY_REPOSITORY_UV_BOOTSTRAP_TRUSTED_HOST",
        "GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "HOME",
        "LANG",
        "LC_ALL",
        "NO_PROXY",
        "PATH",
        "PYTHONPATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TMPDIR",
        "TZ",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    ),
}

DEFAULT_REPOSITORY_SERVICE_IMAGE = "gateway-repository-service:local"
DEFAULT_REPOSITORY_BASE_IMAGE = "python:3.14.6-slim-bookworm"
DEFAULT_REPOSITORY_CLIENT_IMAGE = "gateway-repository-client-e2e:local"
DEFAULT_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE = "gateway-repository-client-e2e-base:local"


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
            "reason": (
                "Cargo workspace, every crate's sources and tests, Cargo.lock, and "
                "rust-toolchain.toml; Git trees exclude the untracked target/."
                if package == RUST_PACKAGE
                else "Package source, tests, pyproject.toml, lockfile, and Python selector."
            ),
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


def _hash_gzip_json_payload(digest: Any, path: Path) -> None:
    """Hash the decoded content of a gzip JSON cache, ignoring its temporary filename header."""
    payload_digest = hashlib.sha256()
    payload_size = 0
    try:
        with gzip.open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                payload_size += len(chunk)
                if payload_size > MAX_GZIP_JSON_PAYLOAD_BYTES:
                    raise ClosureError(f"gzip JSON cache exceeds digest limit: {path}")
                payload_digest.update(chunk)
    except (OSError, EOFError, zlib.error) as exc:
        raise ClosureError(f"could not decode gzip JSON cache {path}: {exc}") from exc

    digest.update(b"gzip-json-payload\0")
    digest.update(payload_size.to_bytes(8, "big"))
    digest.update(payload_digest.digest())


def _directory_content_digest(
    path: Path,
    *,
    normalize_hypothesis_gzip: bool = False,
) -> str:
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
        if (
            normalize_hypothesis_gzip
            and entry_kind == "file"
            and relative.startswith("unicode_data/")
            and candidate.name.endswith(".json.gz")
        ):
            _hash_gzip_json_payload(digest, source)
            continue
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


def _docker_image_id(repo_root: Path, image_reference: str) -> str:
    completed = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image_reference],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode == 0 and completed.stdout.strip():
        return completed.stdout.strip()
    error = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    lowered_error = error.lower()
    if any(
        marker in lowered_error
        for marker in ("no such image", "no such object", "not found")
    ):
        return "missing"
    raise ClosureError(f"could not inspect Docker image {image_reference}: {error or completed.returncode}")


def _docker_image_inventory(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["docker", "image", "ls", "--no-trunc", "--format", "{{.Repository}}:{{.Tag}} {{.ID}}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        error = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
        raise ClosureError(f"could not inspect Docker image inventory: {error or completed.returncode}")
    return sorted(line.strip() for line in completed.stdout.splitlines() if line.strip())


def _external_override_inputs(
    repo_root: Path,
    environment: Mapping[str, str],
) -> dict[str, str | None]:
    results: dict[str, str | None] = {
        "uv_consume_script_sha256": None,
        "lock_snapshot_sha256": None,
    }
    configured_consumer = environment.get("GATEWAY_UV_CONSUME")
    if configured_consumer:
        consumer_path = Path(configured_consumer)
        if not consumer_path.is_absolute():
            consumer_path = repo_root / consumer_path
        if not consumer_path.is_file():
            raise ClosureError(f"configured uv-consume script is missing: {consumer_path}")
        results["uv_consume_script_sha256"] = hashlib.sha256(
            consumer_path.read_bytes()
        ).hexdigest()

    configured_lock_root = environment.get("GATEWAY_VNEXT_LOCK_ROOT")
    if configured_lock_root:
        lock_root = Path(configured_lock_root)
        if not lock_root.is_absolute():
            lock_root = repo_root / lock_root
        lock_hashes: dict[str, str] = {}
        for package in PYTHON_PACKAGES:
            package_path = PACKAGE_PATHS[package]
            lock_path = lock_root / package_path.removeprefix("vnext/") / "uv.lock"
            if not lock_path.is_file():
                raise ClosureError(f"configured lock snapshot is missing: {lock_path}")
            lock_hashes[package] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
        results["lock_snapshot_sha256"] = hashlib.sha256(
            _canonical_json(lock_hashes)
        ).hexdigest()
    return results


def _docker_build_inputs(
    repo_root: Path,
    package: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Capture Docker selectors, sensitive settings, and build-input image IDs."""
    if package not in PACKAGE_DOCKER_INPUTS:
        return {}
    environment = os.environ if environ is None else environ
    setting_names = set(DOCKER_INPUT_ENVIRONMENT[package])
    setting_names.update(
        name
        for name in environment
        if name.startswith(("COMPOSE_", "DOCKER_", "GATEWAY_", "UV_"))
        and name not in {"GATEWAY_TEST_PACKAGES", "GATEWAY_TEST_WORKERS"}
        and not name.startswith("GATEWAY_AUDIT_")
    )
    setting_fingerprints = {
        name: {
            "set": name in environment,
            "sha256": (
                hashlib.sha256(environment[name].encode("utf-8")).hexdigest()
                if name in environment
                else None
            ),
        }
        for name in sorted(setting_names)
    }

    repository_lock = repo_root / "vnext" / "repository_service" / "uv.lock"
    repository_lock_sha256 = hashlib.sha256(repository_lock.read_bytes()).hexdigest()
    repository_service_image = (
        environment.get("GATEWAY_REPOSITORY_SERVICE_IMAGE") or DEFAULT_REPOSITORY_SERVICE_IMAGE
    )
    repository_base_image = (
        environment.get("GATEWAY_REPOSITORY_BASE_IMAGE") or DEFAULT_REPOSITORY_BASE_IMAGE
    )
    dependency_base_image = environment.get("GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE") or (
        f"gateway-p2r1-repository:lock-{repository_lock_sha256[:12]}"
    )
    selections = {
        "repository_service_image": repository_service_image,
        "repository_service_base_image": repository_base_image,
        "repository_service_dependency_base_image": dependency_base_image,
        "repository_service_use_preloaded_dependencies": (
            environment.get("GATEWAY_REPOSITORY_USE_PRELOADED_DEPENDENCIES") or "0"
        ),
        "compose_build_network": environment.get("GATEWAY_DOCKER_BUILD_NETWORK") or "",
        "repository_service_script_build_network": (
            environment.get("GATEWAY_DOCKER_BUILD_NETWORK") or "host"
        ),
    }
    image_references = {
        "python:3.14.6-slim-bookworm",
        repository_base_image,
        repository_service_image,
        dependency_base_image,
    }
    if package == "backend":
        toolchain_selector = tomllib.loads(
            (repo_root / "vnext" / "rust" / "rust-toolchain.toml").read_text(
                encoding="utf-8"
            )
        )["toolchain"]
        default_backend_dependency_base_image = (
            f"rust:{toolchain_selector['channel']}-bookworm"
        )
        backend_dependency_base_image = (
            environment.get("GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE")
            or default_backend_dependency_base_image
        )
        selections["backend_dependency_base_image"] = backend_dependency_base_image
        selections["backend_use_preloaded_dependencies"] = (
            environment.get("GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES") or "0"
        )
        image_references.add(backend_dependency_base_image)
    else:
        client_dependency_base_image = (
            environment.get("GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE")
            or DEFAULT_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE
        )
        selections["repository_client_image"] = DEFAULT_REPOSITORY_CLIENT_IMAGE
        selections["repository_client_dependency_base_image"] = client_dependency_base_image
        image_references.add(DEFAULT_REPOSITORY_CLIENT_IMAGE)
        image_references.add(client_dependency_base_image)

    configured_image_references = {
        name: value
        for name, value in environment.items()
        if name.startswith("GATEWAY_") and name.endswith("_IMAGE") and value
    }
    selections["configured_image_references"] = dict(sorted(configured_image_references.items()))
    image_references.update(configured_image_references.values())

    # These tags name outputs rebuilt by the Compose harness from the current
    # source identity. Their selected names are inputs; their changing local
    # image IDs are outputs and must not make a later manifest differ.
    harness_rebuilt_images = {
        DEFAULT_REPOSITORY_SERVICE_IMAGE,
        DEFAULT_REPOSITORY_CLIENT_IMAGE,
    }
    image_references.difference_update(harness_rebuilt_images)

    image_ids = {
        reference: _docker_image_id(repo_root, reference)
        for reference in sorted(image_references)
    }
    prebuilt_enabled = environment.get("GATEWAY_COMPOSE_GATE_PREBUILT", "").strip() in {
        "1",
        "true",
        "yes",
    }
    selections["compose_gate_prebuilt"] = prebuilt_enabled
    prebuilt_inventory: list[str] | None = None
    if package == "backend" and prebuilt_enabled:
        # Per-test Compose project names can include the current pid and tmp path. When
        # the harness is told to skip builds, every local image may be a possible input.
        prebuilt_inventory = _docker_image_inventory(repo_root)

    return {
        "setting_fingerprints": setting_fingerprints,
        "effective_selections": selections,
        "image_ids": image_ids,
        "prebuilt_local_image_inventory": prebuilt_inventory,
        "external_override_inputs": _external_override_inputs(repo_root, environment),
    }


def _rust_environment_fingerprints(environment: Mapping[str, str]) -> dict[str, object]:
    """Fingerprint environment settings that can change Rust build or test results."""
    names = set(RUST_ENVIRONMENT_NAMES)
    names.update(name for name in environment if name.startswith(RUST_ENVIRONMENT_PREFIXES))
    names.difference_update(RUST_ENVIRONMENT_EXCLUDED)
    return {
        name: {
            "set": name in environment,
            "sha256": (
                hashlib.sha256(environment[name].encode("utf-8")).hexdigest()
                if name in environment
                else None
            ),
        }
        for name in sorted(names)
    }


def _pyo3_interpreter(environment: Mapping[str, str]) -> str | None:
    """Return the interpreter PyO3's build script selects, in its documented order."""
    configured = environment.get("PYO3_PYTHON")
    if configured:
        return configured
    for prefix_name in ("VIRTUAL_ENV", "CONDA_PREFIX"):
        prefix = environment.get(prefix_name)
        if prefix:
            candidate = Path(prefix) / "bin" / "python"
            if candidate.exists():
                return str(candidate)
    for name in ("python3", "python"):
        found = shutil.which(name, path=environment.get("PATH"))
        if found:
            return found
    return None


def collect_rust_environment(
    repo_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Read the Rust toolchain selected in vnext/rust and the settings that affect it."""
    environment = os.environ if environ is None else environ
    workspace = repo_root / PACKAGE_PATHS[RUST_PACKAGE]
    versions = {
        "rustc_version": _command_output(["rustc", "-vV"], cwd=workspace),
        "cargo_version": _command_output(["cargo", "--version"], cwd=workspace),
        "rustfmt_version": _command_output(["rustfmt", "--version"], cwd=workspace),
        "clippy_driver_version": _command_output(["clippy-driver", "--version"], cwd=workspace),
        "pyo3_python": environment.get("PYO3_PYTHON") or "",
    }
    interpreter = _pyo3_interpreter(environment)
    versions["pyo3_interpreter_-VV"] = (
        _command_output([interpreter, "-VV"], cwd=workspace) if interpreter else "missing"
    )
    versions["rust_build_settings"] = json.dumps(
        _rust_environment_fingerprints(environment),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return versions


def _cargo_config_files(
    repo_root: Path,
    environment: Mapping[str, str],
) -> list[Path]:
    """List the existing cargo config files that cargo reads for vnext/rust."""
    workspace = repo_root / PACKAGE_PATHS[RUST_PACKAGE]
    directories = [workspace, *workspace.parents]
    cargo_home = environment.get("CARGO_HOME")
    if cargo_home:
        home_directory = Path(cargo_home)
    elif environment.get("HOME"):
        home_directory = Path(environment["HOME"]) / ".cargo"
    else:
        home_directory = None
    candidates: list[Path] = []
    for directory in directories:
        candidates.extend(
            (directory / ".cargo" / "config.toml", directory / ".cargo" / "config")
        )
    if home_directory is not None:
        candidates.extend((home_directory / "config.toml", home_directory / "config"))
    result: list[Path] = []
    for candidate in candidates:
        absolute = Path(os.path.abspath(candidate))
        if absolute not in result and (absolute.exists() or absolute.is_symlink()):
            if not absolute.is_file():
                raise ClosureError(f"cargo config is not a regular file: {absolute}")
            result.append(absolute)
    return result


def _cargo_config_digest(
    repo_root: Path,
    environment: Mapping[str, str],
) -> tuple[str, list[str]]:
    """Hash cargo config files by path and content; missing files are omitted."""
    digest = hashlib.sha256()
    digest.update(b"cargo-config-v1\0")
    entries: list[str] = []
    for path in _cargo_config_files(repo_root, environment):
        manifest_path = _manifest_path(repo_root, path)
        content_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        encoded_path = manifest_path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(bytes.fromhex(content_sha256))
        entries.append(f"{manifest_path} sha256={content_sha256}")
    return digest.hexdigest(), entries


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
        docker_context = _command_output(["docker", "context", "show"], cwd=repo_root)
        docker_endpoint = _command_output(
            [
                "docker",
                "context",
                "inspect",
                docker_context,
                "--format",
                "{{json .Endpoints.docker}}",
            ],
            cwd=repo_root,
        )
        versions["docker_context"] = docker_context
        versions["docker_context_endpoint_sha256"] = hashlib.sha256(
            docker_endpoint.encode("utf-8")
        ).hexdigest()
        versions["docker_platform_and_driver"] = _command_output(
            ["docker", "info", "--format", "{{.OSType}}/{{.Architecture}} {{.Driver}}"],
            cwd=repo_root,
        )
        versions["docker_build_inputs"] = json.dumps(
            _docker_build_inputs(repo_root, package),
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


def _dockerignore_patterns(dockerignore_path: Path) -> tuple[re.Pattern[str], ...]:
    """Compile the Docker ignore syntax used by this context, failing closed on extensions."""
    if dockerignore_path.is_symlink() or not dockerignore_path.is_file():
        raise ClosureError(f"Docker context requires a regular .dockerignore: {dockerignore_path}")
    try:
        lines = dockerignore_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ClosureError(f"could not read Docker ignore rules {dockerignore_path}: {exc}") from exc

    compiled: list[re.Pattern[str]] = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or raw_line.startswith("#"):
            continue
        if line.startswith("!"):
            raise ClosureError(
                f"unsupported negated Docker ignore rule at {dockerignore_path}:{line_number}"
            )
        pattern = posixpath.normpath(line).strip("/")
        if pattern in {"", "."}:
            continue
        if pattern == ".." or pattern.startswith("../"):
            raise ClosureError(
                f"unsupported parent-relative Docker ignore rule at "
                f"{dockerignore_path}:{line_number}: {line}"
            )
        if any(character in pattern for character in "[]\\"):
            raise ClosureError(
                f"unsupported Docker ignore glob at {dockerignore_path}:{line_number}: {line}"
            )

        translated: list[str] = []
        index = 0
        while index < len(pattern):
            if pattern.startswith("**/", index):
                translated.append("(?:.*/)?")
                index += 3
            elif pattern.startswith("**", index):
                raise ClosureError(
                    f"unsupported Docker double-star glob at "
                    f"{dockerignore_path}:{line_number}: {line}"
                )
            elif pattern[index] == "*":
                translated.append("[^/]*")
                index += 1
            elif pattern[index] == "?":
                translated.append("[^/]")
                index += 1
            else:
                translated.append(re.escape(pattern[index]))
                index += 1
        expression = "".join(translated)
        compiled.append(re.compile(rf"^{expression}$"))
    return tuple(compiled)


def _docker_context_non_git_digest(
    repo_root: Path,
    context: str,
    dockerfiles: Sequence[str],
) -> tuple[str, list[str]]:
    """Hash non-Git filesystem entries Docker will include from a build context."""
    context_root = repo_root / context
    if not context_root.is_dir() or context_root.is_symlink():
        raise ClosureError(f"Docker context is not a regular directory: {context_root}")
    rules = _dockerignore_patterns(context_root / ".dockerignore")
    for dockerfile in dockerfiles:
        dockerfile_path = Path(dockerfile)
        specific_ignore = repo_root / dockerfile_path.with_name(
            f"{dockerfile_path.name}.dockerignore"
        )
        if specific_ignore.exists() or specific_ignore.is_symlink():
            raise ClosureError(
                "Dockerfile-specific ignore rules require explicit closure modeling: "
                f"{specific_ignore}"
            )

    tracked_paths = {
        path
        for path in _run_git(repo_root, "ls-files", "-z").split("\0")
        if path
    }
    tracked_files: set[str] = set()
    tracked_directories: set[str] = set()
    prefix = f"{context.rstrip('/')}/"
    for path in tracked_paths:
        if path == context:
            tracked_files.add("")
            continue
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix) :]
        tracked_files.add(relative)
        parent = Path(relative).parent
        while parent != Path("."):
            tracked_directories.add(parent.as_posix())
            parent = parent.parent

    def ignored(relative: str) -> bool:
        return any(rule.fullmatch(relative) is not None for rule in rules)

    entries: list[tuple[str, Path, str]] = []

    def raise_walk_error(error: OSError) -> None:
        raise ClosureError(f"could not enumerate Docker context {context_root}: {error}")

    for current, dirnames, filenames in os.walk(
        context_root,
        topdown=True,
        followlinks=False,
        onerror=raise_walk_error,
    ):
        current_path = Path(current)
        current_relative = current_path.relative_to(context_root).as_posix()
        if current_relative == ".":
            current_relative = ""
        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            candidate = current_path / dirname
            relative = f"{current_relative}/{dirname}" if current_relative else dirname
            if ignored(relative):
                continue
            if candidate.is_symlink():
                if relative not in tracked_files:
                    entries.append((relative, candidate, "symlink"))
                continue
            if relative not in tracked_directories:
                entries.append((relative, candidate, "directory"))
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in sorted(filenames):
            candidate = current_path / filename
            relative = f"{current_relative}/{filename}" if current_relative else filename
            if ignored(relative) or relative in tracked_files:
                continue
            if candidate.is_symlink():
                entry_kind = "symlink"
            elif candidate.is_file():
                entry_kind = "file"
            else:
                raise ClosureError(f"unsupported filesystem entry in Docker context: {candidate}")
            entries.append((relative, candidate, entry_kind))

    ordered_entries = sorted(entries, key=lambda item: item[0])
    digest = hashlib.sha256()
    digest.update(b"docker-context-non-git-v1\0")
    for relative, candidate, entry_kind in ordered_entries:
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(entry_kind.encode("ascii") + b"\0")
        digest.update((candidate.lstat().st_mode & 0o777).to_bytes(2, "big"))
        if entry_kind == "directory":
            continue
        if entry_kind == "symlink":
            target = os.readlink(candidate).encode("utf-8")
            digest.update(len(target).to_bytes(8, "big"))
            digest.update(target)
            continue
        size = candidate.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    included_paths = [
        f"{context.rstrip('/')}/{relative}"
        for relative, _, _ in ordered_entries
    ]
    return digest.hexdigest(), included_paths


def _docker_context_tracked_mode_digest(
    repo_root: Path,
    context: str,
) -> tuple[str, list[str]]:
    """Hash local permission bits Git omits for tracked Docker context paths."""
    context_root = repo_root / context
    if not context_root.is_dir() or context_root.is_symlink():
        raise ClosureError(f"Docker context is not a regular directory: {context_root}")

    tracked_paths = {
        path
        for path in _run_git(repo_root, "ls-files", "-z").split("\0")
        if path
    }
    prefix = f"{context.rstrip('/')}/"
    relative_paths = {"."}
    for path in tracked_paths:
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix) :]
        if not relative:
            continue
        relative_paths.add(relative)
        parent = Path(relative).parent
        while parent != Path("."):
            relative_paths.add(parent.as_posix())
            parent = parent.parent

    digest = hashlib.sha256()
    digest.update(b"docker-context-tracked-worktree-modes-v1\0")
    entries: list[str] = []
    for relative in sorted(relative_paths):
        candidate = context_root if relative == "." else context_root / relative
        try:
            file_info = candidate.lstat()
        except OSError as exc:
            raise ClosureError(
                f"could not stat tracked Docker context path {candidate}: {exc}"
            ) from exc
        if stat.S_ISDIR(file_info.st_mode):
            entry_kind = "directory"
        elif stat.S_ISLNK(file_info.st_mode):
            entry_kind = "symlink"
        elif stat.S_ISREG(file_info.st_mode):
            entry_kind = "file"
        else:
            raise ClosureError(f"unsupported tracked Docker context entry: {candidate}")

        mode = file_info.st_mode & 0o7777
        encoded_path = relative.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(entry_kind.encode("ascii") + b"\0")
        digest.update(mode.to_bytes(2, "big"))
        path = f"{context.rstrip('/')}/{relative}" if relative != "." else context
        entries.append(f"{path} kind={entry_kind} mode={mode:04o}")
    return digest.hexdigest(), entries


def _finish_manifest(
    *,
    package: str,
    head: str,
    worktree_head: str,
    components: list[dict[str, Any]],
) -> dict[str, Any]:
    digest_components = []
    for component in components:
        digest_component = {
            key: component[key]
            for key in ("name", "kind", "git_object_type", "paths", "digest")
        }
        if "entries" in component:
            digest_component["entries"] = component["entries"]
        digest_components.append(digest_component)
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
    component_specs = _component_specs(package)
    for spec in component_specs:
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
        if spec["name"] == "docker:context:vnext":
            context_digest, context_entries = _docker_context_non_git_digest(
                repo_root,
                spec["path"],
                [
                    item["path"]
                    for item in component_specs
                    if item["name"].startswith("dockerfile:")
                ],
            )
            components.append(
                {
                    "name": "non-git:docker-context:vnext",
                    "kind": "content",
                    "git_object_type": None,
                    "paths": [spec["path"]],
                    "digest": context_digest,
                    "entries": context_entries,
                    "reason": (
                        "Docker includes ignored and other non-Git files in the build context unless "
                        "excluded by .dockerignore; hash every included non-Git entry. The tracked "
                        "context remains represented by its Git tree component."
                    ),
                }
            )
            tracked_mode_digest, tracked_mode_entries = _docker_context_tracked_mode_digest(
                repo_root,
                spec["path"],
            )
            components.append(
                {
                    "name": "non-git:docker-context-tracked-modes:vnext",
                    "kind": "content",
                    "git_object_type": None,
                    "paths": [spec["path"]],
                    "digest": tracked_mode_digest,
                    "entries": tracked_mode_entries,
                    "reason": (
                        "Git stores only the executable bit for tracked files, while Docker receives "
                        "local permission modes for context files and directories. Hash every tracked "
                        "context path and its ancestors conservatively, including context-root mode."
                    ),
                }
            )

    if package == RUST_PACKAGE:
        _append_rust_non_git_components(repo_root, components, environment_values=environment)
        components.sort(key=lambda component: component["name"])
        return _finish_manifest(
            package=package,
            head=selected_revision,
            worktree_head=head,
            components=components,
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
            "digest": _directory_content_digest(
                hypothesis_storage_path,
                normalize_hypothesis_gzip=True,
            ),
            "reason": (
                "Hypothesis may read cached constants, Unicode data, and examples while generating "
                "test inputs; hash the effective package storage directory, including an explicit "
                "missing-directory state. Decode Unicode JSON gzip caches before hashing because "
                "their gzip header records a random temporary filename that is not payload data."
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
            "name": "environment:runtime-and-docker-build",
            "kind": "environment",
            "git_object_type": None,
            "paths": [],
            "digest": hashlib.sha256(_canonical_json(environment_values)).hexdigest(),
            "values": environment_values,
            "reason": (
                "Python, Unicode, Dolt, uv, rustc, Docker and Compose identities plus the effective "
                "Docker build configuration, selected local image IDs, and prebuilt image inventory."
            ),
        }
    )
    components.sort(key=lambda component: component["name"])
    return _finish_manifest(
        package=package,
        head=selected_revision,
        worktree_head=head,
        components=components,
    )


def _append_rust_non_git_components(
    repo_root: Path,
    components: list[dict[str, Any]],
    *,
    environment_values: Mapping[str, str] | None,
) -> None:
    """Add the rust package's cargo config and toolchain components.

    The rust package has no uv environment, Hypothesis storage, pytest cache, or
    legacy input; crate downloads are pinned by Cargo.lock checksums.
    """
    config_digest, config_entries = _cargo_config_digest(repo_root, os.environ)
    components.append(
        {
            "name": "non-git:cargo-config",
            "kind": "content",
            "git_object_type": None,
            "paths": [],
            "digest": config_digest,
            "entries": config_entries,
            "reason": (
                "cargo merges .cargo/config.toml files from vnext/rust and its ancestors plus "
                "CARGO_HOME; they can change rustflags, sources, and profiles. Hash each "
                "existing file by path and content."
            ),
        }
    )
    values = (
        dict(environment_values)
        if environment_values is not None
        else collect_rust_environment(repo_root)
    )
    if not values:
        raise ClosureError("environment version set must not be empty")
    components.append(
        {
            "name": "environment:rust-toolchain",
            "kind": "environment",
            "git_object_type": None,
            "paths": [],
            "digest": hashlib.sha256(_canonical_json(values)).hexdigest(),
            "values": values,
            "reason": (
                "rustc, cargo, rustfmt, and clippy-driver selected by rust-toolchain.toml, the "
                "interpreter PyO3's build script uses (PYO3_PYTHON when set), and fingerprints "
                "of CARGO_*/RUST*/PYO3_* and related settings, excluding CARGO_TARGET_DIR."
            ),
        }
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

        digest_components = []
        for component in sorted(result.values(), key=lambda item: item["name"]):
            digest_component = {
                key: component[key]
                for key in ("name", "kind", "git_object_type", "paths", "digest")
            }
            if "entries" in component:
                entries = component["entries"]
                if not isinstance(entries, list) or any(not isinstance(path, str) for path in entries):
                    raise ClosureError(f"manifest component entries are malformed: {component['name']}")
                digest_component["entries"] = entries
            digest_components.append(digest_component)
        digest_payload = {
            "schema": manifest["schema"],
            "schema_version": manifest["schema_version"],
            "package": manifest["package"],
            "components": digest_components,
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
        source_signature = None
        if source_component:
            source_signature = {
                key: source_component[key]
                for key in ("kind", "git_object_type", "paths", "digest")
            }
            if "entries" in source_component:
                source_signature["entries"] = source_component["entries"]
        current_signature = None
        if current_component:
            current_signature = {
                key: current_component[key]
                for key in ("kind", "git_object_type", "paths", "digest")
            }
            if "entries" in current_component:
                current_signature["entries"] = current_component["entries"]
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
            "source_entries": source_component.get("entries") if source_component else None,
            "current_entries": current_component.get("entries") if current_component else None,
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
