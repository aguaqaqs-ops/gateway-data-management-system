"""Unit tests for the standard-library test input closure manifest utility."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = VNEXT_ROOT.parent
CLOSURE_SCRIPT = VNEXT_ROOT / "scripts" / "test_input_closure.py"
CLOSURE = runpy.run_path(str(CLOSURE_SCRIPT))
PACKAGES = CLOSURE["PACKAGES"]
FAKE_ENVIRONMENT = {
    "python_-VV": "Python 3.14.6 (fixture)",
    "python_unicode_data_version": "16.0.0",
    "dolt_version": "dolt version 2.1.11",
    "uv_version": "uv 0.12.5",
    "rustc_version": "rustc 1.97.0 (fixture)",
}


def _fixture_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "closure-repo"
    paths: set[str] = {"legacy/reference.json"}
    for package in PACKAGES:
        paths.update(spec["path"] for spec in CLOSURE["_component_specs"](package))
    for relative in sorted(paths):
        path = repo_root / relative
        if path.suffix or path.name == "Dockerfile":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"fixture for {relative}\n", encoding="utf-8")
        else:
            path.mkdir(parents=True, exist_ok=True)
            (path / "fixture.txt").write_text(f"fixture for {relative}\n", encoding="utf-8")
    for package in PACKAGES:
        environment = repo_root / "vnext" / package / ".venv"
        site_packages = environment / "lib" / "python3.14" / "site-packages"
        site_packages.mkdir(parents=True, exist_ok=True)
        (environment / "pyvenv.cfg").write_text("fixture environment\n", encoding="utf-8")
        (site_packages / "fixture_dependency.py").write_text(
            f"PACKAGE = {package!r}\n", encoding="utf-8"
        )

    (repo_root / ".gitignore").write_text("**/.venv/\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q", str(repo_root)], check=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.name", "Closure Test"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_root), "config", "user.email", "closure@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo_root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "commit", "-qm", "closure fixture"],
        check=True,
    )
    return repo_root


def _manifest(repo_root: Path, package: str = "backend") -> dict[str, Any]:
    return cast(
        dict[str, Any],
        CLOSURE["build_manifest"](
            repo_root,
            package,
            environment=FAKE_ENVIRONMENT,
        ),
    )


@pytest.mark.unit
def test_closure_manifest_lists_package_shared_and_docker_build_inputs(tmp_path: Path) -> None:
    repo_root = _fixture_repo(tmp_path)
    backend = _manifest(repo_root, "backend")
    backend_components = {component["name"]: component for component in backend["components"]}
    package_tree = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD:vnext/backend"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert backend_components["package:backend"]["digest"] == package_tree
    assert backend_components["shared:scripts"]["paths"] == ["vnext/scripts"]
    assert backend_components["shared:workspace-definition"]["paths"] == [
        "vnext/repository-workspace.toml"
    ]
    assert backend_components["shared:rust-toolchain-selector"]["paths"] == [
        "vnext/rust/rust-toolchain.toml"
    ]
    assert backend_components["rust:workspace"]["paths"] == ["vnext/rust"]
    assert backend_components["docker:context:vnext"]["digest"] == subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD:vnext"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    repository_service = _manifest(repo_root, "repository_service")
    service_components = {component["name"]: component for component in repository_service["components"]}
    assert service_components["dockerfile:repository-client-e2e"]["paths"] == [
        "vnext/repository_client/tests/Dockerfile"
    ]
    assert service_components["path-dependency:vnext/repository_contracts"]["digest"]
    assert service_components["test-authority:runtime-provider-feasibility"]["paths"] == [
        "docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md"
    ]
    assert service_components["non-git:legacy-content"]["kind"] == "content"
    assert service_components["non-git:package-uv-environment"]["kind"] == "content"
    assert service_components["non-git:package-uv-environment"]["paths"] == [
        "vnext/repository_service/.venv"
    ]
    assert service_components["environment:python-dolt-uv-rustc"]["values"] == FAKE_ENVIRONMENT


@pytest.mark.unit
def test_package_uv_environment_content_is_hashed_but_bytecode_is_derived(
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    original = _manifest(repo_root, "shared_kernel")
    original_component = next(
        component
        for component in original["components"]
        if component["name"] == "non-git:package-uv-environment"
    )

    dependency = (
        repo_root
        / "vnext"
        / "shared_kernel"
        / ".venv"
        / "lib"
        / "python3.14"
        / "site-packages"
        / "fixture_dependency.py"
    )
    dependency.write_text("PACKAGE = 'changed'\n", encoding="utf-8")
    changed = _manifest(repo_root, "shared_kernel")
    changed_component = next(
        component
        for component in changed["components"]
        if component["name"] == "non-git:package-uv-environment"
    )
    assert changed_component["digest"] != original_component["digest"]

    bytecode = dependency.parent / "__pycache__" / "fixture_dependency.cpython-314.pyc"
    bytecode.parent.mkdir()
    bytecode.write_bytes(b"derived bytecode")
    after_bytecode = _manifest(repo_root, "shared_kernel")
    after_component = next(
        component
        for component in after_bytecode["components"]
        if component["name"] == "non-git:package-uv-environment"
    )
    assert after_component["digest"] == changed_component["digest"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("package", "required_paths"),
    [
        ("repository_client", {"vnext/repository_contracts"}),
        (
            "backend",
            {
                "vnext/shared_kernel",
                "vnext/repository_client",
                "vnext/repository_contracts",
                "vnext/rust/gateway-compute-python-impl",
                "vnext/rust/gateway-compute-core",
                "vnext/rust/gateway-shared-kernel",
            },
        ),
    ],
)
def test_path_dependency_closure_includes_transitive_dependencies(
    package: str,
    required_paths: set[str],
) -> None:
    package_path = CLOSURE["PACKAGE_PATHS"][package]
    dependencies = set(CLOSURE["expand_path_dependencies"](package_path))
    assert required_paths <= dependencies


@pytest.mark.unit
def test_compare_reports_reuse_and_lists_changed_components(tmp_path: Path) -> None:
    repo_root = _fixture_repo(tmp_path)
    source = _manifest(repo_root, "repository_service")
    unchanged = copy.deepcopy(source)
    unchanged["head"] = "different-head"
    result = CLOSURE["compare_manifests"](source, unchanged)
    assert result["status"] == "可沿用"
    assert result["changed_components"] == []

    changed = copy.deepcopy(unchanged)
    changed["components"][0]["digest"] = "changed-digest"
    digest_components = [
        {
            key: component[key]
            for key in ("name", "kind", "git_object_type", "paths", "digest")
        }
        for component in changed["components"]
    ]
    changed["total_digest"] = hashlib.sha256(
        CLOSURE["_canonical_json"](
            {
                "schema": changed["schema"],
                "schema_version": changed["schema_version"],
                "package": changed["package"],
                "components": digest_components,
            }
        )
    ).hexdigest()
    result = CLOSURE["compare_manifests"](source, changed)
    assert result["status"] == "运行"
    assert result["changed_components"] == [
        {
            "component": source["components"][0]["name"],
            "source_kind": source["components"][0]["kind"],
            "current_kind": source["components"][0]["kind"],
                "source_git_object_type": source["components"][0]["git_object_type"],
                "current_git_object_type": source["components"][0]["git_object_type"],
            "source_paths": source["components"][0]["paths"],
            "current_paths": source["components"][0]["paths"],
            "source_digest": source["components"][0]["digest"],
            "current_digest": "changed-digest",
        }
    ]


@pytest.mark.unit
def test_compare_cli_rejects_dirty_worktree(tmp_path: Path) -> None:
    repo_root = _fixture_repo(tmp_path)
    source_path = tmp_path / "source.json"
    current_path = tmp_path / "current.json"
    manifest = _manifest(repo_root, "shared_kernel")
    source_path.write_text(json.dumps(manifest), encoding="utf-8")
    current_path.write_text(json.dumps(manifest), encoding="utf-8")

    clean_result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(CLOSURE_SCRIPT),
            "compare",
            "--root",
            str(repo_root),
            "--source",
            str(source_path),
            "--current",
            str(current_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert clean_result.returncode == 0, clean_result.stderr
    assert json.loads(clean_result.stdout)["status"] == "可沿用"

    tracked_file = repo_root / "vnext" / "shared_kernel" / "pyproject.toml"
    tracked_file.write_text("dirty\n", encoding="utf-8")
    dirty_result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(CLOSURE_SCRIPT),
            "compare",
            "--root",
            str(repo_root),
            "--source",
            str(source_path),
            "--current",
            str(current_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert dirty_result.returncode == 2
    assert "worktree is dirty" in dirty_result.stderr
