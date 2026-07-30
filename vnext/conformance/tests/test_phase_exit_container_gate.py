"""Regression tests for PHASE-EXIT-CONTAINER gate static behavior and fail-closed paths."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.phase_exit_container

REPO_ROOT = Path(__file__).resolve().parents[3]
VNEXT_ROOT = REPO_ROOT / "vnext"
GATE_SCRIPT = VNEXT_ROOT / "scripts" / "phase_exit_container_gate.sh"
PINS_FILE = VNEXT_ROOT / "deploy" / "phase-1-image-pins.env"
DOCKERFILE = VNEXT_ROOT / "backend" / "Dockerfile"
PATCH_SHA_SCRIPT = VNEXT_ROOT / "scripts" / "verify-wp5-r5-patch-sha.sh"
EVIDENCE_PATH = (
    REPO_ROOT / "docs/backend-vnext/refactoring/temporary/phase-1/wp5-r5-phase1-exit-evidence.md"
)
LOCK_PATHS = (
    VNEXT_ROOT / "rust/Cargo.lock",
    VNEXT_ROOT / "backend/uv.lock",
    VNEXT_ROOT / "backend/uv.container.lock",
    VNEXT_ROOT / "shared_kernel/uv.lock",
    VNEXT_ROOT / "conformance/uv.lock",
    VNEXT_ROOT / "repository_service/uv.lock",
)
COMPOSE_PHASE_EXIT = VNEXT_ROOT / "deploy" / "compose.phase-exit.yaml"


def _run_gate(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(GATE_SCRIPT), *args],
        cwd=REPO_ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def test_phase_exit_gate_script_exists() -> None:
    assert GATE_SCRIPT.is_file()


def test_pins_file_requires_digests() -> None:
    text = PINS_FILE.read_text(encoding="utf-8")
    assert "RUST_BUILDER_IMAGE=" in text
    assert "PYTHON_RUNTIME_IMAGE=" in text
    for line in text.splitlines():
        if line.startswith("RUST_BUILDER_IMAGE=") or line.startswith("PYTHON_RUNTIME_IMAGE="):
            assert "@sha256:" in line, line


def test_pins_file_includes_uv_wheel_sha() -> None:
    text = PINS_FILE.read_text(encoding="utf-8")
    assert "UV_PIP_WHEEL_URL=https://files.pythonhosted.org/" in text
    assert "UV_PIP_WHEEL_SHA256=" in text
    for line in text.splitlines():
        if line.startswith("UV_PIP_WHEEL_SHA256="):
            digest = line.split("=", 1)[1].strip()
            assert len(digest) == 64
            assert digest == digest.lower()


def test_dockerfile_installs_uv_from_staged_wheel() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    pins = PINS_FILE.read_text(encoding="utf-8")
    uv_url = next(
        line.split("=", 1)[1].strip()
        for line in pins.splitlines()
        if line.startswith("UV_PIP_WHEEL_URL=")
    )
    uv_basename = uv_url.rsplit("/", 1)[-1]
    assert "UV_WHEEL_BASENAME" in dockerfile
    assert "UV_WHEEL_SHA256" in dockerfile
    assert (
        "/opt/gateway/wheels/${UV_WHEEL_BASENAME}" in dockerfile
        or uv_basename.split("-")[0] in dockerfile
    )
    assert "uv-0.11.28-linux_x86_64.whl" not in dockerfile
    assert 'pip install --no-cache-dir "uv==' not in dockerfile


def test_dockerfile_forbids_invalid_short_wheel_names() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    gate_text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert "gateway-compute-python.whl" not in dockerfile
    assert "uv-0.11.28-linux_x86_64.whl" not in dockerfile
    assert "gateway-compute-python.whl" not in gate_text
    assert "uv-0.11.28-linux_x86_64.whl" not in gate_text


def test_pins_file_includes_pip_wheel_sha() -> None:
    text = PINS_FILE.read_text(encoding="utf-8")
    assert "PIP_VERSION=25.3" in text
    assert "PIP_WHEEL_URL=https://files.pythonhosted.org/" in text
    assert "PIP_WHEEL_SHA256=" in text
    for line in text.splitlines():
        if line.startswith("PIP_WHEEL_SHA256="):
            digest = line.split("=", 1)[1].strip()
            assert len(digest) == 64
            assert digest == digest.lower()


def test_gate_script_bootstraps_pinned_pip_without_host_pip() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert "--without-pip" in text
    assert "bootstrap_pinned_pip_into_venv" in text
    assert "stage_pip_wheel_for_docker_build" in text
    assert "pinned pip version mismatch" in text


def test_gate_blocked_layering_deps_vs_docker_build() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert "phase_exit_is_transport_log" in text
    assert "phase_exit_http_status_is_registry_blocked" in text
    assert "phase_exit_is_docker_pull_local_log" in text
    assert "phase_exit_curl_fetch_to_file" in text
    assert "phase_exit_read_curl_fetch_result" in text
    assert "PHASE_EXIT_LAST_CURL_EC" not in text
    assert "phase_exit_report_docker_pull_failure" in text
    assert "phase_exit_container_deps_wheels.py" in text
    assert "DEPS_WHEELS_SELECTOR" in text
    assert 'phase_exit_assert_curl_fetch_ok "deps-wheel"' in text
    assert "phase_exit_precheck_pypi_index" not in text
    assert "phase_exit_report_download_failure" not in text
    assert "failed (local)" in text
    assert 'phase_exit_blocked "docker build timed out"' not in text
    assert 'phase_exit_blocked "docker build timed out (injected)"' not in text
    assert "docker_build_offline" in text
    assert "docker build failed with exit" in text
    assert "docker build timed out with exit 124" in text
    assert "phase_exit_report_curl_fetch_failure" in text
    assert "download failed (local)" in text
    assert 'phase_exit_blocked "registry pull failed' in text
    assert "registry pull failed (local)" in text


def test_stage_container_deps_export_wiring() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    stage_start = text.index("stage_container_deps_wheels()")
    stage_end = text.index("run_identity_bundle_python()", stage_start)
    stage_body = text[stage_start:stage_end]
    assert "--no-hashes" in stage_body
    assert "--no-annotate" in stage_body
    assert "filter-export" in stage_body
    assert "deps-wheel-list.tsv" in stage_body
    assert "deps wheel select produced empty list" in stage_body
    assert "done < <(" not in stage_body


def _load_deps_wheels_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "phase_exit_container_deps_wheels",
        VNEXT_ROOT / "scripts" / "phase_exit_container_deps_wheels.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_filter_export_strips_uv_export_noise() -> None:
    mod = _load_deps_wheels_module()
    sample = """\
