"""Unit tests for build-repository-service-image.sh exit-code propagation."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from support.compose_build_harness import BUILD_SCRIPT, UV_LOCK_PATH, VNEXT_ROOT


def _uv_lock_sha256() -> str:
    return hashlib.sha256(UV_LOCK_PATH.read_bytes()).hexdigest()


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_docker_script(*, build_exit_code: int | None) -> str:
    lock_sha = _uv_lock_sha256()
    build_handler = (
        "exit 1"
        if build_exit_code is None
        else f"exit {build_exit_code}"
    )
    return f"""#!/usr/bin/env bash
set -euo pipefail
LOCK_SHA="{lock_sha}"
if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  for arg in "$@"; do
    if [[ "$arg" == "--format" ]]; then
      echo "${{LOCK_SHA}}"
      exit 0
    fi
  done
  exit 0
fi
if [[ "$1" == "build" ]]; then
  {build_handler}
fi
echo "unexpected docker invocation: $*" >&2
exit 1
"""


def _run_build_script(
    tmp_path: Path,
    *,
    timeout_script: str,
    docker_build_exit_code: int | None,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "timeout", timeout_script)
    _write_executable(
        bin_dir / "docker",
        _fake_docker_script(build_exit_code=docker_build_exit_code),
    )
    _write_executable(
        bin_dir / "curl",
        "#!/usr/bin/env bash\nexit 1\n",
    )
    lock_sha = _uv_lock_sha256()
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["GATEWAY_P2R1_UV_LOCK_SHA256"] = lock_sha
    env["GATEWAY_P2R1_DEPENDENCY_BASE_IMAGE"] = f"gateway-p2r1-repository:lock-{lock_sha[:12]}"
    env["GATEWAY_REPOSITORY_SERVICE_IMAGE"] = "gateway-repository-service:test-exit-code"
    return subprocess.run(
        ["bash", str(BUILD_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=VNEXT_ROOT,
    )


@pytest.mark.unit
def test_build_script_propagates_docker_failure(tmp_path: Path) -> None:
    completed = _run_build_script(
        tmp_path,
        timeout_script='#!/usr/bin/env bash\nshift\nexec "$@"\n',
        docker_build_exit_code=42,
    )
    assert completed.returncode == 42
    assert "==> built" not in completed.stdout


@pytest.mark.unit
def test_build_script_propagates_timeout_exit(tmp_path: Path) -> None:
    completed = _run_build_script(
        tmp_path,
        timeout_script="#!/usr/bin/env bash\nexit 124\n",
        docker_build_exit_code=None,
    )
    assert completed.returncode == 124
    assert "timed out after 1800s" in completed.stderr
    assert "==> built" not in completed.stdout
