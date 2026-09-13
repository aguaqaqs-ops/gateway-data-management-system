"""Architecture and import boundary tests for repository distributions."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
VNEXT_ROOT = REPO_ROOT / "vnext"
INVENTORY_PATH = VNEXT_ROOT / "repository-workspace.toml"

REPOSITORY_DISTRIBUTIONS = frozenset(
    {
        "gateway-repository-contracts",
        "gateway-repository-client",
        "gateway-repository-service",
    }
)

DEPENDENCY_NAME_PATTERN = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)")


def _load_inventory() -> dict[str, object]:
    return tomllib.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _load_pyproject(project_path: Path) -> dict[str, object]:
    return tomllib.loads((project_path / "pyproject.toml").read_text(encoding="utf-8"))


def _runtime_dependency_names(pyproject: dict[str, object]) -> list[str]:
    project = pyproject.get("project", {})
    if not isinstance(project, dict):
        return []
    dependencies = project.get("dependencies", [])
    if not isinstance(dependencies, list):
        return []
    names: list[str] = []
    for item in dependencies:
        if not isinstance(item, str):
            continue
        match = DEPENDENCY_NAME_PATTERN.match(item.strip())
        if match is not None:
            names.append(match.group(1))
    return names


def _repository_runtime_dependencies(pyproject: dict[str, object]) -> list[str]:
    return [
        name for name in _runtime_dependency_names(pyproject) if name in REPOSITORY_DISTRIBUTIONS
    ]


def test_inventory_member_set_is_exact() -> None:
    inventory = _load_inventory()
    members = inventory.get("members", {})
    assert isinstance(members, dict)
    assert set(members.keys()) == REPOSITORY_DISTRIBUTIONS


def test_inventory_lock_paths_exist_and_are_independent() -> None:
    inventory = _load_inventory()
    members = inventory["members"]
    assert isinstance(members, dict)
    lock_paths: list[Path] = []
    for member in members.values():
        assert isinstance(member, dict)
        lock_path = REPO_ROOT / str(member["lock_path"])
        assert lock_path.is_file()
        lock_paths.append(lock_path.resolve())
    assert len(lock_paths) == len(set(lock_paths))


def test_inventory_matches_pyproject_metadata() -> None:
    inventory = _load_inventory()
    members = inventory["members"]
    assert isinstance(members, dict)
    for distribution, member in members.items():
        assert isinstance(member, dict)
        project_path = REPO_ROOT / str(member["project_path"])
        pyproject = _load_pyproject(project_path)
        project = pyproject.get("project", {})
        assert isinstance(project, dict)
        assert project["name"] == member["distribution"]
        assert project["name"] == distribution
        expected_import = distribution.replace("-", "_")
        assert member["import_name"] == expected_import


def test_inventory_repository_runtime_dependencies_match_pyproject() -> None:
    inventory = _load_inventory()
    members = inventory["members"]
    assert isinstance(members, dict)
    for member in members.values():
        assert isinstance(member, dict)
        project_path = REPO_ROOT / str(member["project_path"])
        pyproject = _load_pyproject(project_path)
        allowed = member.get("allowed_runtime_dependencies", [])
        assert isinstance(allowed, list)
        assert _repository_runtime_dependencies(pyproject) == allowed


def test_dependency_edges_are_acyclic_and_repository_only() -> None:
    inventory = _load_inventory()
    edges = inventory.get("dependency_edges", {})
    assert isinstance(edges, dict)
    assert set(edges.keys()) == {"gateway-repository-client", "gateway-repository-service"}
    for source, targets in edges.items():
        assert source in REPOSITORY_DISTRIBUTIONS
        assert isinstance(targets, list)
        assert targets == ["gateway-repository-contracts"]
    assert "gateway-repository-contracts" not in edges


def test_forbidden_imports_inventory_present() -> None:
    inventory = _load_inventory()
    forbidden = inventory.get("forbidden_imports", {})
    assert isinstance(forbidden, dict)
    assert set(forbidden.keys()) == {
        "gateway-repository-contracts",
        "gateway-repository-client",
        "gateway-repository-service",
    }


def test_repository_sources_do_not_import_non_repository_packages() -> None:
    forbidden = (
        "gateway_shared_kernel",
        "gateway_backend",
        "gateway_compute",
        "gateway_conformance",
    )
    package_roots = (
        REPO_ROOT / "vnext/repository_contracts/src",
        REPO_ROOT / "vnext/repository_client/src",
        REPO_ROOT / "vnext/repository_service/src",
    )
    for package_root in package_roots:
        for source in package_root.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            for import_name in forbidden:
                assert import_name not in text, source


def test_backend_forbidden_dependency_and_import() -> None:
    inventory = _load_inventory()
    backend = inventory.get("backend", {})
    assert isinstance(backend, dict)
    backend_path = REPO_ROOT / str(backend["project_path"])
    pyproject = _load_pyproject(backend_path)
    runtime_names = _runtime_dependency_names(pyproject)
    forbidden_deps = backend.get("forbidden_dependencies", [])
    assert isinstance(forbidden_deps, list)
    for dep in forbidden_deps:
        assert dep not in runtime_names

    forbidden_imports = backend.get("forbidden_imports", [])
    assert isinstance(forbidden_imports, list)
    src_root = backend_path / "src"
    for source in src_root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for import_name in forbidden_imports:
            assert import_name not in text


def _run_isolated_import_probe(project_dir: Path, script: str) -> subprocess.CompletedProcess[str]:
    venv_dir = tempfile.mkdtemp(prefix="uv-r1-")
    try:
        env = os.environ.copy()
        for inherited_name in (
            "PYTHONHOME",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "UV_DEFAULT_INDEX",
            "UV_INDEX_URL",
            "UV_INSECURE_HOST",
            "PIP_INDEX_URL",
            "PIP_TRUSTED_HOST",
        ):
            env.pop(inherited_name, None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["UV_PROJECT_ENVIRONMENT"] = venv_dir
        sync = subprocess.run(
            ["uv", "sync", "--locked", "--offline", "--all-groups"],
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if sync.returncode != 0:
            return sync
        return subprocess.run(
            ["uv", "run", "--offline", "--no-sync", "python", "-c", script],
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        shutil.rmtree(venv_dir, ignore_errors=True)


@pytest.mark.parametrize(
    ("project_rel", "must_importable", "must_not_findable"),
    [
        (
            "vnext/repository_contracts",
            ["gateway_repository_contracts"],
            ["gateway_repository_client", "gateway_repository_service"],
        ),
        (
            "vnext/repository_client",
            ["gateway_repository_contracts", "gateway_repository_client"],
            ["gateway_repository_service"],
        ),
        (
            "vnext/repository_service",
            ["gateway_repository_contracts", "gateway_repository_service"],
            ["gateway_repository_client"],
        ),
    ],
)
def test_import_isolation_in_isolated_environments(
    project_rel: str,
    must_importable: list[str],
    must_not_findable: list[str],
) -> None:
    project_dir = REPO_ROOT / project_rel
    import_lines = "\n".join(f"import {name}" for name in must_importable)
    check_lines = "\n".join(
        f"assert importlib.util.find_spec('{name}') is None" for name in must_not_findable
    )
    script = f"""
import importlib.util
{import_lines}
{check_lines}
"""
    result = _run_isolated_import_probe(project_dir, script)
    assert result.returncode == 0, result.stdout + result.stderr
