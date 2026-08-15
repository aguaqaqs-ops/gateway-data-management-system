"""Unit tests for repository-image provenance helper and identity model."""

from __future__ import annotations

import copy
import json
import os
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path
import pytest

from support.build_context_digest import (
    CANONICAL_MANIFEST_PATH,
    IDENTITY_SCHEMA,
    IDENTITY_SCHEMA_VERSION,
    EffectiveInputManifest,
    ImageIdentity,
    ProvenanceError,
    compute_build_input_revision,
    compute_candidate_sha,
    compute_image_identity,
    compute_source_tree_sha256,
    load_manifest,
    main,
    vnext_root_from_here,
)

MANIFEST_RELPATH = "vnext/repository_service/tests/support/repository_image_inputs.json"
VALID_MANIFEST: dict[str, object] = {
    "schema": "gateway.p2r1.effective-input-manifest",
    "schema_version": 1,
    "digest_encoding_version": 1,
    "source_roots": [
        "vnext/repository_service",
        "vnext/repository_contracts",
    ],
    "build_definition_paths": [
        "vnext/.dockerignore",
        "vnext/deploy/compose.yaml",
        "vnext/scripts/build-repository-service-image.sh",
    ],
    "excluded_dir_names": [
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "htmlcov",
    ],
    "excluded_file_suffixes": [".pyc", ".pyo"],
}
DEFAULT_FILES: dict[str, str] = {
    "vnext/repository_service/src/example.py": "service\n",
    "vnext/repository_service/README.md": "readme\n",
    "vnext/repository_service/tests/test_example.py": "def test_ok():\n    assert True\n",
    "vnext/repository_service/uv.lock": "lock\n",
    "vnext/repository_service/Dockerfile": "FROM python\n",
    "vnext/repository_contracts/src/example.py": "contracts\n",
    "vnext/.dockerignore": "**/.venv\n",
    "vnext/scripts/build-repository-service-image.sh": "#!/bin/sh\n",
    "vnext/deploy/compose.yaml": "services: {}\n",
    ".gitignore": ".pytest_cache/\n.mypy_cache/\n.ruff_cache/\n.venv/\n__pycache__/\n*.pyc\n*.pyo\n",
    "docs/outside.md": "docs-only\n",
}
SOURCE_BYTE_PATHS = (
    "vnext/repository_service/src/example.py",
    "vnext/repository_service/README.md",
    "vnext/repository_service/tests/test_example.py",
    "vnext/repository_service/uv.lock",
    "vnext/repository_service/Dockerfile",
    "vnext/repository_contracts/src/example.py",
)
BUILD_INPUT_ONLY_PATHS = (
    "vnext/.dockerignore",
    "vnext/scripts/build-repository-service-image.sh",
    "vnext/deploy/compose.yaml",
)
_SHA40 = "0123456789abcdef0123456789abcdef01234567"


def _with_manifest(**changes: object) -> dict[str, object]:
    payload = copy.deepcopy(VALID_MANIFEST)
    payload.update(changes)
    return payload


def _without_key(key: str) -> dict[str, object]:
    payload = copy.deepcopy(VALID_MANIFEST)
    del payload[key]
    return payload