fastapi==0.139.0 \\
    --hash=sha256:abc
    # via gateway-backend
colorama==0.4.6 ; sys_platform == 'win32'
pyarrow==25.0.0
"""
    got = mod.iter_export_requirements(sample)
    names = {name for name, _ in got}
    assert "fastapi" in names
    assert "pyarrow" in names
    assert "colorama" not in names


def test_uv_export_filter_select_produces_pyarrow_wheel() -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")
    selector = VNEXT_ROOT / "scripts" / "phase_exit_container_deps_wheels.py"
    with tempfile.TemporaryDirectory() as tmp:
        export_dir = Path(tmp) / "container-export"
        export_dir.mkdir()
        shutil.copy(
            VNEXT_ROOT / "backend" / "pyproject.container.toml",
            export_dir / "pyproject.toml",
        )
        shutil.copy(VNEXT_ROOT / "backend" / "uv.container.lock", export_dir / "uv.lock")
        shutil.copy(VNEXT_ROOT / "backend" / ".python-version", export_dir / ".python-version")
        proc = subprocess.run(
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-hashes",
                "--no-annotate",
                "-o",
                "requirements.txt",
            ],
            cwd=export_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        req_pypi = export_dir / "requirements-pypi.txt"
        proc = subprocess.run(
            [
                sys.executable,
                str(selector),
                "filter-export",
                "--input",
                "requirements.txt",
                "-o",
                str(req_pypi),
            ],
            cwd=export_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        proc = subprocess.run(
            [
                sys.executable,
                str(selector),
                "select",
                "--requirements",
                str(req_pypi),
                "--lock",
                "uv.lock",
                "--python-tag",
                "cp314",
            ],
            cwd=export_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        assert len(lines) > 0
        assert any("pyarrow" in ln and "manylinux" in ln and "x86_64" in ln for ln in lines)


def test_deps_classify_regression_subcommand() -> None:
    proc = _run_gate("deps-classify-regression")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "deps-classify regression ok" in proc.stdout


def test_bootstrap_pip_regression_subcommand() -> None:
    proc = _run_gate("bootstrap-pip-regression")
    if proc.returncode != 0 and "BLOCKED:" in proc.stderr:
        pytest.skip(f"network blocked for pip wheel download: {proc.stderr}")
    assert proc.returncode == 0, proc.stderr
    assert "pip 25.3" in proc.stdout


def test_dockerfile_has_no_floating_syntax_directive() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "syntax=docker/dockerfile" not in dockerfile


def test_gate_script_uses_pip_download_not_uv_pip_download() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert "uv pip download" not in text
    stage_start = text.index("stage_container_deps_wheels()")
    stage_end = text.index("run_identity_bundle_python()", stage_start)
    stage_body = text[stage_start:stage_end]
    assert "-m pip download" not in stage_body
    assert "run_identity_bundle_python" in text
    assert "rollback_identity_artifact" in text
    assert "identity_persist_attempted" in text


def test_deps_lock_wheel_selector() -> None:
    selector = VNEXT_ROOT / "scripts" / "phase_exit_container_deps_wheels.py"
    lock = VNEXT_ROOT / "backend" / "uv.container.lock"
    proc = subprocess.run(
        [
            sys.executable,
            str(selector),
            "select-regression",
            "--lock",
            str(lock),
            "--python-tag",
            "cp314",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_platform_wheel_exact_abi_rejects_cp314t() -> None:
    mod = _load_deps_wheels_module()
    cp314t = "https://files.pythonhosted.org/pkg-0.0.1-cp314-cp314t-manylinux_2_28_x86_64.whl"
    cp314 = "https://files.pythonhosted.org/pkg-0.0.1-cp314-cp314-manylinux_2_28_x86_64.whl"
    assert mod._is_platform_wheel(cp314t, "cp314") is False
    assert mod._is_platform_wheel(cp314, "cp314") is True
    wheels = [
        {"url": cp314t, "hash": "sha256:" + "a" * 64},
        {"url": cp314, "hash": "sha256:" + "b" * 64},
    ]
    url, _, base = mod.select_wheel_url(wheels, "cp314")
    assert "cp314t" not in base.lower()
    assert "-cp314-cp314-" in base.lower()


def test_gate_sh_binds_expected_head() -> None:
    gate_sh = (VNEXT_ROOT / "scripts" / "gate.sh").read_text(encoding="utf-8")
    assert 'export EXPECTED_HEAD="$(git -C "${REPO_ROOT}" rev-parse HEAD)"' in gate_sh


def test_gate_script_uses_unique_image_tag() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert 'PHASE_EXIT_IMAGE_TAG="gateway-vnext-phase1-exit:${source_revision:0:12}-$$"' in text


def test_gate_script_always_compose_down() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert 'docker compose -f "${COMPOSE_PHASE_EXIT_FILE}" -p "${project}" down' in text
    assert 'if [[ -n "${project_containers}" ]]; then' not in text


def test_dockerfile_uses_host_staged_wheel_only() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "maturin build" not in dockerfile
    assert "rust-builder" not in dockerfile
    assert "GATEWAY_COMPUTE_WHEEL_BASENAME" in dockerfile
    assert "COPY rust" not in dockerfile


def test_compose_phase_exit_file_uses_prebuilt_image() -> None:
    text = COMPOSE_PHASE_EXIT.read_text(encoding="utf-8")
    assert "PHASE_EXIT_IMAGE_TAG" in text
    assert "build:" not in text
    assert "GATEWAY_INSTALLED_WHEEL_PATH" not in text


def test_default_compose_config_q_with_four_variables() -> None:
    compose_file = VNEXT_ROOT / "deploy" / "compose.yaml"
    assert "GATEWAY_INSTALLED_WHEEL_PATH" not in compose_file.read_text(encoding="utf-8")
    env = {
        **os.environ,
        "PHASE_EXIT_IMAGE_TAG": "gateway-vnext-test:local",
        "SOURCE_REVISION": "abc123",
        "WHEEL_SHA256": "a" * 64,
        "EXTENSION_SHA256": "b" * 64,
    }
    proc = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "config", "-q"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_dockerfile_installs_frozen_dependencies_from_offline_wheelhouse() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "container-deps-wheels" in dockerfile
    assert "uv export --frozen --offline" in dockerfile
    assert "uv pip install --python .venv/bin/python --offline --no-index" in dockerfile
    assert "--find-links /opt/gateway/wheels/deps" in dockerfile
    assert 'PYTHONPATH="/app/backend/src:/app/shared_kernel/src"' in dockerfile


def test_network_deadline_zero_rejected() -> None:
    proc = _run_gate("check-static", env={"PHASE_EXIT_NETWORK_DEADLINE_SEC": "0"})
    assert proc.returncode != 0
    assert "PHASE_EXIT_NETWORK_DEADLINE_SEC" in proc.stderr


def test_force_cleanup_fail_forbidden_on_formal_gate() -> None:
    proc = _run_gate("gate", env={"PHASE_EXIT_CONTAINER_FORCE_CLEANUP_FAIL": "1"})
    assert proc.returncode != 0
    assert "FORCE_CLEANUP_FAIL is not permitted" in proc.stderr


def test_inject_tmp_rm_fail_forbidden_on_formal_gate() -> None:
    proc = _run_gate("gate", env={"PHASE_EXIT_CONTAINER_INJECT_TMP_RM_FAIL": "1"})
    assert proc.returncode != 0
    assert "INJECT_TMP_RM_FAIL is not permitted" in proc.stderr


def test_inject_deps_timeout_forbidden_on_formal_gate() -> None:
    proc = _run_gate("gate", env={"PHASE_EXIT_CONTAINER_INJECT_DEPS_TIMEOUT": "1"})
    assert proc.returncode != 0
    assert "INJECT_DEPS_TIMEOUT is not permitted" in proc.stderr


def test_dockerfile_runtime_stage_has_no_rust_copy() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    runtime = dockerfile.split("FROM ${PYTHON_RUNTIME_IMAGE}", 1)[1]
    assert "COPY rust" not in runtime
    assert "curl" not in dockerfile.lower() or "install.sh" not in dockerfile


def test_check_static_passes() -> None:
    proc = _run_gate("check-static")
    assert proc.returncode == 0, proc.stderr
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert 'pip install --no-cache-dir "uv==' not in dockerfile


def test_dirty_worktree_rejected() -> None:
    marker = REPO_ROOT / ".phase-exit-dirty-marker"
    marker.write_text("x", encoding="utf-8")
    try:
        proc = _run_gate("gate", env={"PHASE_EXIT_CONTAINER_ALLOW_DIRTY": "0"})
        assert proc.returncode != 0
        assert "dirty worktree" in proc.stderr
    finally:
        marker.unlink(missing_ok=True)


def test_clean_worktree_compares_against_head() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert "diff --quiet HEAD -- ." in text
    assert "trap 'local ec=$?" not in text
    assert "phase_exit_exit_trap" in text


def test_allow_dirty_forbidden_on_formal_gate() -> None:
    proc = _run_gate(
        "gate",
        env={
            "PHASE_EXIT_CONTAINER_ALLOW_DIRTY": "1",
        },
    )
    assert proc.returncode != 0
    assert "PHASE_EXIT_CONTAINER_ALLOW_DIRTY is not permitted" in proc.stderr


def test_inject_body_success_forbidden_on_formal_gate() -> None:
    proc = _run_gate(
        "gate",
        env={
            "PHASE_EXIT_CONTAINER_INJECT_BODY_SUCCESS": "1",
            "PHASE_EXIT_CONTAINER_SKIP_PLATFORM_CHECK": "1",
        },
    )
    assert proc.returncode != 0
    assert "INJECT_BODY_SUCCESS is not permitted" in proc.stderr
    assert "gate passed" not in proc.stdout
    assert "gate passed" not in proc.stderr


def test_regression_mode_forbidden_on_formal_gate() -> None:
    proc = _run_gate(
        "gate",
        env={
            "PHASE_EXIT_CONTAINER_REGRESSION_MODE": "1",
            "PHASE_EXIT_CONTAINER_INJECT_BODY_SUCCESS": "1",
            "PHASE_EXIT_CONTAINER_ALLOW_DIRTY": "1",
            "PHASE_EXIT_CONTAINER_SKIP_PLATFORM_CHECK": "1",
        },
    )
    assert proc.returncode != 0
    assert "REGRESSION_MODE is not permitted" in proc.stderr
    assert "injected body success" not in proc.stdout
    assert "injected body success" not in proc.stderr


def test_expected_head_mismatch_rejected() -> None:
    proc = _run_gate(
        "gate",
        env={
            "EXPECTED_HEAD": "0" * 40,
        },
    )
    assert proc.returncode != 0
    assert (
        "HEAD mismatch" in proc.stderr
        or "dirty worktree" in proc.stderr
        or "PHASE_EXIT_CONTAINER_ALLOW_DIRTY" in proc.stderr
        or "SKIP_PLATFORM_CHECK" in proc.stderr
        or "INJECT_BODY_SUCCESS" in proc.stderr
    )


def test_expected_head_required_when_not_injected() -> None:
    env = {k: v for k, v in os.environ.items() if k != "EXPECTED_HEAD"}
    proc = _run_gate("gate", env=env)
    assert proc.returncode != 0
    combined = proc.stderr + proc.stdout
    assert (
        "EXPECTED_HEAD is required" in combined
        or "dirty worktree" in combined
        or "not permitted on formal" in combined
    )


def test_registry_blocked_exit_code() -> None:
    proc = _run_gate(
        "verify-registry-blocked",
        env={
            "PHASE_EXIT_CONTAINER_INJECT_REGISTRY_BLOCKED": "1",
        },
    )
    assert proc.returncode == 3
    assert "BLOCKED:" in proc.stderr


def test_pull_timeout_inject_exit_code() -> None:
    proc = _run_gate(
        "verify-registry-blocked",
        env={
            "PHASE_EXIT_CONTAINER_INJECT_PULL_TIMEOUT": "1",
        },
    )
    assert proc.returncode == 3
    assert "BLOCKED:" in proc.stderr
    assert "timed out" in proc.stderr


def test_build_timeout_inject_is_wired_in_gate_script() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert "PHASE_EXIT_CONTAINER_INJECT_BUILD_TIMEOUT" in text
    assert "docker_build_offline" in text
    assert "docker_build_with_blocked" not in text
    assert 'phase_exit_blocked "docker build timed out (injected)"' not in text
    assert "docker build timed out (injected)" in text


def test_docker_daemon_inject_rejected() -> None:
    text = GATE_SCRIPT.read_text(encoding="utf-8")
    assert "PHASE_EXIT_CONTAINER_INJECT_DOCKER_DAEMON_FAIL" in text


def test_trap_regression_exit_codes() -> None:
    proc = _run_gate("trap-regression")
    assert proc.returncode == 0, proc.stderr


def test_success_path_regression_exit_codes() -> None:
    proc = _run_gate("success-path-regression")
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_gate_does_not_mutate_lockfiles() -> None:
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in LOCK_PATHS}
    proc = _run_gate("check-static")
    assert proc.returncode == 0, proc.stderr
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in LOCK_PATHS}
    assert before == after


def test_wp5_r5_patch_sha_script_exists() -> None:
    assert PATCH_SHA_SCRIPT.is_file()


def _evidence_patch_sha() -> str:
    text = EVIDENCE_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("EXPECTED_SHA="):
            return line.split("=", 1)[1].strip()
    raise AssertionError("EXPECTED_SHA missing from evidence")


def test_wp5_r5_patch_sha_matches_worktree() -> None:
    if not EVIDENCE_PATH.is_file():
        pytest.skip("evidence not written yet")
    proc = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    sha = proc.stdout.split()[0]
    expected = _evidence_patch_sha()
    assert sha == expected


def test_wp5_r5_patch_sha_rejects_exclude_override() -> None:
    proc = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        env={**os.environ, "EXCLUDE": "other.md"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "EXCLUDE override is not permitted" in proc.stderr


@pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(),
    reason="git repository required for patch SHA index isolation test",
)
def test_wp5_r5_patch_sha_stable_after_git_add(tmp_path: Path) -> None:
    index_before = subprocess.run(
        ["git", "write-tree"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    probe = REPO_ROOT / "vnext" / ".wp5-r5-patch-sha-probe"
    probe.write_text("probe\n", encoding="utf-8")
    proc_before = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    before = proc_before.stdout.split()[0]
    temp_index = tmp_path / "isolated-index"
    temp_index.write_bytes(b"")
    env = {**os.environ, "GIT_INDEX_FILE": str(temp_index)}
    try:
        subprocess.run(["git", "read-tree", "HEAD"], cwd=REPO_ROOT, env=env, check=True)
        subprocess.run(["git", "add", str(probe)], cwd=REPO_ROOT, env=env, check=True)
        proc_after = subprocess.run(
            ["bash", str(PATCH_SHA_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        after = proc_after.stdout.split()[0]
        assert before == after
    finally:
        probe.unlink(missing_ok=True)
    index_after = subprocess.run(
        ["git", "write-tree"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert index_before == index_after


def test_wp5_r5_patch_sha_stable_under_locale() -> None:
    proc_c = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        env={**os.environ, "LC_ALL": "C"},
        text=True,
        capture_output=True,
        check=True,
    )
    proc_utf = subprocess.run(
        ["bash", str(PATCH_SHA_SCRIPT)],
        cwd=REPO_ROOT,
        env={**os.environ, "LC_ALL": "en_US.UTF-8"},
        text=True,
        capture_output=True,
        check=True,
    )
    assert proc_c.stdout.split()[0] == proc_utf.stdout.split()[0]
