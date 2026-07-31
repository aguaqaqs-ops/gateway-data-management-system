"""Phase 1 protected-identity comparison for Phase 2 closure lint."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from gateway_conformance.sanitize import sanitize_message

PHASE1_EXIT_SOURCE = "7702d2127712193a8a88e66ba614dc073922ac15"
PHASE1_ADMIN_BASELINE = "9b4adbcb27b322c625f14f628ed80450826b7c0d"
IDENTITY_DIGEST = "95b3d7633caa7b536960552ba72e29b18bbe0fb6434d97b51b9cb40b9dde5f58"
IDENTITY_BASENAME = f"phase-exit-container-identity-{IDENTITY_DIGEST}.json"
IDENTITY_ARTIFACT_REL = (
    "docs/backend-vnext/refactoring/temporary/phase-1/artifacts/" + IDENTITY_BASENAME
)
SIGNOFF_REL = "docs/backend-vnext/refactoring/temporary/phase-1/phase-1-closure-signoff.md"
EXIT_EVIDENCE_REL = (
    "docs/backend-vnext/refactoring/temporary/phase-1/wp5-r5-phase1-exit-evidence.md"
)
FROZEN_GATE_SCRIPT_REL = "vnext/scripts/phase_exit_container_gate.sh"

_PHASE1_BASELINE_PREFIXES: tuple[str, ...] = (
    "vnext/conformance/",
    "vnext/backend/",
    "vnext/rust/",
    "vnext/shared_kernel/",
    "vnext/scripts/",
    "vnext/deploy/",
    "docs/backend-vnext/refactoring/temporary/phase-1/",
    "vnext/fixtures/scenarios/data/canonical-row-hashes/",
    "vnext/fixtures/vectors/",
)

_PHASE2_ALLOWED_NEW_PREFIXES: tuple[str, ...] = (
    "vnext/conformance/phase2/",
    "vnext/repository_contracts/",
    "vnext/repository_client/",
    "vnext/repository_service/",
)

_ARTIFACTS_DIR_REL = "docs/backend-vnext/refactoring/temporary/phase-1/artifacts"
_EXIT_SOURCE_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_IDENTITY_PREFIX = "phase-exit-container-identity-"


class Phase1ProtectionCode(StrEnum):
    NON_GIT_REPO = "phase1.protection.non_git_repo"
    BASELINE_MISSING = "phase1.protection.baseline_missing"
    GIT_COMMAND_FAILED = "phase1.protection.git_command_failed"
    PROTECTED_FILE_MISSING = "phase1.protection.protected_file_missing"
    PROTECTED_FILE_MODIFIED = "phase1.protection.protected_file_modified"
    PROTECTED_FILE_DELETED = "phase1.protection.protected_file_deleted"
    PROTECTED_SYMLINK_REPLACEMENT = "phase1.protection.symlink_replacement"
    PATH_ESCAPE = "phase1.protection.path_escape"
    INDEX_MODE_MISMATCH = "phase1.protection.index_mode_mismatch"
    PROTECTED_PREFIX_EXTRA = "phase1.protection.protected_prefix_extra"
    IDENTITY_ARTIFACT_MISSING = "phase1.protection.identity_artifact_missing"
    IDENTITY_DIGEST_MISMATCH = "phase1.protection.identity_digest_mismatch"
    IDENTITY_FILENAME_MISMATCH = "phase1.protection.identity_filename_mismatch"
    IDENTITY_SOURCE_REVISION = "phase1.protection.identity_source_revision"
    IDENTITY_GATE_STATUS = "phase1.protection.identity_gate_status"
    IDENTITY_ALTERNATE_AMBIGUITY = "phase1.protection.identity_alternate_ambiguity"
    SIGNOFF_SOURCE_REVISION = "phase1.protection.signoff_source_revision"
    SIGNOFF_ARTIFACT_BINDING = "phase1.protection.signoff_artifact_binding"
    UNREADABLE_MATERIAL = "phase1.protection.unreadable_material"


@dataclass(frozen=True, slots=True)
class ProtectionResult:
    ok: bool
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InventoryResult:
    ok: bool
    paths: tuple[str, ...]
    diagnostic: str | None


@dataclass(frozen=True, slots=True)
class TreeEntry:
    mode: str
    blob_sha: str


def _git_run(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        shell=False,
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _split_nul_records(raw: bytes) -> tuple[str, ...]:
    if not raw:
        return ()
    records: list[str] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            records.append(record.decode("utf-8"))
        except UnicodeDecodeError:
            records.append(record.decode("utf-8", "surrogateescape"))
    return tuple(records)


def _parse_ls_tree_line(line: str) -> tuple[str, str, str] | None:
    parts = line.split("\t", 1)
    if len(parts) != 2:
        return None
    meta, path = parts
    meta_parts = meta.split()
    if len(meta_parts) < 3:
        return None
    mode, obj_type, blob_sha = meta_parts[0], meta_parts[1], meta_parts[2]
    if obj_type != "blob":
        return None
    return mode, blob_sha, path


def _parse_ls_files_line(line: str) -> tuple[str, str, str] | None:
    parts = line.split()
    if len(parts) < 4:
        return None
    mode, blob_sha, _stage, path = parts[0], parts[1], parts[2], " ".join(parts[3:])
    return mode, blob_sha, path


def _protected_paths_at_baseline(repo_root: Path) -> InventoryResult:
    combined: set[str] = set()
    for prefix in _PHASE1_BASELINE_PREFIXES:
        proc = _git_run(
            repo_root,
            "ls-tree",
            "-r",
            "-z",
            PHASE1_ADMIN_BASELINE,
            "--",
            prefix,
        )
        if proc.returncode != 0:
            return InventoryResult(False, (), Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
        for line in _split_nul_records(proc.stdout):
            parsed = _parse_ls_tree_line(line)
            if parsed is not None:
                combined.add(parsed[2])
    return InventoryResult(True, tuple(sorted(combined)), None)


def _protected_paths_at_head(repo_root: Path) -> InventoryResult:
    head_proc = _git_run(repo_root, "rev-parse", "HEAD")
    if head_proc.returncode != 0:
        return InventoryResult(False, (), Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
    head = head_proc.stdout.decode("utf-8").strip()
    combined: set[str] = set()
    for prefix in _PHASE1_BASELINE_PREFIXES:
        proc = _git_run(
            repo_root,
            "ls-tree",
            "-r",
            "-z",
            head,
            "--",
            prefix,
        )
        if proc.returncode != 0:
            return InventoryResult(False, (), Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
        for line in _split_nul_records(proc.stdout):
            parsed = _parse_ls_tree_line(line)
            if parsed is not None:
                combined.add(parsed[2])
    return InventoryResult(True, tuple(sorted(combined)), None)


def _merge_protected_paths(
    baseline_paths: tuple[str, ...], head_paths: tuple[str, ...]
) -> tuple[str, ...]:
    combined = {
        path for path in (*baseline_paths, *head_paths) if not _is_phase2_allowed_new_path(path)
    }
    return tuple(sorted(combined))


def _tree_entries_at_ref(
    repo_root: Path, git_ref: str, rel_paths: tuple[str, ...]
) -> dict[str, TreeEntry] | None:
    entries: dict[str, TreeEntry] = {}
    for rel_path in rel_paths:
        proc = _git_run(
            repo_root,
            "ls-tree",
            git_ref,
            "--",
            rel_path,
        )
        if proc.returncode != 0:
            return None
        line = proc.stdout.decode("utf-8").strip()
        if not line:
            return None
        parsed = _parse_ls_tree_line(line)
        if parsed is None:
            return None
        mode, blob_sha, path = parsed
        entries[path] = TreeEntry(mode=mode, blob_sha=blob_sha)
    return entries


def _index_tree_entries(repo_root: Path, rel_paths: tuple[str, ...]) -> dict[str, TreeEntry] | None:
    entries: dict[str, TreeEntry] = {}
    for rel_path in rel_paths:
        proc = _git_run(repo_root, "ls-files", "-s", "--", rel_path)
        if proc.returncode != 0:
            return None
        line = proc.stdout.decode("utf-8").strip()
        if not line:
            return None
        parsed = _parse_ls_files_line(line)
        if parsed is None:
            return None
        mode, blob_sha, path = parsed
        entries[path] = TreeEntry(mode=mode, blob_sha=blob_sha)
    return entries


def _stat_mode_to_git(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "120000"
    if stat.S_ISDIR(mode):
        return "040000"
    perms = stat.S_IMODE(mode)
    if perms & 0o111:
        return "100755"
    return "100644"


def _path_without_symlink_ancestor(repo_root: Path, rel_path: str) -> Path | None:
    repo_resolved = repo_root.resolve()
    current = repo_resolved
    parts = [part for part in rel_path.split("/") if part not in ("", ".")]
    for index, part in enumerate(parts):
        if part == "..":
            return None
        current = current / part
        if not current.exists() and not current.is_symlink():
            if index == len(parts) - 1:
                break
            return None
        try:
            if stat.S_ISLNK(os.lstat(current).st_mode):
                return None
        except OSError:
            return None
    try:
        resolved = current.resolve()
        resolved.relative_to(repo_resolved)
    except OSError, ValueError:
        if current.exists() or current.is_symlink():
            return None
    return current


def _has_symlink_ancestor(repo_root: Path, rel_path: str) -> bool:
    parts = [part for part in rel_path.split("/") if part not in ("", ".")]
    if len(parts) <= 1:
        return False
    parent_rel = "/".join(parts[:-1])
    return _path_without_symlink_ancestor(repo_root, parent_rel) is None


def _git_hash_object(repo_root: Path, rel_path: str) -> str | None:
    if _has_symlink_ancestor(repo_root, rel_path):
        return None
    proc = _git_run(repo_root, "hash-object", rel_path)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "surrogateescape").strip()


def _worktree_entry(repo_root: Path, rel_path: str) -> TreeEntry | None:
    path = repo_root / rel_path
    if not path.exists() and not path.is_symlink():
        return None
    try:
        if stat.S_ISLNK(os.lstat(path).st_mode):
            return TreeEntry(mode="120000", blob_sha="")
    except OSError:
        return None
    if _has_symlink_ancestor(repo_root, rel_path):
        return None
    git_mode = _stat_mode_to_git(os.lstat(path).st_mode)
    blob_sha = _git_hash_object(repo_root, rel_path)
    if blob_sha is None:
        return None
    return TreeEntry(mode=git_mode, blob_sha=blob_sha)


def _is_phase2_allowed_new_path(rel_path: str) -> bool:
    if rel_path == "vnext/repository-workspace.toml":
        return True
    return any(rel_path.startswith(prefix) for prefix in _PHASE2_ALLOWED_NEW_PREFIXES)


def _indexed_paths_under_prefixes(repo_root: Path, prefixes: tuple[str, ...]) -> set[str] | None:
    paths: set[str] = set()
    for prefix in prefixes:
        proc = _git_run(repo_root, "ls-files", "-z", "--", prefix)
        if proc.returncode != 0:
            return None
        paths.update(_split_nul_records(proc.stdout))
    return paths


def _untracked_paths_under_prefixes(repo_root: Path, prefixes: tuple[str, ...]) -> set[str] | None:
    paths: set[str] = set()
    for prefix in prefixes:
        proc = _git_run(
            repo_root,
            "ls-files",
            "-z",
            "--others",
            "--exclude-standard",
            "--",
            prefix,
        )
        if proc.returncode != 0:
            return None
        paths.update(_split_nul_records(proc.stdout))
    return paths


def _scan_identity_artifacts(repo_root: Path) -> tuple[str, ...]:
    artifacts_dir = repo_root / _ARTIFACTS_DIR_REL
    if not artifacts_dir.is_dir():
        return ()
    names: list[str] = []
    for entry in artifacts_dir.iterdir():
        if not entry.name.startswith(_IDENTITY_PREFIX) or not entry.name.endswith(".json"):
            continue
        if entry.is_dir():
            continue
        names.append(entry.name)
    return tuple(sorted(names))


def _validate_identity_artifact(repo_root: Path, diagnostics: list[str]) -> None:
    artifact_path = repo_root / IDENTITY_ARTIFACT_REL
    if not artifact_path.is_file():
        diagnostics.append(Phase1ProtectionCode.IDENTITY_ARTIFACT_MISSING.value)
        return
    if artifact_path.is_symlink():
        diagnostics.append(Phase1ProtectionCode.PROTECTED_SYMLINK_REPLACEMENT.value)
        return

    try:
        raw = artifact_path.read_bytes()
    except OSError:
        diagnostics.append(Phase1ProtectionCode.UNREADABLE_MATERIAL.value)
        return
    try:
        doc = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        diagnostics.append(Phase1ProtectionCode.UNREADABLE_MATERIAL.value)
        return

    content_digest = _sha256_bytes(raw)
    if content_digest != IDENTITY_DIGEST:
        diagnostics.append(Phase1ProtectionCode.IDENTITY_DIGEST_MISMATCH.value)
    if artifact_path.name != IDENTITY_BASENAME:
        diagnostics.append(Phase1ProtectionCode.IDENTITY_FILENAME_MISMATCH.value)

    gate_status = doc.get("gate_status")
    if gate_status != "passed":
        diagnostics.append(Phase1ProtectionCode.IDENTITY_GATE_STATUS.value)

    for field in ("source_revision", "expected_head"):
        value = doc.get(field)
        if not isinstance(value, str) or not _EXIT_SOURCE_PATTERN.fullmatch(value):
            diagnostics.append(Phase1ProtectionCode.IDENTITY_SOURCE_REVISION.value)
            break
        if value != PHASE1_EXIT_SOURCE:
            diagnostics.append(Phase1ProtectionCode.IDENTITY_SOURCE_REVISION.value)
            break

    identity_files = _scan_identity_artifacts(repo_root)
    canonical = {IDENTITY_BASENAME, "phase-exit-container-identity-latest.json"}
    extras = [name for name in identity_files if name not in canonical]
    if extras:
        diagnostics.append(Phase1ProtectionCode.IDENTITY_ALTERNATE_AMBIGUITY.value)

    artifacts_dir = repo_root / _ARTIFACTS_DIR_REL
    if artifacts_dir.is_dir():
        for entry in artifacts_dir.iterdir():
            if not entry.name.startswith(_IDENTITY_PREFIX) or not entry.name.endswith(".json"):
                continue
            if entry.is_symlink() and entry.name != "phase-exit-container-identity-latest.json":
                diagnostics.append(Phase1ProtectionCode.IDENTITY_ALTERNATE_AMBIGUITY.value)

    latest = repo_root / _ARTIFACTS_DIR_REL / "phase-exit-container-identity-latest.json"
    if latest.exists():
        if latest.is_symlink():
            target = str(latest.readlink())
            if target != IDENTITY_BASENAME:
                diagnostics.append(Phase1ProtectionCode.IDENTITY_ALTERNATE_AMBIGUITY.value)
        else:
            diagnostics.append(Phase1ProtectionCode.IDENTITY_ALTERNATE_AMBIGUITY.value)


def _validate_signoff(repo_root: Path, diagnostics: list[str]) -> None:
    signoff_path = repo_root / SIGNOFF_REL
    if not signoff_path.is_file():
        diagnostics.append(Phase1ProtectionCode.PROTECTED_FILE_MISSING.value)
        return
    try:
        text = signoff_path.read_text(encoding="utf-8")
    except UnicodeDecodeError, OSError:
        diagnostics.append(Phase1ProtectionCode.UNREADABLE_MATERIAL.value)
        return

    if PHASE1_EXIT_SOURCE not in text:
        diagnostics.append(Phase1ProtectionCode.SIGNOFF_SOURCE_REVISION.value)
    if IDENTITY_DIGEST not in text:
        diagnostics.append(Phase1ProtectionCode.SIGNOFF_ARTIFACT_BINDING.value)
    if IDENTITY_BASENAME not in text:
        diagnostics.append(Phase1ProtectionCode.SIGNOFF_ARTIFACT_BINDING.value)


def _compare_protected_paths(
    repo_root: Path, protected_paths: tuple[str, ...], diagnostics: list[str]
) -> None:
    head_proc = _git_run(repo_root, "rev-parse", "HEAD")
    if head_proc.returncode != 0:
        diagnostics.append(Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
        return
    head = head_proc.stdout.decode("utf-8").strip()

    reference_entries = _tree_entries_at_ref(repo_root, head, protected_paths)
    if reference_entries is None:
        diagnostics.append(Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
        return

    index_entries = _index_tree_entries(repo_root, protected_paths)
    if index_entries is None:
        diagnostics.append(Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
        return

    for rel_path in protected_paths:
        reference = reference_entries.get(rel_path)
        if reference is None:
            diagnostics.append(f"{Phase1ProtectionCode.PROTECTED_FILE_MISSING.value}:{rel_path}")
            continue

        if _has_symlink_ancestor(repo_root, rel_path):
            diagnostics.append(f"{Phase1ProtectionCode.PATH_ESCAPE.value}:{rel_path}")
            continue

        index_entry = index_entries.get(rel_path)
        if index_entry is None:
            diagnostics.append(f"{Phase1ProtectionCode.PROTECTED_FILE_MISSING.value}:{rel_path}")
            continue

        worktree = _worktree_entry(repo_root, rel_path)
        if worktree is None:
            path = repo_root / rel_path
            if path.is_symlink():
                diagnostics.append(
                    f"{Phase1ProtectionCode.PROTECTED_SYMLINK_REPLACEMENT.value}:{rel_path}"
                )
            elif _has_symlink_ancestor(repo_root, rel_path):
                diagnostics.append(f"{Phase1ProtectionCode.PATH_ESCAPE.value}:{rel_path}")
            else:
                diagnostics.append(
                    f"{Phase1ProtectionCode.PROTECTED_FILE_MISSING.value}:{rel_path}"
                )
            continue

        if worktree.mode == "120000":
            diagnostics.append(
                f"{Phase1ProtectionCode.PROTECTED_SYMLINK_REPLACEMENT.value}:{rel_path}"
            )
            continue

        if index_entry.mode != reference.mode or index_entry.blob_sha != reference.blob_sha:
            diagnostics.append(f"{Phase1ProtectionCode.INDEX_MODE_MISMATCH.value}:{rel_path}")
            continue

        if worktree.mode != reference.mode or worktree.blob_sha != reference.blob_sha:
            diagnostics.append(f"{Phase1ProtectionCode.PROTECTED_FILE_MODIFIED.value}:{rel_path}")


def _check_prefix_extras(
    repo_root: Path,
    baseline_inventory: frozenset[str],
    diagnostics: list[str],
) -> None:
    indexed = _indexed_paths_under_prefixes(repo_root, _PHASE1_BASELINE_PREFIXES)
    if indexed is None:
        diagnostics.append(Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
        return
    untracked = _untracked_paths_under_prefixes(repo_root, _PHASE1_BASELINE_PREFIXES)
    if untracked is None:
        diagnostics.append(Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
        return
    observed = indexed | untracked
    for rel_path in sorted(observed):
        if rel_path in baseline_inventory:
            continue
        if _is_phase2_allowed_new_path(rel_path):
            continue
        diagnostics.append(f"{Phase1ProtectionCode.PROTECTED_PREFIX_EXTRA.value}:{rel_path}")


def verify_phase1_protection(repo_root: Path) -> ProtectionResult:
    diagnostics: list[str] = []
    try:
        return _verify_phase1_protection_impl(repo_root, diagnostics)
    except UnicodeDecodeError, OSError:
        diagnostics.append(Phase1ProtectionCode.UNREADABLE_MATERIAL.value)
        return ProtectionResult(False, tuple(sorted(set(diagnostics))))


def _verify_phase1_protection_impl(repo_root: Path, diagnostics: list[str]) -> ProtectionResult:
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        return ProtectionResult(False, (Phase1ProtectionCode.NON_GIT_REPO.value,))

    head_proc = _git_run(repo_root, "rev-parse", "HEAD")
    if head_proc.returncode != 0:
        diagnostics.append(Phase1ProtectionCode.GIT_COMMAND_FAILED.value)

    show_proc = _git_run(repo_root, "cat-file", "-e", f"{PHASE1_ADMIN_BASELINE}^{{commit}}")
    if show_proc.returncode != 0:
        diagnostics.append(Phase1ProtectionCode.BASELINE_MISSING.value)
        return ProtectionResult(False, tuple(sorted(set(diagnostics))))

    inventory = _protected_paths_at_baseline(repo_root)
    if not inventory.ok:
        diagnostics.append(inventory.diagnostic or Phase1ProtectionCode.GIT_COMMAND_FAILED.value)
        return ProtectionResult(False, tuple(sorted(set(diagnostics))))

    head_inventory = _protected_paths_at_head(repo_root)
    if not head_inventory.ok:
        diagnostics.append(
            head_inventory.diagnostic or Phase1ProtectionCode.GIT_COMMAND_FAILED.value
        )
        return ProtectionResult(False, tuple(sorted(set(diagnostics))))

    protected_paths = _merge_protected_paths(inventory.paths, head_inventory.paths)

    _compare_protected_paths(repo_root, protected_paths, diagnostics)
    _check_prefix_extras(repo_root, frozenset(protected_paths), diagnostics)
    _validate_identity_artifact(repo_root, diagnostics)
    _validate_signoff(repo_root, diagnostics)

    sanitized = tuple(sorted({sanitize_message(item) for item in diagnostics}))
    return ProtectionResult(ok=not sanitized, diagnostics=sanitized)