MALFORMED_MANIFESTS: tuple[tuple[str, object, str], ...] = (
    ("not-json", "{", "not valid JSON"),
    ("non-object", ["vnext/repository_service"], "JSON object"),
    ("missing-schema", _without_key("schema"), "missing required fields"),
    ("extra-field", _with_manifest(unknown="x"), "unsupported fields"),
    ("unsupported-schema", _with_manifest(schema="other"), "unsupported manifest schema"),
    (
        "unsupported-schema-version",
        _with_manifest(schema_version=2),
        "unsupported manifest schema version",
    ),
    (
        "bool-schema-version",
        _with_manifest(schema_version=True),
        "schema_version must be an integer",
    ),
    (
        "unsupported-encoding",
        _with_manifest(digest_encoding_version=2),
        "unsupported digest encoding version",
    ),
    ("empty-source-roots", _with_manifest(source_roots=[]), "source_roots must not be empty"),
    (
        "duplicate-source-root",
        _with_manifest(source_roots=["vnext/repository_service", "vnext/repository_service"]),
        "duplicate paths",
    ),
    (
        "absolute-source-root",
        _with_manifest(source_roots=["/tmp/repository_service", "vnext/repository_contracts"]),
        "repository-relative POSIX path",
    ),
    (
        "escape-source-root",
        _with_manifest(source_roots=["vnext/../secret", "vnext/repository_contracts"]),
        "empty, '.', or '..'",
    ),
    (
        "glob-source-root",
        _with_manifest(source_roots=["vnext/repository_service/**", "vnext/repository_contracts"]),
        "glob metacharacters",
    ),
    (
        "duplicate-build-definition",
        _with_manifest(
            build_definition_paths=[
                "vnext/.dockerignore",
                "vnext/.dockerignore",
                "vnext/deploy/compose.yaml",
                "vnext/scripts/build-repository-service-image.sh",
            ]
        ),
        "duplicate paths",
    ),
    (
        "absolute-build-definition",
        _with_manifest(
            build_definition_paths=[
                "/etc/compose.yaml",
                "vnext/.dockerignore",
                "vnext/scripts/build-repository-service-image.sh",
            ]
        ),
        "repository-relative POSIX path",
    ),
    (
        "source-owned-build-definition",
        _with_manifest(
            build_definition_paths=[
                "vnext/.dockerignore",
                "vnext/deploy/compose.yaml",
                "vnext/repository_service/Dockerfile",
            ]
        ),
        "duplicates a source-root owner",
    ),
)
GIT_REVISION_FAULTS: tuple[tuple[str, str, str], ...] = (
    ("empty", "", "unable to resolve build-input revision"),
    ("short", "abc123def456", "40-character lowercase hex digest"),
    ("uppercase", "A" * 40, "40-character lowercase hex digest"),
)
CANDIDATE_SHA_FAULTS: tuple[tuple[str, str, str], ...] = (
    ("empty", "", "40-character lowercase hex digest"),
    ("short", "abc123d", "40-character lowercase hex digest"),
    ("uppercase", "A" * 40, "40-character lowercase hex digest"),
)
TRACKED_PATH_FAULTS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("escape", ("../secret.py",), "empty, '.', or '..'"),
    ("absolute", ("/tmp/example.py",), "repository-relative POSIX path"),
    ("glob", ("vnext/repository_service/*.py",), "glob metacharacters"),
    (
        "duplicate",
        (
            "vnext/repository_service/src/example.py",
            "vnext/repository_service/src/example.py",
        ),
        "duplicated",
    ),
    (
        "outside-root",
        ("vnext/scripts/build-repository-service-image.sh",),
        "escapes source roots",
    ),
)


def _git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "GIT_AUTHOR_NAME": "s5-a-test",
            "GIT_AUTHOR_EMAIL": "s5-a-test@example.test",
            "GIT_COMMITTER_NAME": "s5-a-test",
            "GIT_COMMITTER_EMAIL": "s5-a-test@example.test",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    return env


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    if check and completed.returncode != 0:
        raise AssertionError(f"git {args} failed: {completed.stderr}")
    return completed


def _write_files(repo: Path, files: dict[str, str]) -> Path:
    payload = dict(files)
    payload[MANIFEST_RELPATH] = json.dumps(VALID_MANIFEST, indent=2) + "\n"
    for relative, content in payload.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return repo / MANIFEST_RELPATH


def _seed_repo(tmp_path: Path, *, name: str = "repo") -> tuple[Path, EffectiveInputManifest]:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    manifest_path = _write_files(repo, DEFAULT_FILES)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo, load_manifest(manifest_path, repo_root=repo)


def _commit_path(repo: Path, relative: str, content: str, message: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", "--", relative)
    _git(repo, "commit", "-m", message)


def _make_tracked_dirty(repo: Path) -> None:
    (repo / "vnext/repository_service/src/example.py").write_text("dirty-tracked\n")


def _make_untracked_dirty(repo: Path) -> None:
    (repo / "vnext/repository_service/oops.py").write_text("untracked\n")


def _make_unmerged_dirty(repo: Path) -> None:
    _git(repo, "checkout", "-b", "other")
    _commit_path(repo, "vnext/repository_service/src/example.py", "other\n", "other")
    _git(repo, "checkout", "main")
    _commit_path(repo, "vnext/repository_service/src/example.py", "main-side\n", "main-side")
    completed = _git(repo, "merge", "other", check=False)
    assert completed.returncode != 0


DIRTY_CASES: tuple[tuple[str, Callable[[Path], None]], ...] = (
    ("tracked", _make_tracked_dirty),
    ("untracked", _make_untracked_dirty),
    ("unmerged", _make_unmerged_dirty),
)


def _patch_git_text(
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
    *,
    log_stdout: str | None = None,
    head_stdout: str | None = None,
    verify_commit_ok: bool = True,
) -> None:
    import support.build_context_digest as helper

    real = helper._git_text

    def fake(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if repo_root != repo:
            return real(repo_root, args)
        if args[:3] == ["log", "-1", "--format=%H"] and log_stdout is not None:
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout=log_stdout,
                stderr="",
            )
        if args[:3] == ["rev-parse", "--verify", "HEAD"] and head_stdout is not None:
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=0,
                stdout=head_stdout,
                stderr="",
            )
        if (
            len(args) >= 3
            and args[0] == "rev-parse"
            and args[1] == "--verify"
            and args[2].endswith("^{commit}")
            and not verify_commit_ok
        ):
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=1,
                stdout="",
                stderr="",
            )
        return real(repo_root, args)

    monkeypatch.setattr(helper, "_git_text", fake)


