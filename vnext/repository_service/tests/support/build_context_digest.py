"""Canonical repository-image provenance helper.

Formal identity is the three-field result from ``identity`` / ``compute_image_identity``:
literal ``candidate_sha``, manifest-derived ``build_input_revision``, and framed
``source_tree_sha256``. Path policy lives only in the sibling versioned manifest.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MANIFEST_SCHEMA = "gateway.p2r1.effective-input-manifest"
MANIFEST_SCHEMA_VERSION = 1
DIGEST_ENCODING_VERSION = 1
IDENTITY_SCHEMA = "gateway.p2r1.build-identity"
IDENTITY_SCHEMA_VERSION = 1
CANONICAL_MANIFEST_PATH = Path(__file__).resolve().with_name("repository_image_inputs.json")
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_GLOB_CHARS = frozenset("*?[]")
_REQUIRED_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "schema_version",
        "digest_encoding_version",
        "source_roots",
        "build_definition_paths",
        "excluded_dir_names",
        "excluded_file_suffixes",
    }
)
_USAGE = (
    "usage: build_context_digest.py "
    "<identity|candidate-sha|source-tree-sha256|build-input-revision|head-sha>"
)
_COMMANDS = frozenset(
    {
        "identity",
        "candidate-sha",
        "source-tree-sha256",
        "build-input-revision",
        "head-sha",
    }
)


class ProvenanceError(RuntimeError):
    """Fail-closed identity or effective-input manifest error."""


@dataclass(frozen=True)
class EffectiveInputManifest:
    schema: str
    schema_version: int
    digest_encoding_version: int
    source_roots: tuple[str, ...]
    build_definition_paths: tuple[str, ...]
    excluded_dir_names: frozenset[str]
    excluded_file_suffixes: tuple[str, ...]
    manifest_path: str

    def build_input_paths(self) -> tuple[str, ...]:
        return tuple(sorted({*self.source_roots, *self.build_definition_paths}))


@dataclass(frozen=True)
class ImageIdentity:
    candidate_sha: str
    build_input_revision: str
    source_tree_sha256: str

    def to_json_dict(self) -> dict[str, str | int]:
        return {
            "schema": IDENTITY_SCHEMA,
            "schema_version": IDENTITY_SCHEMA_VERSION,
            "candidate_sha": self.candidate_sha,
            "build_input_revision": self.build_input_revision,
            "source_tree_sha256": self.source_tree_sha256,
        }


def vnext_root_from_here() -> Path:
    return Path(__file__).resolve().parents[3]


def repo_root_from_vnext(vnext_root: Path) -> Path:
    return vnext_root.parent


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProvenanceError(f"{field} must be an integer")
    return value


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ProvenanceError(f"{field} must be a string")
    return value


def _require_str_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProvenanceError(f"{field} must be a list of strings")
    return list(value)


def _validate_relative_path(relative: str, *, field: str) -> None:
    if not relative or relative.startswith("/") or "\\" in relative:
        raise ProvenanceError(f"{field} must be a repository-relative POSIX path")
    if any(char in relative for char in _GLOB_CHARS):
        raise ProvenanceError(f"{field} must not contain glob metacharacters")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ProvenanceError(f"{field} must not contain empty, '.', or '..' components")


def _unique_sorted_paths(paths: list[str], *, field: str) -> tuple[str, ...]:
    seen: set[str] = set()
    for path in paths:
        _validate_relative_path(path, field=field)
        if path in seen:
            raise ProvenanceError(f"{field} must not contain duplicate paths")
        seen.add(path)
    return tuple(sorted(seen))


def _is_covered(relative: str, owners: tuple[str, ...]) -> bool:
    return any(relative == owner or relative.startswith(f"{owner}/") for owner in owners)


def _contained_path(repo_root: Path, relative: str) -> Path:
    repo_resolved = repo_root.resolve()
    candidate = (repo_root / relative).resolve()
    try:
        candidate.relative_to(repo_resolved)
    except ValueError as exc:
        raise ProvenanceError("path escapes repository root") from exc
    return candidate


def _literal_pathspec(relative: str) -> str:
    return f":(literal){relative}"


def load_manifest(path: Path, *, repo_root: Path) -> EffectiveInputManifest:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProvenanceError("unable to read effective-input manifest") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProvenanceError("manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProvenanceError("manifest must be a JSON object")
    keys = set(payload)
    missing = _REQUIRED_MANIFEST_KEYS - keys
    if missing:
        raise ProvenanceError("manifest is missing required fields")
    extra = keys - _REQUIRED_MANIFEST_KEYS
    if extra:
        raise ProvenanceError("manifest contains unsupported fields")

    schema = _require_str(payload["schema"], "schema")
    if schema != MANIFEST_SCHEMA:
        raise ProvenanceError("unsupported manifest schema")
    schema_version = _require_int(payload["schema_version"], "schema_version")
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise ProvenanceError("unsupported manifest schema version")
    digest_encoding_version = _require_int(
        payload["digest_encoding_version"], "digest_encoding_version"
    )
    if digest_encoding_version != DIGEST_ENCODING_VERSION:
        raise ProvenanceError("unsupported digest encoding version")

    source_roots = _unique_sorted_paths(
        _require_str_list(payload["source_roots"], "source_roots"),
        field="source_roots",
    )
    if not source_roots:
        raise ProvenanceError("source_roots must not be empty")
    build_definition_paths = _unique_sorted_paths(
        _require_str_list(payload["build_definition_paths"], "build_definition_paths"),
        field="build_definition_paths",
    )
    if not build_definition_paths:
        raise ProvenanceError("build_definition_paths must not be empty")
    excluded_dir_names = frozenset(
        _require_str_list(payload["excluded_dir_names"], "excluded_dir_names")
    )
    excluded_file_suffixes = tuple(
        _require_str_list(payload["excluded_file_suffixes"], "excluded_file_suffixes")
    )
    if any(not suffix.startswith(".") for suffix in excluded_file_suffixes):
        raise ProvenanceError("excluded_file_suffixes must start with '.'")

    for root in source_roots:
        resolved = _contained_path(repo_root, root)
        if not resolved.is_dir() or resolved.is_symlink():
            raise ProvenanceError("source root must be a directory")
    for build_path in build_definition_paths:
        if _is_covered(build_path, source_roots):
            raise ProvenanceError("build-definition path duplicates a source-root owner")
        resolved = _contained_path(repo_root, build_path)
        if not resolved.is_file() or resolved.is_symlink():
            raise ProvenanceError("build-definition path must be a regular file")

    try:
        manifest_path = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ProvenanceError("manifest path escapes repository root") from exc
    _validate_relative_path(manifest_path, field="manifest path")
    if not _is_covered(manifest_path, (*source_roots, *build_definition_paths)):
        raise ProvenanceError("manifest is not covered by its own path set")

    return EffectiveInputManifest(
        schema=schema,
        schema_version=schema_version,
        digest_encoding_version=digest_encoding_version,
        source_roots=source_roots,
        build_definition_paths=build_definition_paths,
        excluded_dir_names=excluded_dir_names,
        excluded_file_suffixes=excluded_file_suffixes,
        manifest_path=manifest_path,
    )


def _resolve_repo_root(
    *,
    vnext_root: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    if repo_root is not None:
        return repo_root
    root = vnext_root if vnext_root is not None else vnext_root_from_here()
    return repo_root_from_vnext(root)


def _resolve_manifest(
    repo_root: Path,
    manifest: EffectiveInputManifest | None = None,
) -> EffectiveInputManifest:
    if manifest is not None:
        return manifest
    return load_manifest(CANONICAL_MANIFEST_PATH, repo_root=repo_root)


def _git_text(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _git_bytes(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=False,
    )


def _git_stdout(repo_root: Path, args: list[str]) -> str:
    completed = _git_text(repo_root, args)
    if completed.returncode != 0:
        raise ProvenanceError(f"git {args[0]} failed")
    return completed.stdout.strip()


def _require_full_sha(value: str, *, field: str) -> str:
    if not _FULL_SHA.fullmatch(value):
        raise ProvenanceError(f"{field} must be a 40-character lowercase hex digest")
    return value


def _require_resolvable_commit(repo_root: Path, sha: str, *, field: str) -> str:
    verified = _git_stdout(repo_root, ["rev-parse", "--verify", f"{sha}^{{commit}}"])
    return _require_full_sha(verified, field=field)


def is_worktree_clean(*, repo_root: Path) -> bool:
    completed = _git_text(repo_root, ["status", "--porcelain=v1"])
    if completed.returncode != 0:
        raise ProvenanceError("unable to determine worktree status")
    return completed.stdout == ""


def require_clean_worktree(*, repo_root: Path) -> None:
    if not is_worktree_clean(repo_root=repo_root):
        raise ProvenanceError("worktree is dirty")


def compute_candidate_sha(
    *,
    vnext_root: Path | None = None,
    repo_root: Path | None = None,
) -> str:
    root = _resolve_repo_root(vnext_root=vnext_root, repo_root=repo_root)
    sha = _git_stdout(root, ["rev-parse", "--verify", "HEAD"])
    return _require_full_sha(sha, field="candidate_sha")


def compute_head_sha(*, vnext_root: Path | None = None, repo_root: Path | None = None) -> str:
    return compute_candidate_sha(vnext_root=vnext_root, repo_root=repo_root)


def compute_build_input_revision(
    *,
    vnext_root: Path | None = None,
    repo_root: Path | None = None,
    manifest: EffectiveInputManifest | None = None,
) -> str:
    """Return the latest commit that touched versioned formal build inputs."""

    root = _resolve_repo_root(vnext_root=vnext_root, repo_root=repo_root)
    loaded = _resolve_manifest(root, manifest)
    pathspecs = [_literal_pathspec(path) for path in loaded.build_input_paths()]
    revision = _git_stdout(root, ["log", "-1", "--format=%H", "--", *pathspecs])
    if not revision:
        raise ProvenanceError("unable to resolve build-input revision")
    sha = _require_full_sha(revision, field="build_input_revision")
    return _require_resolvable_commit(root, sha, field="build_input_revision")


def _should_hash_relative(relative: str, manifest: EffectiveInputManifest) -> bool:
    parts = relative.split("/")
    if any(part in manifest.excluded_dir_names for part in parts):
        return False
    return not any(relative.endswith(suffix) for suffix in manifest.excluded_file_suffixes)


def _tracked_source_relpaths(repo_root: Path, manifest: EffectiveInputManifest) -> tuple[str, ...]:
    pathspecs = [_literal_pathspec(root) for root in manifest.source_roots]
    completed = _git_bytes(repo_root, ["ls-files", "-z", "--", *pathspecs])
    if completed.returncode != 0:
        raise ProvenanceError("git ls-files failed")
    relpaths: list[str] = []
    seen: set[str] = set()
    for raw in completed.stdout.split(b"\0"):
        if raw == b"":
            continue
        try:
            relative = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProvenanceError("tracked source path is not valid UTF-8") from exc
        if relative in seen:
            raise ProvenanceError("tracked source path is duplicated")
        seen.add(relative)
        _validate_relative_path(relative, field="tracked source path")
        if not _is_covered(relative, manifest.source_roots):
            raise ProvenanceError("tracked source path escapes source roots")
        _contained_path(repo_root, relative)
        if not _should_hash_relative(relative, manifest):
            continue
        relpaths.append(relative)
    if not relpaths:
        raise ProvenanceError("no tracked source files matched the effective-input manifest")
    return tuple(sorted(relpaths))


def _read_regular_file(repo_root: Path, relative: str) -> bytes:
    path = repo_root / relative
    try:
        status = path.lstat()
    except FileNotFoundError as exc:
        raise ProvenanceError("tracked source path is missing") from exc
    if stat.S_ISLNK(status.st_mode):
        raise ProvenanceError("tracked source path is a symlink")
    if not stat.S_ISREG(status.st_mode):
        raise ProvenanceError("tracked source path is not a regular file")
    return path.read_bytes()


def _put_framed(digest: hashlib._Hash, label: bytes, value: bytes) -> None:
    digest.update(len(label).to_bytes(4, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def compute_source_tree_sha256(
    *,
    vnext_root: Path | None = None,
    repo_root: Path | None = None,
    manifest: EffectiveInputManifest | None = None,
) -> str:
    root = _resolve_repo_root(vnext_root=vnext_root, repo_root=repo_root)
    loaded = _resolve_manifest(root, manifest)
    digest = hashlib.sha256()
    _put_framed(digest, b"schema", loaded.schema.encode("utf-8"))
    _put_framed(digest, b"schema_version", str(loaded.schema_version).encode("ascii"))
    _put_framed(
        digest,
        b"digest_encoding_version",
        str(loaded.digest_encoding_version).encode("ascii"),
    )
    for relative in _tracked_source_relpaths(root, loaded):
        _put_framed(digest, b"path", relative.encode("utf-8"))
        _put_framed(digest, b"bytes", _read_regular_file(root, relative))
    rendered = f"sha256:{digest.hexdigest()}"
    if not _DIGEST.fullmatch(rendered):
        raise ProvenanceError("source-tree digest is malformed")
    return rendered


def compute_image_identity(
    *,
    vnext_root: Path | None = None,
    repo_root: Path | None = None,
    manifest: EffectiveInputManifest | None = None,
) -> ImageIdentity:
    root = _resolve_repo_root(vnext_root=vnext_root, repo_root=repo_root)
    loaded = _resolve_manifest(root, manifest)
    require_clean_worktree(repo_root=root)
    return ImageIdentity(
        candidate_sha=compute_candidate_sha(repo_root=root),
        build_input_revision=compute_build_input_revision(repo_root=root, manifest=loaded),
        source_tree_sha256=compute_source_tree_sha256(repo_root=root, manifest=loaded),
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or args[0] not in _COMMANDS:
        print(_USAGE, file=sys.stderr)
        return 2
    command = args[0]
    try:
        if command == "identity":
            payload = compute_image_identity()
            print(json.dumps(payload.to_json_dict(), ensure_ascii=True))
        elif command in {"candidate-sha", "head-sha"}:
            print(compute_candidate_sha())
        elif command == "source-tree-sha256":
            print(compute_source_tree_sha256())
        elif command == "build-input-revision":
            print(compute_build_input_revision())
    except ProvenanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
