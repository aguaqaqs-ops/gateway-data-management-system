"""Unit tests for prepare-dev-dependencies.sh and index isolation helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
PREPARE_SCRIPT = VNEXT_ROOT / "scripts" / "prepare-dev-dependencies.sh"
INDEX_LIB = VNEXT_ROOT / "scripts" / "lib" / "gateway-index-env.sh"
RUN_TESTS_SCRIPT = VNEXT_ROOT / "scripts" / "run-tests.sh"


def _run_prepare(
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env is not None:
        merged.update(env)
    return subprocess.run(
        ["bash", str(PREPARE_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=merged,
        cwd=VNEXT_ROOT,
    )


@pytest.mark.unit
def test_internal_mode_fails_closed_without_index() -> None:
    completed = _run_prepare(
        env={
            "GATEWAY_DEV_DEPENDENCY_MODE": "internal",
            "UV_INDEX_URL": "",
            "UV_DEFAULT_INDEX": "",
        },
    )
    assert completed.returncode == 2
    assert "requires UV_INDEX_URL or UV_DEFAULT_INDEX" in completed.stderr


@pytest.mark.unit
def test_internal_mode_rejects_invalid_mode() -> None:
    completed = _run_prepare(env={"GATEWAY_DEV_DEPENDENCY_MODE": "mirror"})
    assert completed.returncode == 2
    assert "must be internal or pypi" in completed.stderr


@pytest.mark.unit
def test_prepare_does_not_print_credentials() -> None:
    completed = _run_prepare(
        env={
            "GATEWAY_DEV_DEPENDENCY_MODE": "internal",
            "UV_INDEX_URL": "http://user:secret-pass@internal.example/simple",
            "GATEWAY_DEV_OFFLINE": "1",
        },
    )
    output = f"{completed.stdout}\n{completed.stderr}".lower()
    assert "secret-pass" not in output
    assert "user:secret" not in output
    assert "bearer" not in output
    assert "token" not in output


@pytest.mark.unit
def test_prepare_preserves_all_lockfiles() -> None:
    before = subprocess.run(
        ["bash", "-c", f'source "{INDEX_LIB}" && gateway_snapshot_lockfile_sha256 "{VNEXT_ROOT}"'],
        check=True,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    ).stdout
    completed = _run_prepare(env={"GATEWAY_DEV_DEPENDENCY_MODE": "pypi", "GATEWAY_DEV_OFFLINE": "1"})
    assert completed.returncode == 0, completed.stderr
    after = subprocess.run(
        ["bash", "-c", f'source "{INDEX_LIB}" && gateway_snapshot_lockfile_sha256 "{VNEXT_ROOT}"'],
        check=True,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    ).stdout
    assert before == after
    assert "lockfiles unchanged" in completed.stdout


@pytest.mark.unit
def test_prepare_script_pypi_mode_strips_machine_index() -> None:
    script = PREPARE_SCRIPT.read_text(encoding="utf-8")
    assert 'gateway_with_isolated_index uv "${sync_args[@]}"' in script
    assert 'MODE}" == "pypi"' in script


@pytest.mark.unit
def test_run_tests_strips_machine_index() -> None:
    probe = subprocess.run(
        [
            "bash",
            "-c",
            (
                f'source "{INDEX_LIB}" && '
                'export UV_INDEX_URL=http://internal.example/simple && '
                'export UV_DEFAULT_INDEX=http://internal.example/simple && '
                'gateway_with_isolated_index env | sort'
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=VNEXT_ROOT,
    )
    lines = probe.stdout.splitlines()
    assert not any(line.startswith("UV_INDEX_URL=") for line in lines)
    assert not any(line.startswith("UV_DEFAULT_INDEX=") for line in lines)
    run_tests = RUN_TESTS_SCRIPT.read_text(encoding="utf-8")
    assert "gateway_with_isolated_index" in run_tests
    assert "gateway-index-env.sh" in run_tests