def _patch_ls_files(
    monkeypatch: pytest.MonkeyPatch,
    repo: Path,
    relpaths: tuple[str, ...],
) -> None:
    import support.build_context_digest as helper

    real = helper._git_bytes

    def fake(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
        if repo_root != repo or args[:2] != ["ls-files", "-z"]:
            return real(repo_root, args)
        stdout = b"\0".join(item.encode("utf-8") for item in relpaths) + b"\0"
        return subprocess.CompletedProcess(
            args=["git", *args],
            returncode=0,
            stdout=stdout,
            stderr=b"",
        )

    monkeypatch.setattr(helper, "_git_bytes", fake)


@pytest.mark.unit
def test_canonical_manifest_loads_against_this_checkout() -> None:
    repo_root = vnext_root_from_here().parent
    manifest = load_manifest(CANONICAL_MANIFEST_PATH, repo_root=repo_root)
    assert manifest.source_roots == (
        "vnext/repository_contracts",
        "vnext/repository_service",
    )
    assert manifest.build_definition_paths == (
        "vnext/.dockerignore",
        "vnext/deploy/compose.yaml",
        "vnext/scripts/build-repository-service-image.sh",
    )
    assert manifest.manifest_path == MANIFEST_RELPATH


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "payload", "match"),
    MALFORMED_MANIFESTS,
    ids=[case[0] for case in MALFORMED_MANIFESTS],
)
def test_load_manifest_rejects_malformed_entries(
    tmp_path: Path,
    name: str,
    payload: object,
    match: str,
) -> None:
    repo, _manifest = _seed_repo(tmp_path)
    manifest_path = repo / MANIFEST_RELPATH
    if isinstance(payload, str):
        manifest_path.write_text(payload, encoding="utf-8")
    else:
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProvenanceError, match=match):
        load_manifest(manifest_path, repo_root=repo)
    assert name


@pytest.mark.unit
def test_load_manifest_rejects_uncovered_manifest_path(tmp_path: Path) -> None:
    repo, _manifest = _seed_repo(tmp_path)
    outside = repo / "docs/manifest.json"
    outside.write_text(json.dumps(VALID_MANIFEST), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="not covered by its own path set"):
        load_manifest(outside, repo_root=repo)


@pytest.mark.unit
def test_source_digest_is_deterministic_and_host_path_independent(tmp_path: Path) -> None:
    first_repo, first_manifest = _seed_repo(tmp_path, name="one")
    second_repo = tmp_path / "two"
    second_repo.mkdir()
    _git(second_repo, "init", "--initial-branch=main")
    reversed_files = dict(reversed(list(DEFAULT_FILES.items())))
    manifest_path = _write_files(second_repo, reversed_files)
    _git(second_repo, "add", "-A")
    _git(second_repo, "commit", "-m", "initial")
    second_manifest = load_manifest(manifest_path, repo_root=second_repo)

    first = compute_source_tree_sha256(repo_root=first_repo, manifest=first_manifest)
    second = compute_source_tree_sha256(
        vnext_root=second_repo / "vnext",
        manifest=second_manifest,
    )
    assert first == second
    assert first == compute_source_tree_sha256(repo_root=first_repo, manifest=first_manifest)
    assert first.startswith("sha256:")
    assert str(first_repo) not in first
    assert str(second_repo) not in second


