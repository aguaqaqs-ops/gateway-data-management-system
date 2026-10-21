"""Unit tests for the standard-library test input closure manifest utility."""

from __future__ import annotations

import copy
import gzip
import hashlib
import io
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
CLOSURE_GLOBALS = CLOSURE["_docker_build_inputs"].__globals__
PACKAGES = CLOSURE["PACKAGES"]
FAKE_ENVIRONMENT = {
    "python_-VV": "Python 3.14.6 (fixture)",
    "python_unicode_data_version": "16.0.0",
    "dolt_version": "dolt version 2.1.11",
    "uv_version": "uv 0.12.5",
    "rustc_version": "rustc 1.97.0 (fixture)",
}
FAKE_DOCKER_BUILD_INPUTS = json.dumps(
    {
        "setting_fingerprints": {
            "GATEWAY_REPOSITORY_SERVICE_IMAGE": {"set": False, "sha256": None}
        },
        "effective_selections": {
            "repository_service_image": "gateway-repository-service:local"
        },
        "image_ids": {"python:3.14.6-slim-bookworm": "sha256:fixture"},
        "prebuilt_local_image_inventory": None,
    },
    sort_keys=True,
    separators=(",", ":"),
)


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
        hypothesis_constants = (
            repo_root / "vnext" / package / ".hypothesis" / "constants"
        )
        hypothesis_constants.mkdir(parents=True, exist_ok=True)
        (hypothesis_constants / "fixture-cache-entry").write_text(
            f"cached inputs for {package}\n", encoding="utf-8"
        )
        pytest_cache = repo_root / "vnext" / package / ".pytest_cache" / "v" / "cache"
        pytest_cache.mkdir(parents=True, exist_ok=True)
        (pytest_cache / "nodeids").write_text(
            '["tests/test_example.py::test_case"]\n',
            encoding="utf-8",
        )

    (repo_root / ".gitignore").write_text(
        "**/.venv/\n**/.hypothesis/\n**/.pytest_cache/\n**/custom-hypothesis/\n"
        "**/*.db\n",
        encoding="utf-8",
    )
    dockerignore = repo_root / "vnext" / ".dockerignore"
    dockerignore.write_text(
        "**/.git\n**/.venv\n**/__pycache__\n**/.pytest_cache\n"
        "**/.mypy_cache\n**/.ruff_cache\n**/.hypothesis\n**/*.so\n"
        "**/*.whl\ntarget/\n",
        encoding="utf-8",
    )

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
    environment = dict(FAKE_ENVIRONMENT)
    if package in CLOSURE["PACKAGE_DOCKER_INPUTS"]:
        environment["docker_build_inputs"] = FAKE_DOCKER_BUILD_INPUTS
    return cast(
        dict[str, Any],
        CLOSURE["build_manifest"](
            repo_root,
            package,
            environment=environment,
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
    assert backend_components["non-git:docker-context:vnext"]["kind"] == "content"
    assert backend_components["non-git:docker-context:vnext"]["paths"] == ["vnext"]
    assert backend_components["non-git:docker-context:vnext"]["entries"] == []
    assert backend_components["non-git:docker-context-tracked-modes:vnext"]["kind"] == "content"
    assert backend_components["non-git:docker-context-tracked-modes:vnext"]["paths"] == [
        "vnext"
    ]
    assert any(
        entry.startswith("vnext/backend/Dockerfile kind=file mode=")
        for entry in backend_components["non-git:docker-context-tracked-modes:vnext"][
            "entries"
        ]
    )

    repository_service = _manifest(repo_root, "repository_service")
    service_components = {
        component["name"]: component for component in repository_service["components"]
    }
    assert service_components["dockerfile:repository-client-e2e"]["paths"] == [
        "vnext/repository_client/tests/Dockerfile"
    ]
    assert service_components["non-git:docker-context:vnext"]["kind"] == "content"
    assert service_components["path-dependency:vnext/repository_contracts"]["digest"]
    assert service_components["test-authority:runtime-provider-feasibility"]["paths"] == [
        "docs/backend-vnext/refactoring/formal/plans/p2-r1-runtime-provider-feasibility.md"
    ]
    assert service_components["non-git:legacy-content"]["kind"] == "content"
    assert service_components["non-git:package-uv-environment"]["kind"] == "content"
    assert service_components["non-git:package-uv-environment"]["paths"] == [
        "vnext/repository_service/.venv"
    ]
    assert service_components["non-git:hypothesis-storage"]["kind"] == "content"
    assert service_components["non-git:hypothesis-storage"]["paths"] == [
        "vnext/repository_service/.hypothesis"
    ]
    assert service_components["non-git:pytest-cache"]["kind"] == "content"
    assert service_components["non-git:pytest-cache"]["paths"] == [
        "vnext/repository_service/.pytest_cache"
    ]
    expected_environment = dict(FAKE_ENVIRONMENT)
    expected_environment["docker_build_inputs"] = FAKE_DOCKER_BUILD_INPUTS
    assert service_components["environment:runtime-and-docker-build"]["values"] == (
        expected_environment
    )


@pytest.mark.unit
@pytest.mark.parametrize("package", ["backend", "repository_service"])
def test_docker_context_hashes_included_ignored_files_and_skips_dockerignored_files(
    package: str,
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    original = _manifest(repo_root, package)
    original_component = next(
        component
        for component in original["components"]
        if component["name"] == "non-git:docker-context:vnext"
    )

    included_ignored_file = repo_root / "vnext" / package / "target" / "context-extra.db"
    included_ignored_file.parent.mkdir()
    included_ignored_file.write_text("first build-context payload\n", encoding="utf-8")
    included = _manifest(repo_root, package)
    included_component = next(
        component
        for component in included["components"]
        if component["name"] == original_component["name"]
    )
    assert included_component["digest"] != original_component["digest"]
    assert included_component["entries"] == [
        f"vnext/{package}/target",
        f"vnext/{package}/target/context-extra.db",
    ]
    assert subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""

    dockerignored_file = repo_root / "vnext" / "target" / "excluded.db"
    dockerignored_file.parent.mkdir()
    dockerignored_file.write_text("not in Docker context\n", encoding="utf-8")
    after_excluded = _manifest(repo_root, package)
    after_excluded_component = next(
        component
        for component in after_excluded["components"]
        if component["name"] == original_component["name"]
    )
    assert after_excluded_component["digest"] == included_component["digest"]

    included_ignored_file.write_text("changed build-context payload\n", encoding="utf-8")
    changed = _manifest(repo_root, package)
    changed_component = next(
        component
        for component in changed["components"]
        if component["name"] == original_component["name"]
    )
    assert changed_component["digest"] != included_component["digest"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("relative_path", "candidate_modes"),
    [
        ("vnext/backend/Dockerfile", (0o600, 0o640, 0o620)),
        ("vnext/backend", (0o700, 0o750, 0o755)),
    ],
)
def test_docker_context_hashes_tracked_worktree_modes_even_when_git_is_clean(
    relative_path: str,
    candidate_modes: tuple[int, ...],
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    tracked_path = repo_root / relative_path
    original_mode = tracked_path.lstat().st_mode & 0o7777
    changed_mode = next(mode for mode in candidate_modes if mode != original_mode)
    before = _manifest(repo_root, "backend")
    component_name = "non-git:docker-context-tracked-modes:vnext"
    before_component = next(
        component for component in before["components"] if component["name"] == component_name
    )

    tracked_path.chmod(changed_mode)
    assert subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""

    after = _manifest(repo_root, "backend")
    after_component = next(
        component for component in after["components"] if component["name"] == component_name
    )
    assert after_component["digest"] != before_component["digest"]
    assert any(
        entry.startswith(f"{relative_path} kind=")
        and entry.endswith(f"mode={changed_mode:04o}")
        for entry in after_component["entries"]
    )
    comparison = CLOSURE["compare_manifests"](before, after)
    assert comparison["status"] == "运行"
    assert [item["component"] for item in comparison["changed_components"]] == [
        component_name
    ]


@pytest.mark.unit
def test_dockerfile_specific_ignore_rules_fail_closed(tmp_path: Path) -> None:
    repo_root = _fixture_repo(tmp_path)
    dockerfile_ignore = repo_root / "vnext" / "backend" / "Dockerfile.dockerignore"
    dockerfile_ignore.write_text("**/temporary\n", encoding="utf-8")

    with pytest.raises(CLOSURE["ClosureError"], match="Dockerfile-specific ignore rules"):
        CLOSURE["_docker_context_non_git_digest"](
            repo_root,
            "vnext",
            ["vnext/backend/Dockerfile"],
        )


@pytest.mark.unit
@pytest.mark.parametrize(
    "rule",
    ["!README.md\n", "[ab].txt\n", "**name\n"],
)
def test_unmodeled_dockerignore_syntax_fails_closed(
    rule: str,
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    dockerignore = repo_root / "vnext" / ".dockerignore"
    dockerignore.write_text(rule, encoding="utf-8")

    with pytest.raises(CLOSURE["ClosureError"]):
        CLOSURE["_dockerignore_patterns"](dockerignore)


@pytest.mark.unit
@pytest.mark.parametrize("package", ["backend", "repository_service"])
def test_docker_build_inputs_capture_selected_images_and_sensitive_setting_fingerprints(
    package: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    inspected: list[str] = []
    external_lock_root = tmp_path / "external-vnext"
    for package_name, package_path in CLOSURE["PACKAGE_PATHS"].items():
        lock_path = external_lock_root / package_path.removeprefix("vnext/") / "uv.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(f"external lock for {package_name}\n", encoding="utf-8")
    external_consumer = tmp_path / "external-uv-consume.sh"
    external_consumer.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    def image_id(_repo_root: Path, reference: str) -> str:
        inspected.append(reference)
        return f"sha256:{hashlib.sha256(reference.encode()).hexdigest()}"

    monkeypatch.setitem(CLOSURE_GLOBALS, "_docker_image_id", image_id)
    monkeypatch.setitem(
        CLOSURE_GLOBALS,
        "_docker_image_inventory",
        lambda _root: ["fixture:latest sha256:a"],
    )
    selected_environment = {
        "GATEWAY_REPOSITORY_SERVICE_IMAGE": "fixture/service:custom",
        "GATEWAY_REPOSITORY_BASE_IMAGE": "fixture/python:custom",
        "GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE": "fixture/repository-deps:custom",
        "GATEWAY_REPOSITORY_CLIENT_DEPENDENCY_BASE_IMAGE": "fixture/client-deps:custom",
        "GATEWAY_P2R1_IMAGE": "fixture/p2r1:custom",
        "GATEWAY_COMPOSE_GATE_PREBUILT": "true",
        "COMPOSE_FILE": "vnext/deploy/compose.yaml",
        "GATEWAY_VNEXT_LOCK_ROOT": str(external_lock_root),
        "GATEWAY_UV_CONSUME": str(external_consumer),
        "HTTP_PROXY": "http://user:secret@example.invalid:8080",
    }

    inputs = CLOSURE["_docker_build_inputs"](
        repo_root,
        package,
        environ=selected_environment,
    )

    selections = inputs["effective_selections"]
    assert selections["repository_service_image"] == "fixture/service:custom"
    assert selections["repository_service_base_image"] == "fixture/python:custom"
    assert selections["repository_service_dependency_base_image"] == (
        "fixture/repository-deps:custom"
    )
    image_ids = inputs["image_ids"]
    assert image_ids["fixture/service:custom"].startswith("sha256:")
    assert image_ids["fixture/python:custom"].startswith("sha256:")
    assert image_ids["fixture/repository-deps:custom"].startswith("sha256:")
    assert image_ids["fixture/p2r1:custom"].startswith("sha256:")
    assert "fixture/service:custom" in inspected
    assert "fixture/p2r1:custom" in inspected
    assert inputs["setting_fingerprints"]["COMPOSE_FILE"] == {
        "set": True,
        "sha256": hashlib.sha256(b"vnext/deploy/compose.yaml").hexdigest(),
    }
    if package == "repository_service":
        assert "fixture/client-deps:custom" in inspected
        assert "gateway-repository-client-e2e:local" not in image_ids
        assert "gateway-repository-client-e2e:local" not in inspected
    if package == "backend":
        assert "rust:1.97.0-bookworm" in inspected
    proxy_fingerprint = inputs["setting_fingerprints"]["HTTP_PROXY"]
    assert proxy_fingerprint == {
        "set": True,
        "sha256": hashlib.sha256(selected_environment["HTTP_PROXY"].encode()).hexdigest(),
    }
    assert "user:secret" not in json.dumps(inputs)
    assert inputs["external_override_inputs"]["uv_consume_script_sha256"] == hashlib.sha256(
        external_consumer.read_bytes()
    ).hexdigest()
    assert inputs["external_override_inputs"]["lock_snapshot_sha256"] is not None
    if package == "backend":
        assert selections["compose_gate_prebuilt"] is True
        assert inputs["prebuilt_local_image_inventory"] == ["fixture:latest sha256:a"]
    else:
        assert selections["repository_client_dependency_base_image"] == (
            "fixture/client-deps:custom"
        )
        assert inputs["prebuilt_local_image_inventory"] is None


DOCKER_IMAGE_ID_MANIFEST_CASES = (
    pytest.param(
        "backend",
        "gateway-repository-service:local",
        {},
        False,
        id="backend-rebuilt-repository-service",
    ),
    pytest.param(
        "repository_service",
        "gateway-repository-service:local",
        {},
        False,
        id="repository-service-rebuilt-repository-service",
    ),
    pytest.param(
        "repository_service",
        "gateway-repository-client-e2e:local",
        {},
        False,
        id="repository-service-rebuilt-client-e2e",
    ),
    pytest.param(
        "backend",
        "python:3.14.6-slim-bookworm",
        {},
        True,
        id="backend-python-base",
    ),
    pytest.param(
        "repository_service",
        "python:3.14.6-slim-bookworm",
        {},
        True,
        id="repository-service-python-base",
    ),
    pytest.param(
        "backend",
        "fixture/repository-deps:custom",
        {"GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE": "fixture/repository-deps:custom"},
        True,
        id="backend-repository-dependency-base",
    ),
    pytest.param(
        "repository_service",
        "fixture/repository-deps:custom",
        {"GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE": "fixture/repository-deps:custom"},
        True,
        id="repository-service-dependency-base",
    ),
    pytest.param(
        "repository_service",
        "gateway-repository-client-e2e-base:local",
        {},
        True,
        id="repository-client-dependency-base",
    ),
    pytest.param(
        "backend",
        "rust:1.97.0-bookworm",
        {},
        True,
        id="rust-base",
    ),
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("package", "image_reference", "environment_overrides", "identity_affects_manifest"),
    DOCKER_IMAGE_ID_MANIFEST_CASES,
)
def test_rebuilt_image_ids_are_excluded_and_build_input_ids_change_the_manifest(
    package: str,
    image_reference: str,
    environment_overrides: dict[str, str],
    identity_affects_manifest: bool,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    current_image_id = "sha256:first"
    inspected: list[str] = []

    def image_id(_repo_root: Path, reference: str) -> str:
        inspected.append(reference)
        return current_image_id if reference == image_reference else f"sha256:{reference}"

    monkeypatch.setitem(CLOSURE_GLOBALS, "_docker_image_id", image_id)
    monkeypatch.setitem(CLOSURE_GLOBALS, "_docker_image_inventory", lambda _root: [])

    def manifest() -> dict[str, Any]:
        inputs = CLOSURE["_docker_build_inputs"](
            repo_root,
            package,
            environ=environment_overrides,
        )
        environment = dict(FAKE_ENVIRONMENT)
        environment["docker_build_inputs"] = json.dumps(
            inputs,
            sort_keys=True,
            separators=(",", ":"),
        )
        return cast(
            dict[str, Any],
            CLOSURE["build_manifest"](
                repo_root,
                package,
                environment=environment,
            ),
        )

    first = manifest()
    first_inspected = list(inspected)
    current_image_id = "sha256:second"
    second = manifest()
    comparison = CLOSURE["compare_manifests"](first, second)

    assert (image_reference in first_inspected) is identity_affects_manifest
    assert comparison["status"] == ("运行" if identity_affects_manifest else "可沿用")


@pytest.mark.unit
@pytest.mark.parametrize("package", ["backend", "repository_service"])
def test_changed_docker_build_inputs_require_package_rerun(
    package: str,
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    source = _manifest(repo_root, package)
    environment = dict(FAKE_ENVIRONMENT)
    changed_docker_inputs = json.loads(FAKE_DOCKER_BUILD_INPUTS)
    changed_docker_inputs["image_ids"]["python:3.14.6-slim-bookworm"] = "sha256:changed"
    environment["docker_build_inputs"] = json.dumps(
        changed_docker_inputs,
        sort_keys=True,
        separators=(",", ":"),
    )
    current = CLOSURE["build_manifest"](
        repo_root,
        package,
        environment=environment,
    )

    result = CLOSURE["compare_manifests"](source, current)
    assert result["status"] == "运行"
    assert [change["component"] for change in result["changed_components"]] == [
        "environment:runtime-and-docker-build"
    ]


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
    ("package", "cache_root", "cache_file", "component_name"),
    [
        (
            "shared_kernel",
            ".hypothesis",
            "constants/fixture-cache-entry",
            "non-git:hypothesis-storage",
        ),
        (
            "backend",
            ".hypothesis",
            "constants/fixture-cache-entry",
            "non-git:hypothesis-storage",
        ),
        ("shared_kernel", ".pytest_cache", "v/cache/nodeids", "non-git:pytest-cache"),
        ("backend", ".pytest_cache", "v/cache/nodeids", "non-git:pytest-cache"),
    ],
)
def test_non_git_test_cache_content_is_hashed(
    package: str,
    cache_root: str,
    cache_file: str,
    component_name: str,
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    original = _manifest(repo_root, package)
    original_component = next(
        component
        for component in original["components"]
        if component["name"] == component_name
    )
    cache_entry = (
        repo_root
        / "vnext"
        / package
        / cache_root
        / cache_file
    )

    cache_entry.write_text("changed cached constants\n", encoding="utf-8")
    changed = _manifest(repo_root, package)
    changed_component = next(
        component
        for component in changed["components"]
        if component["name"] == original_component["name"]
    )
    assert changed_component["digest"] != original_component["digest"]

    cache_entry.write_text("changed cached constants\n", encoding="utf-8")
    cache_entry.chmod(0o755)
    changed_mode = _manifest(repo_root, package)
    changed_mode_component = next(
        component
        for component in changed_mode["components"]
        if component["name"] == original_component["name"]
    )
    assert changed_mode_component["digest"] != changed_component["digest"]


@pytest.mark.unit
def test_hypothesis_storage_honors_configured_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    configured = repo_root / "vnext" / "backend" / "custom-hypothesis"
    (configured / "constants").mkdir(parents=True)
    (configured / "constants" / "entry").write_text("external setting\n", encoding="utf-8")
    monkeypatch.setenv("HYPOTHESIS_STORAGE_DIRECTORY", "custom-hypothesis")

    manifest = _manifest(repo_root, "backend")
    component = next(
        item
        for item in manifest["components"]
        if item["name"] == "non-git:hypothesis-storage"
    )
    assert component["paths"] == ["vnext/backend/custom-hypothesis"]
    assert component["digest"] == CLOSURE["_directory_content_digest"](configured)


@pytest.mark.unit
def test_hypothesis_gzip_cache_hashes_decoded_payload_not_temporary_filename(
    tmp_path: Path,
) -> None:
    repo_root = _fixture_repo(tmp_path)
    storage = repo_root / "vnext" / "backend" / ".hypothesis"
    cache_file = storage / "unicode_data" / "16.0.0" / "codec-utf-8.json.gz"
    cache_file.parent.mkdir(parents=True)

    def gzip_cache(payload: bytes, filename: str) -> bytes:
        buffer = io.BytesIO()
        with gzip.GzipFile(filename=filename, mode="wb", fileobj=buffer, mtime=1) as stream:
            stream.write(payload)
        return buffer.getvalue()

    payload = b"[[0, 55295], [57344, 1114111]]"
    first_bytes = gzip_cache(payload, "temporary-one")
    cache_file.write_bytes(first_bytes)
    raw_first = CLOSURE["_directory_content_digest"](storage)
    logical_first = CLOSURE["_directory_content_digest"](
        storage,
        normalize_hypothesis_gzip=True,
    )

    second_bytes = gzip_cache(payload, "temporary-two")
    cache_file.write_bytes(second_bytes)
    raw_second = CLOSURE["_directory_content_digest"](storage)
    logical_second = CLOSURE["_directory_content_digest"](
        storage,
        normalize_hypothesis_gzip=True,
    )
    assert first_bytes != second_bytes
    assert raw_first != raw_second
    assert logical_first == logical_second

    cache_file.write_bytes(gzip_cache(b"[[0, 10]]", "temporary-two"))
    changed_payload = CLOSURE["_directory_content_digest"](
        storage,
        normalize_hypothesis_gzip=True,
    )
    assert changed_payload != logical_second


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
        } | ({"entries": component["entries"]} if "entries" in component else {})
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
            "source_entries": None,
            "current_entries": None,
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