@pytest.mark.unit
@pytest.mark.parametrize("relative", SOURCE_BYTE_PATHS)
def test_source_byte_changes_change_source_digest(tmp_path: Path, relative: str) -> None:
    repo, manifest = _seed_repo(tmp_path)
    before = compute_image_identity(repo_root=repo, manifest=manifest)
    _commit_path(repo, relative, "changed-bytes\n", "source-change")
    after = compute_image_identity(repo_root=repo, manifest=manifest)
    assert after.source_tree_sha256 != before.source_tree_sha256
    assert after.build_input_revision != before.build_input_revision
    assert after.candidate_sha != before.candidate_sha


@pytest.mark.unit
@pytest.mark.parametrize("relative", BUILD_INPUT_ONLY_PATHS)
def test_build_definition_changes_build_input_not_source_bytes(
    tmp_path: Path,
    relative: str,
) -> None:
    repo, manifest = _seed_repo(tmp_path)
    before = compute_image_identity(repo_root=repo, manifest=manifest)
    _commit_path(repo, relative, "changed-build-definition\n", "build-input-change")
    after = compute_image_identity(repo_root=repo, manifest=manifest)
    assert after.source_tree_sha256 == before.source_tree_sha256
    assert after.build_input_revision != before.build_input_revision
    assert after.candidate_sha != before.candidate_sha


@pytest.mark.unit
def test_docs_only_change_updates_only_candidate_sha(tmp_path: Path) -> None:
    repo, manifest = _seed_repo(tmp_path)
    before = compute_image_identity(repo_root=repo, manifest=manifest)
    _commit_path(repo, "docs/outside.md", "docs changed\n", "docs-only")
    after = compute_image_identity(repo_root=repo, manifest=manifest)
    assert after.candidate_sha != before.candidate_sha
    assert after.build_input_revision == before.build_input_revision
    assert after.source_tree_sha256 == before.source_tree_sha256


@pytest.mark.unit
def test_identity_keeps_independent_fields_when_shas_equal(tmp_path: Path) -> None:
    repo, manifest = _seed_repo(tmp_path)
    identity = compute_image_identity(repo_root=repo, manifest=manifest)
    assert identity.candidate_sha == identity.build_input_revision
    payload = identity.to_json_dict()
    assert payload["candidate_sha"] == identity.candidate_sha
    assert payload["build_input_revision"] == identity.build_input_revision
    assert payload["candidate_sha"] == payload["build_input_revision"]
    assert payload["schema"] == IDENTITY_SCHEMA
    assert payload["schema_version"] == IDENTITY_SCHEMA_VERSION


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "mutate"),
    DIRTY_CASES,
    ids=[case[0] for case in DIRTY_CASES],
)
def test_identity_rejects_dirty_worktree(
    tmp_path: Path,
    name: str,
    mutate: Callable[[Path], None],
) -> None:
    repo, manifest = _seed_repo(tmp_path)
    mutate(repo)
    with pytest.raises(ProvenanceError, match="worktree is dirty"):
        compute_image_identity(repo_root=repo, manifest=manifest)
    assert name


@pytest.mark.unit
def test_ignored_cache_does_not_change_digest_or_fail_clean(tmp_path: Path) -> None:
    repo, manifest = _seed_repo(tmp_path)
    before = compute_image_identity(repo_root=repo, manifest=manifest)
    cache = repo / "vnext/repository_service/.pytest_cache/v/cache/nodeids"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("ignored\n", encoding="utf-8")
    after = compute_image_identity(repo_root=repo, manifest=manifest)
    assert after == before


@pytest.mark.unit
def test_untracked_file_is_rejected_by_clean_preflight_not_digest(tmp_path: Path) -> None:
    repo, manifest = _seed_repo(tmp_path)
    before = compute_source_tree_sha256(repo_root=repo, manifest=manifest)
    _make_untracked_dirty(repo)
    with pytest.raises(ProvenanceError, match="worktree is dirty"):
        compute_image_identity(repo_root=repo, manifest=manifest)
    assert compute_source_tree_sha256(repo_root=repo, manifest=manifest) == before


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "stdout", "match"),
    GIT_REVISION_FAULTS,
    ids=[case[0] for case in GIT_REVISION_FAULTS],
)
def test_build_input_revision_rejects_malformed_git_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    stdout: str,
    match: str,
) -> None:
    repo, manifest = _seed_repo(tmp_path)
    _patch_git_text(monkeypatch, repo, log_stdout=f"{stdout}\n")
    with pytest.raises(ProvenanceError, match=match):
        compute_build_input_revision(repo_root=repo, manifest=manifest)
    assert name


@pytest.mark.unit
def test_build_input_revision_rejects_unresolvable_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, manifest = _seed_repo(tmp_path)
    _patch_git_text(monkeypatch, repo, log_stdout=f"{_SHA40}\n", verify_commit_ok=False)
    with pytest.raises(ProvenanceError, match="git rev-parse failed"):
        compute_build_input_revision(repo_root=repo, manifest=manifest)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "stdout", "match"),
    CANDIDATE_SHA_FAULTS,
    ids=[case[0] for case in CANDIDATE_SHA_FAULTS],
)
def test_candidate_sha_rejects_malformed_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    stdout: str,
    match: str,
) -> None:
    repo, _manifest = _seed_repo(tmp_path)
    _patch_git_text(monkeypatch, repo, head_stdout=f"{stdout}\n")
    with pytest.raises(ProvenanceError, match=match):
        compute_candidate_sha(repo_root=repo)
    assert name


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "relpaths", "match"),
    TRACKED_PATH_FAULTS,
    ids=[case[0] for case in TRACKED_PATH_FAULTS],
)
def test_source_digest_rejects_malformed_tracked_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    relpaths: tuple[str, ...],
    match: str,
) -> None:
    repo, manifest = _seed_repo(tmp_path)
    _patch_ls_files(monkeypatch, repo, relpaths)
    with pytest.raises(ProvenanceError, match=match):
        compute_source_tree_sha256(repo_root=repo, manifest=manifest)
    assert name


@pytest.mark.unit
def test_source_digest_rejects_symlink_and_special_and_missing(tmp_path: Path) -> None:
    repo, manifest = _seed_repo(tmp_path)
    target = repo / "vnext/repository_service/src/example.py"
    target.unlink()
    target.symlink_to("README.md")
    with pytest.raises(ProvenanceError, match="symlink"):
        compute_source_tree_sha256(repo_root=repo, manifest=manifest)

    target.unlink()
    os.mkfifo(target)
    with pytest.raises(ProvenanceError, match="not a regular file"):
        compute_source_tree_sha256(repo_root=repo, manifest=manifest)
    assert stat.S_ISFIFO(target.lstat().st_mode)

    target.unlink()
    with pytest.raises(ProvenanceError, match="missing"):
        compute_source_tree_sha256(repo_root=repo, manifest=manifest)


@pytest.mark.unit
def test_build_input_revision_equals_candidate_on_clean_seed(tmp_path: Path) -> None:
    repo, manifest = _seed_repo(tmp_path)
    revision = compute_build_input_revision(repo_root=repo, manifest=manifest)
    assert revision == compute_candidate_sha(repo_root=repo)


@pytest.mark.unit
def test_cli_usage_returns_two_and_omits_host_paths(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert main(["not-a-command"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("usage: build_context_digest.py ")
    assert "/" not in err
    assert "build-revision" not in err
    assert "head-sha" not in err


@pytest.mark.unit
def test_cli_identity_json_shape_and_return_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identity = ImageIdentity(
        candidate_sha="a" * 40,
        build_input_revision="b" * 40,
        source_tree_sha256="sha256:" + "c" * 64,
    )
    monkeypatch.setattr(
        "support.build_context_digest.compute_image_identity",
        lambda **_kwargs: identity,
    )
    assert main(["identity"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload == identity.to_json_dict()
    assert payload["candidate_sha"] != payload["build_input_revision"]
    assert "tmp" not in output
    assert "/root" not in output


@pytest.mark.unit
def test_cli_rejects_removed_build_revision_alias(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "support.build_context_digest.compute_build_input_revision",
        lambda **_kwargs: _SHA40,
    )
    assert main(["build-revision"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("usage: build_context_digest.py ")
    assert "build-revision" not in err
    assert "head-sha" not in err
    assert main(["build-input-revision"]) == 0
    assert capsys.readouterr().out == f"{_SHA40}\n"


@pytest.mark.unit
def test_cli_rejects_removed_head_sha_alias(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "support.build_context_digest.compute_candidate_sha",
        lambda **_kwargs: _SHA40,
    )
    assert main(["head-sha"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("usage: build_context_digest.py ")
    assert "head-sha" not in err
    assert main(["candidate-sha"]) == 0
    assert capsys.readouterr().out == f"{_SHA40}\n"


@pytest.mark.unit
def test_cli_provenance_error_is_nonzero_and_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "support.build_context_digest.compute_image_identity",
        lambda **_kwargs: (_ for _ in ()).throw(ProvenanceError("worktree is dirty")),
    )
    assert main(["identity"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "error: worktree is dirty\n"
    assert "/root" not in captured.err
    assert "token" not in captured.err
